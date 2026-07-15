from heapq import nsmallest

from bpy_extras import view3d_utils
from mathutils.geometry import intersect_line_line, intersect_line_plane
from mathutils import Vector

from .constants import DEFAULT_SNAP_PIXEL_THRESHOLD
from .anchors import resolve_anchor
from .properties import is_guide_object


def copy_snap(snap):
    copied = dict(snap)
    copied["world_co"] = snap["world_co"].copy()
    copied["screen_co"] = snap["screen_co"].copy()
    if "edge_vertices" in copied:
        copied["edge_vertices"] = tuple(copied["edge_vertices"])
    return copied


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

    if context.mode == "EDIT_MESH" and context.edit_object is not None:
        edit_hit = _raycast_edit_mesh(context, origin, direction)
        return edit_hit

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


def _raycast_edit_mesh(context, origin_world, direction_world):
    import bmesh
    from mathutils.bvhtree import BVHTree

    obj = context.edit_object
    if obj is None or obj.type != "MESH":
        return None

    bm = bmesh.from_edit_mesh(obj.data)
    if not bm.faces:
        return None

    bm.faces.ensure_lookup_table()
    bm.faces.index_update()
    tree = BVHTree.FromBMesh(bm)
    inverse = obj.matrix_world.inverted_safe()
    origin_local = inverse @ origin_world
    direction_local = inverse.to_3x3() @ direction_world
    if direction_local.length < 1e-8:
        return None
    direction_local.normalize()

    location, normal, face_index, _distance = tree.ray_cast(
        origin_local,
        direction_local,
    )
    if location is None or face_index is None:
        return None

    normal_world = obj.matrix_world.to_3x3().inverted_safe().transposed() @ normal
    if normal_world.length > 1e-8:
        normal_world.normalize()

    return {
        "object": obj,
        "location": obj.matrix_world @ location,
        "normal": normal_world,
        "face_index": face_index,
        "edit_mesh": True,
    }


def find_nearest_snap_point(
    context,
    mouse_x,
    mouse_y,
    pixel_threshold=None,
    include_guides=True,
    include_free=False,
    plane_point=None,
    plane_normal=None,
):
    pixel_threshold = _configured_snap_pixel_threshold(context, pixel_threshold)
    mouse = Vector((mouse_x, mouse_y))
    candidates = []

    mesh_snap = find_nearest_mesh_snap_point(context, mouse_x, mouse_y, pixel_threshold)
    if mesh_snap is not None:
        candidates.append(mesh_snap)

    if include_guides:
        guide_snap = find_nearest_guide_point(context, mouse_x, mouse_y, pixel_threshold)
        if guide_snap is not None:
            candidates.append(guide_snap)

    if candidates:
        return min(candidates, key=lambda candidate: _snap_candidate_score(candidate, mouse))

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


def _snap_candidate_score(candidate, mouse):
    distance = (candidate["screen_co"] - mouse).length
    return candidate.get("priority", 100), distance


def find_nearest_mesh_snap_point(context, mouse_x, mouse_y, pixel_threshold=DEFAULT_SNAP_PIXEL_THRESHOLD):
    hit = raycast_from_mouse(context, mouse_x, mouse_y)
    if hit is None:
        if context.mode == "EDIT_MESH" and context.edit_object is not None:
            return _nearest_projected_edit_mesh_element(
                context,
                mouse_x,
                mouse_y,
                pixel_threshold,
            )
        return _nearest_projected_vertex(context, mouse_x, mouse_y, pixel_threshold)

    obj = hit["object"]
    mouse = Vector((mouse_x, mouse_y))
    candidates = []
    face_index = hit["face_index"]

    if hit.get("edit_mesh"):
        _add_edit_mesh_candidates(
            context,
            obj,
            face_index,
            mouse,
            candidates,
        )
    elif not obj.modifiers and 0 <= face_index < len(obj.data.polygons):
        polygon = obj.data.polygons[face_index]
        vertex_indices = list(polygon.vertices)
        _add_vertex_candidates(context, obj, vertex_indices, candidates)
        _add_edge_candidates(context, obj, vertex_indices, mouse, candidates, face_index)
        _add_face_center_candidate(context, obj, polygon, candidates, face_index)
    else:
        local_hit = obj.matrix_world.inverted() @ hit["location"]
        _add_vertex_candidates(context, obj, _nearest_base_vertices(obj, local_hit), candidates)

    projected_vertex = _nearest_projected_vertex(context, mouse_x, mouse_y, pixel_threshold)
    if projected_vertex is not None:
        if hit.get("edit_mesh"):
            projected_vertex["priority"] = _edit_mesh_projected_vertex_priority(
                obj,
                face_index,
                projected_vertex,
            )
        candidates.append(projected_vertex)

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
        "type": "FACE",
        "label": "Face",
        "priority": 10,
        "object": obj,
        "vertex_index": -1,
        "face_index": face_index,
        "world_co": hit["location"].copy(),
        "screen_co": screen_co.copy(),
    }


