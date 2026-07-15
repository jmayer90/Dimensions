import bpy

from ..anchors import set_anchor_from_snap
from ..collections import create_guide_object, remove_measurement_snap_proxies
from ..drawing import clear_guide_preview_state, set_guide_preview_state
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


class CADDIM_OT_CreateGuide(bpy.types.Operator):
    bl_idname = "dimensions.create_guide"
    bl_label = "Add Construction Guide"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.mode != "OBJECT":
            self.report({"ERROR"}, "Construction guides work in Object Mode from a 3D View")
            return {"CANCELLED"}
        self.axis = "ALIGNED"
        self.start_snap = None
        self.hover_snap = None
        self.distance_text = ""
        self.distance_input_valid = True
        self.axis_gesture_active = False
        self.state = "PICK_START"
        self._update_preview(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            clear_guide_preview_state()
            return {"CANCELLED"}

        if event.type == "MIDDLEMOUSE" and self.state == "PICK_END":
            if event.value == "PRESS":
                self.axis_gesture_active = True
                self._update_axis_gesture(context, event)
                self._update_preview(context)
                return {"RUNNING_MODAL"}
            if event.value == "RELEASE" and self.axis_gesture_active:
                self.axis_gesture_active = False
                self._update_preview(context)
                return {"RUNNING_MODAL"}

        axis = axis_from_event(event)
        if axis is not None:
            self.axis = axis
            self._update_preview(context)
            self.report({"INFO"}, f"Guide direction: {self.axis.title()}")
            return {"RUNNING_MODAL"}

        if self.state == "PICK_END":
            new_text, handled = update_distance_text(self.distance_text, event)
            if handled:
                self.distance_text = new_text
                self._update_preview(context)
                return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            if self.axis_gesture_active:
                self._update_axis_gesture(context, event)
            plane_point = self.start_snap["world_co"] if self.start_snap is not None else None
            self.hover_snap = find_nearest_snap_point(
                context,
                event.mouse_region_x,
                event.mouse_region_y,
                include_free=True,
                plane_point=plane_point,
            )
            self._update_preview(context)
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.hover_snap is None:
                plane_point = self.start_snap["world_co"] if self.start_snap is not None else None
                self.hover_snap = find_nearest_snap_point(
                    context,
                    event.mouse_region_x,
                    event.mouse_region_y,
                    include_free=True,
                    plane_point=plane_point,
                )
            if self.hover_snap is None:
                return {"RUNNING_MODAL"}
            if self.state == "PICK_START":
                self.start_snap = self._copy_snap(self.hover_snap)
                self.state = "PICK_END"
                self.distance_text = ""
                self._update_preview(context)
                return {"RUNNING_MODAL"}

            return self._commit(context)

        if is_confirm_event(event):
            if self.state == "PICK_END":
                return self._commit(context)
            return {"RUNNING_MODAL"}

        if event.type in {"BACK_SPACE", "DEL"} and event.value == "PRESS":
            if self.state == "PICK_END":
                self._reset_to_start()
                self._update_preview(context)
            return {"RUNNING_MODAL"}

        if event.type == "ESC" and event.value == "PRESS":
            if self.distance_text:
                self.distance_text = ""
                self.distance_input_valid = True
                self._update_preview(context)
                return {"RUNNING_MODAL"}
            if self.state == "PICK_END":
                self._reset_to_start()
                self._update_preview(context)
                return {"RUNNING_MODAL"}
            clear_guide_preview_state()
            return {"CANCELLED"}
        if event.type == "RIGHTMOUSE" and event.value == "PRESS":
            clear_guide_preview_state()
            return {"CANCELLED"}
        if is_navigation_event(event):
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def _commit(self, context):
        end_snap = self._effective_end_snap(context)
        if end_snap is None:
            if self.distance_text:
                self.report({"WARNING"}, f"Invalid distance: {self.distance_text}")
            return {"RUNNING_MODAL"}
        if (end_snap["world_co"] - self.start_snap["world_co"]).length < 1e-6:
            self.report({"WARNING"}, "Choose a direction and a non-zero guide distance")
            return {"RUNNING_MODAL"}
        self._create(context, end_snap)
        clear_guide_preview_state()
        return {"FINISHED"}

    def _effective_end_snap(self, context=None):
        if self.start_snap is None or self.hover_snap is None:
            return None
        snap = self._copy_snap(self.hover_snap)
        raw_delta = snap["world_co"] - self.start_snap["world_co"]
        direction = constrained_delta(raw_delta, self.axis)
        if direction.length < 1e-8:
            return None
        if self.distance_text.strip():
            try:
                direction.normalize()
                direction *= parse_distance_input(context, self.distance_text)
            except (TypeError, ValueError):
                self.distance_input_valid = False
                return None
        self.distance_input_valid = True
        constrained = (direction - raw_delta).length >= 1e-6
        if constrained:
            snap["type"] = "WORLD"
            snap["label"] = "Constrained Point"
            snap["object"] = None
            snap["vertex_index"] = -1
            for key in ("edge_index", "edge_vertices", "edge_factor", "face_index"):
                snap.pop(key, None)
        snap["world_co"] = self.start_snap["world_co"] + direction
        return snap

    def _reset_to_start(self):
        self.start_snap = None
        self.state = "PICK_START"
        self.distance_text = ""
        self.distance_input_valid = True
        self.axis_gesture_active = False

    def _update_axis_gesture(self, context, event):
        axis = axis_from_mouse_direction(
            context,
            self.start_snap["world_co"] if self.start_snap is not None else None,
            event.mouse_region_x,
            event.mouse_region_y,
        )
        if axis is not None:
            self.axis = axis

    def _create(self, context, end_snap):
        obj = create_guide_object(context)
        set_anchor_from_snap(obj.guide_props.start, self.start_snap)
        set_anchor_from_snap(obj.guide_props.end, end_snap)
        obj.guide_props.axis = self.axis
        obj.location = self.start_snap["world_co"]
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        self.report({"INFO"}, "Created construction guide")

    def _update_preview(self, context=None):
        state = {
            "axis": self.axis,
            "state": self.state,
            "distance_text": self.distance_text,
            "distance_input_valid": self.distance_input_valid,
            "axis_gesture_active": self.axis_gesture_active,
        }
        if self.hover_snap is not None:
            state["hover_screen"] = self.hover_snap["screen_co"]
            state["hover_type"] = self.hover_snap.get("type", "WORLD")
            state["hover_label"] = self.hover_snap.get("label", "Point")
            state["hover_snap"] = self._copy_snap(self.hover_snap)
        if self.start_snap is not None:
            state["start_world"] = self.start_snap["world_co"]
            state["axis_origin_world"] = self.start_snap["world_co"]
            state["locked_snaps"] = [self._copy_snap(self.start_snap)]
        if self.state == "PICK_END" and self.hover_snap is not None:
            end_snap = self._effective_end_snap(context)
            if end_snap is not None:
                state["end_world"] = end_snap["world_co"]
        set_guide_preview_state(state)

    @staticmethod
    def _copy_snap(snap):
        return copy_snap(snap)


class CADDIM_OT_ClearGuides(bpy.types.Operator):
    bl_idname = "dimensions.clear_guides"
    bl_label = "Clear All Guides"
    bl_description = "Delete every construction guide in this scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        guide_objects = [
            obj for obj in context.scene.objects
            if hasattr(obj, "guide_props")
            and obj.guide_props.enabled
            and getattr(obj.guide_props, "kind", "GUIDE") == "GUIDE"
        ]
        for obj in guide_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        self.report({"INFO"}, f"Removed {len(guide_objects)} construction guide(s)")
        return {"FINISHED"}


class CADDIM_OT_ClearMeasurements(bpy.types.Operator):
    bl_idname = "dimensions.clear_measurements"
    bl_label = "Clear All Measurements"
    bl_description = "Delete every persistent measurement in this scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        measurement_objects = [
            obj for obj in context.scene.objects
            if hasattr(obj, "guide_props")
            and obj.guide_props.enabled
            and getattr(obj.guide_props, "kind", "GUIDE") == "MEASUREMENT"
        ]
        for obj in measurement_objects:
            remove_measurement_snap_proxies(obj)
            bpy.data.objects.remove(obj, do_unlink=True)
        self.report({"INFO"}, f"Removed {len(measurement_objects)} measurement(s)")
        return {"FINISHED"}
