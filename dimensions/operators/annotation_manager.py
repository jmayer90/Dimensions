"""Annotation-manager row and bulk operations."""

import bpy

from .. import messages
from ..annotation_manager import (
    annotation_is_hidden,
    annotation_property_visible,
    bulk_manager_objects,
    set_annotation_property_visible,
    sync_annotation_manager,
)
from ..properties import (
    apply_scene_style_to_dimension,
    is_dimension_object,
    is_guide_object,
    is_read_only_dimensions_object,
)
from ..collections import (
    detach_annotations_from,
    remove_guide_point_snap_proxies,
    remove_measurement_snap_proxies,
)
from ..drawing import set_preview_state
from ..area_binding import evaluate_area_binding
from ..repair import repair_issues
from .style import _active_style, assign_style_to_annotations


def _managed_object(context, object_name):
    obj = context.scene.objects.get(object_name)
    return obj if is_dimension_object(obj) or is_guide_object(obj) else None


def _select_only(context, obj):
    for selected in context.selected_objects:
        selected.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _remove_managed_object(obj):
    if is_guide_object(obj):
        detach_annotations_from((obj,))
    if is_guide_object(obj) and getattr(obj.guide_props, "kind", "GUIDE") == "MEASUREMENT":
        remove_measurement_snap_proxies(obj)
    if is_guide_object(obj) and getattr(obj.guide_props, "kind", "GUIDE") == "POINT":
        remove_guide_point_snap_proxies(obj)
    mesh = obj.data if getattr(obj, "type", None) == "MESH" else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def _active_row_object(context):
    settings = context.scene.dimensions_settings
    index = settings.active_annotation_manager_index
    if 0 <= index < len(settings.annotation_manager_items):
        return settings.annotation_manager_items[index].annotation
    return None


def isolate_annotations(context, targets):
    """Show only ``targets`` among Dimensions objects; the model stays visible."""
    settings = context.scene.dimensions_settings
    if settings.annotation_manager_isolate_active:
        restore_annotation_visibility(context)
    target_set = set(targets)
    settings.annotation_manager_isolate_records.clear()
    for item in settings.annotation_manager_items:
        obj = item.annotation
        if obj is None:
            continue
        record = settings.annotation_manager_isolate_records.add()
        record.annotation = obj
        record.was_hidden = obj.hide_get()
        record.was_property_visible = annotation_property_visible(obj)
        if obj in target_set and not is_read_only_dimensions_object(obj):
            set_annotation_property_visible(obj, True)
        obj.hide_set(obj not in target_set)
    settings.annotation_manager_isolate_active = True


def restore_annotation_visibility(context):
    settings = context.scene.dimensions_settings
    for record in settings.annotation_manager_isolate_records:
        obj = record.annotation
        if obj is None:
            continue
        if not is_read_only_dimensions_object(obj):
            set_annotation_property_visible(obj, record.was_property_visible)
        if obj.name in context.view_layer.objects:
            obj.hide_set(record.was_hidden)
    settings.annotation_manager_isolate_records.clear()
    settings.annotation_manager_isolate_active = False


class DIMENSIONS_OT_ManagerSelect(bpy.types.Operator):
    bl_idname = "dimensions.manager_select"
    bl_label = "Select Annotation"
    bl_description = "Select this annotation in the viewport and make it active"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        obj = _managed_object(context, self.object_name)
        if obj is None:
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        _select_only(context, obj)
        return {"FINISHED"}


class DIMENSIONS_OT_ManagerRename(bpy.types.Operator):
    bl_idname = "dimensions.manager_rename"
    bl_label = "Rename Annotation"
    bl_description = "Give this annotation a new name"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    name: bpy.props.StringProperty(name="Name")

    def invoke(self, context, _event):
        obj = _managed_object(context, self.object_name)
        if obj is None:
            return {"CANCELLED"}
        self.name = obj.name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = _managed_object(context, self.object_name)
        if obj is None:
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        if is_read_only_dimensions_object(obj):
            self.report(messages.WARNING, messages.MANAGER_LINKED_READ_ONLY)
            return {"CANCELLED"}
        obj.name = self.name.strip() or obj.name
        sync_annotation_manager(context.scene)
        self.report(messages.INFO, messages.renamed_annotation(obj.name))
        return {"FINISHED"}


