from bpy_extras import view3d_utils
from mathutils import Vector

from .constants import DEFAULT_SNAP_PIXEL_THRESHOLD


def get_mouse_ray(context, mouse_region_x, mouse_region_y):
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
    origin, direction = get_mouse_ray(context, mouse_x, mouse_y)
    depsgraph = context.evaluated_depsgraph_get()

    hit, location, normal, face_index, obj, _matrix = context.scene.ray_cast(
        depsgraph,
        origin,
        direction,
    )

    if not hit or obj is None or obj.type != "MESH":
        return None

    if face_index < 0 or face_index >= len(obj.data.polygons):
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
    polygon = obj.data.polygons[hit["face_index"]]
    mouse = Vector((mouse_x, mouse_y))

    best = None
    best_distance = pixel_threshold

    for vertex_index in polygon.vertices:
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
