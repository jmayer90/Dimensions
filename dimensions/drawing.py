import blf
import bpy
import gpu
from bpy.app.handlers import persistent
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Quaternion, Vector

from .anchors import resolve_anchor
from .collections import ensure_measurement_snap_proxy, remove_orphan_measurement_snap_proxies
from .constants import (
    DEFAULT_ARROW_SIZE,
    DEFAULT_HOVER_MARKER_SIZE,
    DEFAULT_LINE_WIDTH,
    DEFAULT_PRECISION,
    DEFAULT_SELECTION_PIXEL_THRESHOLD,
    DEFAULT_TEXT_SIZE,
)
from .properties import is_dimension_object, is_guide_object
from .snapping import construction_segment_world, find_nearest_guide_point, guide_is_visible, guide_segment_world
from .units import format_length, format_volume
from .volume import (
    VOLUME_APPROXIMATE,
    clear_volume_cache,
    get_mesh_volume,
    invalidate_volume_cache_from_depsgraph,
)


_pixel_draw_handler = None
_world_draw_handler = None
_preview_state = None
_measure_state = None
_guide_preview_state = None
_location_sync_active = False
_location_sync_scheduled = False
_AXIS_CANDIDATES = (
    Vector((1.0, 0.0, 0.0)),
    Vector((0.0, 1.0, 0.0)),
    Vector((0.0, 0.0, 1.0)),
)


def tag_redraw_all_view3d():
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue

        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def set_preview_state(preview_state):
    global _preview_state
    _preview_state = preview_state
    tag_redraw_all_view3d()


def clear_preview_state():
    global _preview_state
    _preview_state = None
    tag_redraw_all_view3d()


def set_measure_state(state):
    global _measure_state
    _measure_state = state
    tag_redraw_all_view3d()


def clear_measure_state():
    global _measure_state
    _measure_state = None
    tag_redraw_all_view3d()


def set_guide_preview_state(state):
    global _guide_preview_state
    _guide_preview_state = state
    tag_redraw_all_view3d()


def clear_guide_preview_state():
    global _guide_preview_state
    _guide_preview_state = None
    tag_redraw_all_view3d()


def register_draw_handler():
    global _pixel_draw_handler, _world_draw_handler

    if _dimension_location_sync_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_dimension_location_sync_handler)

    if _world_draw_handler is None:
        _world_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            draw_world_guides,
            (),
            "WINDOW",
            "POST_VIEW",
        )

    if _pixel_draw_handler is None:
        _pixel_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            draw_dimensions,
            (),
            "WINDOW",
            "POST_PIXEL",
        )
    schedule_dimension_location_sync()


def unregister_draw_handler():
    global _pixel_draw_handler, _world_draw_handler, _location_sync_scheduled, _preview_state, _measure_state, _guide_preview_state

    if _dimension_location_sync_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_dimension_location_sync_handler)

    if bpy.app.timers.is_registered(_run_scheduled_location_sync):
        bpy.app.timers.unregister(_run_scheduled_location_sync)
    _location_sync_scheduled = False
    _preview_state = None
    _measure_state = None
    _guide_preview_state = None
    clear_volume_cache()

    if _pixel_draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_pixel_draw_handler, "WINDOW")
        _pixel_draw_handler = None

    if _world_draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_world_draw_handler, "WINDOW")
        _world_draw_handler = None


def schedule_dimension_location_sync():
    global _location_sync_scheduled

    if _location_sync_scheduled:
        return

    _location_sync_scheduled = True
    bpy.app.timers.register(_run_scheduled_location_sync, first_interval=0.0)


def _run_scheduled_location_sync():
    global _location_sync_scheduled
    _location_sync_scheduled = False

    scene = getattr(bpy.context, "scene", None)
    if scene is not None:
        sync_dimension_object_locations(scene)

    return None


@persistent
def _dimension_location_sync_handler(scene, depsgraph):
    invalidate_volume_cache_from_depsgraph(depsgraph)
    sync_dimension_object_locations(scene)


def sync_dimension_object_locations(scene):
    global _location_sync_active

    if _location_sync_active or scene is None:
        return

    _location_sync_active = True
    try:
        remove_orphan_measurement_snap_proxies(scene)
        for obj in list(scene.objects):
            if is_guide_object(obj):
                start_world, _status = resolve_anchor(obj.guide_props.start)
                target_world = start_world
                if getattr(obj.guide_props, "kind", "GUIDE") == "MEASUREMENT":
                    end_world, _end_status = resolve_anchor(obj.guide_props.end)
                    if start_world is not None and end_world is not None:
                        target_world = (start_world + end_world) * 0.5
                if target_world is not None and (obj.matrix_world.translation - target_world).length > 1e-6:
                    matrix_world = obj.matrix_world.copy()
                    matrix_world.translation = target_world
                    obj.matrix_world = matrix_world
                if getattr(obj.guide_props, "kind", "GUIDE") == "MEASUREMENT":
                    ensure_measurement_snap_proxy(obj, scene)
                continue
            if not is_dimension_object(obj):
                continue

            props = obj.dimension_props
            start_world, _start_status = resolve_anchor(props.start)
            end_world, _end_status = resolve_anchor(props.end)
            if start_world is None or end_world is None:
                continue

            geometry = get_dimension_world_geometry(
                props.dimension_type,
                start_world,
                end_world,
                Vector(props.offset_plane_normal),
                props.offset_distance,
                props.offset_angle,
            )
            if geometry is None:
                continue

            target_world = geometry["line_mid_world"]
            if (obj.matrix_world.translation - target_world).length <= 1e-6:
                continue

            matrix_world = obj.matrix_world.copy()
            matrix_world.translation = target_world
            obj.matrix_world = matrix_world
    finally:
        _location_sync_active = False