def _add_edit_mesh_candidates(context, obj, face_index, mouse, candidates):
    import bmesh

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    if face_index < 0 or face_index >= len(bm.faces):
        return

    face = bm.faces[face_index]
    for vertex in face.verts:
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
                "vertex_index": vertex.index,
                "world_co": world_co.copy(),
                "screen_co": screen_co.copy(),
            }
        )

    for edge in face.edges:
        _add_edge_snap_candidates(
            context,
            obj,
            edge.verts[0].co,
            edge.verts[1].co,
            mouse,
            candidates,
            edge_index=edge.index,
            edge_vertices=(edge.verts[0].index, edge.verts[1].index),
            face_index=face.index,
        )

    center_world = obj.matrix_world @ face.calc_center_median()
    center_screen = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        center_world,
    )
    if center_screen is not None:
        candidates.append(
            {
                "type": "FACE",
                "label": "Face Center",
                "priority": 3,
                "object": obj,
                "vertex_index": -1,
                "face_index": face.index,
                "world_co": center_world.copy(),
                "screen_co": center_screen.copy(),
            }
        )


def _edit_mesh_projected_vertex_priority(obj, face_index, candidate):
    import bmesh

    if candidate.get("object") != obj:
        return 4
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    vertex_index = candidate.get("vertex_index", -1)
    if not (0 <= face_index < len(bm.faces) and 0 <= vertex_index < len(bm.verts)):
        return 4
    return 0 if bm.verts[vertex_index] in bm.faces[face_index].verts else 4


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


def _add_edge_candidates(context, obj, vertex_indices, mouse, candidates, face_index=-1):
    if len(vertex_indices) < 2:
        return

    edge_pairs = zip(vertex_indices, vertex_indices[1:] + vertex_indices[:1])
    for start_index, end_index in edge_pairs:
        if start_index >= len(obj.data.vertices) or end_index >= len(obj.data.vertices):
            continue

        _add_edge_snap_candidates(
            context,
            obj,
            obj.data.vertices[start_index].co,
            obj.data.vertices[end_index].co,
            mouse,
            candidates,
            edge_index=-1,
            edge_vertices=(start_index, end_index),
            face_index=face_index,
        )


def _add_edge_snap_candidates(
    context,
    obj,
    start_local,
    end_local,
    mouse,
    candidates,
    edge_index=-1,
    edge_vertices=(-1, -1),
    face_index=-1,
):
    start_world = obj.matrix_world @ start_local
    end_world = obj.matrix_world @ end_local
    start_screen = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        start_world,
    )
    end_screen = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        end_world,
    )
    if start_screen is None or end_screen is None:
        return

    midpoint_world = (start_world + end_world) * 0.5
    midpoint_screen = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        midpoint_world,
    )
    if midpoint_screen is not None:
        candidates.append(
            {
                "type": "EDGE",
                "label": "Midpoint",
                "priority": 1,
                "object": obj,
                "vertex_index": -1,
                "edge_index": edge_index,
                "edge_vertices": edge_vertices,
                "edge_factor": 0.5,
                "face_index": face_index,
                "world_co": midpoint_world.copy(),
                "screen_co": midpoint_screen.copy(),
            }
        )

    screen_segment = end_screen - start_screen
    if screen_segment.length_squared <= 1e-8:
        return

    screen_factor = max(
        0.0,
        min(
            1.0,
            (mouse - start_screen).dot(screen_segment) / screen_segment.length_squared,
        ),
    )
    world_factor = _perspective_correct_segment_factor(
        context,
        start_world,
        end_world,
        screen_factor,
    )
    edge_world = start_world + (end_world - start_world) * world_factor
    edge_screen = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        edge_world,
    )
    if edge_screen is None:
        return

    candidates.append(
        {
            "type": "EDGE",
            "label": "Edge",
            "priority": 2,
            "object": obj,
            "vertex_index": -1,
            "edge_index": edge_index,
            "edge_vertices": edge_vertices,
            "edge_factor": world_factor,
            "face_index": face_index,
            "world_co": edge_world.copy(),
            "screen_co": edge_screen.copy(),
        }
    )


