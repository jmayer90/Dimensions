"""Saved-data schema migration for Dimensions scenes."""

import bpy
from bpy.app.handlers import persistent

from .anchors import migrate_anchor_identity, refresh_anchor_resolution
from .constants import CURRENT_SCHEMA_VERSION
from .properties import (
    STYLE_PROPERTY_NAMES,
    configured_scene_unit_style,
    is_dimension_object,
    is_guide_object,
    is_read_only_dimensions_object,
)


_warned_newer_versions = set()


def scene_has_dimensions_data(scene):
    if scene is None:
        return False
    settings = scene.dimensions_settings
    if settings.schema_version or len(settings.annotation_styles):
        return True
    if any(key not in {"annotation_manager_items", "active_annotation_manager_index"} for key in settings.keys()):
        return True
    return any(
        is_dimension_object(obj) or is_guide_object(obj)
        for obj in scene.objects
    )


def _writable_scene_objects(scene):
    return (obj for obj in scene.objects if not is_read_only_dimensions_object(obj))


def stamp_scene_if_needed(scene):
    """Stamp a scene when Dimensions first creates persistent data in it."""
    if scene is not None and scene_has_dimensions_data(scene):
        migrate_scene(scene)


def prepare_scene_for_write(scene):
    """Advance saved settings before creating a new annotation in the scene."""
    if scene is None:
        return
    if scene_has_dimensions_data(scene):
        migrate_scene(scene)
    else:
        scene.dimensions_settings.schema_version = CURRENT_SCHEMA_VERSION


def migrate_scene(scene):
    """Migrate one scene in-place, without ever downgrading newer data."""
    if scene is None or not scene_has_dimensions_data(scene):
        return False

    settings = scene.dimensions_settings
    version = settings.schema_version
    if version > CURRENT_SCHEMA_VERSION:
        key = (scene.name_full, version)
        if key not in _warned_newer_versions:
            print(
                "Dimensions: scene "
                f"{scene.name!r} uses schema {version}; this add-on supports up to "
                f"schema {CURRENT_SCHEMA_VERSION}. The scene was left unchanged."
            )
            _warned_newer_versions.add(key)
        return False

    changed = False
    while version < CURRENT_SCHEMA_VERSION:
        migration = _MIGRATIONS.get(version)
        if migration is None:
            raise RuntimeError(f"Dimensions has no migration from schema {version}")
        changed = migration(scene) or changed
        version += 1
        settings.schema_version = version
        changed = True
    return changed


def migrate_v0_to_v1(scene):
    """Give legacy vertex anchors durable point IDs."""
    changed = False
    for obj in _writable_scene_objects(scene):
        anchors = []
        if is_dimension_object(obj):
            props = obj.dimension_props
            anchors.extend((props.start, props.end, props.center))
            anchors.extend((
                props.angle_a_start,
                props.angle_a_end,
                props.angle_b_start,
                props.angle_b_end,
            ))
        elif is_guide_object(obj):
            anchors.extend((obj.guide_props.start, obj.guide_props.end))
        for anchor in anchors:
            source = getattr(anchor, "target_object", None)
            if is_read_only_dimensions_object(source):
                continue
            changed = migrate_anchor_identity(anchor) or changed
    return changed


def migrate_v1_to_v2(scene):
    """Initialize additive output settings introduced by the 0.4.0 release.

    Blender supplies RNA property defaults when an older file is opened, so a
    normal v1 file already has valid values.  The guarded assignments keep the
    migration safe for files written while the property group was incomplete,
    without overwriting any values a user may already have set.
    """
    settings = scene.dimensions_settings
    defaults = {
        "output_sizing_mode": "CAMERA",
        "output_line_width": 2.0,
        "output_text_height": 14.0,
        "output_arrow_size": 10.0,
        "output_world_line_width": 0.01,
        "output_world_text_height": 0.2,
        "output_world_arrow_size": 0.15,
        "output_scope": "VISIBLE",
    }
    changed = False
    for property_name, default in defaults.items():
        if not hasattr(settings, property_name):
            continue
        value = getattr(settings, property_name)
        if value is None or value == "":
            setattr(settings, property_name, default)
            changed = True

    # The registry is new in v2.  Preserve complete bindings, while dropping
    # entries that cannot identify a generated source and would otherwise make
    # the first regeneration ambiguous.
    bindings = getattr(settings, "output_source_bindings", None)
    if bindings is not None:
        for index in reversed(range(len(bindings))):
            binding = bindings[index]
            if binding.source is None or not binding.key:
                bindings.remove(index)
                changed = True
    return changed