class DIMENSIONS_OT_ManagerToggleVisibility(bpy.types.Operator):
    bl_idname = "dimensions.manager_toggle_visibility"
    bl_label = "Show or Hide Annotation"
    bl_description = "Show or hide this annotation in the viewport"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        obj = _managed_object(context, self.object_name)
        if obj is None:
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        hidden = annotation_is_hidden(obj)
        if hidden and not is_read_only_dimensions_object(obj):
            set_annotation_property_visible(obj, True)
        obj.hide_set(not hidden)
        return {"FINISHED"}


class DIMENSIONS_OT_ManagerDelete(bpy.types.Operator):
    bl_idname = "dimensions.manager_delete"
    bl_label = "Delete Annotation"
    bl_description = "Delete this annotation or construction object"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        obj = _managed_object(context, self.object_name)
        if obj is None:
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        if is_read_only_dimensions_object(obj):
            self.report(messages.WARNING, messages.MANAGER_LINKED_READ_ONLY)
            return {"CANCELLED"}
        _remove_managed_object(obj)
        sync_annotation_manager(context.scene)
        self.report(messages.INFO, messages.DELETED_ANNOTATION)
        return {"FINISHED"}


class DIMENSIONS_OT_ManagerJumpTo(bpy.types.Operator):
    bl_idname = "dimensions.manager_jump_to"
    bl_label = "Frame Annotation"
    bl_description = "Select this annotation and zoom the viewport to it"
    bl_options = {"REGISTER"}

    object_name: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        obj = _managed_object(context, self.object_name)
        if obj is None:
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        _select_only(context, obj)
        if context.area is None or context.area.type != "VIEW_3D":
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        bpy.ops.view3d.view_selected(use_all_regions=False)
        return {"FINISHED"}


class DIMENSIONS_OT_ManagerRepairEntry(bpy.types.Operator):
    bl_idname = "dimensions.manager_repair_entry"
    bl_label = "Show Repair Sources"
    bl_description = "Select the source geometry of this annotation and mark its last known and suggested positions"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        obj = _managed_object(context, self.object_name)
        if obj is None or not is_dimension_object(obj):
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        props = obj.dimension_props
        if props.annotation_kind == "AREA" and props.measurement_state != "CAPTURED":
            result = evaluate_area_binding(props)
            if result is not None and result.get("evaluation_mode") == "BASE_FALLBACK":
                self.report(messages.WARNING, messages.AREA_MODIFIER_IDENTITY_UNRESOLVED)
                return {"CANCELLED"}
        issues = repair_issues(obj)
        if not issues:
            self.report(messages.WARNING, messages.REPAIR_NOT_REQUIRED)
            return {"CANCELLED"}
        sources = {
            anchor.target_object for anchor in (
                props.start, props.end, props.center, props.angle_a_start,
                props.angle_a_end, props.angle_b_start, props.angle_b_end,
            ) if anchor.target_object is not None
        }
        if props.area_source_object is not None:
            sources.add(props.area_source_object)
        for selected in context.selected_objects:
            selected.select_set(False)
        for source in sources:
            if source.name in context.view_layer.objects:
                source.hide_set(False)
                source.select_set(True)
        obj.hide_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        markers = []
        for issue in issues:
            markers.append({"world_co": tuple(issue["world_co"]), "candidate": False})
            if issue.get("candidate") is not None:
                markers.append({"world_co": tuple(issue["candidate"]["world_co"]), "candidate": True})
        set_preview_state({"state": "REPAIR", "repair_markers": markers})
        self.report(messages.INFO, messages.repair_explanation(issues[0]))
        return {"FINISHED"}


_VISIBILITY_DESCRIPTIONS = {
    "SHOW": "Show the annotations chosen by Apply To",
    "HIDE": "Hide the annotations chosen by Apply To",
    "ISOLATE": (
        "Show only the annotations chosen by Apply To and hide every other annotation and guide. "
        "Your model stays visible. With Selected and nothing selected, the highlighted row is used"
    ),
    "RESTORE": "Restore every annotation and guide to how it was before Isolate",
}


