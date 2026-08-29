"""Creation and editing operators for persistent chain/baseline sets."""

import bpy
from mathutils import Vector

from .. import messages
from ..anchors import set_anchor_from_snap
from ..collections import create_dimension_object
from ..dimension_sets import anchor_snapshot, delete_set_member, dimension_set_world_geometry, insert_chain_anchor
from ..drawing import clear_preview_state, set_preview_state
from ..interaction import push_undo_step, remember_session_context, session_context_changed
from ..preferences import get_preferences
from ..properties import is_dimension_object, is_read_only_dimensions_object
from ..snap_targets import handle_snap_target_event
from ..snapping import copy_snap, find_nearest_snap_point


def _set_object(context, object_name=""):
    obj = context.scene.objects.get(object_name) if object_name else context.view_layer.objects.active
    return obj if is_dimension_object(obj) and obj.dimension_props.annotation_kind == "DIMENSION_SET" else None


def _anchor_snapshot_from_snap(props, snap):
    temporary = props.set_members.add()
    set_anchor_from_snap(temporary.end, snap)
    snapshot = anchor_snapshot(temporary.end)
    props.set_members.remove(len(props.set_members) - 1)
    return snapshot


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
        if context.area is None or context.area.type != "VIEW_3D" or context.mode != "OBJECT":
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        self.datum_snap = None
        self.previous_snap = None
        self.hover_snap = None
        self.set_object_name = ""
        remember_session_context(self, context)
        self._preview()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or session_context_changed(self, context):
            clear_preview_state()
            return {"CANCELLED"}
        if handle_snap_target_event(context, event):
            self._preview()
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            self.hover_snap = find_nearest_snap_point(
                context, event.mouse_region_x, event.mouse_region_y, include_free=True,
                plane_point=None if self.datum_snap is None else self.datum_snap["world_co"],
            )
            self._preview()
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.hover_snap is None:
                self.hover_snap = find_nearest_snap_point(
                    context, event.mouse_region_x, event.mouse_region_y, include_free=True,
                )
            if self.hover_snap is None:
                return {"RUNNING_MODAL"}
            if self.datum_snap is None:
                self.datum_snap = copy_snap(self.hover_snap)
                self.previous_snap = copy_snap(self.hover_snap)
                self._preview()
                return {"RUNNING_MODAL"}
            if (Vector(self.hover_snap["world_co"]) - Vector(self.previous_snap["world_co"])).length < 1e-6:
                self.report(messages.WARNING, messages.DIFFERENT_END_POINT_REQUIRED)
                return {"RUNNING_MODAL"}
            self._commit_member(context, copy_snap(self.hover_snap))
            push_undo_step("Create Dimension Set Member")
            self._preview()
            return {"RUNNING_MODAL"}
        if event.type in {"ESC", "RIGHTMOUSE"}:
            clear_preview_state()
            return {"FINISHED"} if self.set_object_name else {"CANCELLED"}
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def _commit_member(self, context, end_snap):
        obj = bpy.data.objects.get(self.set_object_name) if self.set_object_name else None
        if obj is None:
            obj = create_dimension_object(context, f"DIM {self.set_kind.title()} Set")
            props = obj.dimension_props
            props.annotation_kind = "DIMENSION_SET"
            props.set_kind = self.set_kind
            props.offset_distance = get_preferences(context).default_offset_distance
            view_direction = context.region_data.view_rotation @ Vector((0.0, 0.0, -1.0))
            props.offset_plane_normal = tuple(view_direction.normalized())
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
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj

    def _preview(self):
        preview = {
            "state": "PICK_SET_DATUM" if self.datum_snap is None else "PICK_SET_MEMBER",
            "tool_label": "CHAIN" if self.set_kind == "CHAIN" else "BASELINE",
        }
        if self.datum_snap is not None:
            preview["start_world"] = self.previous_snap["world_co"] if self.set_kind == "CHAIN" else self.datum_snap["world_co"]
        if self.hover_snap is not None:
            preview["hover_screen"] = self.hover_snap.get("screen_co")
            preview["hover_type"] = self.hover_snap.get("type", "WORLD")
            preview["end_world"] = self.hover_snap["world_co"]
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
        obj = _set_object(context, self.object_name)
        if obj is None or obj.dimension_props.set_kind != "CHAIN" or is_read_only_dimensions_object(obj):
            self.report(messages.WARNING, messages.MANAGER_ITEM_MISSING)
            return {"CANCELLED"}
        self.object_name = obj.name
        self.member_index = self.member_index if self.member_index >= 0 else obj.dimension_props.active_set_member_index
        self.hover_snap = None
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        obj = _set_object(context, self.object_name)
        if obj is None:
            clear_preview_state()
            return {"CANCELLED"}
        if event.type == "MOUSEMOVE":
            self.hover_snap = find_nearest_snap_point(context, event.mouse_region_x, event.mouse_region_y, include_free=True)
            if self.hover_snap is not None:
                set_preview_state({"state": "INSERT_SET_MEMBER", "hover_screen": self.hover_snap.get("screen_co")})
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS" and self.hover_snap is not None:
            props = obj.dimension_props
            anchor = _anchor_snapshot_from_snap(props, self.hover_snap)
            insert_chain_anchor(props, self.member_index, anchor)
            clear_preview_state()
            return {"FINISHED"}
        if event.type in {"ESC", "RIGHTMOUSE"}:
            clear_preview_state()
            return {"CANCELLED"}
        return {"PASS_THROUGH"} if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"} else {"RUNNING_MODAL"}


classes = (
    DIMENSIONS_OT_CreateDimensionSet,
    DIMENSIONS_OT_DeleteDimensionSetMember,
    DIMENSIONS_OT_InsertDimensionSetMember,
)