def migrate_v2_to_v3(scene):
    """Initialize the additive scene snap-target override disabled."""
    settings = scene.dimensions_settings
    changed = False
    if settings.use_snap_target_override:
        settings.use_snap_target_override = False
        changed = True
    for identifier in (
        "vertex", "edge", "midpoint", "face_center", "face_point", "guide",
        "measurement_endpoint", "measurement_midpoint", "measurement_segment",
    ):
        property_name = f"snap_{identifier}"
        if not getattr(settings, property_name):
            setattr(settings, property_name, True)
            changed = True
    return changed


def migrate_v3_to_v4(scene):
    """Preserve every existing annotation value as an explicit style override."""
    changed = False
    for obj in _writable_scene_objects(scene):
        if not is_dimension_object(obj):
            continue
        props = obj.dimension_props
        props.style_name = ""
        for property_name in STYLE_PROPERTY_NAMES:
            setattr(props, f"override_{property_name}", True)
        # Precision and unit format did not exist locally before v4. Their
        # explicit values mirror the scene defaults, preserving label output.
        props.precision = scene.dimensions_settings.precision
        props.unit_style = configured_scene_unit_style(scene.dimensions_settings)
        changed = True
    return changed


def migrate_v4_to_v5(scene):
    """Record truthful anchor resolution state and last-known source names."""
    changed = False
    for obj in _writable_scene_objects(scene):
        anchors = []
        if is_dimension_object(obj):
            props = obj.dimension_props
            anchors.extend((props.start, props.end, props.center))
            anchors.extend((
                props.angle_a_start,
                props.angle_a_end,
                props.angle_b_start,
                props.angle_b_end,
            ))
        elif is_guide_object(obj):
            anchors.extend((obj.guide_props.start, obj.guide_props.end))
        for anchor in anchors:
            before = (anchor.resolution_status, anchor.source_object_name, tuple(anchor.world_co))
            refresh_anchor_resolution(anchor)
            changed = before != (
                anchor.resolution_status, anchor.source_object_name, tuple(anchor.world_co),
            ) or changed
    return changed


def migrate_v5_to_v6(scene):
    """Initialize additive, scene-owned vector export settings."""
    settings = scene.dimensions_settings
    defaults = {
        "vector_paper_size": "A4",
        "vector_orientation": "PORTRAIT",
        "vector_scale_denominator": 10.0,
        "vector_line_width_mm": 0.25,
        "vector_text_height_mm": 3.5,
        "vector_arrow_size_mm": 2.5,
    }
    changed = False
    for property_name, default in defaults.items():
        value = getattr(settings, property_name, None)
        invalid = value is None or value == ""
        if isinstance(default, float):
            invalid = invalid or float(value) <= 0.0
        if invalid:
            setattr(settings, property_name, default)
            changed = True
    return changed


def migrate_v6_to_v7(_scene):
    """Formerly initialized chain/baseline set storage.

    Schema 16 converts every saved set into ordinary linear dimensions, so this
    step has nothing left to initialize.
    """
    return False


def migrate_v7_to_v8(scene):
    """Initialize the additive guide-point snap target and manager filter."""
    settings = scene.dimensions_settings
    changed = False
    for property_name in ("snap_guide_point", "annotation_manager_kind_point"):
        if not getattr(settings, property_name):
            setattr(settings, property_name, True)
            changed = True
    return changed