def get_measure_world_points(_extension_axis, start_world, end_world):
    return start_world, end_world, (end_world - start_world).length


def get_dimension_world_geometry(
    dimension_type,
    start_world,
    end_world,
    plane_normal,
    offset_distance,
    offset_angle=0.0,
):
    measure_start_world, measure_end_world, value = get_measure_world_points(
        dimension_type,
        start_world,
        end_world,
    )

    measure_vector = measure_end_world - measure_start_world
    if measure_vector.length < 1e-6:
        return None

    measure_direction = measure_vector.normalized()
    stable_plane_normal, offset_direction = get_offset_basis(
        dimension_type,
        measure_direction,
        plane_normal,
    )

    if abs(offset_angle) >= 1e-6:
        offset_rotation = Quaternion(measure_direction, offset_angle)
        offset_direction = offset_rotation @ offset_direction
        stable_plane_normal = measure_direction.cross(offset_direction).normalized()

    if offset_direction.length < 1e-6:
        return None

    offset_direction.normalize()
    offset_vector = offset_direction * offset_distance

    line_start_world = measure_start_world + offset_vector
    line_end_world = measure_end_world + offset_vector

    return {
        "measure_start_world": measure_start_world,
        "measure_end_world": measure_end_world,
        "measure_direction_world": measure_direction,
        "plane_normal_world": stable_plane_normal,
        "offset_direction_world": offset_direction,
        "offset_distance": offset_distance,
        "offset_angle": offset_angle,
        "line_start_world": line_start_world,
        "line_end_world": line_end_world,
        "line_mid_world": (line_start_world + line_end_world) * 0.5,
        "value": value,
    }


def get_offset_basis(extension_axis, measure_direction, plane_normal):
    stable_plane_normal = _sanitize_plane_normal(measure_direction, plane_normal)
    preferred_offset_direction = stable_plane_normal.cross(measure_direction)
    axis_directions = {
        "X": Vector((1.0, 0.0, 0.0)),
        "Y": Vector((0.0, 1.0, 0.0)),
        "Z": Vector((0.0, 0.0, 1.0)),
    }

    candidates = []
    for axis_name, axis_direction in axis_directions.items():
        perpendicular_axis = axis_direction - measure_direction * axis_direction.dot(measure_direction)
        if perpendicular_axis.length >= 1e-6:
            candidates.append((axis_name, perpendicular_axis.normalized()))

    if not candidates:
        return stable_plane_normal, preferred_offset_direction

    if extension_axis in axis_directions:
        matching_candidate = next(
            (candidate for name, candidate in candidates if name == extension_axis),
            None,
        )
    else:
        matching_candidate = None

    if matching_candidate is None:
        preferred_direction = preferred_offset_direction.normalized()
        _axis_name, matching_candidate = max(
            candidates,
            key=lambda item: abs(item[1].dot(preferred_direction)),
        )
        if matching_candidate.dot(preferred_direction) < 0.0:
            matching_candidate.negate()

    offset_direction = matching_candidate
    stable_plane_normal = measure_direction.cross(offset_direction).normalized()

    return stable_plane_normal, offset_direction


def build_dimension_geometry_for_object(context, dimension_object):
    props = dimension_object.dimension_props

    start_world, start_status = resolve_anchor(props.start)
    end_world, end_status = resolve_anchor(props.end)
    if start_world is None or end_world is None:
        return None

    world_geometry = get_dimension_world_geometry(
        props.dimension_type,
        start_world,
        end_world,
        Vector(props.offset_plane_normal),
        props.offset_distance,
        props.offset_angle,
    )
    if world_geometry is None:
        return None

    screen_geometry = _project_dimension_geometry(
        context,
        start_world,
        end_world,
        world_geometry,
    )
    if screen_geometry is None:
        return None

    screen_geometry["value"] = world_geometry["value"]
    screen_geometry["dimension_type"] = props.dimension_type
    screen_geometry["start_status"] = start_status
    screen_geometry["end_status"] = end_status
    scene_settings = getattr(context.scene, "dimensions_settings", None)
    screen_geometry["precision"] = (
        scene_settings.precision if scene_settings is not None else DEFAULT_PRECISION
    )
    screen_geometry["text_placement"] = (
        scene_settings.text_placement if scene_settings is not None else "INLINE"
    )
    screen_geometry["line_width"] = props.line_width
    screen_geometry["text_size"] = props.text_size
    screen_geometry["arrow_size"] = props.arrow_size
    screen_geometry["custom_text"] = props.custom_text.strip()
    screen_geometry["custom_text_position"] = props.custom_text_position
    return screen_geometry


def draw_dimensions():
    context = bpy.context

    if context.area is None or context.area.type != "VIEW_3D":
        return

    if context.region is None or context.region.type != "WINDOW":
        return

    if context.region_data is None:
        return

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    gpu.state.line_width_set(DEFAULT_LINE_WIDTH)

    try:
        for obj in context.scene.objects:
            if not is_dimension_object(obj):
                continue

            props = obj.dimension_props
            if not props.visible or not _object_visible_in_viewport(context, obj):
                continue

            geometry = build_dimension_geometry_for_object(context, obj)
            if geometry is None:
                continue

            if geometry["start_status"] != "LINKED" or geometry["end_status"] != "LINKED":
                color = (1.0, 0.18, 0.08, 1.0)
            else:
                color = props.selected_color if obj.select_get() else props.color
            _draw_dimension_geometry(context, shader, geometry, color, geometry["precision"])

        if _preview_state is not None:
            _draw_preview(context, shader, _preview_state)

        if _guide_preview_state is not None:
            _draw_guide_preview_marker(shader, _guide_preview_state)

        if _measure_state is not None:
            _draw_transient_measure(context, shader, _measure_state)

        for interaction_state in (_preview_state, _guide_preview_state, _measure_state):
            if interaction_state is not None:
                _draw_interaction_status(interaction_state)

        _draw_persistent_measurements(context)

        _draw_selected_object_overlay(context)
    finally:
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set("NONE")


