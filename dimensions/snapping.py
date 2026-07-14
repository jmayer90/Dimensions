from heapq import nsmallest

from bpy_extras import view3d_utils
from mathutils.geometry import intersect_line_plane
from mathutils import Vector

from .constants import DEFAULT_SNAP_PIXEL_THRESHOLD
from .anchors import resolve_anchor
from .properties import is_guide_object


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
            "type": "VERTEX",
            "label": "Vertex",
            "object": obj,
            "vertex_index": vertex_index,
            "world_co": world_co.copy(),
            "screen_co": screen_co.copy(),
        }

    return best


def find_nearest_snap_point(
    context,
    mouse_x,
    mouse_y,
    pixel_threshold=DEFAULT_SNAP_PIXEL_THRESHOLD,
    include_guides=True,
    include_free=False,
    plane_point=None,
    plane_normal=None,
):
    best = find_nearest_mesh_snap_point(context, mouse_x, mouse_y, pixel_threshold)
    if best is not None and best.get("label") != "Face":
        best_distance = (best["screen_co"] - Vector((mouse_x, mouse_y))).length
    else:
        best_distance = pixel_threshold

    if include_guides:
        guide_snap = find_nearest_guide_point(context, mouse_x, mouse_y, pixel_threshold)
        if guide_snap is not None:
            guide_distance = (guide_snap["screen_co"] - Vector((mouse_x, mouse_y))).length
            if guide_distance < best_distance:
                best = guide_snap
                best_distance = guide_distance

    if best is not None:
        return best

    if include_free:
        free_world = project_mouse_to_plane(context, mouse_x, mouse_y, plane_point, plane_normal)
        if free_world is not None:
            screen_co = view3d_utils.location_3d_to_region_2d(
                context.region,
                context.region_data,
                free_world,
            )
            return {
                "type": "WORLD",
                "label": "Point",
                "object": None,
                "vertex_index": -1,
                "world_co": free_world.copy(),
                "screen_co": Vector((mouse_x, mouse_y)) if screen_co is None else screen_co.copy(),
            }

    return None


def find_nearest_mesh_snap_point(context, mouse_x, mouse_y, pixel_threshold=DEFAULT_SNAP_PIXEL_THRESHOLD):
    hit = raycast_from_mouse(context, mouse_x, mouse_y)
    if hit is None:
        return None

    obj = hit["object"]
    mouse = Vector((mouse_x, mouse_y))
    candidates = []
    face_index = hit["face_index"]

    if not obj.modifiers and 0 <= face_index < len(obj.data.polygons):
        polygon = obj.data.polygons[face_index]
        vertex_indices = list(polygon.vertices)
        _add_vertex_candidates(context, obj, vertex_indices, candidates)
        _add_edge_candidates(context, obj, vertex_indices, mouse, candidates)
        _add_face_center_candidate(context, obj, polygon, candidates)
    else:
        local_hit = obj.matrix_world.inverted() @ hit["location"]
        _add_vertex_candidates(context, obj, _nearest_base_vertices(obj, local_hit), candidates)

    best = _best_snap_candidate(candidates, mouse, pixel_threshold)
    if best is not None:
        return best

    screen_co = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        hit["location"],
    )
    if screen_co is None:
        screen_co = mouse

    return {
        "type": "WORLD",
        "label": "Face",
        "object": None,
        "vertex_index": -1,
        "world_co": hit["location"].copy(),
        "screen_co": screen_co.copy(),
    }


def _add_vertex_candidates(context, obj, vertex_indices, candidates):
    for vertex_index in vertex_indices:
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

        candidates.append(
            {
                "type": "VERTEX",
                "label": "Vertex",
                "priority": 0,
                "object": obj,
                "vertex_index": vertex_index,
                "world_co": world_co.copy(),
                "screen_co": screen_co.copy(),
            }
        )


def _add_edge_candidates(context, obj, vertex_indices, mouse, candidates):
    if len(vertex_indices) < 2:
        return

    edge_pairs = zip(vertex_indices, vertex_indices[1:] + vertex_indices[:1])
    for start_index, end_index in edge_pairs:
        if start_index >= len(obj.data.vertices) or end_index >= len(obj.data.vertices):
            continue

        start_world = obj.matrix_world @ obj.data.vertices[start_index].co
        end_world = obj.matrix_world @ obj.data.vertices[end_index].co
        start_screen = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, start_world)
        end_screen = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, end_world)
        if start_screen is None or end_screen is None:
            continue

        midpoint_world = (start_world + end_world) * 0.5
        midpoint_screen = (start_screen + end_screen) * 0.5
        candidates.append(
            {
                "type": "WORLD",
                "label": "Midpoint",
                "priority": 1,
                "object": None,
                "vertex_index": -1,
                "world_co": midpoint_world.copy(),
                "screen_co": midpoint_screen.copy(),
            }
        )

        screen_segment = end_screen - start_screen
        if screen_segment.length_squared <= 1e-8:
            continue

        factor = max(0.0, min(1.0, (mouse - start_screen).dot(screen_segment) / screen_segment.length_squared))
        edge_screen = start_screen + screen_segment * factor
        edge_world = start_world + (end_world - start_world) * factor
        candidates.append(
            {
                "type": "WORLD",
                "label": "Edge",
                "priority": 2,
                "object": None,
                "vertex_index": -1,
                "world_co": edge_world.copy(),
                "screen_co": edge_screen.copy(),
            }
        )