def _perspective_correct_segment_factor(context, start_world, end_world, screen_factor):
    start_clip = context.region_data.perspective_matrix @ start_world.to_4d()
    end_clip = context.region_data.perspective_matrix @ end_world.to_4d()
    if abs(start_clip.w) < 1e-8 or abs(end_clip.w) < 1e-8:
        return screen_factor

    start_weight = (1.0 - screen_factor) / start_clip.w
    end_weight = screen_factor / end_clip.w
    denominator = start_weight + end_weight
    if abs(denominator) < 1e-8:
        return screen_factor

    return max(0.0, min(1.0, end_weight / denominator))


def _add_face_center_candidate(context, obj, polygon, candidates, face_index=-1):
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
            "type": "FACE",
            "label": "Face Center",
            "priority": 3,
            "object": obj,
            "vertex_index": -1,
            "face_index": face_index,
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

        score = candidate.get("priority", 100), distance
        if best is None or score < best[0]:
            best = (score, candidate)

    return None if best is None else best[1]


def _configured_snap_pixel_threshold(context, requested_threshold):
    if requested_threshold is not None:
        return float(requested_threshold)
    settings = getattr(getattr(context, "scene", None), "dimensions_settings", None)
    if settings is None:
        return DEFAULT_SNAP_PIXEL_THRESHOLD
    return float(settings.snap_pixel_radius)


def _nearest_projected_vertex(context, mouse_x, mouse_y, pixel_threshold):
    if not has_view3d_window_region(context):
        return None

    mouse = Vector((mouse_x, mouse_y))
    best = None
    if context.mode == "EDIT_MESH" and context.edit_object is not None:
        import bmesh

        objects_and_vertices = [(context.edit_object, bmesh.from_edit_mesh(context.edit_object.data).verts)]
    else:
        objects_and_vertices = [
            (obj, obj.data.vertices)
            for obj in getattr(context, "visible_objects", ())
            if obj.type == "MESH"
        ]

    for obj, vertices in objects_and_vertices:
        if context.mode == "EDIT_MESH":
            vertices.ensure_lookup_table()
            vertices.index_update()
        for vertex in vertices:
            world_co = obj.matrix_world @ vertex.co
            screen_co = view3d_utils.location_3d_to_region_2d(
                context.region,
                context.region_data,
                world_co,
            )
            if screen_co is None:
                continue
            distance = (screen_co - mouse).length
            if distance >= pixel_threshold or (best is not None and distance >= best[0]):
                continue
            best = (
                distance,
                {
                    "type": "VERTEX",
                    "label": "Vertex",
                    "priority": 0,
                    "object": obj,
                    "vertex_index": vertex.index,
                    "world_co": world_co.copy(),
                    "screen_co": screen_co.copy(),
                },
            )
    return None if best is None else best[1]


def _nearest_projected_edit_mesh_element(context, mouse_x, mouse_y, pixel_threshold):
    import bmesh

    obj = context.edit_object
    if obj is None or obj.type != "MESH":
        return None

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    mouse = Vector((mouse_x, mouse_y))
    candidates = []

    for vertex in bm.verts:
        if vertex.hide:
            continue
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
                "vertex_index": vertex.index,
                "world_co": world_co.copy(),
                "screen_co": screen_co.copy(),
            }
        )

    for edge in bm.edges:
        if edge.hide:
            continue
        linked_face = next((face for face in edge.link_faces if not face.hide), None)
        _add_edge_snap_candidates(
            context,
            obj,
            edge.verts[0].co,
            edge.verts[1].co,
            mouse,
            candidates,
            edge_index=edge.index,
            edge_vertices=(edge.verts[0].index, edge.verts[1].index),
            face_index=-1 if linked_face is None else linked_face.index,
        )

    return _best_snap_candidate(candidates, mouse, pixel_threshold)


def find_nearest_guide_point(context, mouse_x, mouse_y, pixel_threshold=DEFAULT_SNAP_PIXEL_THRESHOLD):
    if not has_view3d_window_region(context):
        return None

    mouse = Vector((mouse_x, mouse_y))
    ray_origin, ray_direction = get_mouse_ray(context, mouse_x, mouse_y)
    best = None
    best_distance = pixel_threshold

    for obj in context.scene.objects:
        if not guide_is_visible(context, obj):
            continue

        if getattr(obj.guide_props, "kind", "GUIDE") == "MEASUREMENT":
            candidate = _nearest_measurement_segment_snap(
                context,
                obj,
                mouse,
                pixel_threshold,
            )
            if candidate is None:
                continue
            distance = (candidate["screen_co"] - mouse).length
            if distance >= best_distance:
                continue
            best_distance = distance
            best = candidate
            continue

        line = guide_line_world(obj)
        if line is None:
            continue

        line_origin, line_direction = line
        closest_points = intersect_line_line(
            ray_origin,
            ray_origin + ray_direction,
            line_origin,
            line_origin + line_direction,
        )
        if closest_points is None:
            continue

        ray_point, world_co = closest_points
        if (ray_point - ray_origin).dot(ray_direction) < 0.0:
            continue

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
            "type": "GUIDE",
            "label": "Guide",
            "priority": 1,
            "object": None,
            "vertex_index": -1,
            "world_co": world_co.copy(),
            "screen_co": screen_co.copy(),
            "guide_object": obj,
        }

    return best


