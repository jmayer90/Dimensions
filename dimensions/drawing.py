import blf
import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .anchors import resolve_anchor
from .constants import (
    DEFAULT_ARROW_SIZE,
    DEFAULT_HOVER_MARKER_SIZE,
    DEFAULT_LINE_WIDTH,
    DEFAULT_SELECTION_PIXEL_THRESHOLD,
    DEFAULT_TEXT_SIZE,
)
from .properties import is_dimension_object
from .units import format_length


_draw_handler = None
_preview_state = None
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


def register_draw_handler():
    global _draw_handler

    if _draw_handler is not None:
        return

    _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        draw_dimensions,
        (),
        "WINDOW",
        "POST_PIXEL",
    )


def unregister_draw_handler():
    global _draw_handler

    if _draw_handler is None:
        return

    bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, "WINDOW")
    _draw_handler = None


def get_measure_world_points(dimension_type, start_world, end_world):
    if dimension_type == "X":
        measure_end = Vector((end_world.x, start_world.y, start_world.z))
        return start_world, measure_end, abs(end_world.x - start_world.x)

    if dimension_type == "Y":
        measure_end = Vector((start_world.x, end_world.y, start_world.z))
        return start_world, measure_end, abs(end_world.y - start_world.y)

    if dimension_type == "Z":
        measure_end = Vector((start_world.x, start_world.y, end_world.z))
        return start_world, measure_end, abs(end_world.z - start_world.z)

    return start_world, end_world, (end_world - start_world).length


def get_dimension_world_geometry(dimension_type, start_world, end_world, plane_normal, offset_distance):
    measure_start_world, measure_end_world, value = get_measure_world_points(
        dimension_type,
        start_world,
        end_world,
    )

    measure_vector = measure_end_world - measure_start_world
    if measure_vector.length < 1e-6:
        return None

    measure_direction = measure_vector.normalized()
    stable_plane_normal = _sanitize_plane_normal(measure_direction, plane_normal)
    offset_direction = stable_plane_normal.cross(measure_direction)
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
        "line_start_world": line_start_world,
        "line_end_world": line_end_world,
        "line_mid_world": (line_start_world + line_end_world) * 0.5,
        "value": value,
    }


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
    screen_geometry["precision"] = props.precision
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
            if not props.visible or obj.hide_get():
                continue

            geometry = build_dimension_geometry_for_object(context, obj)
            if geometry is None:
                continue

            color = props.selected_color if obj.select_get() else props.color
            _draw_dimension_geometry(context, shader, geometry, color, props.precision)

        if _preview_state is not None:
            _draw_preview(context, shader, _preview_state)

        _draw_selected_object_overlay(context)
    finally:
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set("NONE")


def _draw_dimension_geometry(context, shader, geometry, color, precision):
    line_segments = [
        geometry["anchor_start_screen"],
        geometry["line_start_screen"],
        geometry["anchor_end_screen"],
        geometry["line_end_screen"],
        geometry["line_start_screen"],
        geometry["line_end_screen"],
    ]
    line_segments.extend(_build_arrow_segments(geometry["line_start_screen"], geometry["line_direction_screen"]))
    line_segments.extend(_build_arrow_segments(geometry["line_end_screen"], -geometry["line_direction_screen"]))

    batch = batch_for_shader(shader, "LINES", {"pos": line_segments})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

    label = format_length(context, geometry["value"], precision)
    _draw_text(label, geometry["line_mid_screen"], color)


