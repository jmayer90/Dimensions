import bpy
from bpy.app.handlers import persistent

from .constants import DEFAULT_AUTO_MERGE_DISTANCE_METERS


def auto_merge_threshold_for_scene(scene):
    """Return a conservative 0.1 mm merge distance in scene coordinates."""
    unit_settings = scene.unit_settings
    if unit_settings.system == "NONE":
        return DEFAULT_AUTO_MERGE_DISTANCE_METERS

    scale_length = max(float(unit_settings.scale_length), 1e-12)
    return min(DEFAULT_AUTO_MERGE_DISTANCE_METERS / scale_length, 1.0)


def initialize_scene_mesh_workflow(scene):
    """Apply SketchUp-friendly mesh settings once, preserving later user edits."""
    if scene is None or not hasattr(scene, "dimensions_settings"):
        return False

    settings = scene.dimensions_settings
    if settings.mesh_workflow_initialized:
        return False

    tool_settings = scene.tool_settings
    tool_settings.use_mesh_automerge = True
    tool_settings.use_mesh_automerge_and_split = True
    tool_settings.double_threshold = auto_merge_threshold_for_scene(scene)
    settings.mesh_workflow_initialized = True
    return True


@persistent
def _initialize_mesh_workflow_on_load(_filepath):
    for scene in bpy.data.scenes:
        initialize_scene_mesh_workflow(scene)


@persistent
def _initialize_mesh_workflow_for_new_scene(scene, _depsgraph):
    initialize_scene_mesh_workflow(scene)


def register_mesh_workflow_defaults():
    if _initialize_mesh_workflow_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_initialize_mesh_workflow_on_load)
    if _initialize_mesh_workflow_for_new_scene not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_initialize_mesh_workflow_for_new_scene)

    for scene in bpy.data.scenes:
        initialize_scene_mesh_workflow(scene)


def unregister_mesh_workflow_defaults():
    if _initialize_mesh_workflow_for_new_scene in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_initialize_mesh_workflow_for_new_scene)
    if _initialize_mesh_workflow_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_initialize_mesh_workflow_on_load)
