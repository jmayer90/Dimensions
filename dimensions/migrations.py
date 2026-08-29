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
)


_warned_newer_versions = set()


def scene_has_dimensions_data(scene):
    return any(
        is_dimension_object(obj) or is_guide_object(obj)
        for obj in scene.objects
    )


def stamp_scene_if_needed(scene):
    """Stamp a scene when Dimensions first creates persistent data in it."""
    if scene is not None and scene_has_dimensions_data(scene):
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
    for obj in scene.objects:
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
    for obj in scene.objects:
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
    for obj in scene.objects:
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


def migrate_v6_to_v7(scene):
    """Initialize additive persistent chain/baseline set storage.

    Existing annotations remain independent. Blender supplies empty member
    collections and the automatic-spacing default for files written by v6.
    """
    changed = False
    for obj in scene.objects:
        if not is_dimension_object(obj):
            continue
        props = obj.dimension_props
        if getattr(props, "annotation_kind", "LINEAR") != "DIMENSION_SET":
            continue
        if props.set_kind not in {"CHAIN", "BASELINE"}:
            props.set_kind = "CHAIN"
            changed = True
        if props.set_spacing < 0.0:
            props.set_spacing = 0.0
            changed = True
    return changed


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

    for obj in scene.objects:
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


def migrate_v9_to_v10(scene):
    """Initialize additive circular binding storage without changing legacy annotations."""
    changed = False
    settings = scene.dimensions_settings
    if not settings.annotation_manager_kind_circle:
        settings.annotation_manager_kind_circle = True
        changed = True
    for obj in scene.objects:
        if not is_dimension_object(obj):
            continue
        props = obj.dimension_props
        if getattr(props, "annotation_kind", "LINEAR") != "CIRCLE":
            continue
        if props.circle_fit_warning_threshold <= 0.0:
            props.circle_fit_warning_threshold = 0.02
            changed = True
    return changed


def migrate_v10_to_v11(scene):
    """Initialize additive derived-guide relationship storage as fixed/live."""
    changed = False
    for obj in scene.objects:
        if not is_guide_object(obj):
            continue
        props = obj.guide_props
        if props.derived or props.derivation_mode != "NONE":
            props.derived = False
            props.derivation_mode = "NONE"
            changed = True
        if props.derived_state != "LIVE":
            props.derived_state = "LIVE"
            changed = True
    return changed


def migrate_v11_to_v12(scene):
    """Initialize additive named datum and coordinate/elevation storage."""
    changed = False
    settings = scene.dimensions_settings
    for name in ("coordinate", "elevation", "datum"):
        property_name = f"annotation_manager_kind_{name}"
        if not getattr(settings, property_name):
            setattr(settings, property_name, True)
            changed = True
    for obj in scene.objects:
        if is_guide_object(obj) and getattr(obj.guide_props, "kind", "GUIDE") == "POINT":
            props = obj.guide_props
            if props.is_datum and not props.datum_name.strip():
                props.datum_name = obj.name
                changed = True
        elif is_dimension_object(obj):
            props = obj.dimension_props
            if props.annotation_kind == "ELEVATION" and props.elevation_precision < 0:
                props.elevation_precision = 3
                changed = True
    return changed


def migrate_v12_to_v13(scene):
    """Initialize additive guide-plane and active construction-plane storage."""
    settings = scene.dimensions_settings
    changed = False
    if settings.active_plane_mode not in {"NONE", "GUIDE", "FACE", "VIEW", "WORLD_XY", "WORLD_YZ", "WORLD_ZX"}:
        settings.active_plane_mode = "NONE"
        settings.active_plane_object = None
        changed = True
    for property_name in ("snap_guide_plane", "annotation_manager_kind_plane"):
        if not getattr(settings, property_name):
            setattr(settings, property_name, True)
            changed = True
    for obj in scene.objects:
        if not is_guide_object(obj) or getattr(obj.guide_props, "kind", "GUIDE") != "PLANE":
            continue
        props = obj.guide_props
        if props.plane_extent <= 0.0:
            props.plane_extent = 2.0
            changed = True
        if props.plane_state not in {"LIVE", "NEEDS_REPAIR", "CYCLE"}:
            props.plane_state = "NEEDS_REPAIR"
            changed = True
    return changed


def migrate_v13_to_v14(scene):
    """Initialize additive angular and repeated-spacing guide definitions."""
    changed = False
    for obj in scene.objects:
        if not is_guide_object(obj):
            continue
        props = obj.guide_props
        if props.derivation_mode == "SPACING":
            if props.spacing_interval <= 0.0:
                props.spacing_interval = 1.0
                changed = True
            if props.spacing_count < 2:
                props.spacing_count = 2
                changed = True
            if props.spacing_extent <= 0.0:
                props.spacing_extent = props.spacing_interval * (props.spacing_count - 1)
                changed = True
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
}


def migrate_open_scenes():
    for scene in bpy.data.scenes:
        migrate_scene(scene)


@persistent
def _load_post_handler(_dummy):
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