def _draw_preview(context, shader, preview_state):
    hover_screen = preview_state.get("hover_screen")
    if hover_screen is not None:
        _draw_marker(shader, hover_screen, (0.3, 1.0, 0.3, 1.0))

    start_world = preview_state.get("start_world")
    end_world = preview_state.get("end_world")
    if start_world is None or end_world is None:
        return

    plane_normal = preview_state.get("offset_plane_normal")
    offset_distance = preview_state.get("offset_distance", 0.0)
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

    color = (0.9, 0.9, 0.2, 0.9)
    line_segments = [
        screen_geometry["anchor_start_screen"],
        screen_geometry["line_start_screen"],
        screen_geometry["anchor_end_screen"],
        screen_geometry["line_end_screen"],
        screen_geometry["line_start_screen"],
        screen_geometry["line_end_screen"],
    ]
    line_segments.extend(_build_arrow_segments(screen_geometry["line_start_screen"], screen_geometry["line_direction_screen"]))
    line_segments.extend(_build_arrow_segments(screen_geometry["line_end_screen"], -screen_geometry["line_direction_screen"]))

    batch = batch_for_shader(shader, "LINES", {"pos": line_segments})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

    label = format_length(context, world_geometry["value"], 3)
    _draw_text(label, screen_geometry["line_mid_screen"], color)


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

    margin_x = 20
    line_y = 22
    current_y = 28
    header_color = (0.95, 0.95, 0.95, 1.0)
    text_color = (0.80, 0.88, 0.95, 1.0)

    _draw_text_left("Selected Object Dimensions", Vector((margin_x, current_y)), header_color)
    current_y += line_y

    for obj in selected_mesh_objects[:6]:
        if settings.show_overlay_object_name:
            _draw_text_left(obj.name, Vector((margin_x, current_y)), header_color)
            current_y += line_y

        dims = sorted((obj.dimensions.x, obj.dimensions.y, obj.dimensions.z), reverse=True)
        label = (
            f"Length {format_length(context, dims[0], 3)}   "
            f"Width {format_length(context, dims[1], 3)}   "
            f"Thickness {format_length(context, dims[2], 3)}"
        )
        _draw_text_left(label, Vector((margin_x, current_y)), text_color)
        current_y += line_y


def find_dimension_hit(context, mouse_x, mouse_y, threshold=DEFAULT_SELECTION_PIXEL_THRESHOLD):
    mouse = Vector((mouse_x, mouse_y))
    best = None

    for obj in context.scene.objects:
        if not is_dimension_object(obj):
            continue

        props = obj.dimension_props
        if not props.visible or obj.hide_get():
            continue

        geometry = build_dimension_geometry_for_object(context, obj)
        if geometry is None:
            continue

        distance = _geometry_hit_distance(context, geometry, props.precision, mouse)
        if distance is None or distance > threshold:
            continue

        if best is None or distance < best[0]:
            best = (distance, obj)

    return None if best is None else best[1]


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
    }


def _sanitize_plane_normal(measure_direction, plane_normal):
    candidate = plane_normal.normalized() if plane_normal.length > 1e-6 else Vector((0.0, 0.0, 1.0))
    if abs(candidate.dot(measure_direction)) < 0.98:
        return candidate

    fallback = min(_AXIS_CANDIDATES, key=lambda axis: abs(axis.dot(measure_direction)))
    return fallback.normalized()


def _build_arrow_segments(point, direction):
    arrow_scale = DEFAULT_ARROW_SIZE
    perpendicular = Vector((-direction.y, direction.x))
    left = point + (direction * arrow_scale) + (perpendicular * arrow_scale * 0.45)
    right = point + (direction * arrow_scale) - (perpendicular * arrow_scale * 0.45)
    return [
        point,
        left,
        point,
        right,
    ]


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


def _draw_text(text, position, color):
    font_id = 0
    blf.size(font_id, DEFAULT_TEXT_SIZE)
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


def _project_world_to_screen(context, world_co):
    return view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        world_co,
    )


def _geometry_hit_distance(context, geometry, precision, mouse):
    segments = (
        (geometry["anchor_start_screen"], geometry["line_start_screen"]),
        (geometry["anchor_end_screen"], geometry["line_end_screen"]),
        (geometry["line_start_screen"], geometry["line_end_screen"]),
    )

    best_distance = min(_point_to_segment_distance(mouse, start, end) for start, end in segments)

    label = format_length(context, geometry["value"], precision)
    label_distance = _point_to_label_distance(label, geometry["line_mid_screen"], mouse)
    best_distance = min(best_distance, label_distance)

    return best_distance


def _point_to_segment_distance(point, start, end):
    segment = end - start
    length_squared = segment.length_squared
    if length_squared <= 1e-8:
        return (point - start).length

    factor = max(0.0, min(1.0, (point - start).dot(segment) / length_squared))
    projection = start + (segment * factor)
    return (point - projection).length


def _point_to_label_distance(text, position, point):
    font_id = 0
    blf.size(font_id, DEFAULT_TEXT_SIZE)
    text_width, text_height = blf.dimensions(font_id, text)

    left = position.x - (text_width * 0.5)
    right = left + text_width
    bottom = position.y - (text_height * 0.5)
    top = bottom + text_height

    dx = max(left - point.x, 0.0, point.x - right)
    dy = max(bottom - point.y, 0.0, point.y - top)
    return (dx * dx + dy * dy) ** 0.5
