import bpy

from .. import messages
from ..properties import (
    apply_dimension_style_to_scene,
    apply_scene_style_to_dimension,
    clear_dimension_style_overrides,
    configured_scene_unit_style,
    find_annotation_style,
    is_dimension_object,
    is_read_only_dimensions_object,
    resolve_dimension_style,
)


def _active_style(settings):
    index = settings.active_annotation_style_index
    return settings.annotation_styles[index] if 0 <= index < len(settings.annotation_styles) else None


def _unique_style_name(settings, base):
    names = {style.name for style in settings.annotation_styles}
    if base not in names:
        return base
    number = 2
    while f"{base} {number}" in names:
        number += 1
    return f"{base} {number}"


def _copy_style(source, target):
    for name in (
        "color", "selected_color", "line_width", "text_size", "precision",
        "arrow_size", "arrow_end_style", "start_end_style", "end_end_style",
        "extension_gap", "extension_overshoot", "value_prefix", "value_suffix",
        "tolerance_mode", "tolerance_upper", "tolerance_lower", "unit_style",
        "secondary_unit_style", "secondary_precision", "dual_unit_arrangement",
        "label_orientation", "label_line_mode",
    ):
        value = getattr(source, name)
        setattr(target, name, tuple(value) if name in {"color", "selected_color"} else value)


def assign_style_to_annotations(settings, objects, style_name, *, clear_overrides=False):
    """Assignment seam used now by selection and later by UX-02 filtered sets."""
    if style_name and find_annotation_style(settings, style_name) is None:
        return 0
    count = 0
    for obj in objects:
        if is_dimension_object(obj) and not is_read_only_dimensions_object(obj):
            obj.dimension_props.style_name = style_name
            if clear_overrides:
                clear_dimension_style_overrides(obj.dimension_props)
            count += 1
    return count


def _linked_style_users(scene, style_name):
    return tuple(
        obj for obj in scene.objects
        if is_dimension_object(obj)
        and is_read_only_dimensions_object(obj)
        and obj.dimension_props.style_name == style_name
    )


class CADDIM_OT_ResetStyleToGlobal(bpy.types.Operator):
    bl_idname = "dimensions.reset_style_to_global"
    bl_label = "Reset to Global"
    bl_description = "Copy the global dimension style to the selected dimension"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active
        return is_dimension_object(obj) and not is_read_only_dimensions_object(obj)

    def execute(self, context):
        dimension_object = context.view_layer.objects.active
        apply_scene_style_to_dimension(
            context.scene.dimensions_settings,
            dimension_object.dimension_props,
        )
        self.report(messages.INFO, messages.RESET_GLOBAL_STYLE)
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
            if not is_dimension_object(obj) or is_read_only_dimensions_object(obj):
                continue

            apply_scene_style_to_dimension(settings, obj.dimension_props)
            count += 1

        self.report(messages.INFO, messages.applied_global_style(count))
        return {"FINISHED"}


class CADDIM_OT_CopyStyleToGlobal(bpy.types.Operator):
    bl_idname = "dimensions.copy_style_to_global"
    bl_label = "Copy to Global"
    bl_description = "Use the selected dimension's local style as the new global style"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active
        return is_dimension_object(obj) and not is_read_only_dimensions_object(obj)

    def execute(self, context):
        dimension_object = context.view_layer.objects.active
        settings = context.scene.dimensions_settings
        apply_dimension_style_to_scene(
            resolve_dimension_style(settings, dimension_object.dimension_props),
            settings,
        )
        self.report(messages.INFO, messages.COPIED_GLOBAL_STYLE)
        return {"FINISHED"}


class CADDIM_OT_CreateAnnotationStyle(bpy.types.Operator):
    bl_idname = "dimensions.create_annotation_style"
    bl_label = "Create Style"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.dimensions_settings
        style = settings.annotation_styles.add()
        style.name = _unique_style_name(settings, "Style")
        style.color = tuple(settings.dimension_color)
        style.selected_color = tuple(settings.selected_dimension_color)
        style.line_width = settings.dimension_line_width
        style.text_size = settings.dimension_text_size
        style.precision = settings.precision
        style.arrow_size = settings.dimension_arrow_size
        style.arrow_end_style = settings.dimension_arrow_end_style
        style.start_end_style = settings.dimension_start_end_style
        style.end_end_style = settings.dimension_end_end_style
        style.extension_gap = settings.dimension_extension_gap
        style.extension_overshoot = settings.dimension_extension_overshoot
        style.unit_style = configured_scene_unit_style(settings)
        style.secondary_unit_style = settings.dimension_secondary_unit_style
        style.secondary_precision = settings.dimension_secondary_precision
        style.dual_unit_arrangement = settings.dimension_dual_unit_arrangement
        style.label_orientation = settings.dimension_label_orientation
        style.label_line_mode = settings.dimension_label_line_mode
        settings.active_annotation_style_index = len(settings.annotation_styles) - 1
        self.report(messages.INFO, messages.created_style(style.name))
        return {"FINISHED"}