def migrate_v8_to_v9(scene):
    """Preserve legacy endpoint and label presentation in the expanded style model."""
    settings = scene.dimensions_settings

    def endpoint(value):
        return "ARCHITECTURAL_TICK" if value == "ARCHITECTURAL_TICK" else "OPEN"

    line_mode = "ABOVE" if settings.text_placement == "ABOVE" else "BROKEN"
    settings.dimension_start_end_style = endpoint(settings.dimension_arrow_end_style)
    settings.dimension_end_end_style = endpoint(settings.dimension_arrow_end_style)
    settings.dimension_extension_gap = 0.0
    settings.dimension_extension_overshoot = 0.0
    settings.dimension_secondary_unit_style = "NONE"
    settings.dimension_secondary_precision = 2
    settings.dimension_dual_unit_arrangement = "BRACKETS"
    settings.dimension_label_orientation = "HORIZONTAL"
    settings.dimension_label_line_mode = line_mode

    for style in settings.annotation_styles:
        style.start_end_style = endpoint(style.arrow_end_style)
        style.end_end_style = endpoint(style.arrow_end_style)
        style.extension_gap = 0.0
        style.extension_overshoot = 0.0
        style.secondary_unit_style = "NONE"
        style.secondary_precision = 2
        style.dual_unit_arrangement = "BRACKETS"
        style.label_orientation = "HORIZONTAL"
        style.label_line_mode = line_mode

    for obj in _writable_scene_objects(scene):
        if not is_dimension_object(obj):
            continue
        props = obj.dimension_props
        props.start_end_style = endpoint(props.arrow_end_style)
        props.end_end_style = endpoint(props.arrow_end_style)
        props.extension_gap = 0.0
        props.extension_overshoot = 0.0
        props.secondary_unit_style = "NONE"
        props.secondary_precision = 2
        props.dual_unit_arrangement = "BRACKETS"
        props.label_orientation = "HORIZONTAL"
        props.label_line_mode = line_mode
        for name in (
            "start_end_style", "end_end_style", "extension_gap", "extension_overshoot",
            "secondary_unit_style", "secondary_precision", "dual_unit_arrangement",
            "label_orientation", "label_line_mode",
        ):
            setattr(props, f"override_{name}", True)
    return True


def migrate_v9_to_v10(_scene):
    """Formerly initialized circular-dimension storage, removed in schema 16."""
    return False


def migrate_v10_to_v11(_scene):
    """Formerly initialized derived-guide storage, removed in schema 16."""
    return False


def migrate_v11_to_v12(_scene):
    """Formerly initialized datum, coordinate, and elevation storage, removed in schema 16."""
    return False


def migrate_v12_to_v13(scene):
    """Initialize the additive guide-plane snap target and manager filter."""
    settings = scene.dimensions_settings
    changed = False
    for property_name in ("snap_guide_plane", "annotation_manager_kind_plane"):
        if not getattr(settings, property_name):
            setattr(settings, property_name, True)
            changed = True
    return changed


def migrate_v13_to_v14(_scene):
    """Formerly initialized angular and repeated-spacing guides, removed in schema 16."""
    return False


def migrate_v14_to_v15(scene):
    """Initialize additive single-sheet border and title-block settings."""
    settings = scene.dimensions_settings
    defaults = {
        "sheet_border_enabled": False,
        "sheet_title_block_enabled": False,
        "sheet_margin_mm": 10.0,
        "sheet_title_block_width_mm": 80.0,
        "sheet_title_block_height_mm": 30.0,
        "sheet_drawing_title": "",
        "sheet_drawing_number": "",
        "sheet_revision": "",
        "sheet_author": "",
        "sheet_date": "",
    }
    changed = False
    for property_name, default in defaults.items():
        value = getattr(settings, property_name, None)
        invalid = value is None
        if isinstance(default, float):
            invalid = invalid or float(value) <= 0.0
        if invalid:
            setattr(settings, property_name, default)
            changed = True
    return changed