def draw_world_guides():
    context = bpy.context

    if context.area is None or context.area.type != "VIEW_3D":
        return

    if context.region is None or context.region.type != "WINDOW":
        return

    if context.region_data is None:
        return

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")

    try:
        _draw_construction_guides(context, shader)
        _draw_tool_snap_highlights(context, shader)
        for interaction_state in (_preview_state, _guide_preview_state, _measure_state):
            if interaction_state is not None:
                _draw_axis_gesture(context, shader, interaction_state)
        if _guide_preview_state is not None:
            _draw_guide_preview_world(context, shader, _guide_preview_state)
    finally:
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set("NONE")


def _axis_endpoint(start_world, end_world, axis):
    if axis == "X":
        return Vector((end_world.x, start_world.y, start_world.z))
    if axis == "Y":
        return Vector((start_world.x, end_world.y, start_world.z))
    if axis == "Z":
        return Vector((start_world.x, start_world.y, end_world.z))
    return end_world


def _draw_construction_guides(context, shader):
    settings = getattr(context.scene, "dimensions_settings", None)
    if settings is None or not settings.show_construction_guides:
        return
    for obj in context.scene.objects:
        if not guide_is_visible(context, obj):
            continue
        segment = guide_segment_world(obj)
        if segment is None:
            continue
        _draw_world_segment(shader, segment[0], segment[1], settings.guide_color, settings.guide_line_width)


def _draw_guide_preview_marker(shader, state):
    hover = state.get("hover_screen")
    if hover is not None:
        _draw_marker(shader, hover, _snap_marker_color(state))


def _draw_guide_preview_world(context, shader, state):
    start = state.get("start_world")
    end = state.get("end_world")
    if start is None or end is None:
        return
    settings = getattr(context.scene, "dimensions_settings", None)
    color = tuple(settings.guide_color) if settings is not None else (0.22, 0.70, 1.0, 0.7)
    width = settings.guide_line_width if settings is not None else 1.0
    _draw_guide_preview_segment(shader, start, end, state.get("axis", "ALIGNED"), color, width)


def _draw_guide_preview_segment(shader, start, end, axis, color, line_width):
    if axis == "X":
        direction = Vector((1.0, 0.0, 0.0))
    elif axis == "Y":
        direction = Vector((0.0, 1.0, 0.0))
    elif axis == "Z":
        direction = Vector((0.0, 0.0, 1.0))
    else:
        direction = end - start
        if direction.length < 1e-6:
            return
        direction.normalize()
        _draw_world_segment(shader, start - direction * 10000.0, start + direction * 10000.0, color, line_width)
        return

    _draw_world_segment(shader, start - direction * 10000.0, start + direction * 10000.0, color, line_width)


def _draw_world_segment(shader, start_world, end_world, color, line_width):
    gpu.state.line_width_set(line_width)
    batch = batch_for_shader(shader, "LINES", {"pos": [start_world, end_world]})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _draw_axis_gesture(context, shader, state):
    if not state.get("axis_gesture_active"):
        return
    origin = state.get("axis_origin_world")
    if origin is None:
        return
    origin = Vector(origin)
    extent = max(float(context.region_data.view_distance) * 0.22, 0.1)
    active_axis = state.get("axis", "ALIGNED")
    axes = {
        "X": (Vector((1.0, 0.0, 0.0)), (1.0, 0.18, 0.12, 0.95)),
        "Y": (Vector((0.0, 1.0, 0.0)), (0.22, 1.0, 0.18, 0.95)),
        "Z": (Vector((0.0, 0.0, 1.0)), (0.20, 0.48, 1.0, 0.95)),
    }
    for axis, (direction, color) in axes.items():
        width = 5.0 if axis == active_axis else 2.0
        _draw_world_segment(
            shader,
            origin - direction * extent,
            origin + direction * extent,
            color,
            width,
        )


def _draw_tool_snap_highlights(context, shader):
    locked_color = (0.10, 0.72, 1.0, 0.9)
    hover_color = (1.0, 0.58, 0.06, 1.0)
    for state in (_preview_state, _guide_preview_state, _measure_state):
        if state is None:
            continue
        for snap in state.get("locked_snaps", ()):
            _draw_snap_highlight(context, shader, snap, locked_color, show_object_context=False)
        hover_snap = state.get("hover_snap")
        if hover_snap is not None:
            _draw_snap_highlight(context, shader, hover_snap, hover_color, show_object_context=True)


