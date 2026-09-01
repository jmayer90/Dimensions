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
from ..collections import remove_guide_point_snap_proxies, remove_measurement_snap_proxies
from ..drawing import set_preview_state
from ..derived_guides import resolve_source
from ..area_binding import evaluate_area_binding
from ..repair import repair_issues
from ..anchors import anchor_resolution
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
    if is_guide_object(obj) and getattr(obj.guide_props, "kind", "GUIDE") == "MEASUREMENT":
        remove_measurement_snap_proxies(obj)
    if is_guide_object(obj) and getattr(obj.guide_props, "kind", "GUIDE") == "POINT":
        remove_guide_point_snap_proxies(obj)
    bpy.data.objects.remove(obj, do_unlink=True)


def isolate_annotations(context, targets):
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
        if obj is not None and obj.name in context.view_layer.objects:
            obj.hide_set(record.was_hidden)
            if not is_read_only_dimensions_object(obj):
                set_annotation_property_visible(obj, record.was_property_visible)
    settings.annotation_manager_isolate_records.clear()
    settings.annotation_manager_isolate_active = False


class DIMENSIONS_OT_ManagerSelect(bpy.types.Operator):
    bl_idname = "dimensions.manager_select"
    bl_label = "Select Annotation"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = _managed_object(context, self.object_name)
        if obj is None:
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        _select_only(context, obj)
        return {"FINISHED"}


class DIMENSIONS_OT_ManagerSelectSetMember(bpy.types.Operator):
    bl_idname = "dimensions.manager_select_set_member"
    bl_label = "Select Dimension Set Member"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()
    member_index: bpy.props.IntProperty(default=0, min=0)

    def execute(self, context):
        obj = _managed_object(context, self.object_name)
        if obj is None or not is_dimension_object(obj) or obj.dimension_props.annotation_kind != "DIMENSION_SET":
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        if self.member_index >= len(obj.dimension_props.set_members):
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        obj.dimension_props.active_set_member_index = self.member_index
        _select_only(context, obj)
        return {"FINISHED"}


class DIMENSIONS_OT_ManagerRename(bpy.types.Operator):
    bl_idname = "dimensions.manager_rename"
    bl_label = "Rename Annotation"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()
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
    bl_label = "Toggle Annotation Visibility"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()

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
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()

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
    bl_options = {"REGISTER"}

    object_name: bpy.props.StringProperty()

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
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = _managed_object(context, self.object_name)
        if obj is not None and is_guide_object(obj) and getattr(obj.guide_props, "kind", "GUIDE") == "POINT":
            _select_only(context, obj)
            return bpy.ops.dimensions.reattach_anchor("INVOKE_DEFAULT", anchor_name="START")
        if obj is not None and is_guide_object(obj) and getattr(obj.guide_props, "kind", "GUIDE") == "PLANE":
            _select_only(context, obj)
            return bpy.ops.dimensions.repair_guide_plane("INVOKE_DEFAULT", object_name=obj.name)
        if obj is not None and is_guide_object(obj) and getattr(obj.guide_props, "derived", False):
            _select_only(context, obj)
            props = obj.guide_props
            if resolve_source(props.source_a) is None:
                slot = "A"
            elif props.derivation_mode == "CENTERLINE" and resolve_source(props.source_b) is None:
                slot = "B"
            elif (
                props.derivation_mode in {"ANGULAR", "SPACING"}
                and anchor_resolution(props.construction_pivot)[1] != "BY_ID"
            ):
                slot = "PIVOT"
            elif (
                props.derivation_mode == "SPACING"
                and props.spacing_mode == "DISTRIBUTE"
                and anchor_resolution(props.spacing_end)[1] != "BY_ID"
            ):
                slot = "SPACING_END"
            else:
                slot = "A"
            return bpy.ops.dimensions.repair_derived_guide_source("INVOKE_DEFAULT", source_slot=slot)
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
        if getattr(props, "annotation_kind", "LINEAR") == "DIMENSION_SET":
            sources.update(
                anchor.target_object
                for member in props.set_members
                for anchor in (member.start, member.end)
                if anchor.target_object is not None
            )
        elif getattr(props, "annotation_kind", "LINEAR") == "CIRCLE":
            sources.update(
                anchor.target_object for anchor in props.circle_vertices
                if anchor.target_object is not None
            )
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


class DIMENSIONS_OT_ManagerBulkVisibility(bpy.types.Operator):
    bl_idname = "dimensions.manager_bulk_visibility"
    bl_label = "Bulk Annotation Visibility"
    bl_options = {"REGISTER", "UNDO"}

    action: bpy.props.EnumProperty(items=[
        ("SHOW", "Show", "Show annotations in scope"),
        ("HIDE", "Hide", "Hide annotations in scope"),
        ("ISOLATE", "Isolate", "Show only annotations in scope"),
        ("RESTORE", "Exit Isolate", "Restore visibility from before isolate"),
    ])

    def execute(self, context):
        if self.action == "RESTORE":
            restore_annotation_visibility(context)
            self.report(messages.INFO, messages.MANAGER_ISOLATE_RESTORED)
            return {"FINISHED"}
        objects = bulk_manager_objects(context)
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
    bl_label = "Delete Annotations in Scope"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objects = tuple(
            obj for obj in bulk_manager_objects(context)
            if not is_read_only_dimensions_object(obj)
        )
        for obj in objects:
            _remove_managed_object(obj)
        sync_annotation_manager(context.scene)
        self.report(messages.INFO, messages.manager_deleted(len(objects)))
        return {"FINISHED"}


class DIMENSIONS_OT_ManagerBulkStyle(bpy.types.Operator):
    bl_idname = "dimensions.manager_bulk_style"
    bl_label = "Apply Named Style to Scope"
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
    bl_label = "Reset Scope to Global Style"
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
    DIMENSIONS_OT_ManagerSelectSetMember,
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
