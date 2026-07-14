from mathutils import Vector


def set_anchor(anchor, obj, vertex_index):
    if obj is None or obj.type != "MESH":
        raise ValueError("Anchor target must be a mesh object")

    if vertex_index < 0 or vertex_index >= len(obj.data.vertices):
        raise ValueError("Anchor vertex index is out of range")

    vertex = obj.data.vertices[vertex_index]

    anchor.target_object = obj
    anchor.vertex_index = vertex_index
    anchor.fallback_local_co = tuple(vertex.co)
    anchor.status = "LINKED"


def resolve_anchor(anchor):
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