class DIMENSIONS_OT_ManagerBulkVisibility(bpy.types.Operator):
    bl_idname = "dimensions.manager_bulk_visibility"
    bl_label = "Annotation Visibility"
    bl_description = "Show, hide, or isolate annotations"
    bl_options = {"REGISTER", "UNDO"}

    action: bpy.props.EnumProperty(
        items=[
            ("SHOW", "Show", _VISIBILITY_DESCRIPTIONS["SHOW"]),
            ("HIDE", "Hide", _VISIBILITY_DESCRIPTIONS["HIDE"]),
            ("ISOLATE", "Isolate", _VISIBILITY_DESCRIPTIONS["ISOLATE"]),
            ("RESTORE", "Exit Isolate", _VISIBILITY_DESCRIPTIONS["RESTORE"]),
        ],
        options={"SKIP_SAVE"},
    )

    @classmethod
    def description(cls, _context, properties):
        return _VISIBILITY_DESCRIPTIONS.get(properties.action, cls.bl_description)

    def execute(self, context):
        settings = context.scene.dimensions_settings
        if self.action == "RESTORE":
            restore_annotation_visibility(context)
            self.report(messages.INFO, messages.MANAGER_ISOLATE_RESTORED)
            return {"FINISHED"}
        objects = bulk_manager_objects(context)
        if not objects and settings.annotation_manager_bulk_scope == "SELECTED":
            active_row = _active_row_object(context)
            objects = () if active_row is None else (active_row,)
        if not objects:
            self.report(messages.WARNING, messages.MANAGER_SCOPE_EMPTY)
            return {"CANCELLED"}
        if self.action == "ISOLATE":
            isolate_annotations(context, objects)
        else:
            hidden = self.action == "HIDE"
            for obj in objects:
                if not hidden and not is_read_only_dimensions_object(obj):
                    set_annotation_property_visible(obj, True)
                obj.hide_set(hidden)
        self.report(messages.INFO, messages.manager_bulk_changed(len(objects)))
        return {"FINISHED"}


class DIMENSIONS_OT_ManagerBulkDelete(bpy.types.Operator):
    bl_idname = "dimensions.manager_bulk_delete"
    bl_label = "Delete Annotations"
    bl_description = "Delete every annotation chosen by Apply To"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objects = tuple(
            obj for obj in bulk_manager_objects(context)
            if not is_read_only_dimensions_object(obj)
        )
        if not objects:
            self.report(messages.WARNING, messages.MANAGER_SCOPE_EMPTY)
            return {"CANCELLED"}
        for obj in objects:
            _remove_managed_object(obj)
        sync_annotation_manager(context.scene)
        self.report(messages.INFO, messages.manager_deleted(len(objects)))
        return {"FINISHED"}


class DIMENSIONS_OT_ManagerBulkStyle(bpy.types.Operator):
    bl_idname = "dimensions.manager_bulk_style"
    bl_label = "Apply Named Style"
    bl_description = "Assign the highlighted named style to every annotation chosen by Apply To"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.dimensions_settings
        style = _active_style(settings)
        if style is None:
            self.report(messages.WARNING, messages.MANAGER_STYLE_REQUIRED)
            return {"CANCELLED"}
        count = assign_style_to_annotations(
            settings, bulk_manager_objects(context), style.name, clear_overrides=True,
        )
        self.report(messages.INFO, messages.assigned_style(style.name, count))
        return {"FINISHED"}


class DIMENSIONS_OT_ManagerBulkResetStyle(bpy.types.Operator):
    bl_idname = "dimensions.manager_bulk_reset_style"
    bl_label = "Reset to Global Style"
    bl_description = "Give every annotation chosen by Apply To the global dimension style"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.dimensions_settings
        count = 0
        for obj in bulk_manager_objects(context):
            if is_dimension_object(obj) and not is_read_only_dimensions_object(obj):
                apply_scene_style_to_dimension(settings, obj.dimension_props)
                count += 1
        self.report(messages.INFO, messages.applied_global_style(count))
        return {"FINISHED"}


classes = (
    DIMENSIONS_OT_ManagerSelect,
    DIMENSIONS_OT_ManagerRename,
    DIMENSIONS_OT_ManagerToggleVisibility,
    DIMENSIONS_OT_ManagerDelete,
    DIMENSIONS_OT_ManagerJumpTo,
    DIMENSIONS_OT_ManagerRepairEntry,
    DIMENSIONS_OT_ManagerBulkVisibility,
    DIMENSIONS_OT_ManagerBulkDelete,
    DIMENSIONS_OT_ManagerBulkStyle,
    DIMENSIONS_OT_ManagerBulkResetStyle,
)
