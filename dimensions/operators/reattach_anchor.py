import bpy

from ..interaction import modal_cleanup_on_exception

from ..viewport_state import viewport_key

from .. import messages
from ..anchors import resolve_anchor, set_anchor_from_snap
from ..drawing import clear_preview_state, set_preview_state
from ..properties import is_dimension_object, is_read_only_dimensions_object
from ..snapping import copy_snap, find_nearest_snap_point
from ..snap_targets import handle_snap_target_event


class CADDIM_OT_ReattachAnchor(bpy.types.Operator):
    bl_idname = "dimensions.reattach_anchor"
    bl_label = "Reattach Dimension Anchor"
    bl_description = "Click a new point for this end of the selected dimension; its placement is kept"
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
        ],
    )

    def invoke(self, context, event):
        self._session_viewport_key = viewport_key(context)
        if context.area is None or context.area.type != "VIEW_3D":
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            self.report(messages.WARNING, messages.REATTACH_REQUIRE_OBJECT_MODE)
            return {"CANCELLED"}

        active_object = context.view_layer.objects.active
        if not is_dimension_object(active_object) or is_read_only_dimensions_object(active_object):
            self.report(messages.WARNING, messages.SELECT_DIMENSION_FIRST)
            return {"CANCELLED"}

        self.dimension_object = active_object
        self.hover_snap = None

        self._update_preview()
        context.window_manager.modal_handler_add(self)
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
        if context.area is None or context.area.type != "VIEW_3D":
            clear_preview_state(key=getattr(self, "_session_viewport_key", None))
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
            clear_preview_state(key=getattr(self, "_session_viewport_key", None))
            self.report(messages.INFO, messages.reattached_anchor(self.anchor_name))
            return {"FINISHED"}

        if event.type in {"RIGHTMOUSE", "ESC"}:
            clear_preview_state(key=getattr(self, "_session_viewport_key", None))
            return {"CANCELLED"}

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}

        return {"RUNNING_MODAL"}

    def cancel(self, _context):
        clear_preview_state(key=getattr(self, "_session_viewport_key", None))

    def _get_target_anchor(self):
        props = self.dimension_object.dimension_props
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
        props = self.dimension_object.dimension_props
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

        set_preview_state(preview, key=getattr(self, "_session_viewport_key", None))