class CADDIM_OT_DuplicateAnnotationStyle(bpy.types.Operator):
    bl_idname = "dimensions.duplicate_annotation_style"
    bl_label = "Duplicate Style"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_style(context.scene.dimensions_settings) is not None

    def execute(self, context):
        settings = context.scene.dimensions_settings
        source = _active_style(settings)
        duplicate = settings.annotation_styles.add()
        duplicate.name = _unique_style_name(settings, f"{source.name} Copy")
        _copy_style(source, duplicate)
        settings.active_annotation_style_index = len(settings.annotation_styles) - 1
        self.report(messages.INFO, messages.created_style(duplicate.name))
        return {"FINISHED"}


class CADDIM_OT_RenameAnnotationStyle(bpy.types.Operator):
    bl_idname = "dimensions.rename_annotation_style"
    bl_label = "Rename Style"
    bl_options = {"REGISTER", "UNDO"}

    name: bpy.props.StringProperty(name="Name")

    @classmethod
    def poll(cls, context):
        return _active_style(context.scene.dimensions_settings) is not None

    def invoke(self, context, _event):
        self.name = _active_style(context.scene.dimensions_settings).name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        settings = context.scene.dimensions_settings
        style = _active_style(settings)
        old_name = style.name
        if _linked_style_users(context.scene, old_name):
            self.report(messages.WARNING, messages.LINKED_STYLE_USERS)
            return {"CANCELLED"}
        requested = self.name.strip() or "Style"
        style.name = requested if requested == old_name else _unique_style_name(settings, requested)
        for obj in context.scene.objects:
            if is_dimension_object(obj) and obj.dimension_props.style_name == old_name:
                obj.dimension_props.style_name = style.name
        self.report(messages.INFO, messages.renamed_style(style.name))
        return {"FINISHED"}


class CADDIM_OT_DeleteAnnotationStyle(bpy.types.Operator):
    bl_idname = "dimensions.delete_annotation_style"
    bl_label = "Delete Style"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_style(context.scene.dimensions_settings) is not None

    def execute(self, context):
        settings = context.scene.dimensions_settings
        index = settings.active_annotation_style_index
        style_name = settings.annotation_styles[index].name
        if _linked_style_users(context.scene, style_name):
            self.report(messages.WARNING, messages.LINKED_STYLE_USERS)
            return {"CANCELLED"}
        reassigned = assign_style_to_annotations(
            settings,
            (obj for obj in context.scene.objects if is_dimension_object(obj) and obj.dimension_props.style_name == style_name),
            "",
        )
        settings.annotation_styles.remove(index)
        settings.active_annotation_style_index = min(index, max(0, len(settings.annotation_styles) - 1))
        self.report(messages.INFO, messages.deleted_style(style_name, reassigned))
        return {"FINISHED"}


class CADDIM_OT_AssignAnnotationStyle(bpy.types.Operator):
    bl_idname = "dimensions.assign_annotation_style"
    bl_label = "Assign Style to Selection"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_style(context.scene.dimensions_settings) is not None

    def execute(self, context):
        settings = context.scene.dimensions_settings
        style = _active_style(settings)
        count = assign_style_to_annotations(
            settings, context.selected_objects, style.name, clear_overrides=True
        )
        self.report(messages.INFO, messages.assigned_style(style.name, count))
        return {"FINISHED"}


class CADDIM_OT_SelectAnnotationStyleUsers(bpy.types.Operator):
    bl_idname = "dimensions.select_annotation_style_users"
    bl_label = "Select Style Users"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_style(context.scene.dimensions_settings) is not None

    def execute(self, context):
        style = _active_style(context.scene.dimensions_settings)
        count = 0
        for obj in context.view_layer.objects:
            selected = is_dimension_object(obj) and obj.dimension_props.style_name == style.name
            obj.select_set(selected)
            count += int(selected)
        self.report(messages.INFO, messages.selected_style_users(style.name, count))
        return {"FINISHED"}


class CADDIM_OT_ClearAnnotationStyleOverrides(bpy.types.Operator):
    bl_idname = "dimensions.clear_annotation_style_overrides"
    bl_label = "Clear Overrides and Inherit"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active
        return is_dimension_object(obj) and not is_read_only_dimensions_object(obj)

    def execute(self, context):
        clear_dimension_style_overrides(context.view_layer.objects.active.dimension_props)
        self.report(messages.INFO, messages.CLEARED_STYLE_OVERRIDES)
        return {"FINISHED"}


classes = (
    CADDIM_OT_ResetStyleToGlobal,
    CADDIM_OT_ApplyGlobalStyleToAll,
    CADDIM_OT_CopyStyleToGlobal,
    CADDIM_OT_CreateAnnotationStyle,
    CADDIM_OT_DuplicateAnnotationStyle,
    CADDIM_OT_RenameAnnotationStyle,
    CADDIM_OT_DeleteAnnotationStyle,
    CADDIM_OT_AssignAnnotationStyle,
    CADDIM_OT_SelectAnnotationStyleUsers,
    CADDIM_OT_ClearAnnotationStyleOverrides,
)
