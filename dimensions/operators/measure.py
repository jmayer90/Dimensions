import bpy
from mathutils import Vector

from ..anchors import set_world_anchor
from ..collections import create_measurement_object, ensure_measurement_snap_proxy
from ..drawing import clear_measure_state, set_measure_state
from ..snapping import find_nearest_snap_point
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
        self.end_world = None
        self.hover_snap = None
        self.distance_text = ""
        self.distance_input_valid = True
        self._update_overlay(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            clear_measure_state()
            return {"CANCELLED"}

        if event.type in {"A", "X", "Y", "Z"} and event.value == "PRESS":
            self.axis = "ALIGNED" if event.type == "A" else event.type
            self._update_effective_end(context)
            self._update_overlay(context)
            self.report({"INFO"}, f"Measurement direction: {self.axis.title()}")
            return {"RUNNING_MODAL"}

        if self.state == "PICK_END" and self._handle_distance_key(context, event):
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
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
                self.start_world = self.hover_snap["world_co"].copy()
                self.end_world = self.start_world.copy()
                self.state = "PICK_END"
                self._update_overlay(context)
                return {"RUNNING_MODAL"}
            return self._commit(context)

        if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            if self.state == "PICK_END":
                return self._commit(context)
            return {"RUNNING_MODAL"}

        if event.type in {"BACK_SPACE", "DEL"} and event.value == "PRESS":
            if self.state == "PICK_END" and self.distance_text:
                self.distance_text = self.distance_text[:-1]
                self._update_effective_end(context)
                self._update_overlay(context)
            else:
                self._clear(context)
            return {"RUNNING_MODAL"}

        if event.type == "ESC" and event.value == "PRESS":
            if self.state != "PICK_START":
                self._clear(context)
                return {"RUNNING_MODAL"}
            clear_measure_state()
            return {"CANCELLED"}

        if event.type == "RIGHTMOUSE":
            clear_measure_state()
            return {"CANCELLED"}

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def _handle_distance_key(self, context, event):
        if event.value != "PRESS":
            return False
        character = event.ascii
        if not character or character not in "0123456789.-/'\" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ":
            return False
        self.distance_text += character
        self._update_effective_end(context)
        self._update_overlay(context)
        return True

    def _update_effective_end(self, context):
        if self.start_world is None or self.hover_snap is None:
            return
        raw_delta = self.hover_snap["world_co"] - self.start_world
        if self.axis == "X":
            direction = Vector((raw_delta.x, 0.0, 0.0))
        elif self.axis == "Y":
            direction = Vector((0.0, raw_delta.y, 0.0))
        elif self.axis == "Z":
            direction = Vector((0.0, 0.0, raw_delta.z))
        else:
            direction = raw_delta
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

    def _clear(self, context):
        self.state = "PICK_START"
        self.start_world = None
        self.end_world = None
        self.distance_text = ""
        self.distance_input_valid = True
        self._update_overlay(context)

    def _update_overlay(self, context):
        state = {"state": self.state, "axis": "ALIGNED", "distance_text": self.distance_text}
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
