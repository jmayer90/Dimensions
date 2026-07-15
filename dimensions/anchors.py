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


def set_world_anchor(anchor, world_co):
    anchor.anchor_type = "WORLD"
    anchor.target_object = None
    anchor.vertex_index = -1
    anchor.vertex_id = 0
    anchor.fallback_local_co = (0.0, 0.0, 0.0)
    anchor.world_co = tuple(world_co)


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


def resolve_anchor(anchor):
    if getattr(anchor, "anchor_type", "VERTEX") == "WORLD":
        return Vector(anchor.world_co)

    if getattr(anchor, "anchor_type", "VERTEX") == "OBJECT_POINT":
        obj = anchor.target_object
        if obj is None or obj.type != "MESH":
            return Vector(anchor.world_co)
        return obj.matrix_world @ Vector(anchor.fallback_local_co)

    obj = anchor.target_object

    if obj is None or obj.type != "MESH":
        return Vector(anchor.world_co)

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
            return _resolve_vertex_matches(obj, anchor, matches)
    else:
        if vertex_id > 0:
            attribute = mesh.attributes.get(VERTEX_ID_ATTRIBUTE)
            matches = [] if attribute is None else [
                mesh.vertices[index]
                for index, item in enumerate(attribute.data)
                if item.value == vertex_id
            ]
            return _resolve_vertex_matches(obj, anchor, matches)

    # Pre-0.1.3 files have no durable ID. Keep them usable until scene sync
    # assigns one.
    if 0 <= vertex_index < len(mesh.vertices):
        local_co = mesh.vertices[vertex_index].co
        return obj.matrix_world @ local_co

    fallback_local = Vector(anchor.fallback_local_co)
    return obj.matrix_world @ fallback_local


def migrate_anchor_identity(anchor):
    if getattr(anchor, "anchor_type", "VERTEX") != "VERTEX" or getattr(anchor, "vertex_id", 0) > 0:
        return False
    obj = anchor.target_object
    vertex_index = anchor.vertex_index
    if obj is None or obj.type != "MESH" or not (0 <= vertex_index < len(obj.data.vertices)):
        return False
    anchor.vertex_id = ensure_object_vertex_id(obj, vertex_index)
    return True


def _resolve_vertex_matches(obj, anchor, matches):
    if not matches:
        return obj.matrix_world @ Vector(anchor.fallback_local_co)
    fallback = Vector(anchor.fallback_local_co)
    vertex = min(matches, key=lambda item: (item.co - fallback).length_squared)
    return obj.matrix_world @ vertex.co.copy()
