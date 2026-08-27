"""Saved-data schema migration for Dimensions scenes."""

import bpy
from bpy.app.handlers import persistent

from .anchors import migrate_anchor_identity
from .constants import CURRENT_SCHEMA_VERSION
from .properties import is_dimension_object, is_guide_object


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


_MIGRATIONS = {0: migrate_v0_to_v1, 1: migrate_v1_to_v2}


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