_LEGACY_ANNOTATION_KINDS = {3: "DIMENSION_SET", 4: "CIRCLE", 5: "COORDINATE", 6: "ELEVATION"}
_LEGACY_AXIS_NAMES = {1: "X", 2: "Y", 3: "Z"}
_ANCHOR_TYPES = ("VERTEX", "OBJECT_POINT", "WORLD")
_LEGACY_DIMENSION_KEYS = (
    "datum_object", "coordinate_components", "coordinate_alignment", "coordinate_alignment_offset",
    "coordinate_sign", "coordinate_show_plus", "coordinate_show_negative", "elevation_axis",
    "elevation_mode", "elevation_reference", "elevation_precision", "elevation_show_plus",
    "elevation_prefix", "elevation_suffix", "set_kind", "set_members", "active_set_member_index",
    "set_spacing", "set_expanded", "circle_kind", "circle_fit_mode", "circle_source_object",
    "circle_vertices", "circle_closed", "circle_fit_error", "circle_fit_warning_threshold",
    "circle_center", "circle_normal", "circle_start_direction", "circle_radius", "circle_sweep",
    "circle_leader_angle", "circle_label_distance",
)
_LEGACY_GUIDE_KEYS = (
    "is_datum", "datum_name", "datum_orientation", "axis", "derived", "derivation_mode",
    "source_a", "source_b", "construction_pivot", "spacing_end", "guide_angle", "spacing_mode",
    "spacing_interval", "spacing_count", "spacing_extent", "offset_distance", "offset_side",
    "derived_direction", "derived_state", "last_resolved_origin", "last_resolved_direction",
    "plane_definition", "plane_point_a", "plane_point_b", "plane_point_c", "plane_normal",
    "plane_axis_u", "plane_state",
)
_LEGACY_SCENE_KEYS = (
    "active_plane_mode", "active_plane_object", "active_plane_origin", "active_plane_normal",
    "active_plane_axis_u", "annotation_manager_kind_dimension_set", "annotation_manager_kind_circle",
    "annotation_manager_kind_coordinate", "annotation_manager_kind_elevation",
    "annotation_manager_kind_datum",
)


def _raw_group(owner, name):
    """Return the saved property group behind ``owner.<name>``, including removed fields."""
    getter = getattr(owner, "bl_system_properties_get", None)
    if getter is None:
        return None
    try:
        storage = getter()
    except (TypeError, RuntimeError):
        return None
    if storage is None:
        return None
    try:
        return storage[name]
    except (KeyError, TypeError):
        return None


def _raw_value(group, key, default=None):
    if group is None:
        return default
    try:
        return group[key]
    except (KeyError, TypeError):
        return default


def _raw_vector(group, key, default):
    from mathutils import Vector

    value = _raw_value(group, key)
    try:
        vector = Vector(tuple(value))
    except (TypeError, ValueError):
        return Vector(default)
    return vector if len(vector) == 3 else Vector(default)


def _drop_raw_keys(group, keys):
    if group is None:
        return
    for key in keys:
        try:
            del group[key]
        except (KeyError, TypeError):
            pass


def _copy_raw_anchor(raw, owner, key):
    """Copy a saved anchor group verbatim, bypassing RNA update callbacks."""
    if raw is None:
        return False
    target = _raw_group(owner, "dimension_props")
    if target is None:
        return False
    target[key] = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw)
    return True


def _copy_simple_properties(source, target, skip=()):
    for prop in source.bl_rna.properties:
        name = prop.identifier
        if name in skip or name == "rna_type" or prop.is_readonly or prop.type in {"POINTER", "COLLECTION"}:
            continue
        try:
            setattr(target, name, getattr(source, name))
        except (AttributeError, TypeError, ValueError):
            pass