def _draw_snap_highlight(context, shader, snap, color, show_object_context=False):
    geometry = _snap_highlight_geometry(
        context,
        snap,
        include_object_context=show_object_context,
    )
    if geometry is None:
        return

    kind = geometry["kind"]
    points = geometry["points"]
    object_edges = geometry.get("object_edges", ())
    if show_object_context and object_edges:
        gpu.state.depth_test_set("LESS_EQUAL")
        try:
            gpu.state.line_width_set(1.0)
            batch = batch_for_shader(shader, "LINES", {"pos": object_edges})
            shader.bind()
            shader.uniform_float("color", (0.015, 0.015, 0.015, 0.72))
            batch.draw(shader)
            object_vertices = geometry.get("object_vertices", ())
            if object_vertices:
                gpu.state.point_size_set(3.0)
                batch = batch_for_shader(shader, "POINTS", {"pos": object_vertices})
                shader.bind()
                shader.uniform_float("color", (0.01, 0.01, 0.01, 0.8))
                batch.draw(shader)
                gpu.state.point_size_set(1.0)
        finally:
            gpu.state.depth_test_set("NONE")

    if kind == "FACE" and len(points) >= 3:
        from mathutils.geometry import tessellate_polygon

        triangles = tessellate_polygon([points])
        triangle_points = []
        for triangle in triangles:
            for value in triangle:
                triangle_points.append(points[value] if isinstance(value, int) else value)
        if triangle_points:
            batch = batch_for_shader(shader, "TRIS", {"pos": triangle_points})
            shader.bind()
            shader.uniform_float("color", (color[0], color[1], color[2], 0.16))
            batch.draw(shader)
        outline = []
        for index, point in enumerate(points):
            outline.extend((point, points[(index + 1) % len(points)]))
        gpu.state.line_width_set(2.25)
        batch = batch_for_shader(shader, "LINES", {"pos": outline})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
        return

    if kind in {"EDGE", "GUIDE"} and len(points) == 2:
        gpu.state.line_width_set(2.25)
        batch = batch_for_shader(shader, "LINES", {"pos": points})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
        return

    if kind == "VERTEX" and points:
        connected_edges = geometry.get("connected_edges", ())
        if connected_edges:
            gpu.state.line_width_set(2.5)
            batch = batch_for_shader(shader, "LINES", {"pos": connected_edges})
            shader.bind()
            shader.uniform_float("color", color)
            batch.draw(shader)
        gpu.state.point_size_set(9.0)
        batch = batch_for_shader(shader, "POINTS", {"pos": [points[0]]})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
        gpu.state.point_size_set(1.0)


def _snap_highlight_geometry(context, snap, include_object_context=True):
    """Resolve a snap target into world geometry for viewport highlighting."""
    if snap is None:
        return None
    snap_type = snap.get("type", "WORLD")
    construction_object = snap.get("guide_object")
    if construction_object is not None:
        if snap_type == "GUIDE":
            segment = guide_segment_world(construction_object)
            return None if segment is None else {"kind": "GUIDE", "points": list(segment)}
        if snap_type == "MEASUREMENT":
            segment = construction_segment_world(construction_object)
            if segment is None:
                return None
            if snap.get("label") in {"Measurement Start", "Measurement Midpoint", "Measurement End"}:
                return {"kind": "VERTEX", "points": [snap["world_co"].copy()]}
            return {"kind": "EDGE", "points": list(segment)}

    obj = snap.get("object")
    if obj is None or getattr(obj, "type", None) != "MESH":
        return None

    matrix = obj.matrix_world
    if obj.mode == "EDIT" and getattr(context, "edit_object", None) == obj:
        import bmesh

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        object_edges = (
            [
                matrix @ vertex.co
                for edge in bm.edges
                for vertex in edge.verts
                if not edge.hide
            ]
            if include_object_context
            else []
        )
        object_vertices = (
            [matrix @ vertex.co for vertex in bm.verts if not vertex.hide]
            if include_object_context
            else []
        )
        if snap_type == "VERTEX":
            index = snap.get("vertex_index", -1)
            if 0 <= index < len(bm.verts):
                vertex = bm.verts[index]
                connected_edges = [
                    matrix @ edge_vertex.co
                    for edge in vertex.link_edges
                    if not edge.hide
                    for edge_vertex in edge.verts
                ]
                return {
                    "kind": "VERTEX",
                    "points": [matrix @ vertex.co],
                    "connected_edges": connected_edges,
                    "object_edges": object_edges,
                    "object_vertices": object_vertices,
                }
        elif snap_type == "EDGE":
            edge = None
            index = snap.get("edge_index", -1)
            if 0 <= index < len(bm.edges):
                edge = bm.edges[index]
            if edge is None:
                vertices = snap.get("edge_vertices", ())
                if len(vertices) == 2 and all(0 <= index < len(bm.verts) for index in vertices):
                    edge = bm.edges.get((bm.verts[vertices[0]], bm.verts[vertices[1]]))
            if edge is not None:
                return {
                    "kind": "EDGE",
                    "points": [matrix @ vertex.co for vertex in edge.verts],
                    "object_edges": object_edges,
                    "object_vertices": object_vertices,
                }
        elif snap_type == "FACE":
            index = snap.get("face_index", -1)
            if 0 <= index < len(bm.faces):
                return {
                    "kind": "FACE",
                    "points": [matrix @ vertex.co for vertex in bm.faces[index].verts],
                    "object_edges": object_edges,
                    "object_vertices": object_vertices,
                }
        return None

    mesh = obj.data
    object_edges = (
        [
            matrix @ mesh.vertices[vertex_index].co
            for edge in mesh.edges
            if not edge.hide
            for vertex_index in edge.vertices
        ]
        if include_object_context
        else []
    )
    object_vertices = (
        [matrix @ vertex.co for vertex in mesh.vertices if not vertex.hide]
        if include_object_context
        else []
    )
    if snap_type == "VERTEX":
        index = snap.get("vertex_index", -1)
        if 0 <= index < len(mesh.vertices):
            connected_edges = [
                matrix @ mesh.vertices[vertex_index].co
                for edge in mesh.edges
                if not edge.hide and index in edge.vertices
                for vertex_index in edge.vertices
            ]
            return {
                "kind": "VERTEX",
                "points": [matrix @ mesh.vertices[index].co],
                "connected_edges": connected_edges,
                "object_edges": object_edges,
                "object_vertices": object_vertices,
            }
    elif snap_type == "EDGE":
        vertices = snap.get("edge_vertices", ())
        if len(vertices) != 2:
            edge_index = snap.get("edge_index", -1)
            if 0 <= edge_index < len(mesh.edges):
                vertices = mesh.edges[edge_index].vertices
        if len(vertices) == 2 and all(0 <= index < len(mesh.vertices) for index in vertices):
            return {
                "kind": "EDGE",
                "points": [matrix @ mesh.vertices[index].co for index in vertices],
                "object_edges": object_edges,
                "object_vertices": object_vertices,
            }
    elif snap_type == "FACE":
        index = snap.get("face_index", -1)
        if 0 <= index < len(mesh.polygons):
            return {
                "kind": "FACE",
                "points": [matrix @ mesh.vertices[vertex_index].co for vertex_index in mesh.polygons[index].vertices],
                "object_edges": object_edges,
                "object_vertices": object_vertices,
            }
    return None


