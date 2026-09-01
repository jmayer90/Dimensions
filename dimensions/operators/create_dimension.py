import bpy
from mathutils.geometry import intersect_line_plane
from mathutils import Vector

from .. import messages
from ..anchors import set_anchor_from_snap
from ..collections import create_dimension_object
from ..constants import DEFAULT_OFFSET_DISTANCE
from ..drawing import (
    clear_preview_state,
    get_dimension_world_geometry,
    get_measure_world_points,
    get_offset_basis,
    set_preview_state,
)
from ..interaction import (
    axis_label,
    axis_from_event,
    axis_from_mouse_direction,
    axis_world_direction,
    constrained_delta,
    continuous_placement_enabled,
    is_confirm_event,
    is_navigation_event,
    push_undo_step,
    remember_session_context,
    session_axis,
    session_context_changed,
    update_distance_text,
)
from ..modal_state import PointPlacementState
from ..inference import InferenceSession, cycle_local_axis, handle_inference_event, inference_status
from ..preferences import get_preferences
from ..snap_targets import handle_snap_target_event
from ..snapping import copy_snap, find_nearest_snap_point, get_mouse_ray, has_view3d_window_region
from ..units import parse_distance_input
from .selection_annotations import create_dimension_from_selected_edge


class CADDIM_OT_CreateDimension(bpy.types.Operator):
    bl_idname = "dimensions.create_dimension"
    bl_label = "Create Dimension"
    bl_description = "Create from one selected Edit Mode edge, or interactively pick two points"
    bl_options = {"REGISTER", "UNDO"}

    # The state machine owns the interaction contract; these expose it under the
    # names the operator body and the preview payload already use.
    @property
    def state(self):
        return self._state_machine.stage

    @property
    def dimension_type(self):
        return self._state_machine.axis

    @dimension_type.setter
    def dimension_type(self, value):
        self._state_machine.axis = value

    @property
    def distance_text(self):
        return self._state_machine.numeric_text

    @distance_text.setter
    def distance_text(self, value):
        self._state_machine.set_numeric_text(value, self._state_machine.numeric_valid)

    @property
    def distance_input_valid(self):
        return self._state_machine.numeric_valid

    @distance_input_valid.setter
    def distance_input_valid(self, value):
        self._state_machine.numeric_valid = bool(value)

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}

        if context.mode not in {"OBJECT", "EDIT_MESH"}:
            self.report(messages.WARNING, messages.DIMENSIONS_REQUIRE_SUPPORTED_MODE)
            return {"CANCELLED"}

        continuous_placement = continuous_placement_enabled(context)
        if context.mode == "EDIT_MESH":
            dimension = create_dimension_from_selected_edge(context)
            if dimension is not None:
                self.report(messages.INFO, messages.CREATED_SELECTED_EDGE)
                if not continuous_placement:
                    return {"FINISHED"}
                push_undo_step("Create Dimension")

        self.continuous_placement = continuous_placement
        self._state_machine = PointPlacementState(axis=session_axis(context))
        self.hover_snap = None
        self.hover_mouse = None
        self.start_snap = None
        self.end_snap = None
        self.offset_distance = getattr(get_preferences(context), "default_offset_distance", DEFAULT_OFFSET_DISTANCE)
        self.offset_plane_normal = None
        self.axis_gesture_active = False
        self.inference_axis = self.dimension_type
        self.inference_session = InferenceSession()
        remember_session_context(self, context)

        self._update_preview()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            clear_preview_state()
            return {"CANCELLED"}
        if self.continuous_placement and session_context_changed(self, context):
            clear_preview_state()
            return {"CANCELLED"}
        if handle_snap_target_event(context, event):
            self._update_preview()
            return {"RUNNING_MODAL"}
        if handle_inference_event(self.inference_session, event):
            self._update_preview()
            return {"RUNNING_MODAL"}

        if event.type == "MIDDLEMOUSE" and self.state == "SET_OFFSET":
            if event.value == "PRESS":
                self.axis_gesture_active = True
                self._update_axis_gesture(context, event)
                self._update_preview()
                return {"RUNNING_MODAL"}
            if event.value == "RELEASE" and self.axis_gesture_active:
                self.axis_gesture_active = False
                self._update_preview()
                return {"RUNNING_MODAL"}

        axis = axis_from_event(event)
        if axis is not None and self.state in {"PICK_START", "SET_OFFSET"}:
            self.inference_axis = cycle_local_axis(self.inference_axis, axis, context)
            self.dimension_type = "ALIGNED" if self.inference_axis.startswith("LOCAL_") else self.inference_axis
            if self.state == "SET_OFFSET":
                self._configure_offset_plane(context)
                if self.distance_text:
                    self._apply_numeric_input(context)
                else:
                    self._update_offset(context, event.mouse_region_x, event.mouse_region_y)
            self._update_preview()
            self.report(messages.INFO, messages.extension_axis(axis_label(self.inference_axis)))
            return {"RUNNING_MODAL"}

        if self.state in {"PICK_END", "SET_OFFSET"}:
            new_text, handled = update_distance_text(self.distance_text, event)
            if handled:
                self.distance_text = new_text
                self._apply_numeric_input(context)
                self._update_preview()
                return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            if self.axis_gesture_active:
                self._update_axis_gesture(context, event)
            if self.state in {"PICK_START", "PICK_END"}:
                plane_point = self.start_snap["world_co"] if self.start_snap is not None else None
                self.hover_snap = find_nearest_snap_point(
                    context,
                    event.mouse_region_x,
                    event.mouse_region_y,
                    include_free=True,
                    plane_point=plane_point,
                    inference_session=self.inference_session,
                    inference_origin=plane_point,
                    inference_axis=self.inference_axis,
                )
                self.hover_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            elif self.state == "SET_OFFSET" and not self.distance_text:
                self._update_offset(context, event.mouse_region_x, event.mouse_region_y)

            self._update_preview()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.state == "PICK_START":
                click_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
                if self.hover_snap is None or self.hover_mouse is None or click_mouse != self.hover_mouse:
                    self.hover_snap = find_nearest_snap_point(
                        context,
                        event.mouse_region_x,
                        event.mouse_region_y,
                        include_free=True,
                        inference_session=self.inference_session,
                        inference_axis=self.inference_axis,
                    )
                    self.hover_mouse = click_mouse
                if self.hover_snap is None:
                    return {"RUNNING_MODAL"}

                return self._accept_start()

            if self.state == "PICK_END":
                click_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
                if self.hover_snap is None or self.hover_mouse is None or click_mouse != self.hover_mouse:
                    self.hover_snap = find_nearest_snap_point(
                        context,
                        event.mouse_region_x,
                        event.mouse_region_y,
                        include_free=True,
                        plane_point=self.start_snap["world_co"],
                        inference_session=self.inference_session,
                        inference_origin=self.start_snap["world_co"],
                        inference_axis=self.inference_axis,
                    )
                    self.hover_mouse = click_mouse
                if self.hover_snap is None:
                    return {"RUNNING_MODAL"}

                return self._accept_end(context)

            if self.state == "SET_OFFSET":
                if self.distance_text and not self.distance_input_valid:
                    self.report(messages.WARNING, messages.invalid_distance(self.distance_text))
                    return {"RUNNING_MODAL"}
                if self._create_dimension(context):
                    return self._after_commit(context)
                return {"RUNNING_MODAL"}

        if is_confirm_event(event):
            if self.state == "PICK_START":
                if self.hover_snap is not None:
                    return self._accept_start()
                return {"RUNNING_MODAL"}
            if self.state == "PICK_END":
                return self._accept_end(context)
            if self.state == "SET_OFFSET":
                if self.distance_text and not self.distance_input_valid:
                    self.report(messages.WARNING, messages.invalid_distance(self.distance_text))
                    return {"RUNNING_MODAL"}
                if self._create_dimension(context):
                    return self._after_commit(context)
                return {"RUNNING_MODAL"}

        if event.type in {"BACK_SPACE", "DEL"} and event.value == "PRESS":
            self._step_back()
            self._update_preview()
            return {"RUNNING_MODAL"}

        if event.type == "ESC" and event.value == "PRESS":
            if self.continuous_placement:
                clear_preview_state()
                return {"CANCELLED"}
            if self.distance_text:
                self.distance_text = ""
                self.distance_input_valid = True
                self._update_preview()
                return {"RUNNING_MODAL"}
            if self.state != "PICK_START":
                self._step_back()
                self._update_preview()
                return {"RUNNING_MODAL"}
            clear_preview_state()
            return {"CANCELLED"}

        if event.type == "RIGHTMOUSE" and event.value == "PRESS":
            clear_preview_state()
            return {"CANCELLED"}

        if is_navigation_event(event):
            return {"PASS_THROUGH"}

        return {"RUNNING_MODAL"}

    def cancel(self, _context):
        clear_preview_state()

    def _accept_start(self):
        if self.hover_snap is None:
            return {"RUNNING_MODAL"}
        self.start_snap = self._copy_snap(self.hover_snap)
        self._state_machine.accept_point()
        self.distance_text = ""
        self.distance_input_valid = True
        self._update_preview()
        return {"RUNNING_MODAL"}

    def _accept_end(self, context):
        effective_end = self._effective_end_snap(context)
        if effective_end is None:
            if self.distance_text:
                self.report(messages.WARNING, messages.invalid_distance(self.distance_text))
            else:
                # A second pick on the first point cannot define a dimension. Say so
                # rather than refusing the stage silently.
                self.report(messages.WARNING, messages.DIFFERENT_END_POINT_REQUIRED)
            return {"RUNNING_MODAL"}
        self.end_snap = effective_end
        if (self.end_snap["world_co"] - self.start_snap["world_co"]).length < 1e-6:
            self.report(messages.WARNING, messages.DIFFERENT_END_POINT_REQUIRED)
            self.end_snap = None
            return {"RUNNING_MODAL"}

        self.distance_text = ""
        self.distance_input_valid = True
        self._begin_offset_stage(context)
        self._state_machine.accept_point()
        self._update_preview()
        return {"RUNNING_MODAL"}

    def _effective_end_snap(self, context):
        if self.start_snap is None or self.hover_snap is None:
            return None
        snap = self._copy_snap(self.hover_snap)
        raw_delta = snap["world_co"] - self.start_snap["world_co"]
        direction = constrained_delta(raw_delta, self.dimension_type, context)
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
        if self.dimension_type == "ALIGNED" and not self.distance_text.strip():
            return snap
        snap["type"] = "WORLD"
        snap["label"] = "Typed Point" if self.distance_text.strip() else "Constrained Point"
        snap["object"] = None
        snap["vertex_index"] = -1
        for key in ("edge_index", "edge_vertices", "edge_factor", "face_index"):
            snap.pop(key, None)
        snap["world_co"] = self.start_snap["world_co"] + direction
        return snap

    def _apply_numeric_input(self, context):
        if not self.distance_text.strip():
            self.distance_input_valid = True
            return
        if self.state == "PICK_END":
            self._effective_end_snap(context)
            return
        try:
            self.offset_distance = parse_distance_input(context, self.distance_text)
        except (TypeError, ValueError):
            self.distance_input_valid = False
            return
        self.distance_input_valid = True

    def _step_back(self):
        self.distance_text = ""
        self.distance_input_valid = True
        self.axis_gesture_active = False
        self.inference_axis = self.dimension_type
        self.inference_session.clear()
        previous_state = self.state
        transition = self._state_machine.step_back()
        if transition == "CANCELLED":
            return
        if previous_state == "SET_OFFSET":
            self.end_snap = None
            self.offset_plane_normal = None
        elif previous_state == "PICK_END":
            self.start_snap = None
            self.end_snap = None
            self.offset_plane_normal = None

    def _update_axis_gesture(self, context, event):
        if self.start_snap is None or self.end_snap is None:
            return
        origin = (self.start_snap["world_co"] + self.end_snap["world_co"]) * 0.5
        axis = axis_from_mouse_direction(
            context,
            origin,
            event.mouse_region_x,
            event.mouse_region_y,
        )
        if axis is None:
            return
        self.dimension_type = axis
        self.inference_axis = axis
        self._configure_offset_plane(context)
        if self.distance_text:
            self._apply_numeric_input(context)
        else:
            self._update_offset(context, event.mouse_region_x, event.mouse_region_y)

    def _update_offset(self, context, mouse_x, mouse_y):
        if self.start_snap is None or self.end_snap is None:
            return

        if not has_view3d_window_region(context):
            return

        start_world = self.start_snap["world_co"]
        end_world = self.end_snap["world_co"]
        measure_start_world, measure_end_world, _value = get_measure_world_points(
            self.dimension_type,
            start_world,
            end_world,
        )
        measure_vector = measure_end_world - measure_start_world
        if measure_vector.length < 1e-6 or self.offset_plane_normal is None:
            return

        plane_point = (measure_start_world + measure_end_world) * 0.5
        plane_normal = self.offset_plane_normal
        line_origin, line_direction = get_mouse_ray(context, mouse_x, mouse_y)
        hit_point = intersect_line_plane(
            line_origin,
            line_origin + (line_direction * 100000.0),
            plane_point,
            plane_normal,
            False,
        )
        if hit_point is None:
            return

        _stable_plane_normal, offset_direction = get_offset_basis(
            self.dimension_type,
            measure_vector.normalized(),
            plane_normal,
        )
        if offset_direction.length < 1e-6:
            return

        offset_direction.normalize()
        self.offset_distance = (hit_point - plane_point).dot(offset_direction)

    def _begin_offset_stage(self, context):
        start_world = self.start_snap["world_co"]
        end_world = self.end_snap["world_co"]
        measure_start_world, measure_end_world, _value = get_measure_world_points(
            self.dimension_type,
            start_world,
            end_world,
        )
        measure_vector = measure_end_world - measure_start_world
        if measure_vector.length < 1e-6:
            self.offset_plane_normal = Vector((0.0, 0.0, 1.0))
            return

        measure_direction = measure_vector.normalized()
        view_direction = context.region_data.view_rotation @ Vector((0.0, 0.0, -1.0))
        view_direction.normalize()
        stable_plane_normal, _offset_direction = get_offset_basis(
            "ALIGNED",
            measure_direction,
            view_direction,
        )
        self.offset_plane_normal = stable_plane_normal

    def _configure_offset_plane(self, context):
        if self.dimension_type == "ALIGNED":
            self._begin_offset_stage(context)
            return

        start_world = self.start_snap["world_co"]
        end_world = self.end_snap["world_co"]
        measure_vector = end_world - start_world
        if measure_vector.length < 1e-6:
            return

        measure_direction = measure_vector.normalized()
        axis_direction = axis_world_direction(context, self.dimension_type)
        perpendicular_axis = axis_direction - measure_direction * axis_direction.dot(measure_direction)

        if perpendicular_axis.length < 1e-6:
            self._begin_offset_stage(context)
            return

        perpendicular_axis.normalize()
        self.offset_plane_normal = measure_direction.cross(perpendicular_axis).normalized()

    def _create_dimension(self, context):
        if self.start_snap is None or self.end_snap is None:
            return False

        if (self.end_snap["world_co"] - self.start_snap["world_co"]).length < 1e-6:
            self.report(messages.WARNING, messages.DIFFERENT_END_POINT_REQUIRED)
            return False

        if self.offset_plane_normal is None:
            self._begin_offset_stage(context)
            if self.offset_plane_normal is None:
                self.report(messages.WARNING, messages.DIMENSION_OFFSET_PLANE_REQUIRED)
                return False

        dimension_object = create_dimension_object(context, "DIM Dimension")

        set_anchor_from_snap(dimension_object.dimension_props.start, self.start_snap)
        set_anchor_from_snap(dimension_object.dimension_props.end, self.end_snap)
        dimension_object.dimension_props.dimension_type = self.dimension_type
        dimension_object.dimension_props.offset_distance = self.offset_distance
        dimension_object.dimension_props.offset_plane_normal = tuple(self.offset_plane_normal)
        geometry = get_dimension_world_geometry(
            self.dimension_type,
            self.start_snap["world_co"],
            self.end_snap["world_co"],
            self.offset_plane_normal,
            self.offset_distance,
        )
        if geometry is not None:
            dimension_object.location = geometry["line_mid_world"]
        else:
            dimension_object.location = (self.start_snap["world_co"] + self.end_snap["world_co"]) * 0.5

        if context.mode == "OBJECT":
            for selected_object in context.selected_objects:
                selected_object.select_set(False)
            dimension_object.select_set(True)
            context.view_layer.objects.active = dimension_object

        self.report(messages.INFO, messages.CREATED_DIMENSION)
        return True

    def _after_commit(self, context):
        if not self.continuous_placement:
            clear_preview_state()
            return {"FINISHED"}
        push_undo_step("Create Dimension")
        self._state_machine.restart()
        self.hover_snap = None
        self.hover_mouse = None
        self.start_snap = None
        self.end_snap = None
        self.offset_plane_normal = None
        self.axis_gesture_active = False
        self.inference_axis = self.dimension_type
        self.inference_session.clear()
        remember_session_context(self, context)
        self._update_preview()
        return {"RUNNING_MODAL"}

    def _update_preview(self):
        preview = {
            "state": self.state,
            "axis": self.inference_axis,
            "axis_selectable": self._state_machine.accepts_axis_lock,
            "dimension_type": self.dimension_type,
            "offset_distance": self.offset_distance,
            "distance_text": self.distance_text,
            "distance_input_valid": self.distance_input_valid,
            "axis_gesture_active": self.axis_gesture_active,
            "continuous_placement": self.continuous_placement,
        }
        status = inference_status(self.inference_session)
        if status:
            preview["inference_status"] = status

        if self.hover_snap is not None:
            preview["hover_screen"] = self.hover_snap["screen_co"]
            preview["hover_type"] = self.hover_snap.get("type", "WORLD")
            preview["hover_label"] = self.hover_snap.get("label", "Point")
            preview["hover_snap"] = self._copy_snap(self.hover_snap)

        if self.start_snap is not None:
            preview["start_world"] = self.start_snap["world_co"]
            preview["locked_snaps"] = [self._copy_snap(self.start_snap)]

        if self.state == "PICK_END" and self.start_snap is not None and self.hover_snap is not None:
            end_snap = self._effective_end_snap(bpy.context)
            if end_snap is not None:
                preview["end_world"] = end_snap["world_co"]
        elif self.end_snap is not None:
            preview["end_world"] = self.end_snap["world_co"]
            preview.setdefault("locked_snaps", []).append(self._copy_snap(self.end_snap))
            preview["axis_origin_world"] = (
                self.start_snap["world_co"] + self.end_snap["world_co"]
            ) * 0.5

        if self.offset_plane_normal is not None:
            preview["offset_plane_normal"] = tuple(self.offset_plane_normal)

        set_preview_state(preview)

    @staticmethod
    def _copy_snap(snap):
        return copy_snap(snap)
