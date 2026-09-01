import blf
import bpy
import gpu
from math import atan2, cos, degrees, pi, sin, tau
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Quaternion, Vector

from .anchors import dimension_source_is_missing, resolve_anchor
from .area_binding import area_label_world, evaluate_area_binding
from .angle_binding import resolve_angle_source
from .constants import (
    DEFAULT_ARROW_SIZE,
    DEFAULT_HOVER_MARKER_SIZE,
    DEFAULT_LINE_WIDTH,
    DEFAULT_PRECISION,
    DEFAULT_SELECTION_PIXEL_THRESHOLD,
    DEFAULT_TEXT_SIZE,
)
from .dimension_geometry import (
    get_angle_world_geometry,
    get_dimension_world_geometry,
    get_measure_world_points,
    get_offset_basis,
    sanitize_plane_normal,
)
from .dimension_sets import dimension_set_state, dimension_set_world_geometry
from .circle_binding import circle_geometry, circle_value
from .coordinate_dimensions import coordinate_label, coordinate_values, elevation_value, signed_number
from .properties import (
    is_dimension_object,
    is_guide_object,
    is_read_only_dimensions_object,
    resolve_dimension_style,
)
from .preferences import get_preferences
from .collections import get_scene_collection
from .snapping import construction_segment_world, find_nearest_guide_point, guide_is_visible, guide_segment_world
from .scene_sync import register_scene_sync, unregister_scene_sync
from .units import format_area, format_dual_length, format_length, format_volume
from .volume import (
    VOLUME_APPROXIMATE,
    get_mesh_volume,
)
from .viewport_state import (
    clear_all_states,
    clear_state,
    get_state,
    set_state,
    tag_redraw_all_view3d,
)


_pixel_draw_handler = None
_world_draw_handler = None
# One entry per viewport, holding the view it was built for. A viewport whose view
# changed drops its own geometry without disturbing any other viewport, so the cache
# stays bounded by the number of open 3D views rather than growing on every orbit.
_dimension_geometry_cache = {}
_text_layout_cache = {}
_text_metrics_cache = {}
_geometry_build_count = 0
_MAX_TEXT_LAYOUT_ENTRIES = 4096


def invalidate_dimension_geometry_cache():
    _dimension_geometry_cache.clear()
    _text_layout_cache.clear()


def geometry_build_count():
    """Number of full geometry rebuilds since registration, for cache tests."""
    return _geometry_build_count


class SegmentBatcher:
    """Accumulate line segments so annotations sharing a color and width cost one batch.

    Annotation overlays are overwhelmingly two colors — selected and unselected — so
    collapsing them turns a per-annotation upload into a per-color upload. Text is
    collected alongside and drawn after the lines, because ``blf`` cannot be batched.
    """

    def __init__(self, shader):
        self._shader = shader
        self._segments = {}
        self._text_items = []

    def add_segments(self, segments, color, line_width=DEFAULT_LINE_WIDTH):
        if not segments:
            return
        key = (tuple(round(float(channel), 6) for channel in color), round(float(line_width), 3))
        self._segments.setdefault(key, []).extend(segments)

    def add_text(self, text, position, color, text_size=DEFAULT_TEXT_SIZE, align="CENTER", rotation=0.0):
        self._text_items.append((text, position, tuple(color), text_size, align, rotation))

    @property
    def batch_count(self):
        return len(self._segments)

    def flush(self):
        for (color, line_width), segments in self._segments.items():
            gpu.state.line_width_set(line_width)
            batch = batch_for_shader(self._shader, "LINES", {"pos": segments})
            self._shader.bind()
            self._shader.uniform_float("color", color)
            batch.draw(self._shader)
        self._segments.clear()
        for text, position, color, text_size, align, rotation in self._text_items:
            if align == "LEFT":
                _draw_text_left(text, position, color, text_size)
            elif align == "RIGHT":
                _draw_text_right(text, position, color, text_size)
            else:
                _draw_text(text, position, color, text_size, rotation)
        self._text_items.clear()


def set_preview_state(preview_state):
    state = dict(preview_state)
    from .snap_targets import snap_target_status

    state.setdefault("snap_target_status", snap_target_status(bpy.context))
    state.setdefault("tool_label", {
        "ANGLE": "ANGLE",
        "AREA": "AREA",
    }.get(state.get("annotation_kind"), "DIM"))
    set_state("DIMENSION", state)


def clear_preview_state():
    clear_state("DIMENSION")


def set_measure_state(state, context=None):
    display_state = dict(state)
    from .snap_targets import snap_target_status

    context = context or bpy.context
    display_state.setdefault("snap_target_status", snap_target_status(context))
    display_state.setdefault("tool_label", "MEASURE")
    set_state("MEASURE", display_state, context)


def clear_measure_state(context=None, key=None):
    clear_state("MEASURE", context, key)


def set_guide_preview_state(state):
    display_state = dict(state)
    from .snap_targets import snap_target_status

    display_state.setdefault("snap_target_status", snap_target_status(bpy.context))
    display_state.setdefault("tool_label", "GUIDE")
    set_state("GUIDE", display_state)


def clear_guide_preview_state():
    clear_state("GUIDE")


def register_draw_handler():
    global _pixel_draw_handler, _world_draw_handler

    register_scene_sync()

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


def unregister_draw_handler():
    global _pixel_draw_handler, _world_draw_handler

    unregister_scene_sync()
    clear_all_states()
    invalidate_dimension_geometry_cache()
    _text_metrics_cache.clear()

    if _pixel_draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_pixel_draw_handler, "WINDOW")
        _pixel_draw_handler = None

    if _world_draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_world_draw_handler, "WINDOW")
        _world_draw_handler = None


def build_dimension_geometry_for_object(context, dimension_object):
    global _geometry_build_count
    _geometry_build_count += 1
    props = dimension_object.dimension_props

    if getattr(props, "annotation_kind", "LINEAR") == "AREA":
        return _build_area_geometry(context, props)
    if getattr(props, "annotation_kind", "LINEAR") == "ANGLE":
        return _build_angle_geometry(context, props)
    if getattr(props, "annotation_kind", "LINEAR") == "DIMENSION_SET":
        return _build_dimension_set_geometry(context, props)
    if getattr(props, "annotation_kind", "LINEAR") == "CIRCLE":
        return _build_circle_geometry(context, props)
    if getattr(props, "annotation_kind", "LINEAR") in {"COORDINATE", "ELEVATION"}:
        return _build_coordinate_elevation_geometry(context, props)

    start_world = resolve_anchor(props.start)
    end_world = resolve_anchor(props.end)
    if start_world is None or end_world is None:
        return None

    world_geometry = get_dimension_world_geometry(
        props.dimension_type,
        start_world,
        end_world,
        Vector(props.offset_plane_normal),
        props.offset_distance,
        props.offset_angle,
        props.measurement_mode,
    )
    if world_geometry is None:
        return None

    placement_offset = Vector(props.presentation_offset)
    if placement_offset.length_squared > 1e-12:
        world_geometry = dict(world_geometry)
        for key in ("line_start_world", "line_end_world", "line_mid_world"):
            world_geometry[key] = world_geometry[key] + placement_offset

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
    screen_geometry["measurement_mode"] = props.measurement_mode
    screen_geometry["measurement_state"] = (
        "NEEDS_REPAIR" if dimension_source_is_missing(props) else props.measurement_state
    )
    scene_settings = getattr(context.scene, "dimensions_settings", None)
    screen_geometry["text_placement"] = (
        scene_settings.text_placement if scene_settings is not None else "INLINE"
    )
    screen_geometry["custom_text"] = props.custom_text.strip()
    screen_geometry["custom_text_position"] = props.custom_text_position
    return _annotation_style(context, props, screen_geometry)


