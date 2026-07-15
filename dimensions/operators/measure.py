import bpy

from ..anchors import set_world_anchor
from ..collections import create_measurement_object, ensure_measurement_snap_proxy
from ..drawing import clear_measure_state, set_measure_state
from ..interaction import (
    axis_from_event,
    axis_from_mouse_direction,
    constrained_delta,
    is_confirm_event,
    is_navigation_event,
    update_distance_text,
)
from ..snapping import copy_snap, find_nearest_snap_point
from ..units import parse_distance_input


class CADDIM_OT_Measure(bpy.types.Operator):
    """Create a persistent finite construction measurement."""

    bl_idname = "dimensions.measure"
    bl_label = "Measure"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.mode != "OBJECT":
            self.report({"ERROR"}, "Measure works in Object Mode from a 3D View")
            return {"CANCELLED"}

        self.state = "PICK_START"
        self.axis = "ALIGNED"
        self.start_world = None
        self.start_snap = None
        self.end_world = None
        self.hover_snap = None
        self.distance_text = ""
        self.distance_input_valid = True
        self.axis_gesture_active = False
        self._update_overlay(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            clear_measure_state()
            return {"CANCELLED"}

        if event.type == "MIDDLEMOUSE" and self.state == "PICK_END":
            if event.value == "PRESS":
                self.axis_gesture_active = True
                self._update_axis_gesture(context, event)
                self._update_overlay(context)
                return {"RUNNING_MODAL"}
            if event.value == "RELEASE" and self.axis_gesture_active:
                self.axis_gesture_active = False
                self._update_overlay(context)
                return {"RUNNING_MODAL"}

        axis = axis_from_event(event)
        if axis is not None:
            self.axis = axis
            self._update_effective_end(context)
            self._update_overlay(context)
            self.report({"INFO"}, f"Measurement direction: {self.axis.title()}")
            return {"RUNNING_MODAL"}

        if self.state == "PICK_END":
            new_text, handled = update_distance_text(self.distance_text, event)
            if handled:
                self.distance_text = new_text
                self._update_effective_end(context)
                self._update_overlay(context)
                return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            if self.axis_gesture_active:
                self._update_axis_gesture(context, event)
            self.hover_snap = self._find_snap(context, event)
            self._update_effective_end(context)
            self._update_overlay(context)
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.hover_snap is None:
                self.hover_snap = self._find_snap(context, event)
            if self.hover_snap is None:
                return {"RUNNING_MODAL"}
            if self.state == "PICK_START":
                self.start_snap = copy_snap(self.hover_snap)
                self.start_world = self.hover_snap["world_co"].copy()
                self.end_world = self.start_world.copy()
                self.state = "PICK_END"
                self._update_overlay(context)
                return {"RUNNING_MODAL"}
            return self._commit(context)

        if is_confirm_event(event):
            if self.state == "PICK_END":
                return self._commit(context)
            return {"RUNNING_MODAL"}

        if event.type in {"BACK_SPACE", "DEL"} and event.value == "PRESS":
            self._clear(context)
            return {"RUNNING_MODAL"}

        if event.type == "ESC" and event.value == "PRESS":
            if self.distance_text:
                self.distance_text = ""
                self._update_effective_end(context)
                self._update_overlay(context)
                return {"RUNNING_MODAL"}
            if self.state != "PICK_START":
                self._clear(context)
                return {"RUNNING_MODAL"}
            clear_measure_state()
            return {"CANCELLED"}

        if event.type == "RIGHTMOUSE" and event.value == "PRESS":
            clear_measure_state()
            return {"CANCELLED"}

        if is_navigation_event(event):
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def _update_effective_end(self, context):
        if self.start_world is None or self.hover_snap is None:
            return
        raw_delta = self.hover_snap["world_co"] - self.start_world
        direction = constrained_delta(raw_delta, self.axis)
        if direction.length < 1e-8:
            self.end_world = self.start_world.copy()
            return
        if self.distance_text.strip():
            try:
                distance = parse_distance_input(context, self.distance_text)
            except (TypeError, ValueError):
                self.distance_input_valid = False
                self.end_world = self.start_world + direction
                return
            self.distance_input_valid = True
            direction.normalize()
            self.end_world = self.start_world + direction * distance
        else:
            self.distance_input_valid = True
            self.end_world = self.start_world + direction

    def _commit(self, context):
        self._update_effective_end(context)
        if self.distance_text.strip() and not self.distance_input_valid:
            self.report({"WARNING"}, f"Invalid distance: {self.distance_text}")
            return {"RUNNING_MODAL"}
        if self.start_world is None or self.end_world is None or (self.end_world - self.start_world).length < 1e-6:
            self.report({"WARNING"}, "Choose a direction and a non-zero measurement distance")
            return {"RUNNING_MODAL"}

        obj = create_measurement_object(context)
        set_world_anchor(obj.guide_props.start, self.start_world)
        set_world_anchor(obj.guide_props.end, self.end_world)
        obj.location = (self.start_world + self.end_world) * 0.5
        ensure_measurement_snap_proxy(obj, context.scene)
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        clear_measure_state()
        self.report({"INFO"}, "Created persistent measurement")
        return {"FINISHED"}

    def _update_axis_gesture(self, context, event):
        axis = axis_from_mouse_direction(
            context,
            self.start_world,
            event.mouse_region_x,
            event.mouse_region_y,
        )
        if axis is not None:
            self.axis = axis

    def _clear(self, context):
        self.state = "PICK_START"
        self.start_world = None
        self.start_snap = None
        self.end_world = None
        self.distance_text = ""
        self.distance_input_valid = True
        self.axis_gesture_active = False
        self._update_overlay(context)

    def _update_overlay(self, context):
        state = {
            "state": self.state,
            "axis": self.axis,
            "distance_text": self.distance_text,
            "distance_input_valid": self.distance_input_valid,
            "axis_gesture_active": self.axis_gesture_active,
        }
        if self.hover_snap is not None:
            state["hover_screen"] = self.hover_snap["screen_co"]
            state["hover_type"] = self.hover_snap.get("type", "WORLD")
            state["hover_label"] = self.hover_snap.get("label", "Point")
            state["hover_snap"] = copy_snap(self.hover_snap)
        if self.start_world is not None:
            state["start_world"] = self.start_world
            state["axis_origin_world"] = self.start_world
        if self.start_snap is not None:
            state["locked_snaps"] = [copy_snap(self.start_snap)]
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