def _add_face_center_candidate(context, obj, polygon, candidates):
    center_world = obj.matrix_world @ polygon.center
    center_screen = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        center_world,
    )
    if center_screen is None:
        return

    candidates.append(
        {
            "type": "WORLD",
            "label": "Face Center",
            "priority": 3,
            "object": None,
            "vertex_index": -1,
            "world_co": center_world.copy(),
            "screen_co": center_screen.copy(),
        }
    )


def _best_snap_candidate(candidates, mouse, pixel_threshold):
    best = None
    for candidate in candidates:
        distance = (candidate["screen_co"] - mouse).length
        if distance >= pixel_threshold:
            continue

        score = distance + (candidate.get("priority", 100) * 2.0)
        if best is None or score < best[0]:
            best = (score, candidate)

    return None if best is None else best[1]


def find_nearest_guide_point(context, mouse_x, mouse_y, pixel_threshold=DEFAULT_SNAP_PIXEL_THRESHOLD):
    if not has_view3d_window_region(context):
        return None

    mouse = Vector((mouse_x, mouse_y))
    best = None
    best_distance = pixel_threshold

    for obj in context.scene.objects:
        if not is_guide_object(obj):
            continue

        segment = guide_segment_world(obj)
        if segment is None:
            continue

        start_world, end_world = segment
        start_screen = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, start_world)
        end_screen = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, end_world)
        if start_screen is None or end_screen is None:
            continue

        screen_segment = end_screen - start_screen
        if screen_segment.length_squared <= 1e-8:
            continue

        factor = max(0.0, min(1.0, (mouse - start_screen).dot(screen_segment) / screen_segment.length_squared))
        screen_co = start_screen + screen_segment * factor
        distance = (screen_co - mouse).length
        if distance >= best_distance:
            continue

        world_co = start_world + (end_world - start_world) * factor
        best_distance = distance
        best = {
            "type": "WORLD",
            "label": "Guide",
            "object": None,
            "vertex_index": -1,
            "world_co": world_co.copy(),
            "screen_co": screen_co.copy(),
            "guide_object": obj,
        }

    return best


def guide_segment_world(guide_object, extent=10000.0):
    start_world, _start_status = resolve_anchor(guide_object.guide_props.start)
    end_world, _end_status = resolve_anchor(guide_object.guide_props.end)
    if start_world is None or end_world is None:
        return None

    axis = guide_object.guide_props.axis
    if axis == "X":
        direction = Vector((1.0, 0.0, 0.0))
    elif axis == "Y":
        direction = Vector((0.0, 1.0, 0.0))
    elif axis == "Z":
        direction = Vector((0.0, 0.0, 1.0))
    else:
        direction = end_world - start_world
        if direction.length < 1e-6:
            return None
        direction.normalize()
        return start_world - direction * extent, start_world + direction * extent

    return start_world - direction * extent, start_world + direction * extent


def project_mouse_to_plane(context, mouse_x, mouse_y, plane_point=None, plane_normal=None):
    if not has_view3d_window_region(context):
        return None

    line_origin, line_direction = get_mouse_ray(context, mouse_x, mouse_y)
    if plane_point is None:
        plane_point = Vector((0.0, 0.0, 0.0))
    if plane_normal is None:
        plane_normal = context.region_data.view_rotation @ Vector((0.0, 0.0, -1.0))

    if plane_normal.length < 1e-6:
        return None

    return intersect_line_plane(
        line_origin,
        line_origin + line_direction * 100000.0,
        Vector(plane_point),
        Vector(plane_normal).normalized(),
        False,
    )


def _nearest_base_vertices(obj, local_hit, limit=16):
    if obj.type != "MESH" or not obj.data.vertices:
        return []

    nearest = nsmallest(
        limit,
        enumerate(obj.data.vertices),
        key=lambda item: (item[1].co - local_hit).length_squared,
    )
    return [index for index, _vertex in nearest]
