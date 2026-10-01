"""Cached annotation-manager registry, filtering, values, and selection sync."""

from math import degrees
from types import SimpleNamespace

from mathutils import Vector

from .anchors import resolve_anchor
from .angle_binding import resolve_angle_source
from .area_binding import evaluate_area_binding
from .dimension_geometry import get_angle_world_geometry
from .properties import is_dimension_object, is_guide_object, resolve_dimension_style
from .units import format_area, format_length


_index_sync_active = False
_registry_rebuild_count = 0


def annotation_manager_objects(scene):
    return tuple(sorted(
        (obj for obj in scene.objects if is_dimension_object(obj) or is_guide_object(obj)),
        key=lambda obj: obj.name.casefold(),
    ))


def annotation_kind(obj):
    if is_dimension_object(obj):
        return getattr(obj.dimension_props, "annotation_kind", "LINEAR")
    if is_guide_object(obj):
        kind = getattr(obj.guide_props, "kind", "GUIDE")
        return {"MEASUREMENT": "MEASUREMENT", "POINT": "POINT", "PLANE": "PLANE"}.get(kind, "GUIDE")
    return "UNKNOWN"


def annotation_state(obj):
    if is_dimension_object(obj):
        return getattr(obj.dimension_props, "measurement_state", "LIVE")
    return "LIVE"


def annotation_property_visible(obj):
    if is_dimension_object(obj):
        return bool(obj.dimension_props.visible)
    if is_guide_object(obj):
        return bool(obj.guide_props.visible)
    return True


def annotation_is_hidden(obj):
    return obj.hide_get() or not annotation_property_visible(obj)


def set_annotation_property_visible(obj, visible):
    if is_dimension_object(obj):
        obj.dimension_props.visible = visible
    elif is_guide_object(obj):
        obj.guide_props.visible = visible


def annotation_references_object(annotation, target):
    if target is None or annotation is None:
        return False
    if is_dimension_object(annotation):
        props = annotation.dimension_props
        anchors = (
            props.start, props.end, props.center, props.angle_a_start,
            props.angle_a_end, props.angle_b_start, props.angle_b_end,
        )
        return props.area_source_object == target or any(anchor.target_object == target for anchor in anchors)
    if is_guide_object(annotation) and getattr(annotation.guide_props, "kind", "GUIDE") == "MEASUREMENT":
        return any(
            anchor.target_object == target
            for anchor in (annotation.guide_props.start, annotation.guide_props.end)
        )
    return False


def _linear_value(props):
    start = resolve_anchor(props.start)
    end = resolve_anchor(props.end)
    if start is None or end is None:
        return None
    delta = Vector(end) - Vector(start)
    mode = getattr(props, "measurement_mode", "TRUE")
    if mode == "DELTA_X":
        return abs(delta.x)
    if mode == "DELTA_Y":
        return abs(delta.y)
    if mode == "DELTA_Z":
        return abs(delta.z)
    return delta.length


def annotation_display_value(scene, obj):
    context = SimpleNamespace(scene=scene)
    kind = annotation_kind(obj)
    if is_guide_object(obj):
        precision = scene.dimensions_settings.precision
        if kind == "GUIDE":
            return "Guide Line"
        if kind == "POINT":
            return "Guide Point"
        if kind == "PLANE":
            spacing = format_length(context, obj.guide_props.plane_spacing, precision)
            return f"Grid · {spacing} spacing"
        start = resolve_anchor(obj.guide_props.start)
        end = resolve_anchor(obj.guide_props.end)
        if start is None or end is None:
            return "Unavailable"
        return format_length(context, (Vector(end) - Vector(start)).length, scene.dimensions_settings.precision)

    props = obj.dimension_props
    style = resolve_dimension_style(scene.dimensions_settings, props)
    if kind == "LINEAR":
        value = _linear_value(props)
        return "Unavailable" if value is None else format_length(context, value, style.precision, style.unit_style)
    if kind == "AREA":
        result = evaluate_area_binding(props) if props.measurement_state != "CAPTURED" else None
        value = result["area"] if result is not None else props.area_value
        return format_area(context, value, style.precision, style.unit_style)
    if kind == "ANGLE":
        source = resolve_angle_source(props)
        if source is None:
            return "Unavailable"
        geometry = get_angle_world_geometry(
            source["start"], source["center"], source["end"],
            props.angle_radius, source.get("arc_mode", "MINOR"),
        )
        return "Unavailable" if geometry is None else f"{degrees(geometry['value']):.{min(style.precision, 3)}f}\N{DEGREE SIGN}"
    return ""


def sync_annotation_manager(scene):
    """Refresh the registry only when membership/order changes; update display fields in place."""
    global _registry_rebuild_count
    settings = getattr(scene, "dimensions_settings", None)
    if settings is None or not hasattr(settings, "annotation_manager_items"):
        return False
    objects = annotation_manager_objects(scene)
    existing = tuple(item.annotation for item in settings.annotation_manager_items)
    rebuilt = existing != objects
    if rebuilt:
        settings.annotation_manager_items.clear()
        for obj in objects:
            item = settings.annotation_manager_items.add()
            item.annotation = obj
        _registry_rebuild_count += 1
    for item in settings.annotation_manager_items:
        obj = item.annotation
        if obj is None:
            continue
        values = {
            "name": obj.name,
            "kind": annotation_kind(obj),
            "state": annotation_state(obj),
            "display_value": annotation_display_value(scene, obj),
        }
        for name, value in values.items():
            if getattr(item, name) != value:
                setattr(item, name, value)
    return rebuilt


def registry_rebuild_count():
    return _registry_rebuild_count


def manager_item_matches(settings, item):
    obj = item.annotation
    if obj is None:
        return False
    query = settings.annotation_manager_search.strip().casefold()
    if query and query not in item.name.casefold():
        return False
    kind = item.kind.lower()
    if not getattr(settings, f"annotation_manager_kind_{kind}", False):
        return False
    state = item.state.lower()
    if not getattr(settings, f"annotation_manager_state_{state}", False):
        return False
    if settings.annotation_manager_references_active and not annotation_references_object(
        obj, settings.annotation_manager_reference_object
    ):
        return False
    return True


def filtered_manager_objects(settings):
    return tuple(
        item.annotation for item in settings.annotation_manager_items
        if manager_item_matches(settings, item)
    )


def bulk_manager_objects(context):
    settings = context.scene.dimensions_settings
    if settings.annotation_manager_bulk_scope == "SELECTED":
        managed = set(annotation_manager_objects(context.scene))
        return tuple(obj for obj in context.selected_objects if obj in managed)
    return filtered_manager_objects(settings)


def select_manager_index(settings, context):
    if _index_sync_active:
        return
    index = settings.active_annotation_manager_index
    if not (0 <= index < len(settings.annotation_manager_items)):
        return
    obj = settings.annotation_manager_items[index].annotation
    if obj is None or obj.name not in context.view_layer.objects:
        return
    for selected in context.selected_objects:
        selected.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def set_active_index_from_viewport(settings, active_object):
    global _index_sync_active
    for index, item in enumerate(settings.annotation_manager_items):
        if item.annotation != active_object or settings.active_annotation_manager_index == index:
            continue
        _index_sync_active = True
        try:
            settings.active_annotation_manager_index = index
        finally:
            _index_sync_active = False
        return


def capture_reference_object(settings, context):
    if not settings.annotation_manager_references_active:
        return
    active = getattr(context.view_layer.objects, "active", None)
    if active is not None and not (is_dimension_object(active) or is_guide_object(active)):
        settings.annotation_manager_reference_object = active