def _draw_interaction_status(state):
    parts = []
    label = state.get("hover_label")
    if label:
        parts.append(label)
    axis = state.get("axis", "ALIGNED")
    if axis != "ALIGNED":
        prefix = "MMB " if state.get("axis_gesture_active") else ""
        parts.append(f"{prefix}{axis} Axis")
    distance_text = state.get("distance_text", "").strip()
    if distance_text:
        parts.append(f"Input: {distance_text}")
    if not parts:
        return
    position = state.get("hover_screen")
    if position is None:
        position = Vector((24.0, 44.0))
    else:
        position = Vector((position.x + 14.0, position.y + 18.0))
    color = (
        (1.0, 0.22, 0.12, 1.0)
        if not state.get("distance_input_valid", True)
        else (1.0, 0.82, 0.28, 1.0)
    )
    _draw_text_left(" | ".join(parts), position, color)


def _draw_transient_measure(context, shader, state):
    hover = state.get("hover_screen")
    if hover is not None:
        _draw_marker(shader, hover, _snap_marker_color(state))
    start = state.get("start_world")
    raw_end = state.get("end_world")
    if start is None or raw_end is None:
        return
    end = _axis_endpoint(start, raw_end, state.get("axis", "ALIGNED"))
    start_screen = _project_world_to_screen(context, start)
    end_screen = _project_world_to_screen(context, end)
    if start_screen is None or end_screen is None or (end_screen - start_screen).length < 0.5:
        return
    settings = getattr(context.scene, "dimensions_settings", None)
    precision = settings.precision if settings is not None else DEFAULT_PRECISION
    text_size = settings.dimension_text_size if settings is not None else DEFAULT_TEXT_SIZE
    color = (0.35, 1.0, 0.72, 1.0)
    gpu.state.line_width_set(2.0)
    batch = batch_for_shader(shader, "LINES", {"pos": [start_screen, end_screen]})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    _draw_marker(shader, start_screen, color)
    _draw_marker(shader, end_screen, color)
    direction = (end_screen - start_screen).normalized()
    perpendicular = Vector((-direction.y, direction.x))
    label_position = (start_screen + end_screen) * 0.5 + perpendicular * (text_size + 4.0)
    label = state.get("distance_text", "").strip()
    if not label:
        label = format_length(context, (end - start).length, precision)
    _draw_text(label, label_position, color, text_size)


def _draw_persistent_measurements(context):
    settings = getattr(context.scene, "dimensions_settings", None)
    if settings is None or not settings.show_construction_guides:
        return
    precision = settings.precision
    text_size = settings.dimension_text_size
    color = tuple(settings.guide_color)
    for obj in context.scene.objects:
        if not guide_is_visible(context, obj):
            continue
        if getattr(obj.guide_props, "kind", "GUIDE") != "MEASUREMENT":
            continue
        segment = construction_segment_world(obj)
        if segment is None:
            continue
        start_world, end_world = segment
        start_screen = _project_world_to_screen(context, start_world)
        end_screen = _project_world_to_screen(context, end_world)
        if start_screen is None or end_screen is None or (end_screen - start_screen).length < 0.5:
            continue
        direction = (end_screen - start_screen).normalized()
        perpendicular = Vector((-direction.y, direction.x))
        label_position = (start_screen + end_screen) * 0.5 + perpendicular * (text_size + 4.0)
        _draw_text(format_length(context, (end_world - start_world).length, precision), label_position, color, text_size)


