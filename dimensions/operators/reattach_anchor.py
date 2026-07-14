import bpy

from ..anchors import resolve_anchor, set_anchor_from_snap
from ..drawing import clear_preview_state, set_preview_state
from ..properties import is_dimension_object
from ..snapping import find_nearest_snap_point


class CADDIM_OT_ReattachAnchor(bpy.types.Operator):
    bl_idname = "dimensions.reattach_anchor"
    bl_label = "Reattach Dimension Anchor"
    bl_options = {"REGISTER", "UNDO"}

    anchor_name: bpy.props.EnumProperty(
        name="Anchor",
        items=[
            ("START", "Start", "Reattach the start anchor"),
            ("END", "End", "Reattach the end anchor"),
        ],
    )

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            self.report({"ERROR"}, "Run this operator from a 3D View")
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            self.report({"ERROR"}, "Anchor reattachment currently works only in Object Mode")
            return {"CANCELLED"}

        active_object = context.view_layer.objects.active
        if not is_dimension_object(active_object):
            self.report({"ERROR"}, "Select a dimension first")
            return {"CANCELLED"}

        self.dimension_object = active_object
        self.hover_snap = None

        self._update_preview()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            clear_preview_state()
            return {"CANCELLED"}

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
            clear_preview_state()
            self.report({"INFO"}, f"Reattached {self.anchor_name.lower()} anchor")
            return {"FINISHED"}

        if event.type in {"RIGHTMOUSE", "ESC"}:
            clear_preview_state()
            return {"CANCELLED"}

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}

        return {"RUNNING_MODAL"}

    def _get_target_anchor(self):
        if self.anchor_name == "START":
            return self.dimension_object.dimension_props.start

        return self.dimension_object.dimension_props.end

    def _update_preview(self):
        props = self.dimension_object.dimension_props
        start_world, _ = resolve_anchor(props.start)
        end_world, _ = resolve_anchor(props.end)

        preview = {
            "state": f"REATTACH_{self.anchor_name}",
            "dimension_type": props.dimension_type,
            "offset_distance": props.offset_distance,
            "offset_angle": props.offset_angle,
            "offset_plane_normal": tuple(props.offset_plane_normal),
        }

        if self.hover_snap is not None:
            preview["hover_screen"] = self.hover_snap["screen_co"]
            preview["hover_type"] = self.hover_snap.get("type", "WORLD")
            preview["hover_label"] = self.hover_snap.get("label", "Point")

        if self.anchor_name == "START":
            preview["start_world"] = self.hover_snap["world_co"] if self.hover_snap is not None else start_world
            preview["end_world"] = end_world
        else:
            preview["start_world"] = start_world
            preview["end_world"] = self.hover_snap["world_co"] if self.hover_snap is not None else end_world

        set_preview_state(preview)
