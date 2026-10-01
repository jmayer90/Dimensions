"""Guided, explicitly confirmed annotation repair operators."""

import bpy

from ..interaction import is_navigation_event, modal_cleanup_on_exception, set_tool_status_text

from ..viewport_state import viewport_key
from mathutils import Vector

from .. import messages
from ..anchors import anchor_resolution, is_construction_grid, set_world_anchor
from ..area_binding import area_source_is_read_only
from ..annotation_manager import annotation_manager_objects
from ..drawing import clear_preview_state, set_preview_state
from ..properties import is_dimension_object, is_read_only_dimensions_object
from ..repair import (
    apply_repair_issue,
    apply_suggested_repairs,
    rebind_area_preserving_presentation,
    repair_anchor,
    repair_cause,
    repair_issues,
    stored_repair_issues,
)
from ..scene_sync import sync_scene_objects
from ..snapping import find_nearest_snap_point, raycast_from_mouse


def _editable_annotation(context, object_name):
    obj = context.scene.objects.get(object_name) if object_name else context.view_layer.objects.active
    if not is_dimension_object(obj):
        return None
    return obj


def _repair_markers(issues):
    markers = []
    for issue in issues:
        markers.append({"world_co": tuple(issue["world_co"]), "candidate": False})
        candidate = issue.get("candidate")
        if candidate is not None:
            markers.append({"world_co": tuple(candidate["world_co"]), "candidate": True})
    return markers


class DIMENSIONS_OT_RepairAcceptSuggestion(bpy.types.Operator):
    bl_idname = "dimensions.repair_accept_suggestion"
    bl_label = "Accept Suggested Repair"
    bl_description = "Rebind broken sources to the shown nearest candidate"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()

    def invoke(self, context, _event):
        self._session_viewport_key = viewport_key(context)
        return context.window_manager.invoke_confirm(self, _event)

    def execute(self, context):
        annotation = _editable_annotation(context, self.object_name)
        if annotation is None:
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        if is_read_only_dimensions_object(annotation):
            self.report(messages.WARNING, messages.REPAIR_LINKED_READ_ONLY)
            return {"CANCELLED"}
        issues = repair_issues(annotation)
        if not issues:
            self.report(messages.WARNING, messages.REPAIR_NOT_REQUIRED)
            return {"CANCELLED"}
        count = apply_suggested_repairs(annotation)
        if not count:
            self.report(messages.WARNING, messages.REPAIR_NO_SUGGESTION)
            return {"CANCELLED"}
        sync_scene_objects(context.scene)
        clear_preview_state(key=getattr(self, "_session_viewport_key", None))
        self.report(messages.INFO, messages.accepted_repairs(count))
        return {"FINISHED"}


class DIMENSIONS_OT_RepairConvertWorld(bpy.types.Operator):
    bl_idname = "dimensions.repair_convert_world"
    bl_label = "Convert to World Point"
    bl_description = "Keep the last known position as a fixed world point"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()
    anchor_name: bpy.props.StringProperty()

    def execute(self, context):
        annotation = _editable_annotation(context, self.object_name)
        if annotation is None or is_read_only_dimensions_object(annotation):
            self.report(messages.WARNING, messages.REPAIR_LINKED_READ_ONLY)
            return {"CANCELLED"}
        anchor = repair_anchor(annotation.dimension_props, self.anchor_name)
        if anchor is None or anchor_resolution(anchor)[1] != "UNRESOLVABLE":
            self.report(messages.WARNING, messages.REPAIR_SOURCE_GONE)
            return {"CANCELLED"}
        world = anchor_resolution(anchor)[0]
        set_world_anchor(anchor, world)
        annotation.dimension_props.measurement_state = (
            "NEEDS_REPAIR" if repair_issues(annotation) else "LIVE"
        )
        sync_scene_objects(context.scene)
        self.report(messages.INFO, messages.converted_anchor(self.anchor_name))
        return {"FINISHED"}


class DIMENSIONS_OT_RepairFrameIssue(bpy.types.Operator):
    bl_idname = "dimensions.repair_frame_issue"
    bl_label = "Frame Last Known Position"
    bl_description = "Zoom the viewport to where the missing source was last seen"
    bl_options = {"REGISTER"}

    object_name: bpy.props.StringProperty()

    def execute(self, context):
        annotation = _editable_annotation(context, self.object_name)
        issues = () if annotation is None else repair_issues(annotation)
        if not issues:
            self.report(messages.WARNING, messages.REPAIR_NOT_REQUIRED)
            return {"CANCELLED"}
        if context.region_data is None:
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        # Only the view moves: a tool preview here would outlive the operator and leave a stale badge.
        context.region_data.view_location = Vector(issues[0]["world_co"])
        return {"FINISHED"}