def _draw_dimension_geometry(context, shader, geometry, color, precision):
    label = format_length(context, geometry["value"], precision)
    text_layout = _build_text_layout(
        label,
        geometry,
        geometry.get("text_placement", "INLINE"),
        geometry.get("custom_text", ""),
        geometry.get("custom_text_position", "ABOVE"),
        geometry.get("text_size", DEFAULT_TEXT_SIZE),
        geometry.get("arrow_size", DEFAULT_ARROW_SIZE),
    )
    line_segments = [
        geometry["anchor_start_screen"],
        geometry["line_start_screen"],
        geometry["anchor_end_screen"],
        geometry["line_end_screen"],
    ]
    line_segments.extend(text_layout["line_segments"])
    arrow_size = geometry.get("arrow_size", DEFAULT_ARROW_SIZE)
    line_segments.extend(_build_arrow_segments(geometry["line_start_screen"], geometry["line_direction_screen"], arrow_size))
    line_segments.extend(_build_arrow_segments(geometry["line_end_screen"], -geometry["line_direction_screen"], arrow_size))

    gpu.state.line_width_set(geometry.get("line_width", DEFAULT_LINE_WIDTH))
    batch = batch_for_shader(shader, "LINES", {"pos": line_segments})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

    text_size = geometry.get("text_size", DEFAULT_TEXT_SIZE)
    for text, position in text_layout["text_items"]:
        _draw_text(text, position, color, text_size)
    broken = []
    if geometry.get("start_status") != "LINKED":
        broken.append(f"Start: {geometry.get('start_status', 'Unknown').replace('_', ' ').title()}")
    if geometry.get("end_status") != "LINKED":
        broken.append(f"End: {geometry.get('end_status', 'Unknown').replace('_', ' ').title()}")
    if broken:
        warning_position = geometry["line_mid_screen"] + Vector((0.0, -(text_size + 10.0)))
        _draw_text(" | ".join(broken), warning_position, (1.0, 0.18, 0.08, 1.0), text_size)


def _draw_preview(context, shader, preview_state):
    hover_screen = preview_state.get("hover_screen")
    if hover_screen is not None:
        _draw_marker(shader, hover_screen, _snap_marker_color(preview_state))

    start_world = preview_state.get("start_world")
    end_world = preview_state.get("end_world")
    if start_world is None or end_world is None:
        return

    plane_normal = preview_state.get("offset_plane_normal")
    offset_distance = preview_state.get("offset_distance", 0.0)
    offset_angle = preview_state.get("offset_angle", 0.0)
    dimension_type = preview_state.get("dimension_type", "ALIGNED")

    if plane_normal is None:
        plane_normal = _sanitize_plane_normal(
            (end_world - start_world).normalized() if (end_world - start_world).length > 1e-6 else Vector((1.0, 0.0, 0.0)),
            Vector((0.0, 0.0, 1.0)),
        )

    world_geometry = get_dimension_world_geometry(
        dimension_type,
        start_world,
        end_world,
        Vector(plane_normal),
        offset_distance,
        offset_angle,
    )
    if world_geometry is None:
        return

    screen_geometry = _project_dimension_geometry(
        context,
        start_world,
        end_world,
        world_geometry,
    )
    if screen_geometry is None:
        return

    scene_settings = getattr(context.scene, "dimensions_settings", None)
    precision = scene_settings.precision if scene_settings is not None else DEFAULT_PRECISION
    label = format_length(context, world_geometry["value"], precision)
    if scene_settings is not None:
        color = tuple(scene_settings.dimension_color)
        line_width = scene_settings.dimension_line_width
        text_size = scene_settings.dimension_text_size
        arrow_size = scene_settings.dimension_arrow_size
        text_placement = scene_settings.text_placement
    else:
        color = (0.2, 0.75, 1.0, 0.95)
        line_width = DEFAULT_LINE_WIDTH
        text_size = DEFAULT_TEXT_SIZE
        arrow_size = DEFAULT_ARROW_SIZE
        text_placement = "INLINE"
    text_layout = _build_text_layout(
        label,
        screen_geometry,
        text_placement,
        text_size=text_size,
        arrow_size=arrow_size,
    )
    line_segments = [
        screen_geometry["anchor_start_screen"],
        screen_geometry["line_start_screen"],
        screen_geometry["anchor_end_screen"],
        screen_geometry["line_end_screen"],
    ]
    line_segments.extend(text_layout["line_segments"])
    line_segments.extend(_build_arrow_segments(screen_geometry["line_start_screen"], screen_geometry["line_direction_screen"], arrow_size))
    line_segments.extend(_build_arrow_segments(screen_geometry["line_end_screen"], -screen_geometry["line_direction_screen"], arrow_size))

    gpu.state.line_width_set(line_width)
    batch = batch_for_shader(shader, "LINES", {"pos": line_segments})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

    for text, position in text_layout["text_items"]:
        _draw_text(text, position, color, text_size)


def _draw_selected_object_overlay(context):
    settings = getattr(context.scene, "dimensions_settings", None)
    if settings is None or not settings.show_selected_object_overlay:
        return

    selected_mesh_objects = [
        obj for obj in context.selected_objects
        if obj.type == "MESH" and not is_dimension_object(obj)
    ]
    if not selected_mesh_objects:
        return

    line_y = 22
    header_color = (0.95, 0.95, 0.95, 1.0)
    text_color = (0.80, 0.88, 0.95, 1.0)

    lines = [("Selected Mesh Size", header_color)]
    depsgraph = context.evaluated_depsgraph_get()
    for obj in selected_mesh_objects[:6]:
        if settings.show_overlay_object_name:
            lines.append((obj.name, header_color))

        dims = sorted((obj.dimensions.x, obj.dimensions.y, obj.dimensions.z), reverse=True)
        label = (
            f"Length {format_length(context, dims[0], 3)}   "
            f"Width {format_length(context, dims[1], 3)}   "
            f"Thickness {format_length(context, dims[2], 3)}"
        )
        lines.append((label, text_color))
        if settings.show_overlay_volume:
            volume, status = get_mesh_volume(obj, depsgraph)
            if volume is None:
                volume_label = "Volume N/A"
            else:
                approximation = "~" if status == VOLUME_APPROXIMATE else ""
                volume_label = f"Volume {approximation}{format_volume(context, volume, 3)}"
            lines.append((volume_label, text_color))

    is_right = settings.hud_corner in {"BOTTOM_RIGHT", "TOP_RIGHT"}
    is_top = settings.hud_corner in {"TOP_LEFT", "TOP_RIGHT"}
    current_x = (
        context.region.width - settings.hud_padding_horizontal
        if is_right
        else settings.hud_padding_horizontal
    )
    if is_top:
        current_y = context.region.height - settings.hud_padding_vertical - DEFAULT_TEXT_SIZE
    else:
        current_y = settings.hud_padding_vertical + ((len(lines) - 1) * line_y)

    draw_text = _draw_text_right if is_right else _draw_text_left
    for text, color in lines:
        draw_text(text, Vector((current_x, current_y)), color)
        current_y -= line_y


