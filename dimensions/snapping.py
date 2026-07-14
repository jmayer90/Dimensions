from heapq import nsmallest

from bpy_extras import view3d_utils
from mathutils import Vector

from .constants import DEFAULT_SNAP_PIXEL_THRESHOLD


def has_view3d_window_region(context):
    return (
        context is not None
        and context.area is not None
        and context.area.type == "VIEW_3D"
        and context.region is not None
        and context.region.type == "WINDOW"
        and context.region_data is not None
    )


def get_mouse_ray(context, mouse_region_x, mouse_region_y):
    if not has_view3d_window_region(context):
        raise ValueError("A 3D View window region is required for mouse ray calculations")

    mouse = Vector((mouse_region_x, mouse_region_y))

    origin = view3d_utils.region_2d_to_origin_3d(
        context.region,
        context.region_data,
        mouse,
    )
    direction = view3d_utils.region_2d_to_vector_3d(
        context.region,
        context.region_data,
        mouse,
    )

    return origin, direction.normalized()


def raycast_from_mouse(context, mouse_x, mouse_y):
    if not has_view3d_window_region(context):
        return None

    origin, direction = get_mouse_ray(context, mouse_x, mouse_y)
    depsgraph = context.evaluated_depsgraph_get()

    hit, location, normal, face_index, obj, _matrix = context.scene.ray_cast(
        depsgraph,
        origin,
        direction,
    )

    if not hit or obj is None or obj.type != "MESH":
        return None

    return {
        "object": obj,
        "location": location,
        "normal": normal,
        "face_index": face_index,
    }


def find_nearest_face_vertex(
    context,
    mouse_x,
    mouse_y,
    pixel_threshold=DEFAULT_SNAP_PIXEL_THRESHOLD,
):
    hit = raycast_from_mouse(context, mouse_x, mouse_y)
    if hit is None:
        return None

    obj = hit["object"]
    mouse = Vector((mouse_x, mouse_y))

    candidate_vertices = []
    face_index = hit["face_index"]
    
    if not obj.modifiers and 0 <= face_index < len(obj.data.polygons):
        polygon = obj.data.polygons[face_index]
        candidate_vertices = list(polygon.vertices)
    else:
        local_hit = obj.matrix_world.inverted() @ hit["location"]
        candidate_vertices = _nearest_base_vertices(obj, local_hit)

    if not candidate_vertices:
        return None

    best = None
    best_distance = pixel_threshold

    for vertex_index in candidate_vertices:
        if vertex_index < 0 or vertex_index >= len(obj.data.vertices):
            continue
        vertex = obj.data.vertices[vertex_index]
        world_co = obj.matrix_world @ vertex.co
        screen_co = view3d_utils.location_3d_to_region_2d(
            context.region,
            context.region_data,
            world_co,
        )

        if screen_co is None:
            continue

        distance = (screen_co - mouse).length
        if distance >= best_distance:
            continue

        best_distance = distance
        best = {
            "object": obj,
            "vertex_index": vertex_index,
            "world_co": world_co.copy(),
            "screen_co": screen_co.copy(),
        }

    return best


def _nearest_base_vertices(obj, local_hit, limit=16):
    if obj.type != "MESH" or not obj.data.vertices:
        return []

    nearest = nsmallest(
        limit,
        enumerate(obj.data.vertices),
        key=lambda item: (item[1].co - local_hit).length_squared,
    )
    return [index for index, _vertex in nearest]
