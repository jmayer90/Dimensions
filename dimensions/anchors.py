from mathutils import Vector


VERTEX_ID_ATTRIBUTE = "dimensions_anchor_id"
VERTEX_ID_COUNTER = "dimensions_anchor_next_id"


def ensure_vertex_id(mesh, vertex_index):
    if vertex_index < 0 or vertex_index >= len(mesh.vertices):
        raise ValueError("Anchor vertex index is out of range")
    attribute = mesh.attributes.get(VERTEX_ID_ATTRIBUTE)
    if attribute is None:
        attribute = mesh.attributes.new(VERTEX_ID_ATTRIBUTE, "INT", "POINT")
    elif attribute.data_type != "INT" or attribute.domain != "POINT":
        raise ValueError(f"Reserved attribute {VERTEX_ID_ATTRIBUTE!r} must be an INT POINT attribute")
    value = attribute.data[vertex_index].value
    if value > 0:
        return value
    next_id = max(
        int(mesh.get(VERTEX_ID_COUNTER, 1)),
        max((item.value for item in attribute.data), default=0) + 1,
    )
    attribute.data[vertex_index].value = next_id
    mesh[VERTEX_ID_COUNTER] = next_id + 1
    return next_id


def ensure_object_vertex_id(obj, vertex_index):
    if obj.mode != "EDIT":
        return ensure_vertex_id(obj.data, vertex_index)
    import bmesh

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    if vertex_index < 0 or vertex_index >= len(bm.verts):
        raise ValueError("Anchor vertex index is out of range")
    layer = bm.verts.layers.int.get(VERTEX_ID_ATTRIBUTE)
    if layer is None:
        layer = bm.verts.layers.int.new(VERTEX_ID_ATTRIBUTE)
    value = bm.verts[vertex_index][layer]
    if value > 0:
        return value
    next_id = max(
        int(obj.data.get(VERTEX_ID_COUNTER, 1)),
        max((vertex[layer] for vertex in bm.verts), default=0) + 1,
    )
    bm.verts[vertex_index][layer] = next_id
    obj.data[VERTEX_ID_COUNTER] = next_id + 1
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    return next_id


def set_anchor(anchor, obj, vertex_index):
    if obj is None or obj.type != "MESH":
        raise ValueError("Anchor target must be a mesh object")

    if vertex_index < 0 or vertex_index >= len(obj.data.vertices):
        raise ValueError("Anchor vertex index is out of range")

    if obj.mode == "EDIT":
        import bmesh

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        vertex_co = bm.verts[vertex_index].co.copy()
    else:
        vertex_co = obj.data.vertices[vertex_index].co.copy()

    anchor.anchor_type = "VERTEX"
    anchor.target_object = obj
    anchor.vertex_index = vertex_index
    anchor.vertex_id = ensure_object_vertex_id(obj, vertex_index)
    anchor.fallback_local_co = tuple(vertex_co)
    anchor.world_co = tuple(obj.matrix_world @ vertex_co)
    anchor.source_object_name = obj.name
    anchor.resolution_status = "BY_ID"


def set_world_anchor(anchor, world_co):
    anchor.anchor_type = "WORLD"
    anchor.target_object = None
    anchor.vertex_index = -1
    anchor.vertex_id = 0
    anchor.fallback_local_co = (0.0, 0.0, 0.0)
    anchor.world_co = tuple(world_co)
    anchor.source_object_name = ""
    anchor.resolution_status = "BY_ID"


def set_object_anchor(anchor, obj, world_co):
    if obj is None or obj.type != "MESH":
        raise ValueError("Object-point anchor target must be a mesh object")
    local_co = obj.matrix_world.inverted_safe() @ Vector(world_co)
    anchor.anchor_type = "OBJECT_POINT"
    anchor.target_object = obj
    anchor.vertex_index = -1
    anchor.vertex_id = 0
    anchor.fallback_local_co = tuple(local_co)
    anchor.world_co = tuple(world_co)
    anchor.source_object_name = obj.name
    anchor.resolution_status = "BY_ID"


def set_anchor_from_snap(anchor, snap):
    if snap is None:
        raise ValueError("Snap target is required")

    if snap.get("type") == "VERTEX" and snap.get("object") is not None:
        set_anchor(anchor, snap["object"], snap["vertex_index"])
        return

    if snap.get("type") in {"EDGE", "FACE"} and snap.get("object") is not None:
        set_object_anchor(anchor, snap["object"], snap["world_co"])
        return

    set_world_anchor(anchor, snap["world_co"])


def anchor_source_is_missing(anchor):
    """Return whether a source-bound anchor has lost its Blender object."""
    return (
        getattr(anchor, "anchor_type", "VERTEX") != "WORLD"
        and anchor.target_object is None
    )


