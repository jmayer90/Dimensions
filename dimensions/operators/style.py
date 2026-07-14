import bpy

from ..properties import (
    apply_dimension_style_to_scene,
    apply_scene_style_to_dimension,
    is_dimension_object,
)


class CADDIM_OT_ResetStyleToGlobal(bpy.types.Operator):
    bl_idname = "dimensions.reset_style_to_global"
    bl_label = "Reset to Global"
    bl_description = "Copy the global dimension style to the selected dimension"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return is_dimension_object(context.view_layer.objects.active)

    def execute(self, context):
        dimension_object = context.view_layer.objects.active
        apply_scene_style_to_dimension(
            context.scene.dimensions_settings,
            dimension_object.dimension_props,
        )
        self.report({"INFO"}, "Reset selected dimension to the global style")
        return {"FINISHED"}


class CADDIM_OT_ApplyGlobalStyleToAll(bpy.types.Operator):
    bl_idname = "dimensions.apply_global_style_to_all"
    bl_label = "Set All Dimensions"
    bl_description = "Copy the global dimension style to every dimension in this scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.dimensions_settings
        count = 0
        for obj in context.scene.objects:
            if not is_dimension_object(obj):
                continue

            apply_scene_style_to_dimension(settings, obj.dimension_props)
            count += 1

        self.report({"INFO"}, f"Applied global style to {count} dimension(s)")
        return {"FINISHED"}


class CADDIM_OT_CopyStyleToGlobal(bpy.types.Operator):
    bl_idname = "dimensions.copy_style_to_global"
    bl_label = "Copy to Global"
    bl_description = "Use the selected dimension's local style as the new global style"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return is_dimension_object(context.view_layer.objects.active)

    def execute(self, context):
        dimension_object = context.view_layer.objects.active
        apply_dimension_style_to_scene(
            dimension_object.dimension_props,
            context.scene.dimensions_settings,
        )
        self.report({"INFO"}, "Copied selected dimension style to global defaults")
        return {"FINISHED"}


classes = (
    CADDIM_OT_ResetStyleToGlobal,
    CADDIM_OT_ApplyGlobalStyleToAll,
    CADDIM_OT_CopyStyleToGlobal,
)