def find_dimension_hit(context, mouse_x, mouse_y, threshold=DEFAULT_SELECTION_PIXEL_THRESHOLD):
    mouse = Vector((mouse_x, mouse_y))
    best = None

    for obj in context.scene.objects:
        if not is_dimension_object(obj):
            continue

        props = obj.dimension_props
        if not props.visible or not _object_visible_in_viewport(context, obj):
            continue

        geometry = build_dimension_geometry_for_object(context, obj)
        if geometry is None:
            continue

        distance = _geometry_hit_distance(context, geometry, geometry["precision"], mouse)
        if distance is None or distance > threshold:
            continue

        if best is None or distance < best[0]:
            best = (distance, obj)

    return None if best is None else best[1]


def find_guide_hit(context, mouse_x, mouse_y, threshold=DEFAULT_SELECTION_PIXEL_THRESHOLD):
    snap = find_nearest_guide_point(context, mouse_x, mouse_y, threshold)
    return None if snap is None else snap.get("guide_object")


def _project_dimension_geometry(context, anchor_start_world, anchor_end_world, world_geometry):
    anchor_start_screen = _project_world_to_screen(context, anchor_start_world)
    anchor_end_screen = _project_world_to_screen(context, anchor_end_world)
    line_start_screen = _project_world_to_screen(context, world_geometry["line_start_world"])
    line_end_screen = _project_world_to_screen(context, world_geometry["line_end_world"])

    if any(value is None for value in (anchor_start_screen, anchor_end_screen, line_start_screen, line_end_screen)):
        return None

    line_direction_screen = line_end_screen - line_start_screen
    if line_direction_screen.length < 0.001:
        return None

    line_direction_screen.normalize()

    return {
        "anchor_start_world": anchor_start_world,
        "anchor_end_world": anchor_end_world,
        "line_start_world": world_geometry["line_start_world"],
        "line_end_world": world_geometry["line_end_world"],
        "line_mid_world": world_geometry["line_mid_world"],
        "measure_start_world": world_geometry["measure_start_world"],
        "measure_end_world": world_geometry["measure_end_world"],
        "anchor_start_screen": anchor_start_screen,
        "anchor_end_screen": anchor_end_screen,
        "line_start_screen": line_start_screen,
        "line_end_screen": line_end_screen,
        "line_mid_screen": (line_start_screen + line_end_screen) * 0.5,
        "line_direction_screen": line_direction_screen,
        "plane_normal_world": world_geometry["plane_normal_world"],
        "offset_direction_world": world_geometry["offset_direction_world"],
        "offset_distance": world_geometry["offset_distance"],
        "offset_angle": world_geometry["offset_angle"],
    }


def _sanitize_plane_normal(measure_direction, plane_normal):
    candidate = plane_normal.normalized() if plane_normal.length > 1e-6 else Vector((0.0, 0.0, 1.0))
    if abs(candidate.dot(measure_direction)) < 0.98:
        return candidate

    fallback = min(_AXIS_CANDIDATES, key=lambda axis: abs(axis.dot(measure_direction)))
    return fallback.normalized()


def _build_arrow_segments(point, direction, arrow_scale=DEFAULT_ARROW_SIZE):
    perpendicular = Vector((-direction.y, direction.x))
    left = point + (direction * arrow_scale) + (perpendicular * arrow_scale * 0.45)
    right = point + (direction * arrow_scale) - (perpendicular * arrow_scale * 0.45)
    return [
        point,
        left,
        point,
        right,
    ]


def _build_text_layout(
    value_text,
    geometry,
    placement,
    custom_text="",
    custom_text_position="ABOVE",
    text_size=DEFAULT_TEXT_SIZE,
    arrow_size=DEFAULT_ARROW_SIZE,
):
    font_id = 0
    blf.size(font_id, text_size)

    text_lines = [value_text]
    if custom_text:
        if custom_text_position == "BELOW":
            text_lines.append(custom_text)
        else:
            text_lines.insert(0, custom_text)

    text_metrics = [
        (text, *blf.dimensions(font_id, text))
        for text in text_lines
    ]
    line_spacing = 3.0 if len(text_metrics) > 1 else 0.0
    block_width = max(width for _text, width, _height in text_metrics)
    block_height = (
        sum(height for _text, _width, height in text_metrics)
        + line_spacing * (len(text_metrics) - 1)
    )

    line_start = geometry["line_start_screen"]
    line_end = geometry["line_end_screen"]
    line_mid = geometry["line_mid_screen"]
    line_direction = geometry["line_direction_screen"]
    full_line = [line_start, line_end]
    text_half_extent_along_line = (
        abs(line_direction.x) * block_width * 0.5
        + abs(line_direction.y) * block_height * 0.5
    )

    if placement == "ABOVE":
        perpendicular = Vector((-line_direction.y, line_direction.x))
        if perpendicular.y < 0.0:
            perpendicular.negate()
        text_half_extent_across_line = (
            abs(perpendicular.x) * block_width * 0.5
            + abs(perpendicular.y) * block_height * 0.5
        )
        block_center = line_mid + perpendicular * (text_half_extent_across_line + 5.0)
        line_segments = full_line
    elif placement == "OUTSIDE":
        block_center = line_end + line_direction * (
            arrow_size + 6.0 + text_half_extent_along_line
        )
        line_segments = full_line
    else:
        gap_half_width = text_half_extent_along_line + 5.0
        line_length = (line_end - line_start).length
        required_length = (gap_half_width * 2.0) + (arrow_size * 2.0)
        if line_length < required_length:
            block_center = line_end + line_direction * (
                arrow_size + 6.0 + text_half_extent_along_line
            )
            line_segments = full_line
        else:
            block_center = line_mid
            line_segments = [
                line_start,
                line_mid - line_direction * gap_half_width,
                line_mid + line_direction * gap_half_width,
                line_end,
            ]

    text_items = []
    current_y = block_center.y + (block_height * 0.5)
    for text, _width, height in text_metrics:
        text_position = Vector((block_center.x, current_y - (height * 0.5)))
        text_items.append((text, text_position))
        current_y -= height + line_spacing

    return {
        "line_segments": line_segments,
        "text_items": text_items,
        "text_position": block_center,
    }


