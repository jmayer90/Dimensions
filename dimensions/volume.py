import bmesh
from math import isfinite


VOLUME_EXACT = "EXACT"
VOLUME_APPROXIMATE = "APPROXIMATE"
VOLUME_UNAVAILABLE = "UNAVAILABLE"


_volume_cache = {}


def clear_volume_cache():
    _volume_cache.clear()


def invalidate_volume_cache_from_depsgraph(depsgraph):
    if depsgraph is None:
        clear_volume_cache()
        return

    if any(update.is_updated_geometry for update in depsgraph.updates):
        clear_volume_cache()


def get_mesh_volume(obj, depsgraph):
    """Return evaluated world-space volume and its confidence classification."""
    if obj is None or obj.type != "MESH" or depsgraph is None:
        return None, VOLUME_UNAVAILABLE

    cache_key = (obj.as_pointer(), depsgraph.as_pointer())
    cached = _volume_cache.get(cache_key)
    if cached is None:
        cached = _calculate_local_mesh_volume(obj, depsgraph)
        _volume_cache[cache_key] = cached

    local_volume, status = cached
    if local_volume is None:
        return None, status

    try:
        evaluated_object = obj.evaluated_get(depsgraph)
        world_scale = abs(evaluated_object.matrix_world.to_3x3().determinant())
    except (ReferenceError, RuntimeError, TypeError, ValueError):
        return None, VOLUME_UNAVAILABLE

    return local_volume * world_scale, status


def _calculate_local_mesh_volume(obj, depsgraph):
    evaluated_object = None
    bm = None
    try:
        evaluated_object = obj.evaluated_get(depsgraph)
        mesh = evaluated_object.to_mesh()
        if mesh is None:
            return None, VOLUME_UNAVAILABLE

        bm = bmesh.new()
        bm.from_mesh(mesh)
        if not bm.faces or not bm.edges:
            return None, VOLUME_UNAVAILABLE

        # A finite enclosed volume requires every edge to have exactly two faces.
        # This also rejects loose edges mixed into an otherwise closed object.
        if any(not edge.is_manifold for edge in bm.edges):
            return None, VOLUME_UNAVAILABLE

        component_count = _count_face_components(bm)
        if component_count == 0:
            return None, VOLUME_UNAVAILABLE

        # Work on the temporary BMesh so inverted but otherwise valid shells do
        # not cancel one another in calc_volume().
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        volume = bm.calc_volume(signed=False)
        if not isfinite(volume):
            return None, VOLUME_UNAVAILABLE
        status = VOLUME_EXACT if component_count == 1 else VOLUME_APPROXIMATE
        return volume, status
    except (ReferenceError, RuntimeError, TypeError, ValueError):
        return None, VOLUME_UNAVAILABLE
    finally:
        if bm is not None:
            bm.free()
        if evaluated_object is not None:
            try:
                evaluated_object.to_mesh_clear()
            except (ReferenceError, RuntimeError):
                pass


def _count_face_components(bm):
    remaining = set(bm.faces)
    component_count = 0

    while remaining:
        component_count += 1
        pending = [remaining.pop()]
        while pending:
            face = pending.pop()
            for edge in face.edges:
                for linked_face in edge.link_faces:
                    if linked_face in remaining:
                        remaining.remove(linked_face)
                        pending.append(linked_face)

    return component_count
