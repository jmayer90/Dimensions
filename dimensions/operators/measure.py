import bpy

from ..drawing import clear_measure_state, set_measure_state
from ..snapping import find_nearest_snap_point


class CADDIM_OT_Measure(bpy.types.Operator):
    """Keep one quick measurement visible only while this tool is active."""

    bl_idname = "dimensions.measure"
    bl_label = "Measure"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.mode != "OBJECT":
            self.report({"ERROR"}, "Measure works in Object Mode from a 3D View")
            return {"CANCELLED"}

        self.state = "PICK_START"
        self.axis = "ALIGNED"
        self.start_world = None
        self.end_world = None
        self.hover_snap = None
        self._update_overlay()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            clear_measure_state()
            return {"CANCELLED"}

        if event.type in {"A", "X", "Y", "Z"} and event.value == "PRESS":
            self.axis = "ALIGNED" if event.type == "A" else event.type
            self._update_overlay()
            self.report({"INFO"}, f"Measurement: {self.axis.title()}")
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            self.hover_snap = self._find_snap(context, event)
            if self.state == "PICK_END" and self.hover_snap is not None:
                self.end_world = self.hover_snap["world_co"].copy()
            self._update_overlay()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.hover_snap is None:
                self.hover_snap = self._find_snap(context, event)
            if self.hover_snap is None:
                return {"RUNNING_MODAL"}
            if self.state in {"PICK_START", "COMPLETE"}:
                self._start_from_hover()
            else:
                self.end_world = self.hover_snap["world_co"].copy()
                self.state = "COMPLETE"
            self._update_overlay()
            return {"RUNNING_MODAL"}

        if event.type in {"BACK_SPACE", "DEL"} and event.value == "PRESS":
            self._clear()
            return {"RUNNING_MODAL"}

        if event.type == "ESC" and event.value == "PRESS":
            if self.state != "PICK_START":
                self._clear()
                return {"RUNNING_MODAL"}
            clear_measure_state()
            return {"CANCELLED"}

        if event.type == "RIGHTMOUSE":
            clear_measure_state()
            return {"CANCELLED"}

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def _start_from_hover(self):
        self.start_world = self.hover_snap["world_co"].copy()
        self.end_world = self.start_world.copy()
        self.state = "PICK_END"

    def _clear(self):
        self.state = "PICK_START"
        self.start_world = None
        self.end_world = None
        clear_measure_state()

    def _update_overlay(self):
        state = {"state": self.state, "axis": self.axis}
        if self.hover_snap is not None:
            state["hover_screen"] = self.hover_snap["screen_co"]
            state["hover_type"] = self.hover_snap.get("type", "WORLD")
            state["hover_label"] = self.hover_snap.get("label", "Point")
        if self.start_world is not None:
            state["start_world"] = self.start_world
        if self.end_world is not None:
            state["end_world"] = self.end_world
        set_measure_state(state)

    def _find_snap(self, context, event):
        return find_nearest_snap_point(
            context,
            event.mouse_region_x,
            event.mouse_region_y,
            include_free=True,
            plane_point=self.start_world,
        )