def _build_dimension_set_geometry(context, props):
    members = []
    invalid_member_count = 0
    presentation_offset = Vector(props.presentation_offset)
    for item in dimension_set_world_geometry(props):
        world_geometry = dict(item)
        if not item.get("geometry_valid", True):
            invalid_member_count += 1
            fallback_direction = item["end_world"] - item["start_world"]
            if fallback_direction.length < 1e-6:
                continue
            offset = Vector(item["offset_direction_world"]) * float(item["offset_distance"])
            world_geometry.update({
                "line_start_world": item["start_world"] + offset,
                "line_end_world": item["end_world"] + offset,
                "line_mid_world": (item["start_world"] + item["end_world"]) * 0.5 + offset,
                "measure_direction_world": fallback_direction.normalized(),
            })
        if presentation_offset.length_squared > 1e-12:
            for key in ("line_start_world", "line_end_world", "line_mid_world"):
                world_geometry[key] = world_geometry[key] + presentation_offset
        screen = _project_dimension_geometry(
            context, item["start_world"], item["end_world"], world_geometry,
        )
        if screen is None:
            continue
        screen.update({
            "value": item["value"],
            "dimension_type": props.dimension_type,
            "measurement_mode": "TRUE",
            "measurement_state": "NEEDS_REPAIR" if not item.get("geometry_valid", True) else item["state"],
            "text_placement": "INLINE",
            "custom_text": "",
            "custom_text_position": "ABOVE",
            "set_member_index": item["index"],
            "invalid_set_geometry": not item.get("geometry_valid", True),
        })
        styled = _annotation_style(context, props, screen)
        if props.set_kind == "BASELINE" and members:
            first = members[0]
            perpendicular = Vector((-styled["line_direction_screen"].y, styled["line_direction_screen"].x))
            source_side = styled["line_mid_screen"] - (
                styled["anchor_start_screen"] + styled["anchor_end_screen"]
            ) * 0.5
            if perpendicular.dot(source_side) < 0.0:
                perpendicular.negate()
            required_pitch = styled["text_size"] * 1.5
            actual_distance = (styled["line_mid_screen"] - first["line_mid_screen"]).dot(perpendicular)
            desired_distance = max(actual_distance, item["index"] * required_pitch)
            desired_mid = first["line_mid_screen"] + perpendicular * desired_distance
            delta = desired_mid - styled["line_mid_screen"]
            for key in ("line_start_screen", "line_end_screen", "line_mid_screen"):
                styled[key] = styled[key] + delta
        label = _format_linear_dimension_label(context, styled, styled["precision"])
        label_width = _text_dimensions(label, styled["text_size"])[0]
        if (styled["line_end_screen"] - styled["line_start_screen"]).length < label_width + styled["arrow_size"] * 2.0:
            styled["text_placement"] = "OUTSIDE" if item["index"] % 2 == 0 else "OUTSIDE_START"
        members.append(styled)
    if not members:
        return None
    return {
        "annotation_kind": "DIMENSION_SET",
        "set_kind": props.set_kind,
        "members": tuple(members),
        "measurement_state": "NEEDS_REPAIR" if invalid_member_count else dimension_set_state(props),
        "invalid_member_count": invalid_member_count,
        "color": members[0]["color"],
        "selected_color": members[0]["selected_color"],
        "precision": members[0]["precision"],
    }


def _build_circle_geometry(context, props):
    fit = circle_geometry(props)
    if fit is None:
        return None
    direction = fit["axis_u"] * cos(props.circle_leader_angle) + fit["axis_v"] * sin(props.circle_leader_angle)
    direction.normalize()
    radius = fit["radius"]
    edge = fit["center"] + direction * radius
    distance = props.circle_label_distance if props.circle_label_distance > 1e-6 else radius * 1.35
    label_world = fit["center"] + direction * distance + Vector(props.presentation_offset)
    points_world = []
    if props.circle_kind == "DIAMETER":
        points_world = [fit["center"] - direction * radius, fit["center"] + direction * radius]
    elif props.circle_kind == "ARC_LENGTH":
        steps = max(12, int(48 * fit["sweep"] / tau))
        for index in range(steps + 1):
            angle = fit["sweep"] * index / steps
            radial = fit["start_direction"].copy()
            radial.rotate(Quaternion(fit["normal"], angle))
            points_world.append(fit["center"] + radial * radius)
    else:
        points_world = [fit["center"], edge]
    points = [_project_world_to_screen(context, point) for point in points_world]
    edge_screen = _project_world_to_screen(context, edge)
    label_screen = _project_world_to_screen(context, label_world)
    if label_screen is None or edge_screen is None or any(point is None for point in points):
        return None
    return _annotation_style(context, props, {
        "annotation_kind": "CIRCLE", "circle_kind": props.circle_kind,
        "points": points, "edge_screen": edge_screen, "label_position": label_screen,
        "line_mid_screen": label_screen, "value": circle_value(props, fit),
        "measurement_state": fit["state"], "fit_error": fit["fit_error"],
        "fit_warning": fit["fit_warning"],
    })


def _build_coordinate_elevation_geometry(context, props):
    kind = props.annotation_kind
    result = coordinate_values(props) if kind == "COORDINATE" else elevation_value(props)
    if result is None:
        return None
    point = result["point"]
    label_world = resolve_anchor(props.end) + Vector(props.presentation_offset)
    if kind == "COORDINATE" and props.coordinate_alignment != "FREE":
        origin = result["origin"]
        x_axis, y_axis, _z_axis = result["axes"]
        delta = point - origin
        if props.coordinate_alignment == "ROW":
            label_world = origin + x_axis * delta.dot(x_axis) + y_axis * props.coordinate_alignment_offset
        else:
            label_world = origin + x_axis * props.coordinate_alignment_offset + y_axis * delta.dot(y_axis)
        label_world += Vector(props.presentation_offset)
    start_screen = _project_world_to_screen(context, point)
    end_screen = _project_world_to_screen(context, label_world)
    if start_screen is None or end_screen is None:
        return None
    geometry = {
        "annotation_kind": kind, "leader_start_screen": start_screen,
        "leader_end_screen": end_screen, "label_position": end_screen,
        "line_mid_screen": (start_screen + end_screen) * 0.5,
        "measurement_state": result["state"],
    }
    geometry.update({"values": result["values"]} if kind == "COORDINATE" else {"value": result["value"]})
    return _annotation_style(context, props, geometry)


def get_cached_dimension_geometry(context, dimension_object):
    """Build screen geometry once per unchanged annotation and viewport view."""
    region = getattr(context, "region", None)
    region_data = getattr(context, "region_data", None)
    if region is None or region_data is None or not hasattr(region_data, "perspective_matrix"):
        return build_dimension_geometry_for_object(context, dimension_object)
    viewport_key = (
        getattr(getattr(context, "window", None), "as_pointer", lambda: 0)(),
        getattr(getattr(context, "area", None), "as_pointer", lambda: 0)(),
        getattr(region, "as_pointer", lambda: id(region))(),
    )
    view = tuple(round(value, 7) for row in region_data.perspective_matrix for value in row)
    cached = _dimension_geometry_cache.get(viewport_key)
    if cached is None or cached["view"] != view:
        cached = {"view": view, "entries": {}}
        _dimension_geometry_cache[viewport_key] = cached
    entries = cached["entries"]
    key = dimension_object.as_pointer()
    if key not in entries:
        entries[key] = build_dimension_geometry_for_object(context, dimension_object)
    return entries[key]


