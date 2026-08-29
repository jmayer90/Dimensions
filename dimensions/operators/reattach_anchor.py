import bpy

from .. import messages
from ..anchors import resolve_anchor, set_anchor_from_snap
from ..drawing import clear_preview_state, set_preview_state
from ..properties import is_dimension_object, is_guide_object, is_read_only_dimensions_object
from ..snapping import copy_snap, find_nearest_snap_point
from ..snap_targets import handle_snap_target_event


class CADDIM_OT_ReattachAnchor(bpy.types.Operator):
    bl_idname = "dimensions.reattach_anchor"
    bl_label = "Reattach Dimension Anchor"
    bl_options = {"REGISTER", "UNDO"}

    anchor_name: bpy.props.EnumProperty(
        name="Anchor",
        items=[
            ("START", "Start", "Reattach the start anchor"),
            ("CENTER", "Center", "Reattach the angle vertex anchor"),
            ("END", "End", "Reattach the end anchor"),
            ("ANGLE_A_START", "First Edge Start", "Reattach the first edge start"),
            ("ANGLE_A_END", "First Edge End", "Reattach the first edge end"),
            ("ANGLE_B_START", "Second Edge Start", "Reattach the second edge start"),
            ("ANGLE_B_END", "Second Edge End", "Reattach the second edge end"),
            ("SET_START", "Set Member Start", "Reattach the selected set member start"),
            ("SET_END", "Set Member End", "Reattach the selected set member end"),
            ("CIRCLE_VERTEX", "Circle Source Point", "Reattach one fitted circle point"),
        ],
    )
    member_index: bpy.props.IntProperty(default=-1)

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            self.report(messages.WARNING, messages.REATTACH_REQUIRE_OBJECT_MODE)
            return {"CANCELLED"}

        active_object = context.view_layer.objects.active
        is_point = (
            is_guide_object(active_object)
            and getattr(active_object.guide_props, "kind", "GUIDE") == "POINT"
        )
        if (not is_dimension_object(active_object) and not is_point) or is_read_only_dimensions_object(active_object):
            self.report(messages.WARNING, messages.SELECT_DIMENSION_FIRST)
            return {"CANCELLED"}

        self.dimension_object = active_object
        self.guide_point_object = active_object if is_point else None
        self.hover_snap = None

        self._update_preview()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            clear_preview_state()
            return {"CANCELLED"}
        if handle_snap_target_event(context, event):
            self._update_preview()
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            self.hover_snap = find_nearest_snap_point(
                context,
                event.mouse_region_x,
                event.mouse_region_y,
                include_free=True,
            )
            self._update_preview()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.hover_snap is None:
                self.hover_snap = find_nearest_snap_point(
                    context,
                    event.mouse_region_x,
                    event.mouse_region_y,
                    include_free=True,
                )
            if self.hover_snap is None:
                return {"RUNNING_MODAL"}

            anchor = self._get_target_anchor()
            set_anchor_from_snap(anchor, self.hover_snap)
            from ..scene_sync import sync_scene_objects

            sync_scene_objects(context.scene)
            clear_preview_state()
            self.report(messages.INFO, messages.reattached_anchor(self.anchor_name))
            return {"FINISHED"}

        if event.type in {"RIGHTMOUSE", "ESC"}:
            clear_preview_state()
            return {"CANCELLED"}

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}

        return {"RUNNING_MODAL"}

    def _get_target_anchor(self):
        if self.guide_point_object is not None:
            return self.guide_point_object.guide_props.start
        props = self.dimension_object.dimension_props
        if self.anchor_name in {"SET_START", "SET_END"}:
            index = self.member_index if self.member_index >= 0 else props.active_set_member_index
            member = props.set_members[index]
            return member.start if self.anchor_name == "SET_START" else member.end
        if self.anchor_name == "CIRCLE_VERTEX":
            return props.circle_vertices[self.member_index]
        return {
            "START": props.start,
            "CENTER": props.center,
            "END": props.end,
            "ANGLE_A_START": props.angle_a_start,
            "ANGLE_A_END": props.angle_a_end,
            "ANGLE_B_START": props.angle_b_start,
            "ANGLE_B_END": props.angle_b_end,
        }[self.anchor_name]

    def _update_preview(self):
        if self.guide_point_object is not None:
            preview = {"state": "REATTACH_START"}
            if self.hover_snap is not None:
                preview.update({
                    "hover_screen": self.hover_snap["screen_co"],
                    "hover_type": self.hover_snap.get("type", "WORLD"),
                    "hover_label": self.hover_snap.get("label", "Point"),
                    "hover_snap": copy_snap(self.hover_snap),
                })
            set_preview_state(preview)
            return
        props = self.dimension_object.dimension_props
        if self.anchor_name == "CIRCLE_VERTEX":
            start_world = end_world = resolve_anchor(props.circle_vertices[self.member_index])
        elif self.anchor_name in {"SET_START", "SET_END"}:
            index = self.member_index if self.member_index >= 0 else props.active_set_member_index
            member = props.set_members[index]
            start_world = resolve_anchor(member.start)
            end_world = resolve_anchor(member.end)
        else:
            start_world = resolve_anchor(props.start)
            end_world = resolve_anchor(props.end)

        preview = {
            "state": f"REATTACH_{self.anchor_name}",
            "dimension_type": props.dimension_type,
            "measurement_mode": props.measurement_mode,
            "offset_distance": props.offset_distance,
            "offset_angle": props.offset_angle,
            "offset_plane_normal": tuple(props.offset_plane_normal),
        }

        if self.hover_snap is not None:
            preview["hover_screen"] = self.hover_snap["screen_co"]
            preview["hover_type"] = self.hover_snap.get("type", "WORLD")
            preview["hover_label"] = self.hover_snap.get("label", "Point")
            preview["hover_snap"] = copy_snap(self.hover_snap)

        if self.anchor_name in {"START", "ANGLE_A_START"}:
            preview["start_world"] = self.hover_snap["world_co"] if self.hover_snap is not None else start_world
            preview["end_world"] = end_world
        elif self.anchor_name == "CENTER":
            preview["start_world"] = start_world
            preview["end_world"] = end_world
        else:
            preview["start_world"] = start_world
            preview["end_world"] = self.hover_snap["world_co"] if self.hover_snap is not None else end_world

        set_preview_state(preview)