def _draw_marker(shader, position, color):
    size = DEFAULT_HOVER_MARKER_SIZE
    marker_segments = [
        Vector((position.x - size, position.y)),
        Vector((position.x + size, position.y)),
        Vector((position.x, position.y - size)),
        Vector((position.x, position.y + size)),
    ]
    batch = batch_for_shader(shader, "LINES", {"pos": marker_segments})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _snap_marker_color(state):
    label = state.get("hover_label")
    snap_type = state.get("hover_type")

    if snap_type == "VERTEX":
        return (0.25, 1.0, 0.35, 1.0)

    if snap_type == "MEASUREMENT":
        return (0.25, 0.72, 1.0, 1.0)

    if label in {"Guide", "Measurement"}:
        return (0.25, 0.72, 1.0, 1.0)

    if label in {"Edge", "Midpoint", "Face Center", "Face"}:
        return (1.0, 0.82, 0.25, 1.0)

    return (1.0, 0.48, 0.20, 1.0)


def _draw_text(text, position, color, text_size=DEFAULT_TEXT_SIZE):
    font_id = 0
    blf.size(font_id, text_size)
    text_width, text_height = blf.dimensions(font_id, text)
    blf.color(font_id, *color)
    blf.position(
        font_id,
        position.x - (text_width * 0.5),
        position.y - (text_height * 0.5),
        0,
    )
    blf.draw(font_id, text)


def _draw_text_left(text, position, color):
    font_id = 0
    blf.size(font_id, DEFAULT_TEXT_SIZE)
    blf.color(font_id, *color)
    blf.position(font_id, position.x, position.y, 0)
    blf.draw(font_id, text)


def _draw_text_right(text, position, color):
    font_id = 0
    blf.size(font_id, DEFAULT_TEXT_SIZE)
    text_width, _text_height = blf.dimensions(font_id, text)
    blf.color(font_id, *color)
    blf.position(font_id, position.x - text_width, position.y, 0)
    blf.draw(font_id, text)


def _project_world_to_screen(context, world_co):
    return view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        world_co,
    )


def _geometry_hit_distance(context, geometry, precision, mouse):
    label = format_length(context, geometry["value"], precision)
    text_layout = _build_text_layout(
        label,
        geometry,
        geometry.get("text_placement", "INLINE"),
        geometry.get("custom_text", ""),
        geometry.get("custom_text_position", "ABOVE"),
        geometry.get("text_size", DEFAULT_TEXT_SIZE),
        geometry.get("arrow_size", DEFAULT_ARROW_SIZE),
    )
    dimension_segments = text_layout["line_segments"]
    segments = [
        (geometry["anchor_start_screen"], geometry["line_start_screen"]),
        (geometry["anchor_end_screen"], geometry["line_end_screen"]),
    ]
    segments.extend(
        (dimension_segments[index], dimension_segments[index + 1])
        for index in range(0, len(dimension_segments), 2)
    )

    best_distance = min(_point_to_segment_distance(mouse, start, end) for start, end in segments)

    for text, position in text_layout["text_items"]:
        label_distance = _point_to_label_distance(
            text,
            position,
            mouse,
            geometry.get("text_size", DEFAULT_TEXT_SIZE),
        )
        best_distance = min(best_distance, label_distance)

    return best_distance


def _object_visible_in_viewport(context, obj):
    try:
        return obj.visible_get(
            view_layer=getattr(context, "view_layer", None),
            viewport=getattr(context, "space_data", None),
        )
    except (AttributeError, TypeError):
        return not obj.hide_get()


def _point_to_segment_distance(point, start, end):
    segment = end - start
    length_squared = segment.length_squared
    if length_squared <= 1e-8:
        return (point - start).length

    factor = max(0.0, min(1.0, (point - start).dot(segment) / length_squared))
    projection = start + (segment * factor)
    return (point - projection).length


def _point_to_label_distance(text, position, point, text_size=DEFAULT_TEXT_SIZE):
    font_id = 0
    blf.size(font_id, text_size)
    text_width, text_height = blf.dimensions(font_id, text)

    left = position.x - (text_width * 0.5)
    right = left + text_width
    bottom = position.y - (text_height * 0.5)
    top = bottom + text_height

    dx = max(left - point.x, 0.0, point.x - right)
    dy = max(bottom - point.y, 0.0, point.y - top)
    return (dx * dx + dy * dy) ** 0.5