def _annotation_style(context, props, geometry):
    settings = getattr(context.scene, "dimensions_settings", None)
    style = resolve_dimension_style(settings, props) if settings is not None else props
    geometry["precision"] = getattr(style, "precision", DEFAULT_PRECISION)
    geometry["line_width"] = style.line_width
    geometry["text_size"] = style.text_size
    geometry["arrow_size"] = style.arrow_size
    geometry["arrow_end_style"] = style.arrow_end_style
    geometry["start_end_style"] = getattr(style, "start_end_style", "OPEN")
    geometry["end_end_style"] = getattr(style, "end_end_style", "OPEN")
    if getattr(style, "arrow_end_style", "ARROW") == "ARCHITECTURAL_TICK":
        if geometry["start_end_style"] == "OPEN":
            geometry["start_end_style"] = "ARCHITECTURAL_TICK"
        if geometry["end_end_style"] == "OPEN":
            geometry["end_end_style"] = "ARCHITECTURAL_TICK"
    geometry["extension_gap"] = getattr(style, "extension_gap", 0.0)
    geometry["extension_overshoot"] = getattr(style, "extension_overshoot", 0.0)
    geometry["color"] = tuple(style.color)
    geometry["selected_color"] = tuple(style.selected_color)
    geometry["unit_style"] = getattr(style, "unit_style", "AUTO")
    geometry["secondary_unit_style"] = getattr(style, "secondary_unit_style", "NONE")
    geometry["secondary_precision"] = getattr(style, "secondary_precision", 2)
    geometry["dual_unit_arrangement"] = getattr(style, "dual_unit_arrangement", "BRACKETS")
    geometry["label_orientation"] = getattr(style, "label_orientation", "HORIZONTAL")
    geometry["label_line_mode"] = getattr(style, "label_line_mode", "BROKEN")
    geometry["custom_text"] = props.custom_text.strip()
    geometry["value_prefix"] = style.value_prefix
    geometry["value_suffix"] = style.value_suffix
    geometry["tolerance_mode"] = style.tolerance_mode
    geometry["tolerance_upper"] = style.tolerance_upper
    geometry["tolerance_lower"] = style.tolerance_lower
    for name in (
        "coordinate_components", "coordinate_show_plus", "coordinate_show_negative",
        "elevation_precision", "elevation_show_plus", "elevation_prefix", "elevation_suffix",
    ):
        geometry[name] = getattr(props, name, None)
    return geometry


def _build_area_geometry(context, props):
    result = evaluate_area_binding(props) if props.measurement_state != "CAPTURED" else None
    if result is not None:
        start_world = result["center"]
        value = result["area"]
        face_count = result["face_count"]
        state = result.get("state", "LIVE")
        evaluation_mode = result.get("evaluation_mode", "BASE")
    else:
        start_world = resolve_anchor(props.start)
        value = props.area_value
        face_count = props.area_face_count
        state = props.measurement_state
        if state != "CAPTURED" and len(props.area_faces) > 0:
            state = "NEEDS_REPAIR"
        evaluation_mode = "CAPTURED" if state == "CAPTURED" else "UNAVAILABLE"
    fallback_end = resolve_anchor(props.end)
    end_world = area_label_world(props, start_world, fallback_end) + Vector(props.presentation_offset)
    start_screen = _project_world_to_screen(context, start_world)
    end_screen = _project_world_to_screen(context, end_world)
    if start_screen is None or end_screen is None:
        return None
    return _annotation_style(context, props, {
        "annotation_kind": "AREA",
        "leader_start_screen": start_screen,
        "leader_end_screen": end_screen,
        "line_mid_screen": (start_screen + end_screen) * 0.5,
        "value": value,
        "measurement_state": state,
        "area_evaluation_mode": evaluation_mode,
        "face_count": face_count,
    })


def _build_angle_geometry(context, props):
    source = resolve_angle_source(props)
    if source is None:
        return None
    placement_offset = Vector(props.presentation_offset)
    start_world = source["start"] + placement_offset
    center_world = source["center"] + placement_offset
    end_world = source["end"] + placement_offset
    start_screen = _project_world_to_screen(context, start_world)
    center_screen = _project_world_to_screen(context, center_world)
    end_screen = _project_world_to_screen(context, end_world)
    if start_screen is None or center_screen is None or end_screen is None:
        return None
    world_geometry = get_angle_world_geometry(
        start_world,
        center_world,
        end_world,
        props.angle_radius,
        source["arc_mode"],
    )
    if world_geometry is None:
        return _annotation_style(context, props, {
            "annotation_kind": "ANGLE",
            "center_screen": center_screen,
            "start_screen": start_screen,
            "end_screen": end_screen,
            "arc_points": [],
            "line_mid_screen": center_screen + Vector((18.0, 18.0)),
            "label_position": center_screen + Vector((18.0, 18.0)),
            "value": 0.0,
            "invalid": True,
            "measurement_state": "NEEDS_REPAIR",
            "angle_mode": props.angle_mode,
        })
    label_position = _project_world_to_screen(context, world_geometry["label_world"])
    arc_points = [_project_world_to_screen(context, point) for point in world_geometry["arc_points_world"]]
    if start_screen is None or center_screen is None or end_screen is None or label_position is None or any(point is None for point in arc_points):
        return None
    state = "NEEDS_REPAIR" if dimension_source_is_missing(props) else props.measurement_state
    return _annotation_style(context, props, {
        "annotation_kind": "ANGLE",
        "center_screen": center_screen,
        "start_screen": start_screen,
        "end_screen": end_screen,
        "arc_points": arc_points,
        "line_mid_screen": label_position,
        "label_position": label_position,
        "value": world_geometry["value"],
        "measurement_state": state,
        "angle_mode": props.angle_mode,
        "connected": source.get("connected", True),
    })


def draw_dimensions():
    context = bpy.context

    if context.area is None or context.area.type != "VIEW_3D":
        return

    if context.region is None or context.region.type != "WINDOW":
        return

    if context.region_data is None:
        return

    preview_state = get_state("DIMENSION", context)
    guide_preview_state = get_state("GUIDE", context)
    measure_state = get_state("MEASURE", context)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    gpu.state.line_width_set(DEFAULT_LINE_WIDTH)

    try:
        batcher = SegmentBatcher(shader)
        collection = get_scene_collection(context.scene, "DIMENSIONS")
        for obj in () if collection is None else collection.all_objects:
            if not is_dimension_object(obj):
                continue

            props = obj.dimension_props
            if not props.visible or not _object_visible_in_viewport(context, obj):
                continue

            geometry = get_cached_dimension_geometry(context, obj)
            if geometry is None:
                continue

            color = geometry["selected_color"] if obj.select_get() else geometry["color"]
            _collect_dimension_geometry(context, batcher, geometry, color, geometry["precision"])
        batcher.flush()

        if preview_state is None or preview_state.get("state") != "HANDLE_DRAG":
            _draw_selected_annotation_handles(context, shader)

        if preview_state is not None:
            _draw_preview(context, shader, preview_state)

        if guide_preview_state is not None:
            _draw_guide_preview_marker(shader, guide_preview_state)

        if measure_state is not None:
            _draw_transient_measure(context, shader, measure_state)

        for interaction_state in (preview_state, guide_preview_state, measure_state):
            if interaction_state is not None:
                _draw_interaction_status(interaction_state)

        _draw_persistent_guide_points(context, shader)
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

    preview_state = get_state("DIMENSION", context)
    guide_preview_state = get_state("GUIDE", context)
    measure_state = get_state("MEASURE", context)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")

    try:
        _draw_construction_guides(context, shader)
        _draw_tool_snap_highlights(context, shader)
        for interaction_state in (preview_state, guide_preview_state, measure_state):
            if interaction_state is not None:
                _draw_axis_gesture(context, shader, interaction_state)
        if guide_preview_state is not None:
            _draw_guide_preview_world(context, shader, guide_preview_state)
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
    batcher = SegmentBatcher(shader)
    collection = get_scene_collection(context.scene, "GUIDES")
    for obj in () if collection is None else collection.all_objects:
        if not guide_is_visible(context, obj):
            continue
        if getattr(obj.guide_props, "kind", "GUIDE") == "PLANE":
            from .guide_planes import active_plane_frame, resolve_guide_plane

            frame = resolve_guide_plane(obj)
            if frame is None:
                origin = Vector(obj.guide_props.last_resolved_origin)
                normal = Vector(obj.guide_props.last_resolved_direction)
                frame = _fallback_plane_frame(origin, normal)
                color = (1.0, 0.18, 0.12, 0.9)
                width = max(1.0, settings.guide_line_width)
            else:
                active = (
                    settings.active_plane_mode == "GUIDE"
                    and settings.active_plane_object == obj
                    and active_plane_frame(context.scene) is not None
                )
                color = (1.0, 0.72, 0.12, 0.95) if active else settings.guide_color
                width = max(3.0, settings.guide_line_width * 2.0) if active else settings.guide_line_width
            if frame is not None:
                batcher.add_segments(
                    _plane_grid_segments(frame, obj.guide_props.plane_extent), color, width,
                )
            continue
        if getattr(obj.guide_props, "derivation_mode", "NONE") == "SPACING":
            lines, segments = _spaced_guide_draw_segments(obj)
            batcher.add_segments(segments, settings.guide_color, settings.guide_line_width)
            if lines:
                continue
        segment = guide_segment_world(obj)
        if segment is None:
            if getattr(obj.guide_props, "derived", False) and obj.guide_props.derived_state != "LIVE":
                origin = Vector(obj.guide_props.last_resolved_origin)
                direction = Vector(obj.guide_props.last_resolved_direction)
                if direction.length > 1e-6:
                    direction.normalize()
                    batcher.add_segments(
                        _dashed_world_line(origin, direction),
                        (1.0, 0.18, 0.12, 0.9),
                        max(1.0, settings.guide_line_width),
                    )
            continue
        batcher.add_segments(list(segment), settings.guide_color, settings.guide_line_width)
    if settings.active_plane_mode not in {"NONE", "GUIDE"}:
        from .guide_planes import active_plane_frame

        frame = active_plane_frame(context.scene)
        if frame is not None:
            extent = max(float(getattr(context.region_data, "view_distance", 5.0)) * 0.4, 1.0)
            batcher.add_segments(
                _plane_grid_segments(frame, extent),
                (1.0, 0.72, 0.12, 0.95),
                max(3.0, settings.guide_line_width * 2.0),
            )
    batcher.flush()


