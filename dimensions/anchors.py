from mathutils import Vector


def set_anchor(anchor, obj, vertex_index):
    if obj is None or obj.type != "MESH":
        raise ValueError("Anchor target must be a mesh object")

    if vertex_index < 0 or vertex_index >= len(obj.data.vertices):
        raise ValueError("Anchor vertex index is out of range")

    vertex = obj.data.vertices[vertex_index]

    anchor.anchor_type = "VERTEX"
    anchor.target_object = obj
    anchor.vertex_index = vertex_index
    anchor.fallback_local_co = tuple(vertex.co)
    anchor.world_co = tuple(obj.matrix_world @ vertex.co)
    anchor.status = "LINKED"


def set_world_anchor(anchor, world_co):
    anchor.anchor_type = "WORLD"
    anchor.target_object = None
    anchor.vertex_index = -1
    anchor.fallback_local_co = (0.0, 0.0, 0.0)
    anchor.world_co = tuple(world_co)
    anchor.status = "LINKED"


def set_object_anchor(anchor, obj, world_co):
    if obj is None or obj.type != "MESH":
        raise ValueError("Object-point anchor target must be a mesh object")
    local_co = obj.matrix_world.inverted_safe() @ Vector(world_co)
    anchor.anchor_type = "OBJECT_POINT"
    anchor.target_object = obj
    anchor.vertex_index = -1
    anchor.fallback_local_co = tuple(local_co)
    anchor.world_co = tuple(world_co)
    anchor.status = "LINKED"


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
        return Vector(anchor.world_co), "LINKED"

    if getattr(anchor, "anchor_type", "VERTEX") == "OBJECT_POINT":
        obj = anchor.target_object
        if obj is None or obj.type != "MESH":
            return None, "MISSING_OBJECT"
        return obj.matrix_world @ Vector(anchor.fallback_local_co), "LINKED"

    obj = anchor.target_object

    if obj is None or obj.type != "MESH":
        return None, "MISSING_OBJECT"

    mesh = obj.data
    vertex_index = anchor.vertex_index

    if obj.mode == "EDIT":
        import bmesh
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        if 0 <= vertex_index < len(bm.verts):
            local_co = bm.verts[vertex_index].co.copy()
            return obj.matrix_world @ local_co, "LINKED"
    else:
        if 0 <= vertex_index < len(mesh.vertices):
            local_co = mesh.vertices[vertex_index].co
            return obj.matrix_world @ local_co, "LINKED"

    fallback_local = Vector(anchor.fallback_local_co)
    return obj.matrix_world @ fallback_local, "DETACHED"