class DIMENSIONS_OT_RepairPickAreaSource(bpy.types.Operator):
    bl_idname = "dimensions.repair_pick_area_source"
    bl_label = "Pick Replacement Area Face"
    bl_description = "Click a face on an object without modifiers to become this Area's new source"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()

    def invoke(self, context, _event):
        self._session_viewport_key = viewport_key(context)
        annotation = _editable_annotation(context, self.object_name)
        if context.area is None or context.area.type != "VIEW_3D":
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        if annotation is None or annotation.dimension_props.annotation_kind != "AREA":
            self.report(messages.WARNING, messages.SELECT_AREA_DIMENSION)
            return {"CANCELLED"}
        if is_read_only_dimensions_object(annotation):
            self.report(messages.WARNING, messages.REPAIR_LINKED_READ_ONLY)
            return {"CANCELLED"}
        if not repair_issues(annotation):
            self.report(messages.WARNING, messages.REPAIR_NOT_REQUIRED)
            return {"CANCELLED"}
        self.annotation_name = annotation.name
        self.hover_source = None
        self.hover_face_index = -1
        context.window_manager.modal_handler_add(self)
        set_tool_status_text(context, "Repair Area: click the replacement face · Esc cancels")
        return {"RUNNING_MODAL"}

    @modal_cleanup_on_exception
    def modal(self, context, event):
        owner_key = getattr(self, "_session_viewport_key", None)
        if owner_key is not None and (
            viewport_key(context) != owner_key
            or getattr(getattr(context, "area", None), "type", None) != "VIEW_3D"
        ):
            self.cancel(context)
            return {"CANCELLED"}
        annotation = bpy.data.objects.get(self.annotation_name)
        if annotation is None or context.area is None or context.area.type != "VIEW_3D":
            clear_preview_state(key=getattr(self, "_session_viewport_key", None))
            return {"CANCELLED"}
        if event.type == "MOUSEMOVE":
            self._update_hover(context, event)
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            self._update_hover(context, event)
            if self.hover_source is None or self.hover_face_index < 0:
                self.report(messages.WARNING, messages.REPAIR_PICK_BASE_FACE)
                return {"RUNNING_MODAL"}
            if area_source_is_read_only(self.hover_source):
                self.report(messages.WARNING, messages.AREA_SOURCE_LINKED)
                return {"RUNNING_MODAL"}
            if self.hover_source.modifiers:
                self.report(messages.WARNING, messages.AREA_BASE_MESH_REQUIRED)
                return {"RUNNING_MODAL"}
            changed = rebind_area_preserving_presentation(
                annotation.dimension_props, self.hover_source, (self.hover_face_index,),
            )
            clear_preview_state(key=getattr(self, "_session_viewport_key", None))
            if not changed:
                self.report(messages.WARNING, messages.AREA_SOURCE_INVALID)
                return {"CANCELLED"}
            sync_scene_objects(context.scene)
            self.report(messages.INFO, messages.accepted_repairs(1))
            return {"FINISHED"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            clear_preview_state(key=getattr(self, "_session_viewport_key", None))
            return {"CANCELLED"}
        if is_navigation_event(event):
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def cancel(self, _context):
        clear_preview_state(key=getattr(self, "_session_viewport_key", None))

    def _update_hover(self, context, event):
        snap = find_nearest_snap_point(
            context, event.mouse_region_x, event.mouse_region_y,
            include_guides=False, include_free=False,
        )
        if snap is not None and (snap.get("guide_plane") or is_construction_grid(snap.get("object"))):
            # Construction grids are never Area sources; use the model surface under the cursor.
            snap = None
        source = None if snap is None else snap.get("object")
        face_index = -1 if snap is None else snap.get("face_index", -1)
        if source is None or face_index < 0:
            hit = raycast_from_mouse(context, event.mouse_region_x, event.mouse_region_y)
            if hit is not None:
                source = hit.get("object")
                face_index = hit.get("face_index", -1)
        self.hover_source = source if source is not None and source.type == "MESH" else None
        self.hover_face_index = face_index
        # Mouse moves read the recorded issues; the live candidate search scans the mesh.
        issues = stored_repair_issues(bpy.data.objects[self.annotation_name])
        markers = _repair_markers(issues)
        if self.hover_source is not None and 0 <= face_index < len(self.hover_source.data.polygons):
            polygon = self.hover_source.data.polygons[face_index]
            markers.append({"world_co": tuple(self.hover_source.matrix_world @ polygon.center), "candidate": True})
        set_preview_state({
            "viewport_key": getattr(self, "_session_viewport_key", None),
            "state": "REPAIR_AREA",
            "tool_label": "REPAIR",
            "prompt": "Click the replacement face",
            "repair_markers": markers,
        })


class DIMENSIONS_OT_RepairBulkCause(bpy.types.Operator):
    bl_idname = "dimensions.repair_bulk_cause"
    bl_label = "Repair Matching Cause"
    bl_description = "Accept suggestions for annotations broken by this same source and cause"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()

    def invoke(self, context, event):
        self._session_viewport_key = viewport_key(context)
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        seed = _editable_annotation(context, self.object_name)
        seed_issues = () if seed is None else repair_issues(seed)
        if not seed_issues:
            self.report(messages.WARNING, messages.REPAIR_NOT_REQUIRED)
            return {"CANCELLED"}
        cause = repair_cause(seed_issues[0])
        count = 0
        for annotation in annotation_manager_objects(context.scene):
            if not is_dimension_object(annotation) or is_read_only_dimensions_object(annotation):
                continue
            for issue in repair_issues(annotation):
                if repair_cause(issue) == cause:
                    count += int(apply_repair_issue(annotation, issue))
        if not count:
            self.report(messages.WARNING, messages.REPAIR_NO_SUGGESTION)
            return {"CANCELLED"}
        sync_scene_objects(context.scene)
        clear_preview_state(key=getattr(self, "_session_viewport_key", None))
        self.report(messages.INFO, messages.accepted_repairs(count))
        return {"FINISHED"}


classes = (
    DIMENSIONS_OT_RepairAcceptSuggestion,
    DIMENSIONS_OT_RepairConvertWorld,
    DIMENSIONS_OT_RepairFrameIssue,
    DIMENSIONS_OT_RepairPickAreaSource,
    DIMENSIONS_OT_RepairBulkCause,
)