def _nearest_measurement_segment_snap(context, measurement_object, mouse, pixel_threshold=DEFAULT_SNAP_PIXEL_THRESHOLD):
    segment = construction_segment_world(measurement_object)
    if segment is None:
        return None

    start_world, end_world = segment
    start_screen = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        start_world,
    )
    end_screen = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        end_world,
    )
    if start_screen is None or end_screen is None:
        return None

    midpoint_world = (start_world + end_world) * 0.5
    midpoint_screen = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        midpoint_world,
    )
    logical_candidates = [
        (start_world, start_screen, "Measurement Start"),
        (end_world, end_screen, "Measurement End"),
    ]
    if midpoint_screen is not None:
        logical_candidates.append((midpoint_world, midpoint_screen, "Measurement Midpoint"))
    nearest_logical = min(
        logical_candidates,
        key=lambda candidate: (candidate[1] - mouse).length,
    )
    if (nearest_logical[1] - mouse).length < pixel_threshold:
        return {
            "type": "MEASUREMENT",
            "label": nearest_logical[2],
            "priority": 0,
            "object": None,
            "vertex_index": -1,
            "world_co": nearest_logical[0].copy(),
            "screen_co": nearest_logical[1].copy(),
            "guide_object": measurement_object,
        }

    screen_segment = end_screen - start_screen
    if screen_segment.length_squared <= 1e-8:
        return None
    screen_factor = max(
        0.0,
        min(
            1.0,
            (mouse - start_screen).dot(screen_segment) / screen_segment.length_squared,
        ),
    )
    world_factor = _perspective_correct_segment_factor(
        context,
        start_world,
        end_world,
        screen_factor,
    )
    world_co = start_world + (end_world - start_world) * world_factor
    screen_co = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        world_co,
    )
    if screen_co is None:
        return None

    return {
        "type": "MEASUREMENT",
        "label": "Measurement",
        "priority": 3,
        "object": None,
        "vertex_index": -1,
        "world_co": world_co.copy(),
        "screen_co": screen_co.copy(),
        "guide_object": measurement_object,
    }


def guide_is_visible(context, guide_object):
    if not is_guide_object(guide_object) or not guide_object.guide_props.visible:
        return False

    settings = getattr(context.scene, "dimensions_settings", None)
    if settings is not None and not settings.show_construction_guides:
        return False

    try:
        return guide_object.visible_get(
            view_layer=getattr(context, "view_layer", None),
            viewport=getattr(context, "space_data", None),
        )
    except (AttributeError, TypeError):
        return not guide_object.hide_get()


def guide_line_world(guide_object):
    if getattr(guide_object.guide_props, "kind", "GUIDE") == "MEASUREMENT":
        return None

    start_world, _start_status = resolve_anchor(guide_object.guide_props.start)
    if start_world is None:
        return None

    axis = guide_object.guide_props.axis
    if axis == "X":
        direction = Vector((1.0, 0.0, 0.0))
    elif axis == "Y":
        direction = Vector((0.0, 1.0, 0.0))
    elif axis == "Z":
        direction = Vector((0.0, 0.0, 1.0))
    else:
        end_world, _end_status = resolve_anchor(guide_object.guide_props.end)
        if end_world is None:
            return None
        direction = end_world - start_world
        if direction.length < 1e-6:
            return None
        direction.normalize()

    return start_world, direction


def guide_segment_world(guide_object, extent=10000.0):
    if getattr(guide_object.guide_props, "kind", "GUIDE") == "MEASUREMENT":
        return construction_segment_world(guide_object)

    line = guide_line_world(guide_object)
    if line is None:
        return None

    origin, direction = line
    return origin - direction * extent, origin + direction * extent


def construction_segment_world(construction_object):
    start_world, _start_status = resolve_anchor(construction_object.guide_props.start)
    end_world, _end_status = resolve_anchor(construction_object.guide_props.end)
    if start_world is None or end_world is None:
        return None
    if (end_world - start_world).length < 1e-6:
        return None
    return start_world, end_world


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
