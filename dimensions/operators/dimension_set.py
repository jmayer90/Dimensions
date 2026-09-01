"""Creation and editing operators for persistent chain/baseline sets."""

import bpy
from mathutils import Vector

from .. import messages
from ..anchors import resolve_anchor, set_anchor_from_snap
from ..collections import create_dimension_object
from ..dimension_sets import (
    anchor_snapshot,
    baseline_spacing,
    delete_set_member,
    dimension_set_candidate_issue,
    dimension_set_direction,
    dimension_set_member_issue,
    dimension_set_world_geometry,
    insert_chain_anchor,
)
from ..drawing import clear_preview_state, set_preview_state
from ..inference import InferenceSession, handle_inference_event, inference_status
from ..interaction import (
    axis_from_event,
    axis_label,
    constrained_delta,
    is_confirm_event,
    is_navigation_event,
    push_undo_step,
    remember_session_context,
    session_axis,
    session_context_changed,
    update_distance_text,
)
from ..preferences import get_preferences
from ..properties import is_dimension_object, is_read_only_dimensions_object
from ..snap_targets import handle_snap_target_event
from ..snapping import copy_snap, find_nearest_snap_point
from ..units import parse_distance_input


def _set_object(context, object_name=""):
    obj = context.scene.objects.get(object_name) if object_name else context.view_layer.objects.active
    return obj if is_dimension_object(obj) and obj.dimension_props.annotation_kind == "DIMENSION_SET" else None


def _anchor_snapshot_from_snap(props, snap):
    temporary = props.set_members.add()
    try:
        set_anchor_from_snap(temporary.end, snap)
        return anchor_snapshot(temporary.end)
    finally:
        props.set_members.remove(len(props.set_members) - 1)