def _convert_dimension_set(obj, raw):
    """Replace one saved chain/baseline set with ordinary linear dimensions."""
    members = list(_raw_value(raw, "set_members", ()) or ())
    baseline = int(_raw_value(raw, "set_kind", 0)) == 1
    spacing = float(_raw_value(raw, "set_spacing", 0.0) or 0.0)
    props = obj.dimension_props
    pitch = spacing if spacing > 1e-6 else max(0.05, float(props.text_size) * 0.015)
    axis = props.dimension_type
    collections = tuple(obj.users_collection)
    created = []
    for index, member in enumerate(members):
        new_object = bpy.data.objects.new(f"{obj.name} {index + 1}", None)
        new_object.empty_display_type = obj.empty_display_type
        new_object.empty_display_size = obj.empty_display_size
        new_object.hide_render = True
        for collection in collections:
            collection.objects.link(new_object)
        new_props = new_object.dimension_props
        _copy_simple_properties(props, new_props, skip={"annotation_kind", "enabled", "placement_initialized"})
        new_props.enabled = True
        new_props.annotation_kind = "LINEAR"
        new_props.measurement_mode = f"DELTA_{axis}" if axis in {"X", "Y", "Z"} else "TRUE"
        new_props.offset_distance = props.offset_distance + (index * pitch if baseline else 0.0)
        new_props.placement_initialized = False
        new_object["_dimensions_new_locator"] = True
        _copy_raw_anchor(_raw_value(member, "start"), new_object, "start")
        _copy_raw_anchor(_raw_value(member, "end"), new_object, "end")
        new_object.location = obj.location
        created.append(new_object)
    bpy.data.objects.remove(obj, do_unlink=True)
    return created