def _spaced_guide_draw_segments(guide, extent=10000.0):
    """Resolve one spaced set into the single line batch used by the draw path."""
    from .derived_guides import spaced_guide_lines

    lines = spaced_guide_lines(guide)
    segments = []
    for origin, direction in lines:
        segments.extend((origin - direction * extent, origin + direction * extent))
    return lines, segments


def _fallback_plane_frame(origin, normal):
    from .guide_planes import plane_frame

    return plane_frame(origin, normal)


def _plane_grid_segments(frame, extent, divisions=10):
    """Return a bounded grid; extent is presentation and never changes definition."""
    origin, axis_u, axis_v, _normal = frame
    extent = max(float(extent), 0.01)
    points = []
    for index in range(-divisions, divisions + 1):
        offset = extent * index / divisions
        points.extend((
            origin + axis_u * -extent + axis_v * offset,
            origin + axis_u * extent + axis_v * offset,
            origin + axis_v * -extent + axis_u * offset,
            origin + axis_v * extent + axis_u * offset,
        ))
    return points


def _dashed_world_line(origin, direction, extent=10000.0, dash=0.25, count=80):
    """Bounded dashed fallback makes a broken derived guide visibly non-live."""
    start = origin - direction * min(extent, dash * count)
    return [
        point
        for index in range(count)
        for point in (
            start + direction * (index * dash * 2.0),
            start + direction * (index * dash * 2.0 + dash),
        )
    ]


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
    from .guide_planes import active_plane_frame

    frame = active_plane_frame(context.scene)
    axis_directions = None if frame is None else {"X": frame[1], "Y": frame[2], "Z": frame[3]}
    _draw_guide_preview_segment(
        shader, start, end, state.get("axis", "ALIGNED"), color, width, axis_directions,
    )