def anchor_resolution(anchor):
    """Return ``(world coordinate, status)`` without changing fallback behavior."""
    anchor_type = getattr(anchor, "anchor_type", "VERTEX")
    if anchor_type == "WORLD":
        return Vector(anchor.world_co), "BY_ID"

    obj = anchor.target_object
    if obj is None or obj.type != "MESH":
        return Vector(anchor.world_co), "UNRESOLVABLE"
    if anchor_type == "OBJECT_POINT":
        return obj.matrix_world @ Vector(anchor.fallback_local_co), "BY_ID"

    mesh = obj.data
    vertex_index = anchor.vertex_index
    vertex_id = getattr(anchor, "vertex_id", 0)
    if obj.mode == "EDIT":
        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        if vertex_id > 0:
            layer = bm.verts.layers.int.get(VERTEX_ID_ATTRIBUTE)
            matches = [] if layer is None else [vert for vert in bm.verts if vert[layer] == vertex_id]
            return _resolved_vertex_matches(obj, anchor, matches)
    elif vertex_id > 0:
        attribute = mesh.attributes.get(VERTEX_ID_ATTRIBUTE)
        matches = [] if attribute is None else [
            mesh.vertices[index]
            for index, item in enumerate(attribute.data)
            if item.value == vertex_id
        ]
        return _resolved_vertex_matches(obj, anchor, matches)

    # Legacy anchors remain clean while migration can still identify their index.
    if 0 <= vertex_index < len(mesh.vertices):
        return obj.matrix_world @ mesh.vertices[vertex_index].co, "BY_ID"
    return obj.matrix_world @ Vector(anchor.fallback_local_co), "BY_FALLBACK"


def refresh_anchor_resolution(anchor):
    """Persist truthful resolution metadata and return the resolved world point."""
    world, status = anchor_resolution(anchor)
    anchor.resolution_status = status
    if anchor.target_object is not None:
        anchor.source_object_name = anchor.target_object.name
    if status == "BY_ID":
        anchor.world_co = tuple(world)
    return world


def dimension_source_is_missing(props):
    """Detect deleted object bindings without broadening into guided repair."""
    annotation_kind = getattr(props, "annotation_kind", "LINEAR")
    if annotation_kind in {"COORDINATE", "ELEVATION"}:
        datum = getattr(props, "datum_object", None)
        return (
            anchor_source_is_missing(props.start)
            or datum is None
            or not hasattr(datum, "guide_props")
            or anchor_source_is_missing(datum.guide_props.start)
        )
    if annotation_kind == "AREA":
        if props.measurement_state == "CAPTURED":
            return False
        return (
            (len(props.area_faces) > 0 and props.area_source_object is None)
            or anchor_source_is_missing(props.start)
            or anchor_source_is_missing(props.end)
        )
    if annotation_kind == "ANGLE":
        anchors = (
            (props.angle_a_start, props.angle_a_end, props.angle_b_start, props.angle_b_end)
            if props.angle_source_mode == "EDGES"
            else (props.start, props.center, props.end)
        )
        return any(anchor_source_is_missing(anchor) for anchor in anchors)
    return anchor_source_is_missing(props.start) or anchor_source_is_missing(props.end)


def dimension_source_anchors(props):
    """Return only anchors that define the current annotation's source."""
    annotation_kind = getattr(props, "annotation_kind", "LINEAR")
    if annotation_kind in {"COORDINATE", "ELEVATION"}:
        return (("POINT", props.start),)
    if annotation_kind == "ANGLE":
        if props.angle_source_mode == "EDGES":
            return (
                ("ANGLE_A_START", props.angle_a_start),
                ("ANGLE_A_END", props.angle_a_end),
                ("ANGLE_B_START", props.angle_b_start),
                ("ANGLE_B_END", props.angle_b_end),
            )
        return (("START", props.start), ("CENTER", props.center), ("END", props.end))
    if annotation_kind == "AREA":
        return (("START", props.start), ("END", props.end))
    return (("START", props.start), ("END", props.end))


def refresh_dimension_anchor_resolutions(props):
    """Refresh source anchors and return LIVE, FALLBACK, or NEEDS_REPAIR."""
    statuses = []
    for _name, anchor in dimension_source_anchors(props):
        refresh_anchor_resolution(anchor)
        statuses.append(anchor.resolution_status)
    if "UNRESOLVABLE" in statuses:
        return "NEEDS_REPAIR"
    if "BY_FALLBACK" in statuses:
        return "FALLBACK"
    return "LIVE"


def resolve_anchor(anchor):
    return anchor_resolution(anchor)[0]


def migrate_anchor_identity(anchor):
    if getattr(anchor, "anchor_type", "VERTEX") != "VERTEX" or getattr(anchor, "vertex_id", 0) > 0:
        return False
    obj = anchor.target_object
    vertex_index = anchor.vertex_index
    if obj is None or obj.type != "MESH" or not (0 <= vertex_index < len(obj.data.vertices)):
        return False
    anchor.vertex_id = ensure_object_vertex_id(obj, vertex_index)
    return True


def _resolved_vertex_matches(obj, anchor, matches):
    if not matches:
        return obj.matrix_world @ Vector(anchor.fallback_local_co), "BY_FALLBACK"
    fallback = Vector(anchor.fallback_local_co)
    vertex = min(matches, key=lambda item: (item.co - fallback).length_squared)
    status = "BY_ID" if len(matches) == 1 else "BY_FALLBACK"
    return obj.matrix_world @ vertex.co.copy(), status