class DIMENSIONS_OT_CreateDimensionSet(bpy.types.Operator):
    bl_idname = "dimensions.create_dimension_set"
    bl_label = "Create Dimension Set"
    bl_description = "Pick a datum, then successive points for a chain or baseline set"
    bl_options = {"REGISTER", "UNDO"}

    set_kind: bpy.props.EnumProperty(items=[
        ("CHAIN", "Chain", "Sequential dimensions on one shared line"),
        ("BASELINE", "Baseline", "Dimensions from one datum on stacked rows"),
    ], default="CHAIN")

    def invoke(self, context, _event):
        if context.area is None or context.area.type != "VIEW_3D":
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        if context.mode not in {"OBJECT", "EDIT_MESH"}:
            self.report(messages.WARNING, messages.DIMENSIONS_REQUIRE_SUPPORTED_MODE)
            return {"CANCELLED"}
        self.datum_snap = None
        self.previous_snap = None
        self.hover_snap = None
        self.hover_mouse = None
        self.set_object_name = ""
        self.axis = session_axis(context)
        self.distance_text = ""
        self.distance_input_valid = True
        self.candidate_issue = None
        self.offset_plane_normal = None
        self.inference_session = InferenceSession()
        remember_session_context(self, context)
        self._preview(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or session_context_changed(self, context):
            clear_preview_state()
            return {"CANCELLED"}
        if handle_snap_target_event(context, event):
            self._preview(context)
            return {"RUNNING_MODAL"}
        if handle_inference_event(self.inference_session, event):
            self._preview(context)
            return {"RUNNING_MODAL"}
        axis = axis_from_event(event)
        if axis is not None:
            obj = bpy.data.objects.get(self.set_object_name) if self.set_object_name else None
            if obj is not None:
                self.report(messages.INFO, messages.DIMENSION_SET_AXIS_LOCKED)
                return {"RUNNING_MODAL"}
            self.axis = axis
            self._preview(context)
            self.report(messages.INFO, messages.extension_axis(axis_label(axis)))
            return {"RUNNING_MODAL"}
        if self.datum_snap is not None:
            new_text, handled = update_distance_text(self.distance_text, event)
            if handled:
                self.distance_text = new_text
                self._effective_end_snap(context)
                self._preview(context)
                return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            self.hover_snap = self._find_hover_snap(context, event)
            self.hover_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            self._effective_end_snap(context)
            self._preview(context)
            return {"RUNNING_MODAL"}
        if (event.type == "LEFTMOUSE" and event.value == "PRESS") or is_confirm_event(event):
            click_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            if event.type == "LEFTMOUSE" and (
                self.hover_snap is None or self.hover_mouse is None or click_mouse != self.hover_mouse
            ):
                self.hover_snap = self._find_hover_snap(context, event)
                self.hover_mouse = click_mouse
            if self.hover_snap is None:
                return {"RUNNING_MODAL"}
            if self.datum_snap is None:
                self.datum_snap = copy_snap(self.hover_snap)
                self.previous_snap = copy_snap(self.hover_snap)
                _plane_point, plane_normal = self._acquisition_plane(context)
                if plane_normal is None:
                    plane_normal = context.region_data.view_rotation @ Vector((0.0, 0.0, -1.0))
                self.offset_plane_normal = Vector(plane_normal).normalized()
                self.distance_text = ""
                self.distance_input_valid = True
                self.hover_snap = None
                self.hover_mouse = None
                self._preview(context)
                return {"RUNNING_MODAL"}
            end_snap = self._effective_end_snap(context)
            if end_snap is None:
                if self.distance_text and not self.distance_input_valid:
                    self.report(messages.WARNING, messages.invalid_distance(self.distance_text))
                elif self.candidate_issue in {"OFF_AXIS", "ZERO_PROJECTION"}:
                    self.report(messages.WARNING, messages.DIMENSION_SET_POINT_OFF_AXIS)
                elif self.candidate_issue == "NON_FORWARD":
                    self.report(messages.WARNING, messages.CHAIN_POINT_MUST_ADVANCE)
                else:
                    self.report(messages.WARNING, messages.DIFFERENT_END_POINT_REQUIRED)
                return {"RUNNING_MODAL"}
            if (Vector(end_snap["world_co"]) - Vector(self._member_start_snap()["world_co"])).length < 1e-6:
                self.report(messages.WARNING, messages.DIFFERENT_END_POINT_REQUIRED)
                return {"RUNNING_MODAL"}
            self._commit_member(context, end_snap)
            push_undo_step("Create Dimension Set Member")
            self.distance_text = ""
            self.distance_input_valid = True
            self.hover_snap = None
            self.hover_mouse = None
            remember_session_context(self, context)
            self._preview(context)
            return {"RUNNING_MODAL"}
        if event.type in {"BACK_SPACE", "DEL"} and event.value == "PRESS":
            self._step_back(context)
            self._preview(context)
            return {"RUNNING_MODAL"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            clear_preview_state()
            return {"FINISHED"} if self.set_object_name else {"CANCELLED"}
        if is_navigation_event(event):
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def cancel(self, _context):
        clear_preview_state()

    def _member_start_snap(self):
        return self.previous_snap if self.set_kind == "CHAIN" else self.datum_snap

    def _acquisition_plane(self, context):
        from ..guide_planes import active_plane_frame

        frame = active_plane_frame(context.scene)
        if frame is not None:
            return frame[0], frame[3]
        return (None, None) if self.datum_snap is None else (self.datum_snap["world_co"], None)

    def _find_hover_snap(self, context, event):
        plane_point, plane_normal = self._acquisition_plane(context)
        return find_nearest_snap_point(
            context, event.mouse_region_x, event.mouse_region_y, include_free=True,
            plane_point=plane_point,
            plane_normal=plane_normal,
            inference_session=self.inference_session,
            inference_origin=None if self.datum_snap is None else self._member_start_snap()["world_co"],
            inference_axis=self.axis,
        )

    def _effective_end_snap(self, context):
        self.candidate_issue = None
        if self.datum_snap is None or self.hover_snap is None:
            return None
        start_snap = self._member_start_snap()
        snap = copy_snap(self.hover_snap)
        raw_delta = Vector(snap["world_co"]) - Vector(start_snap["world_co"])
        direction = constrained_delta(raw_delta, self.axis, context)
        if direction.length < 1e-8:
            self.distance_input_valid = not bool(self.distance_text.strip())
            return None
        if self.distance_text.strip():
            try:
                direction.normalize()
                direction *= parse_distance_input(context, self.distance_text)
            except (TypeError, ValueError):
                self.distance_input_valid = False
                return None
        self.distance_input_valid = True
        if self.axis != "ALIGNED" or self.distance_text.strip():
            snap.update({
                "type": "WORLD",
                "label": "Typed Point" if self.distance_text.strip() else "Constrained Point",
                "object": None,
                "vertex_index": -1,
                "world_co": Vector(start_snap["world_co"]) + direction,
            })
            for key in ("edge_index", "edge_vertices", "edge_factor", "face_index"):
                snap.pop(key, None)
        obj = bpy.data.objects.get(self.set_object_name) if self.set_object_name else None
        if obj is not None:
            self.candidate_issue = dimension_set_candidate_issue(
                obj.dimension_props,
                start_snap["world_co"],
                snap["world_co"],
            )
            if self.candidate_issue is not None:
                return None
        return snap

    def _step_back(self, context):
        if self.distance_text:
            self.distance_text = ""
            self.distance_input_valid = True
            return
        obj = bpy.data.objects.get(self.set_object_name) if self.set_object_name else None
        if obj is not None and obj.dimension_props.set_members:
            props = obj.dimension_props
            props.set_members.remove(len(props.set_members) - 1)
            props.active_set_member_index = max(0, len(props.set_members) - 1)
            if props.set_members:
                last = props.set_members[-1]
                self.previous_snap = self._snap_from_anchor(last.end)
            else:
                bpy.data.objects.remove(obj, do_unlink=True)
                self.set_object_name = ""
                self.previous_snap = copy_snap(self.datum_snap)
            remember_session_context(self, context)
            return
        self.datum_snap = None
        self.previous_snap = None
        self.hover_snap = None
        self.hover_mouse = None
        self.offset_plane_normal = None
        self.inference_session.clear()

    @staticmethod
    def _snap_from_anchor(anchor):
        world = resolve_anchor(anchor)
        world = Vector(anchor.world_co) if world is None else Vector(world)
        anchor_type = getattr(anchor, "anchor_type", "WORLD")
        return {
            "type": "VERTEX" if anchor_type == "VERTEX" else ("FACE" if anchor_type == "OBJECT_POINT" else "WORLD"),
            "label": "Previous Point",
            "object": anchor.target_object,
            "vertex_index": anchor.vertex_index,
            "world_co": world,
            "screen_co": Vector((0.0, 0.0)),
        }

    def _commit_member(self, context, end_snap):
        obj = bpy.data.objects.get(self.set_object_name) if self.set_object_name else None
        if obj is None:
            obj = create_dimension_object(context, f"DIM {self.set_kind.title()} Set")
            props = obj.dimension_props
            props.annotation_kind = "DIMENSION_SET"
            props.set_kind = self.set_kind
            props.dimension_type = self.axis
            props.offset_distance = get_preferences(context).default_offset_distance
            props.offset_plane_normal = tuple(self.offset_plane_normal)
            self.set_object_name = obj.name
        props = obj.dimension_props
        member = props.set_members.add()
        start_snap = self.previous_snap if self.set_kind == "CHAIN" else self.datum_snap
        set_anchor_from_snap(member.start, start_snap)
        set_anchor_from_snap(member.end, end_snap)
        member.measurement_state = "LIVE"
        props.active_set_member_index = len(props.set_members) - 1
        geometry = dimension_set_world_geometry(props)
        if geometry:
            obj.location = geometry[-1]["line_mid_world"]
        self.previous_snap = end_snap
        if context.mode == "OBJECT":
            for selected in context.selected_objects:
                selected.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj

    def _preview(self, context):
        preview = {
            "state": "PICK_SET_DATUM" if self.datum_snap is None else "PICK_SET_MEMBER",
            "tool_label": "CHAIN" if self.set_kind == "CHAIN" else "BASELINE",
            "dimension_type": self.axis,
            "axis": self.axis,
            "axis_selectable": True,
            "distance_text": self.distance_text,
            "distance_input_valid": self.distance_input_valid,
        }
        status = inference_status(self.inference_session)
        if status:
            preview["inference_status"] = status
        if self.datum_snap is not None:
            preview["start_world"] = self._member_start_snap()["world_co"]
        effective_end = self._effective_end_snap(context)
        if effective_end is not None:
            preview["hover_screen"] = effective_end.get("screen_co")
            preview["hover_type"] = effective_end.get("type", "WORLD")
            preview["end_world"] = effective_end["world_co"]
        elif self.hover_snap is not None:
            preview["hover_screen"] = self.hover_snap.get("screen_co")
            preview["hover_type"] = self.hover_snap.get("type", "WORLD")
        if self.candidate_issue in {"OFF_AXIS", "ZERO_PROJECTION"}:
            preview["interaction_warning"] = "Point is off the shared axis"
        elif self.candidate_issue == "NON_FORWARD":
            preview["interaction_warning"] = "Point must advance along the chain"
        obj = bpy.data.objects.get(self.set_object_name) if self.set_object_name else None
        if obj is not None:
            props = obj.dimension_props
            preview["offset_distance"] = props.offset_distance
            if props.set_kind == "BASELINE":
                preview["offset_distance"] += len(props.set_members) * baseline_spacing(props)
            preview["offset_plane_normal"] = tuple(props.offset_plane_normal)
        elif self.datum_snap is not None:
            preview["offset_distance"] = get_preferences(context).default_offset_distance
            if self.offset_plane_normal is not None:
                preview["offset_plane_normal"] = tuple(self.offset_plane_normal)
        set_preview_state(preview)


class DIMENSIONS_OT_DeleteDimensionSetMember(bpy.types.Operator):
    bl_idname = "dimensions.delete_dimension_set_member"
    bl_label = "Delete Set Member"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()
    member_index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        obj = _set_object(context, self.object_name)
        if obj is None or is_read_only_dimensions_object(obj):
            self.report(messages.WARNING, messages.MANAGER_LINKED_READ_ONLY)
            return {"CANCELLED"}
        index = self.member_index if self.member_index >= 0 else obj.dimension_props.active_set_member_index
        if not (0 <= index < len(obj.dimension_props.set_members)):
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        delete_set_member(obj.dimension_props, index)
        if not obj.dimension_props.set_members:
            bpy.data.objects.remove(obj, do_unlink=True)
        self.report(messages.INFO, messages.DELETED_ANNOTATION)
        return {"FINISHED"}


class DIMENSIONS_OT_InsertDimensionSetMember(bpy.types.Operator):
    bl_idname = "dimensions.insert_dimension_set_member"
    bl_label = "Insert Chain Point"
    bl_description = "Pick a point that splits the active chain member"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()
    member_index: bpy.props.IntProperty(default=-1)

    def invoke(self, context, _event):
        if context.area is None or context.area.type != "VIEW_3D":
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            self.report(messages.WARNING, messages.REATTACH_REQUIRE_OBJECT_MODE)
            return {"CANCELLED"}
        obj = _set_object(context, self.object_name)
        if obj is None or obj.dimension_props.set_kind != "CHAIN" or is_read_only_dimensions_object(obj):
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        self.object_name = obj.name
        self.member_index = self.member_index if self.member_index >= 0 else obj.dimension_props.active_set_member_index
        if not (0 <= self.member_index < len(obj.dimension_props.set_members)):
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        self.hover_snap = None
        self.hover_mouse = None
        remember_session_context(self, context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        obj = _set_object(context, self.object_name)
        if obj is None or session_context_changed(self, context):
            clear_preview_state()
            return {"CANCELLED"}
        if handle_snap_target_event(context, event):
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            self.hover_snap = self._find_snap(context, event)
            self.hover_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            if self.hover_snap is not None:
                member = obj.dimension_props.set_members[self.member_index]
                set_preview_state({
                    "state": "INSERT_SET_MEMBER",
                    "hover_screen": self.hover_snap.get("screen_co"),
                    "start_world": resolve_anchor(member.start),
                    "end_world": self.hover_snap["world_co"],
                    "dimension_type": obj.dimension_props.dimension_type,
                    "offset_distance": obj.dimension_props.offset_distance,
                    "offset_plane_normal": tuple(obj.dimension_props.offset_plane_normal),
                })
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            click_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            if self.hover_snap is None or self.hover_mouse is None or click_mouse != self.hover_mouse:
                self.hover_snap = self._find_snap(context, event)
                self.hover_mouse = click_mouse
            if self.hover_snap is None:
                return {"RUNNING_MODAL"}
            props = obj.dimension_props
            member = props.set_members[self.member_index]
            start = resolve_anchor(member.start)
            end = resolve_anchor(member.end)
            point = Vector(self.hover_snap["world_co"])
            direction = dimension_set_direction(props)
            datum = resolve_anchor(props.set_members[0].start)
            if (
                start is None or end is None or datum is None or direction is None
                or (point - Vector(start)).length < 1e-6
                or (point - Vector(end)).length < 1e-6
            ):
                self.report(messages.WARNING, messages.DIFFERENT_END_POINT_REQUIRED)
                return {"RUNNING_MODAL"}
            issues = (
                dimension_set_member_issue(props, start, point, direction, datum),
                dimension_set_member_issue(props, point, end, direction, datum),
            )
            if "OFF_AXIS" in issues or "ZERO_PROJECTION" in issues:
                self.report(messages.WARNING, messages.DIMENSION_SET_POINT_OFF_AXIS)
                return {"RUNNING_MODAL"}
            if any(issue is not None for issue in issues):
                self.report(messages.WARNING, messages.CHAIN_POINT_MUST_ADVANCE)
                return {"RUNNING_MODAL"}
            anchor = _anchor_snapshot_from_snap(props, self.hover_snap)
            insert_chain_anchor(props, self.member_index, anchor)
            clear_preview_state()
            return {"FINISHED"}
        if event.type in {"ESC", "RIGHTMOUSE"}:
            clear_preview_state()
            return {"CANCELLED"}
        return {"PASS_THROUGH"} if is_navigation_event(event) else {"RUNNING_MODAL"}

    def cancel(self, _context):
        clear_preview_state()

    def _find_snap(self, context, event):
        from ..guide_planes import active_plane_frame

        frame = active_plane_frame(context.scene)
        return find_nearest_snap_point(
            context,
            event.mouse_region_x,
            event.mouse_region_y,
            include_free=True,
            plane_point=None if frame is None else frame[0],
            plane_normal=None if frame is None else frame[3],
        )


classes = (
    DIMENSIONS_OT_CreateDimensionSet,
    DIMENSIONS_OT_DeleteDimensionSetMember,
    DIMENSIONS_OT_InsertDimensionSetMember,
)