def _draw_guide_preview_segment(shader, start, end, axis, color, line_width, axis_directions=None):
    axis_directions = axis_directions or {
        "X": Vector((1.0, 0.0, 0.0)),
        "Y": Vector((0.0, 1.0, 0.0)),
        "Z": Vector((0.0, 0.0, 1.0)),
    }
    if axis == "X":
        direction = axis_directions["X"]
    elif axis == "Y":
        direction = axis_directions["Y"]
    elif axis == "Z":
        direction = axis_directions["Z"]
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
    from .guide_planes import active_plane_frame

    frame = active_plane_frame(context.scene)
    directions = (
        (Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0)), Vector((0.0, 0.0, 1.0)))
        if frame is None else (frame[1], frame[2], frame[3])
    )
    axes = {
        "X": (directions[0], (1.0, 0.18, 0.12, 0.95)),
        "Y": (directions[1], (0.22, 1.0, 0.18, 0.95)),
        "Z": (directions[2], (0.20, 0.48, 1.0, 0.95)),
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
    for state in (
        get_state("DIMENSION", context),
        get_state("GUIDE", context),
        get_state("MEASURE", context),
    ):
        if state is None:
            continue
        for snap in state.get("locked_snaps", ()):
            _draw_snap_highlight(context, shader, snap, locked_color, show_object_context=False)
        hover_snap = state.get("hover_snap")
        if hover_snap is not None:
            _draw_snap_highlight(context, shader, hover_snap, hover_color, show_object_context=True)


def _draw_snap_highlight(context, shader, snap, color, show_object_context=False):
    if snap.get("type") == "INFERENCE":
        _draw_inference_indicator(shader, snap, color)
        return
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


def _draw_inference_indicator(shader, snap, color):
    """Draw compact, type-specific inference glyphs in the established snap colors."""
    center = Vector(snap["screen_co"])
    kind = snap.get("inference_type", "")
    size = 8.0
    if kind == "INTERSECTION":
        points = [center + Vector((-size, -size)), center + Vector((size, size)),
                  center + Vector((-size, size)), center + Vector((size, -size))]
    elif kind == "PERPENDICULAR":
        points = [center + Vector((-size, 0)), center,
                  center, center + Vector((0, size)),
                  center + Vector((-size * 0.45, size)), center + Vector((-size * 0.45, size * 0.55))]
    elif kind == "ACTIVE_PLANE":
        points = [center + Vector((0, size)), center + Vector((size, 0)),
                  center + Vector((size, 0)), center + Vector((0, -size)),
                  center + Vector((0, -size)), center + Vector((-size, 0)),
                  center + Vector((-size, 0)), center + Vector((0, size))]
    elif kind == "PARALLEL":
        points = [center + Vector((-size, -3)), center + Vector((size, -3)),
                  center + Vector((-size, 3)), center + Vector((size, 3))]
    elif kind == "LOCAL_AXIS":
        points = [center + Vector((-size, 0)), center + Vector((size, 0)),
                  center + Vector((size - 4, -3)), center + Vector((size, 0)),
                  center + Vector((size - 4, 3)), center + Vector((size, 0))]
    else:  # Extension: dashed-looking collinear segments.
        points = [center + Vector((-size, 0)), center + Vector((-2, 0)),
                  center + Vector((2, 0)), center + Vector((size, 0))]
    gpu.state.line_width_set(2.25)
    batch = batch_for_shader(shader, "LINES", {"pos": points})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    _draw_marker(shader, center, color)


def _snap_highlight_geometry(context, snap, include_object_context=True):
    """Resolve a snap target into world geometry for viewport highlighting."""
    if snap is None:
        return None
    snap_type = snap.get("type", "WORLD")
    construction_object = snap.get("guide_object")
    if construction_object is not None:
        if snap_type == "GUIDE":
            reference_line = snap.get("reference_line")
            segment = (
                (reference_line[0] - reference_line[1] * 10000.0, reference_line[0] + reference_line[1] * 10000.0)
                if reference_line is not None else guide_segment_world(construction_object)
            )
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
    parts = [state.get("tool_label", "DIM")]
    axis = state.get("axis")
    if axis is not None:
        parts.append("Auto" if axis == "ALIGNED" else (f"Local {axis[-1]}" if axis.startswith("LOCAL_") else axis))
    distance_text = state.get("distance_text", "").strip()
    if distance_text:
        parts.append(distance_text if state.get("distance_input_valid", True) else f"! {distance_text}")
    snap_status = state.get("snap_target_status", "")
    if snap_status:
        parts.append(snap_status)
    inference = state.get("inference_status", "")
    if inference:
        parts.append(inference)
    interaction_warning = state.get("interaction_warning", "")
    if interaction_warning:
        parts.append(interaction_warning)
    color = (
        (1.0, 0.22, 0.12, 1.0)
        if not state.get("distance_input_valid", True) or interaction_warning
        else (0.72, 0.78, 0.88, 0.78)
    )
    _draw_text_left(" · ".join(parts), Vector((24.0, 44.0)), color, 12)


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
    lines = state.get("measurement_lines")
    if label:
        lines = (label,)
    elif not lines:
        lines = (format_length(context, (end - start).length, precision),)
    for index, line in enumerate(lines):
        _draw_text(line, label_position + Vector((0.0, -index * (text_size + 3.0))), color, text_size)


def _draw_persistent_measurements(context):
    settings = getattr(context.scene, "dimensions_settings", None)
    if settings is None or not settings.show_construction_guides:
        return
    precision = settings.precision
    text_size = settings.dimension_text_size
    color = tuple(settings.guide_color)
    collection = get_scene_collection(context.scene, "GUIDES")
    for obj in () if collection is None else collection.all_objects:
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


def guide_point_marker_segments(position, size=6.0):
    """Return a constant-pixel square-and-cross marker for a guide point."""
    position = Vector(position)
    corners = (
        position + Vector((-size, -size)), position + Vector((size, -size)),
        position + Vector((size, size)), position + Vector((-size, size)),
    )
    points = []
    for start, end in zip(corners, corners[1:] + corners[:1]):
        points.extend((start, end))
    arm = size * 0.55
    points.extend((
        position + Vector((-arm, 0.0)), position + Vector((arm, 0.0)),
        position + Vector((0.0, -arm)), position + Vector((0.0, arm)),
    ))
    return points


def _draw_persistent_guide_points(context, shader):
    settings = getattr(context.scene, "dimensions_settings", None)
    if settings is None or not settings.show_construction_guides:
        return
    collection = get_scene_collection(context.scene, "GUIDES")
    batcher = SegmentBatcher(shader)
    for obj in () if collection is None else collection.all_objects:
        if (
            not guide_is_visible(context, obj)
            or getattr(obj.guide_props, "kind", "GUIDE") != "POINT"
        ):
            continue
        world_co = resolve_anchor(obj.guide_props.start)
        screen_co = None if world_co is None else _project_world_to_screen(context, world_co)
        if screen_co is None:
            continue
        color = (0.95, 0.25, 1.0, 1.0) if obj.select_get() else tuple(settings.guide_color)
        batcher.add_segments(guide_point_marker_segments(screen_co), color, max(1.0, settings.guide_line_width))
    batcher.flush()


def _collect_dimension_geometry(context, batcher, geometry, color, precision):
    if geometry.get("annotation_kind") in {"COORDINATE", "ELEVATION"}:
        start, end = geometry["leader_start_screen"], geometry["leader_end_screen"]
        segments = [start, end]
        if geometry["annotation_kind"] == "ELEVATION":
            size = geometry.get("arrow_size", DEFAULT_ARROW_SIZE)
            segments.extend((start + Vector((-size * 0.55, size * 0.45)), start, start + Vector((size * 0.55, size * 0.45)), start))
            segments.extend((end + Vector((-size, 0.0)), end + Vector((size, 0.0))))
            precision = geometry.get("elevation_precision")
            if precision is None:
                precision = 3
            label = f"{geometry.get('elevation_prefix') or ''}{signed_number(geometry['value'], precision, bool(geometry.get('elevation_show_plus')))}{geometry.get('elevation_suffix') or ''}"
        else:
            label = coordinate_label(geometry, geometry["values"], lambda value: format_length(context, value, precision, geometry.get("unit_style")))
        if geometry.get("measurement_state") == "NEEDS_REPAIR":
            label += " [Needs Repair]"
        batcher.add_segments(segments, color, geometry.get("line_width", DEFAULT_LINE_WIDTH))
        batcher.add_text(label, end + Vector((6.0, 2.0)), color, geometry.get("text_size", DEFAULT_TEXT_SIZE), align="LEFT")
        return
    if geometry.get("annotation_kind") == "CIRCLE":
        points = geometry["points"]
        segments = []
        for start, end in zip(points, points[1:]):
            segments.extend((start, end))
        if points and (points[-1] - geometry["label_position"]).length > 1.0:
            segments.extend((geometry["edge_screen"], geometry["label_position"]))
        batcher.add_segments(segments, color, geometry.get("line_width", DEFAULT_LINE_WIDTH))
        symbol = {"RADIUS": "R", "DIAMETER": "⌀", "ARC_LENGTH": "⌒"}[geometry["circle_kind"]]
        label = f"{geometry.get('value_prefix', '')}{symbol}{format_length(context, geometry['value'], precision, geometry.get('unit_style'))}{geometry.get('value_suffix', '')}"
        if geometry.get("tolerance_mode") == "SYMMETRIC" and geometry.get("tolerance_upper", 0.0) > 0.0:
            label += f" ±{format_length(context, geometry['tolerance_upper'], precision, geometry.get('unit_style'))}"
        elif geometry.get("tolerance_mode") == "DEVIATION":
            label += f" +{format_length(context, geometry.get('tolerance_upper', 0.0), precision, geometry.get('unit_style'))} / -{format_length(context, geometry.get('tolerance_lower', 0.0), precision, geometry.get('unit_style'))}"
        state = geometry.get("measurement_state", "LIVE")
        if state == "NEEDS_REPAIR":
            label += "  [Needs Repair]"
        elif state == "FALLBACK" and not geometry.get("fit_warning"):
            label += "  [Fallback — Confirm Source]"
        if geometry.get("fit_warning"):
            label += f"  [Fit {geometry['fit_error'] * 100.0:.2f}%]"
        batcher.add_text(label, geometry["label_position"], color, geometry.get("text_size", DEFAULT_TEXT_SIZE), align="LEFT")
        return
    if geometry.get("annotation_kind") == "DIMENSION_SET":
        for member in geometry["members"]:
            member_color = (1.0, 0.18, 0.12, 1.0) if member.get("invalid_set_geometry") else color
            _collect_dimension_geometry(context, batcher, member, member_color, member["precision"])
        return
    if geometry.get("annotation_kind") == "AREA":
        _collect_area_geometry(context, batcher, geometry, color, precision)
        return
    if geometry.get("annotation_kind") == "ANGLE":
        _collect_angle_geometry(batcher, geometry, color, precision)
        return
    label = _format_linear_dimension_label(context, geometry, precision)
    placement = geometry.get("text_placement", "INLINE")
    if placement == "INLINE":
        placement = "ABOVE" if geometry.get("label_line_mode") == "ABOVE" else "INLINE"
    text_layout = _build_text_layout(
        label,
        geometry,
        placement,
        geometry.get("custom_text", ""),
        geometry.get("custom_text_position", "ABOVE"),
        geometry.get("text_size", DEFAULT_TEXT_SIZE),
        geometry.get("arrow_size", DEFAULT_ARROW_SIZE),
    )
    line_segments = []
    for anchor, line in (
        (geometry["anchor_start_screen"], geometry["line_start_screen"]),
        (geometry["anchor_end_screen"], geometry["line_end_screen"]),
    ):
        line_segments.extend(_extension_line_segment(
            anchor, line, geometry.get("extension_gap", 0.0),
            geometry.get("extension_overshoot", 0.0),
        ))
    line_segments.extend(text_layout["line_segments"])
    arrow_size = geometry.get("arrow_size", DEFAULT_ARROW_SIZE)
    line_segments.extend(
        _build_arrow_segments(
            geometry["line_start_screen"],
            geometry["line_direction_screen"],
            arrow_size,
            geometry.get("start_end_style", "OPEN"),
        )
    )
    line_segments.extend(
        _build_arrow_segments(
            geometry["line_end_screen"],
            -geometry["line_direction_screen"],
            arrow_size,
            geometry.get("end_end_style", "OPEN"),
        )
    )

    batcher.add_segments(line_segments, color, geometry.get("line_width", DEFAULT_LINE_WIDTH))

    text_size = geometry.get("text_size", DEFAULT_TEXT_SIZE)
    for text, position in text_layout["text_items"]:
        batcher.add_text(text, position, color, text_size, rotation=text_layout["text_rotation"])


def _extension_line_segment(anchor, line, gap, overshoot):
    direction = Vector(line) - Vector(anchor)
    if direction.length <= 1e-6:
        return []
    direction.normalize()
    return [Vector(anchor) + direction * min(float(gap), (Vector(line) - Vector(anchor)).length), Vector(line) + direction * float(overshoot)]


def _collect_area_geometry(context, batcher, geometry, color, precision):
    start = geometry["leader_start_screen"]
    end = geometry["leader_end_screen"]
    line_width = geometry.get("line_width", DEFAULT_LINE_WIDTH)
    batcher.add_segments([start, end], color, line_width)
    batcher.add_segments(_marker_segments(start), color, line_width)
    state = geometry.get("measurement_state", "CAPTURED")
    state_suffix = {
        "LIVE": "",
        "CAPTURED": "  [Captured]",
        "FALLBACK": (
            "  [Fallback — Modifier Faces Unresolved]"
            if geometry.get("area_evaluation_mode") == "BASE_FALLBACK"
            else "  [Fallback — Confirm Source]"
        ),
        "NEEDS_REPAIR": "  [Needs Repair]",
    }.get(state, "")
    face_suffix = f"  ({geometry.get('face_count', 0)} faces)" if geometry.get("face_count", 0) > 1 else ""
    value = f"{geometry.get('value_prefix', '')}{format_area(context, geometry['value'], precision, geometry.get('unit_style'))}{geometry.get('value_suffix', '')}"
    label = f"Area {value}{face_suffix}{state_suffix}"
    custom_text = geometry.get("custom_text", "")
    if custom_text:
        label = f"{custom_text}  {label}"
    batcher.add_text(
        label,
        end + Vector((6.0, 2.0)),
        color,
        geometry.get("text_size", DEFAULT_TEXT_SIZE),
        align="LEFT",
    )


def _collect_angle_geometry(batcher, geometry, color, precision):
    center = geometry["center_screen"]
    points = [center, geometry["start_screen"], center, geometry["end_screen"]]
    arc = geometry["arc_points"]
    for start, end in zip(arc, arc[1:]):
        points.extend((start, end))
    batcher.add_segments(points, color, geometry.get("line_width", DEFAULT_LINE_WIDTH))
    label = (
        "Angle [Needs Repair]"
        if geometry.get("invalid")
        else f"{geometry.get('value_prefix', '')}{degrees(geometry['value']):.{max(0, min(precision, 3))}f}\u00b0{geometry.get('value_suffix', '')}"
    )
    if geometry.get("measurement_state") == "NEEDS_REPAIR" and not geometry.get("invalid"):
        label += "  [Needs Repair]"
    elif geometry.get("measurement_state") == "FALLBACK":
        label += "  [Fallback — Confirm Source]"
    custom_text = geometry.get("custom_text", "")
    if custom_text:
        label = f"{custom_text}  {label}"
    batcher.add_text(label, geometry["label_position"], color, geometry.get("text_size", DEFAULT_TEXT_SIZE))


def _draw_preview(context, shader, preview_state):
    for marker in preview_state.get("repair_markers", ()):
        screen = _project_world_to_screen(context, marker["world_co"])
        if screen is not None:
            color = (0.25, 1.0, 0.35, 1.0) if marker.get("candidate") else (1.0, 0.18, 0.12, 1.0)
            _draw_marker(shader, screen, color)
    hover_screen = preview_state.get("hover_screen")
    if hover_screen is not None:
        _draw_marker(shader, hover_screen, _snap_marker_color(preview_state))

    start_world = preview_state.get("start_world")
    end_world = preview_state.get("end_world")
    if preview_state.get("annotation_kind") == "CIRCLE":
        center_world = Vector(preview_state.get("center_world"))
        edge_world = Vector(preview_state.get("edge_world"))
        radius = preview_state.get("radius", 0.0)
        direction = (edge_world - center_world).normalized()
        circle_kind = preview_state.get("circle_kind", "RADIUS")
        if circle_kind == "DIAMETER":
            points_world = (center_world - direction * radius, center_world + direction * radius)
        elif circle_kind == "ARC_LENGTH":
            start_direction = Vector(preview_state.get("start_direction_world"))
            normal = Vector(preview_state.get("normal_world"))
            sweep = preview_state.get("sweep", tau)
            steps = max(12, int(48 * sweep / tau))
            arc_points = []
            for index in range(steps + 1):
                radial = start_direction.copy()
                radial.rotate(Quaternion(normal, sweep * index / steps))
                arc_points.append(center_world + radial * radius)
            points_world = tuple(arc_points)
        else:
            points_world = (center_world, edge_world)
        points_screen = tuple(_project_world_to_screen(context, point) for point in points_world)
        edge_screen = _project_world_to_screen(context, edge_world)
        label_screen = _project_world_to_screen(context, preview_state.get("label_world"))
        if edge_screen is None or label_screen is None or any(point is None for point in points_screen):
            return
        preview_batcher = SegmentBatcher(shader)
        segments = []
        for first, second in zip(points_screen, points_screen[1:]):
            segments.extend((first, second))
        segments.extend((edge_screen, label_screen))
        preview_batcher.add_segments(
            segments,
            (1.0, 0.48, 0.20, 1.0), DEFAULT_LINE_WIDTH,
        )
        symbol = {"RADIUS": "R", "DIAMETER": "⌀", "ARC_LENGTH": "⌒"}.get(circle_kind, "R")
        label = f"{symbol}{format_length(context, preview_state.get('value', 0.0), DEFAULT_PRECISION)}"
        preview_batcher.add_text(
            label, label_screen, (1.0, 0.48, 0.20, 1.0), DEFAULT_TEXT_SIZE, align="LEFT",
        )
        preview_batcher.flush()
        return
    if preview_state.get("annotation_kind") == "AREA":
        if start_world is None or end_world is None:
            return
        start_screen = _project_world_to_screen(context, start_world)
        end_screen = _project_world_to_screen(context, end_world)
        if start_screen is None or end_screen is None:
            return
        preview_batcher = SegmentBatcher(shader)
        _collect_area_geometry(context, preview_batcher, {
            "leader_start_screen": start_screen,
            "leader_end_screen": end_screen,
            "value": preview_state.get("area_value", 0.0),
            "face_count": preview_state.get("face_count", 0),
            "measurement_state": "LIVE",
            "line_width": DEFAULT_LINE_WIDTH,
            "text_size": DEFAULT_TEXT_SIZE,
        }, (1.0, 0.48, 0.20, 1.0), DEFAULT_PRECISION)
        preview_batcher.flush()
        return
    if preview_state.get("annotation_kind") == "ANGLE":
        center_world = preview_state.get("center_world")
        if start_world is None or center_world is None or end_world is None:
            return
        world_geometry = get_angle_world_geometry(
            Vector(start_world),
            Vector(center_world),
            Vector(end_world),
            preview_state.get("angle_radius", 0.25),
            preview_state.get("angle_mode", "MINOR"),
        )
        if world_geometry is None:
            return
        geometry = {
            "center_screen": _project_world_to_screen(context, center_world),
            "start_screen": _project_world_to_screen(context, start_world),
            "end_screen": _project_world_to_screen(context, end_world),
            "arc_points": [_project_world_to_screen(context, point) for point in world_geometry["arc_points_world"]],
            "label_position": _project_world_to_screen(context, world_geometry["label_world"]),
            "value": world_geometry["value"],
            "line_width": DEFAULT_LINE_WIDTH,
            "text_size": DEFAULT_TEXT_SIZE,
        }
        if any(value is None for value in (geometry["center_screen"], geometry["start_screen"], geometry["end_screen"], geometry["label_position"])) or any(point is None for point in geometry["arc_points"]):
            return
        preview_batcher = SegmentBatcher(shader)
        _collect_angle_geometry(preview_batcher, geometry, (1.0, 0.48, 0.20, 1.0), DEFAULT_PRECISION)
        preview_batcher.flush()
        return
    if start_world is None or end_world is None:
        return

    plane_normal = preview_state.get("offset_plane_normal")
    offset_distance = preview_state.get("offset_distance", 0.0)
    offset_angle = preview_state.get("offset_angle", 0.0)
    dimension_type = preview_state.get("dimension_type", "ALIGNED")
    measurement_mode = preview_state.get("measurement_mode", "TRUE")

    if plane_normal is None:
        plane_normal = sanitize_plane_normal(
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
        measurement_mode,
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


def find_dimension_hit(context, mouse_x, mouse_y, threshold=None):
    if threshold is None:
        threshold = get_preferences(context).selection_pixel_threshold
    mouse = Vector((mouse_x, mouse_y))
    best = None

    collection = get_scene_collection(context.scene, "DIMENSIONS")
    for obj in () if collection is None else collection.all_objects:
        if not is_dimension_object(obj):
            continue

        props = obj.dimension_props
        if not props.visible or not _object_visible_in_viewport(context, obj):
            continue

        geometry = get_cached_dimension_geometry(context, obj)
        if geometry is None:
            continue

        distance = _geometry_hit_distance(context, geometry, geometry["precision"], mouse)
        if distance is None or distance > threshold:
            continue

        if best is None or distance < best[0]:
            best = (distance, obj)

    return None if best is None else best[1]


def selected_annotation_handles(context):
    """Return constant-pixel handle locations for the active selected annotation."""
    obj = getattr(context.view_layer.objects, "active", None)
    if (
        not is_dimension_object(obj)
        or not obj.select_get()
        or is_read_only_dimensions_object(obj)
        or not obj.dimension_props.visible
        or not _object_visible_in_viewport(context, obj)
    ):
        return ()
    geometry = get_cached_dimension_geometry(context, obj)
    if geometry is None:
        return ()
    kind = obj.dimension_props.annotation_kind
    if kind == "ANGLE":
        points = geometry.get("arc_points", ())
        if not points:
            return ()
        return ({"object": obj, "kind": "ANGLE_RADIUS", "screen_co": Vector(points[len(points) // 2])},)
    if kind == "AREA":
        if evaluate_area_binding(obj.dimension_props) is None:
            return ()
        position = geometry.get("leader_end_screen")
        return () if position is None else (
            {"object": obj, "kind": "AREA_LABEL", "screen_co": Vector(position)},
        )
    if kind == "CIRCLE":
        position = geometry.get("label_position")
        return () if position is None else (
            {"object": obj, "kind": "CIRCLE_LABEL", "screen_co": Vector(position)},
        )
    position = geometry.get("line_mid_screen")
    return () if position is None else (
        {"object": obj, "kind": "LINEAR_OFFSET", "screen_co": Vector(position)},
    )


def find_annotation_handle_hit(context, mouse_x, mouse_y, threshold=11.0):
    mouse = Vector((mouse_x, mouse_y))
    best = None
    for handle in selected_annotation_handles(context):
        distance = (mouse - handle["screen_co"]).length
        if distance <= threshold and (best is None or distance < best[0]):
            best = (distance, handle)
    return None if best is None else best[1]


def _draw_selected_annotation_handles(context, shader):
    for handle in selected_annotation_handles(context):
        points = _annotation_handle_segments(handle["kind"], handle["screen_co"])
        batch = batch_for_shader(shader, "LINES", {"pos": points})
        shader.bind()
        shader.uniform_float("color", (0.95, 0.25, 1.0, 1.0))
        batch.draw(shader)


def _annotation_handle_segments(kind, position, size=7.0):
    """Build screen-pixel handle linework independent of view/world scale."""
    position = Vector(position)
    if kind == "ANGLE_RADIUS":
        points = []
        ring = [
            position + Vector((cos(index * tau / 12.0) * size, sin(index * tau / 12.0) * size))
            for index in range(12)
        ]
        for start, end in zip(ring, ring[1:] + ring[:1]):
            points.extend((start, end))
        return points
    if kind in {"AREA_LABEL", "CIRCLE_LABEL"}:
        return [
            position + Vector((-size, -size)), position + Vector((size, -size)),
            position + Vector((size, -size)), position + Vector((size, size)),
            position + Vector((size, size)), position + Vector((-size, size)),
            position + Vector((-size, size)), position + Vector((-size, -size)),
        ]
    return [
        position + Vector((0.0, size)), position + Vector((size, 0.0)),
        position + Vector((size, 0.0)), position + Vector((0.0, -size)),
        position + Vector((0.0, -size)), position + Vector((-size, 0.0)),
        position + Vector((-size, 0.0)), position + Vector((0.0, size)),
    ]


def find_guide_hit(context, mouse_x, mouse_y, threshold=None):
    if threshold is None:
        threshold = get_preferences(context).selection_pixel_threshold
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


def _build_arrow_segments(point, direction, arrow_scale=DEFAULT_ARROW_SIZE, style="OPEN"):
    """Build screen-space endpoint presentation without changing dimension geometry."""
    if style == "ARCHITECTURAL_TICK":
        tick_direction = (direction + Vector((-direction.y, direction.x))).normalized()
        tick_half_length = arrow_scale * 0.5
        return [
            point - tick_direction * tick_half_length,
            point + tick_direction * tick_half_length,
        ]
    if style == "NONE":
        return []
    perpendicular = Vector((-direction.y, direction.x))
    left = point + (direction * arrow_scale) + (perpendicular * arrow_scale * 0.45)
    right = point + (direction * arrow_scale) - (perpendicular * arrow_scale * 0.45)
    open_segments = [
        point,
        left,
        point,
        right,
    ]
    if style == "FILLED":
        # Close and hatch the triangle so it reads as filled in the line overlay.
        return open_segments + [left, right, point + direction * arrow_scale * 0.5 - perpendicular * arrow_scale * 0.22, point + direction * arrow_scale * 0.5 + perpendicular * arrow_scale * 0.22]
    if style == "DOT":
        points = []
        radius = arrow_scale * 0.38
        ring = [point + Vector((cos(index * tau / 12.0), sin(index * tau / 12.0))) * radius for index in range(12)]
        for start, end in zip(ring, ring[1:] + ring[:1]):
            points.extend((start, end))
        points.extend((point - perpendicular * radius, point + perpendicular * radius, point - direction * radius, point + direction * radius))
        return points
    return open_segments


def _build_text_layout(
    value_text,
    geometry,
    placement,
    custom_text="",
    custom_text_position="ABOVE",
    text_size=DEFAULT_TEXT_SIZE,
    arrow_size=DEFAULT_ARROW_SIZE,
):
    line_start = geometry["line_start_screen"]
    line_end = geometry["line_end_screen"]
    line_mid = geometry["line_mid_screen"]
    line_direction = geometry["line_direction_screen"]
    cache_key = (
        value_text,
        placement,
        custom_text,
        custom_text_position,
        round(float(text_size), 3),
        round(float(arrow_size), 3),
        geometry.get("label_orientation", "HORIZONTAL"),
        _rounded_point(line_start),
        _rounded_point(line_end),
        _rounded_point(line_mid),
        _rounded_point(line_direction),
    )
    cached = _text_layout_cache.get(cache_key)
    if cached is not None:
        return cached

    text_lines = [value_text]
    if custom_text:
        if custom_text_position == "BELOW":
            text_lines.append(custom_text)
        else:
            text_lines.insert(0, custom_text)

    text_metrics = [(text, *_text_dimensions(text, text_size)) for text in text_lines]
    line_spacing = 3.0 if len(text_metrics) > 1 else 0.0
    block_width = max(width for _text, width, _height in text_metrics)
    block_height = (
        sum(height for _text, _width, height in text_metrics)
        + line_spacing * (len(text_metrics) - 1)
    )

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
    elif placement == "OUTSIDE_START":
        block_center = line_start - line_direction * (
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
            # Tight-space routing is deterministic: always use the end side.
            leader_end = block_center - line_direction * (text_half_extent_along_line + 3.0)
            line_segments = full_line + [line_end, leader_end]
        else:
            block_center = line_mid
            line_segments = [
                line_start,
                line_mid - line_direction * gap_half_width,
                line_mid + line_direction * gap_half_width,
                line_end,
            ]

    text_items = []
    current_offset = block_height * 0.5
    aligned = geometry.get("label_orientation", "HORIZONTAL") == "ALIGNED"
    stack_direction = Vector((-line_direction.y, line_direction.x)) if aligned else Vector((0.0, 1.0))
    if stack_direction.y < 0.0:
        stack_direction.negate()
    for text, _width, height in text_metrics:
        current_offset -= height * 0.5
        text_items.append((text, block_center + stack_direction * current_offset))
        current_offset -= height * 0.5 + line_spacing

    text_rotation = atan2(line_direction.y, line_direction.x) if aligned else 0.0
    if text_rotation > pi * 0.5:
        text_rotation -= pi
    elif text_rotation < -pi * 0.5:
        text_rotation += pi

    layout = {
        "line_segments": line_segments,
        "text_items": text_items,
        "text_position": block_center,
        "text_rotation": text_rotation,
    }
    # Keys include screen positions, so an orbit produces a fresh key per frame.
    # Cap the cache rather than letting a long drag grow it without bound.
    if len(_text_layout_cache) >= _MAX_TEXT_LAYOUT_ENTRIES:
        _text_layout_cache.clear()
    _text_layout_cache[cache_key] = layout
    return layout


def _rounded_point(point):
    return (round(float(point.x), 3), round(float(point.y), 3))


def _text_dimensions(text, text_size):
    """Measure a string once per font size. Font metrics do not depend on the view."""
    key = (text, round(float(text_size), 3))
    metrics = _text_metrics_cache.get(key)
    if metrics is None:
        font_id = 0
        blf.size(font_id, text_size)
        metrics = blf.dimensions(font_id, text)
        _text_metrics_cache[key] = metrics
    return metrics


def _marker_segments(position, size=DEFAULT_HOVER_MARKER_SIZE):
    return [
        Vector((position.x - size, position.y)),
        Vector((position.x + size, position.y)),
        Vector((position.x, position.y - size)),
        Vector((position.x, position.y + size)),
    ]


def _draw_marker(shader, position, color):
    marker_segments = _marker_segments(position)
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


def _draw_text(text, position, color, text_size=DEFAULT_TEXT_SIZE, rotation=0.0):
    font_id = 0
    blf.size(font_id, text_size)
    text_width, text_height = blf.dimensions(font_id, text)
    blf.color(font_id, *color)
    if rotation:
        blf.enable(font_id, blf.ROTATION)
        blf.rotation(font_id, rotation)
    try:
        if rotation:
            offset_x = cos(rotation) * text_width * 0.5 - sin(rotation) * text_height * 0.5
            offset_y = sin(rotation) * text_width * 0.5 + cos(rotation) * text_height * 0.5
        else:
            offset_x, offset_y = text_width * 0.5, text_height * 0.5
        blf.position(
            font_id,
            position.x - offset_x,
            position.y - offset_y,
            0,
        )
        blf.draw(font_id, text)
    finally:
        if rotation:
            blf.disable(font_id, blf.ROTATION)


def _draw_text_left(text, position, color, text_size=DEFAULT_TEXT_SIZE):
    font_id = 0
    blf.size(font_id, text_size)
    blf.color(font_id, *color)
    blf.position(font_id, position.x, position.y, 0)
    blf.draw(font_id, text)


def _draw_text_right(text, position, color, text_size=DEFAULT_TEXT_SIZE):
    font_id = 0
    blf.size(font_id, text_size)
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
    if geometry.get("annotation_kind") == "DIMENSION_SET":
        distances = tuple(
            distance for distance in (
            _geometry_hit_distance(context, member, member.get("precision", precision), mouse)
            for member in geometry.get("members", ())
            ) if distance is not None
        )
        return None if not distances else min(distances)
    if geometry.get("annotation_kind") in {"COORDINATE", "ELEVATION"}:
        return _point_to_segment_distance(mouse, geometry["leader_start_screen"], geometry["leader_end_screen"])
    if geometry.get("annotation_kind") == "AREA":
        label = f"Area {format_area(context, geometry['value'], precision, geometry.get('unit_style'))}"
        return min(
            _point_to_segment_distance(mouse, geometry["leader_start_screen"], geometry["leader_end_screen"]),
            _point_to_label_distance(label, geometry["leader_end_screen"] + Vector((6.0, 2.0)), mouse, geometry.get("text_size", DEFAULT_TEXT_SIZE)),
        )
    if geometry.get("annotation_kind") == "ANGLE":
        segments = [(geometry["center_screen"], geometry["start_screen"]), (geometry["center_screen"], geometry["end_screen"])]
        segments.extend(zip(geometry["arc_points"], geometry["arc_points"][1:]))
        label = (
            "Angle [Needs Repair]"
            if geometry.get("invalid")
            else f"{degrees(geometry['value']):.{max(0, min(precision, 3))}f}\u00b0"
        )
        return min(
            min(_point_to_segment_distance(mouse, start, end) for start, end in segments),
            _point_to_label_distance(label, geometry["label_position"], mouse, geometry.get("text_size", DEFAULT_TEXT_SIZE)),
        )
    label = _format_linear_dimension_label(context, geometry, precision)
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


def _format_linear_dimension_label(context, geometry, precision):
    value = format_dual_length(
        context, geometry["value"], precision, geometry.get("unit_style"),
        geometry.get("secondary_unit_style", "NONE"),
        geometry.get("secondary_precision", 2),
        geometry.get("dual_unit_arrangement", "BRACKETS"),
    )
    label = f"{geometry.get('value_prefix', '')}{value}{geometry.get('value_suffix', '')}"
    tolerance_mode = geometry.get("tolerance_mode", "NONE")
    upper = geometry.get("tolerance_upper", 0.0)
    lower = geometry.get("tolerance_lower", 0.0)
    if tolerance_mode == "SYMMETRIC" and upper > 0.0:
        label += f" \u00b1{format_length(context, upper, precision, geometry.get('unit_style'))}"
    elif tolerance_mode == "DEVIATION" and (upper > 0.0 or lower > 0.0):
        label += f" +{format_length(context, upper, precision, geometry.get('unit_style'))} / -{format_length(context, lower, precision, geometry.get('unit_style'))}"
    if geometry.get("measurement_state") == "NEEDS_REPAIR":
        label += "  [Needs Repair]"
    elif geometry.get("measurement_state") == "FALLBACK":
        label += "  [Fallback — Confirm Source]"
    return label


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