def _convert_guide_line(obj, raw):
    from mathutils import Vector

    from .anchors import resolve_anchor, set_world_anchor
    from .construction import set_guide_line_transform

    props = obj.guide_props
    if _raw_value(raw, "derived", 0):
        origin = _raw_vector(raw, "last_resolved_origin", obj.matrix_world.translation)
        direction = _raw_vector(raw, "last_resolved_direction", (1.0, 0.0, 0.0))
    else:
        origin = resolve_anchor(props.start)
        axis = _LEGACY_AXIS_NAMES.get(int(_raw_value(raw, "axis", 0) or 0))
        if axis is not None:
            direction = Vector({"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[axis])
        else:
            direction = resolve_anchor(props.end) - origin
    if direction.length < 1e-8:
        direction = Vector((1.0, 0.0, 0.0))
    direction.normalize()
    set_guide_line_transform(obj, origin, direction)
    set_world_anchor(props.start, origin)
    set_world_anchor(props.end, origin + direction)


def _convert_guide_point(obj):
    from .anchors import resolve_anchor, set_world_anchor

    point = resolve_anchor(obj.guide_props.start)
    matrix = obj.matrix_world.copy()
    matrix.translation = point
    obj.matrix_world = matrix
    set_world_anchor(obj.guide_props.start, point)


def _convert_guide_plane(obj, raw):
    """Replace a saved Empty plane with a snappable grid mesh on its last frame."""
    from .collections import build_guide_plane_object
    from .construction import plane_frame

    origin = _raw_vector(raw, "last_resolved_origin", obj.matrix_world.translation)
    normal = _raw_vector(raw, "last_resolved_direction", (0.0, 0.0, 1.0))
    axis_u = _raw_vector(raw, "plane_axis_u", (1.0, 0.0, 0.0))
    frame = plane_frame(origin, normal, axis_u) or plane_frame(origin, (0.0, 0.0, 1.0))
    collections = tuple(obj.users_collection)
    if not collections:
        return None
    name = obj.name
    extent = obj.guide_props.plane_extent
    visible = obj.guide_props.visible
    hidden = obj.hide_viewport
    bpy.data.objects.remove(obj, do_unlink=True)
    plane = build_guide_plane_object(collections[0], frame, extent, None, name)
    for collection in collections[1:]:
        collection.objects.link(plane)
    plane.name = name
    plane.guide_props.visible = visible
    plane.hide_viewport = hidden
    return plane


def migrate_v15_to_v16(scene):
    """Convert 0.6 data to the simplified 0.7 model.

    Chain and Baseline sets become ordinary linear dimensions. Derived, angular,
    and spaced guides become fixed guide lines at their last resolved position.
    Guide lines and points become transform-defined movable objects, and guide
    planes become snappable grid meshes. Radial, diameter, arc-length,
    coordinate, and elevation annotations are removed because 0.7 has no
    equivalent; their names are printed to the console.
    """
    changed = False
    removed = []
    for obj in list(scene.objects):
        if is_read_only_dimensions_object(obj):
            continue
        dimension_raw = _raw_group(obj, "dimension_props")
        if dimension_raw is not None and _raw_value(dimension_raw, "enabled", 0):
            kind = _LEGACY_ANNOTATION_KINDS.get(int(_raw_value(dimension_raw, "annotation_kind", 0) or 0))
            if kind == "DIMENSION_SET":
                _convert_dimension_set(obj, dimension_raw)
                changed = True
                continue
            if kind in {"CIRCLE", "COORDINATE", "ELEVATION"}:
                removed.append(obj.name)
                bpy.data.objects.remove(obj, do_unlink=True)
                changed = True
                continue
            _drop_raw_keys(dimension_raw, _LEGACY_DIMENSION_KEYS)
        guide_raw = _raw_group(obj, "guide_props")
        if guide_raw is None or not _raw_value(guide_raw, "enabled", 0):
            continue
        kind = obj.guide_props.kind
        if kind == "GUIDE":
            _convert_guide_line(obj, guide_raw)
        elif kind == "POINT":
            _convert_guide_point(obj)
        elif kind == "PLANE" and obj.type != "MESH":
            obj = _convert_guide_plane(obj, guide_raw)
            guide_raw = None if obj is None else _raw_group(obj, "guide_props")
        _drop_raw_keys(guide_raw, _LEGACY_GUIDE_KEYS)
        changed = True
    _drop_raw_keys(_raw_group(scene, "dimensions_settings"), _LEGACY_SCENE_KEYS)
    if removed:
        print(
            "Dimensions 0.7 removed radial, diameter, arc, coordinate, and elevation "
            f"annotations from scene {scene.name!r}: {', '.join(sorted(removed))}"
        )
    return changed


_MIGRATIONS = {
    0: migrate_v0_to_v1,
    1: migrate_v1_to_v2,
    2: migrate_v2_to_v3,
    3: migrate_v3_to_v4,
    4: migrate_v4_to_v5,
    5: migrate_v5_to_v6,
    6: migrate_v6_to_v7,
    7: migrate_v7_to_v8,
    8: migrate_v8_to_v9,
    9: migrate_v9_to_v10,
    10: migrate_v10_to_v11,
    11: migrate_v11_to_v12,
    12: migrate_v12_to_v13,
    13: migrate_v13_to_v14,
    14: migrate_v14_to_v15,
    15: migrate_v15_to_v16,
}


def migrate_open_scenes():
    for scene in bpy.data.scenes:
        migrate_scene(scene)


@persistent
def _load_post_handler(_dummy):
    from .viewport_state import clear_all_states

    clear_all_states()
    migrate_open_scenes()


def _run_deferred_migration():
    migrate_open_scenes()
    return None


def register_migrations():
    if _load_post_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_load_post_handler)
    try:
        migrate_open_scenes()
    except AttributeError:
        # Blender restricts ``bpy.data`` while an add-on registers, so the file
        # that is already open has to be migrated on the next event loop tick.
        bpy.app.timers.register(_run_deferred_migration, first_interval=0.0)


def unregister_migrations():
    if _load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post_handler)
    if bpy.app.timers.is_registered(_run_deferred_migration):
        bpy.app.timers.unregister(_run_deferred_migration)
    _warned_newer_versions.clear()
