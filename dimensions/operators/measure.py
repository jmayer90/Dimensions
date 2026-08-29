import bpy

from .. import messages
from ..anchors import set_world_anchor
from ..collections import create_measurement_object, ensure_measurement_snap_proxy
from ..drawing import clear_measure_state, set_measure_state
from ..interaction import (
    axis_from_event,
    axis_from_mouse_direction,
    continuous_placement_enabled,
    constrained_delta,
    is_confirm_event,
    is_navigation_event,
    push_undo_step,
    remember_session_context,
    session_axis,
    session_context_changed,
    update_distance_text,
)
from ..snapping import copy_snap, find_nearest_snap_point
from ..inference import InferenceSession, cycle_local_axis, handle_inference_event, inference_status
from ..snap_targets import handle_snap_target_event
from ..units import parse_distance_input
from ..measurement_query import format_measurement_query
from ..keymaps import modal_action_from_event


class CADDIM_OT_Measure(bpy.types.Operator):
    """Transient tape measure; persistence is an explicit in-tool action."""

    bl_idname = "dimensions.measure"
    bl_label = "Measure"
    bl_description = "Measure transiently; press P to save the current segment"
    bl_options = {"REGISTER"}

    persistent_mode = False

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.mode not in {"OBJECT", "EDIT_MESH"}:
            self.report(messages.WARNING, messages.MEASURE_REQUIRE_SUPPORTED_MODE)
            return {"CANCELLED"}

        self.state = "PICK_START"
        self.axis = session_axis(context)
        self.continuous_placement = True if not self.persistent_mode else continuous_placement_enabled(context)
        self.start_world = None
        self.start_snap = None
        self.end_world = None
        self.hover_snap = None
        self.distance_text = ""
        self.distance_input_valid = True
        self.axis_gesture_active = False
        self.inference_session = InferenceSession()
        self.completed_start_world = None
        self.completed_end_world = None
        remember_session_context(self, context)
        self._update_overlay(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            clear_measure_state(context)
            return {"CANCELLED"}
        if self.continuous_placement and session_context_changed(self, context):
            clear_measure_state(context)
            return {"CANCELLED"}
        if handle_snap_target_event(context, event):
            self._update_overlay(context)
            return {"RUNNING_MODAL"}
        if handle_inference_event(self.inference_session, event):
            self._update_overlay(context)
            return {"RUNNING_MODAL"}
        action = modal_action_from_event(event)
        if not self.persistent_mode and action == "SAVE_TRANSIENT_MEASURE":
            return self._save_transient(context)
        if not self.persistent_mode and action == "COPY_TRANSIENT_MEASURE":
            return self._copy_transient(context)

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
            self.axis = cycle_local_axis(self.axis, axis, context)
            self._update_effective_end(context)
            self._update_overlay(context)
            self.report(messages.INFO, messages.measurement_direction(self.axis.title()))
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
            return self._commit(context) if self.persistent_mode else self._accept_transient(context)

        if is_confirm_event(event):
            if self.state == "PICK_END":
                return self._commit(context) if self.persistent_mode else self._accept_transient(context)
            return {"RUNNING_MODAL"}

        if event.type in {"BACK_SPACE", "DEL"} and event.value == "PRESS":
            self._clear(context)
            return {"RUNNING_MODAL"}

        if event.type == "ESC" and event.value == "PRESS":
            if self.continuous_placement:
                clear_measure_state(context)
                return {"CANCELLED"}
            if self.distance_text:
                self.distance_text = ""
                self._update_effective_end(context)
                self._update_overlay(context)
                return {"RUNNING_MODAL"}
            if self.state != "PICK_START":
                self._clear(context)
                return {"RUNNING_MODAL"}
            clear_measure_state(context)
            return {"CANCELLED"}

        if event.type == "RIGHTMOUSE" and event.value == "PRESS":
            clear_measure_state(context)
            return {"CANCELLED"}

        if is_navigation_event(event):
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def cancel(self, _context):
        clear_measure_state(_context)

    def _update_effective_end(self, context):
        if self.start_world is None or self.hover_snap is None:
            return
        raw_delta = self.hover_snap["world_co"] - self.start_world
        direction = constrained_delta(raw_delta, self.axis, context)
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
            self.report(messages.WARNING, messages.invalid_distance(self.distance_text))
            return {"RUNNING_MODAL"}
        if self.start_world is None or self.end_world is None or (self.end_world - self.start_world).length < 1e-6:
            self.report(messages.WARNING, messages.MEASUREMENT_DIRECTION_DISTANCE_REQUIRED)
            return {"RUNNING_MODAL"}

        self._create_persistent(context, self.start_world, self.end_world, select=True)
        self.report(messages.INFO, messages.CREATED_MEASUREMENT)
        return self._after_commit(context)

    def _accept_transient(self, context):
        segment = self._current_segment(context)
        if segment is None:
            self.report(messages.WARNING, messages.MEASUREMENT_DIRECTION_DISTANCE_REQUIRED)
            return {"RUNNING_MODAL"}
        self.completed_start_world = segment[0].copy()
        self.completed_end_world = segment[1].copy()
        self.start_world = segment[1].copy()
        self.start_snap = copy_snap(self.hover_snap) if self.hover_snap is not None else None
        self.end_world = None
        self.hover_snap = None
        self.distance_text = ""
        self.distance_input_valid = True
        self.state = "PICK_END"
        self._update_overlay(context)
        return {"RUNNING_MODAL"}

    def _save_transient(self, context):
        segment = self._current_segment(context, allow_completed=True)
        if segment is None:
            self.report(messages.WARNING, messages.MEASUREMENT_REQUIRED_TO_SAVE)
            return {"RUNNING_MODAL"}
        self._create_persistent(context, segment[0], segment[1], select=False)
        self.report(messages.INFO, messages.SAVED_TRANSIENT_MEASUREMENT)
        return {"RUNNING_MODAL"}

    def _copy_transient(self, context):
        segment = self._current_segment(context, allow_completed=True)
        if segment is None:
            self.report(messages.WARNING, messages.MEASUREMENT_REQUIRED_TO_SAVE)
            return {"RUNNING_MODAL"}
        context.window_manager.clipboard = self._formatted_query(context, *segment)["clipboard"]
        self.report(messages.INFO, messages.COPIED_TRANSIENT_MEASUREMENT)
        return {"RUNNING_MODAL"}

    def _current_segment(self, context, allow_completed=False):
        self._update_effective_end(context)
        if self.start_world is not None and self.end_world is not None:
            if (self.end_world - self.start_world).length >= 1e-6:
                return self.start_world, self.end_world
        if allow_completed and self.completed_start_world is not None and self.completed_end_world is not None:
            return self.completed_start_world, self.completed_end_world
        return None

    def _create_persistent(self, context, start, end, select=False):
        obj = create_measurement_object(context)
        set_world_anchor(obj.guide_props.start, start)
        set_world_anchor(obj.guide_props.end, end)
        obj.location = (start + end) * 0.5
        ensure_measurement_snap_proxy(obj, context.scene)
        if select and context.mode == "OBJECT":
            for selected in context.selected_objects:
                selected.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
        return obj

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
        self.inference_session.clear()
        self.completed_start_world = None
        self.completed_end_world = None
        self._update_overlay(context)

    def _after_commit(self, context):
        if not self.continuous_placement:
            clear_measure_state(context)
            return {"FINISHED"}
        push_undo_step("Create Measurement")
        self._clear(context)
        self.hover_snap = None
        remember_session_context(self, context)
        self._update_overlay(context)
        return {"RUNNING_MODAL"}

    def _update_overlay(self, context):
        state = {
            "tool_label": "MEASURE" if self.persistent_mode else "TAPE",
            "state": self.state,
            "axis": self.axis,
            "distance_text": self.distance_text,
            "distance_input_valid": self.distance_input_valid,
            "axis_gesture_active": self.axis_gesture_active,
            "continuous_placement": self.continuous_placement,
            "transient_measure": not self.persistent_mode,
        }
        status = inference_status(self.inference_session)
        if status:
            state["inference_status"] = status
        if self.hover_snap is not None:
            state["hover_screen"] = self.hover_snap["screen_co"]
            state["hover_type"] = self.hover_snap.get("type", "WORLD")
            state["hover_label"] = self.hover_snap.get("label", "Point")
            state["hover_snap"] = copy_snap(self.hover_snap)
        display_segment = self._display_segment()
        if display_segment is not None:
            state["start_world"] = display_segment[0]
            state["end_world"] = display_segment[1]
            state["axis_origin_world"] = display_segment[0]
            if not self.persistent_mode:
                state["measurement_lines"] = self._formatted_query(context, *display_segment)["lines"]
        elif self.start_world is not None:
            state["start_world"] = self.start_world
            state["axis_origin_world"] = self.start_world
        if self.start_snap is not None:
            state["locked_snaps"] = [copy_snap(self.start_snap)]
        set_measure_state(state, context)

    def _display_segment(self):
        if self.start_world is not None and self.end_world is not None and (self.end_world - self.start_world).length >= 1e-8:
            return self.start_world, self.end_world
        if self.completed_start_world is not None and self.completed_end_world is not None:
            return self.completed_start_world, self.completed_end_world
        return None

    @staticmethod
    def _formatted_query(context, start, end):
        settings = getattr(context.scene, "dimensions_settings", None)
        precision = settings.precision if settings is not None else 3
        return format_measurement_query(context, start, end, precision)

    def _find_snap(self, context, event):
        return find_nearest_snap_point(
            context,
            event.mouse_region_x,
            event.mouse_region_y,
            include_free=True,
            plane_point=self.start_world,
            inference_session=self.inference_session,
            inference_origin=self.start_world,
            inference_axis=self.axis,
        )


class CADDIM_OT_PersistentMeasure(CADDIM_OT_Measure):
    """Direct invocation of the former save-on-confirm measurement workflow."""

    bl_idname = "dimensions.measure_persistent"
    bl_label = "Measure (Persistent)"
    bl_description = "Create a saved construction measurement directly"
    bl_options = {"REGISTER", "UNDO"}

    persistent_mode = True
