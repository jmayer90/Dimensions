import bpy
from mathutils.geometry import intersect_line_plane
from mathutils import Vector

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
    axis_from_mouse_direction,
    is_confirm_event,
    is_navigation_event,
    update_distance_text,
)
from ..snapping import copy_snap, find_nearest_snap_point, get_mouse_ray, has_view3d_window_region
from ..units import parse_distance_input
from .selection_annotations import create_dimension_from_selected_edge


class CADDIM_OT_CreateDimension(bpy.types.Operator):
    bl_idname = "dimensions.create_dimension"
    bl_label = "Create Dimension"
    bl_description = "Create from one selected Edit Mode edge, or interactively pick two points"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            self.report({"ERROR"}, "Run this operator from a 3D View")
            return {"CANCELLED"}

        if context.mode not in {"OBJECT", "EDIT_MESH"}:
            self.report({"ERROR"}, "Dimensions work in Object Mode or Mesh Edit Mode")
            return {"CANCELLED"}

        if context.mode == "EDIT_MESH":
            dimension = create_dimension_from_selected_edge(context)
            if dimension is not None:
                self.report({"INFO"}, "Created dimension from selected edge")
                return {"FINISHED"}

        self.state = "PICK_START"
        self.hover_snap = None
        self.start_snap = None
        self.end_snap = None
        self.dimension_type = "ALIGNED"
        self.offset_distance = DEFAULT_OFFSET_DISTANCE
        self.offset_plane_normal = None
        self.distance_text = ""
        self.distance_input_valid = True
        self.axis_gesture_active = False

        self._update_preview()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            clear_preview_state()
            return {"CANCELLED"}

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

        if (
            self.state == "SET_OFFSET"
            and event.type in {"A", "X", "Y", "Z"}
            and event.value == "PRESS"
        ):
            self.dimension_type = "ALIGNED" if event.type == "A" else event.type
            self._configure_offset_plane(context)
            if self.distance_text:
                self._apply_numeric_input(context)
            else:
                self._update_offset(context, event.mouse_region_x, event.mouse_region_y)
            self._update_preview()
            axis_label = "Auto" if self.dimension_type == "ALIGNED" else self.dimension_type
            self.report({"INFO"}, f"Extension axis: {axis_label}")
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
                )
            elif self.state == "SET_OFFSET" and not self.distance_text:
                self._update_offset(context, event.mouse_region_x, event.mouse_region_y)

            self._update_preview()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.state == "PICK_START":
                if self.hover_snap is None:
                    self.hover_snap = find_nearest_snap_point(
                        context,
                        event.mouse_region_x,
                        event.mouse_region_y,
                        include_free=True,
                    )
                if self.hover_snap is None:
                    return {"RUNNING_MODAL"}

                return self._accept_start()

            if self.state == "PICK_END":
                if self.hover_snap is None:
                    self.hover_snap = find_nearest_snap_point(
                        context,
                        event.mouse_region_x,
                        event.mouse_region_y,
                        include_free=True,
                        plane_point=self.start_snap["world_co"],
                    )
                if self.hover_snap is None:
                    return {"RUNNING_MODAL"}

                return self._accept_end(context)

            if self.state == "SET_OFFSET":
                if self.distance_text and not self.distance_input_valid:
                    self.report({"WARNING"}, f"Invalid distance: {self.distance_text}")
                    return {"RUNNING_MODAL"}
                if self._create_dimension(context):
                    clear_preview_state()
                    return {"FINISHED"}
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
                    self.report({"WARNING"}, f"Invalid distance: {self.distance_text}")
                    return {"RUNNING_MODAL"}
                if self._create_dimension(context):
                    clear_preview_state()
                    return {"FINISHED"}
                return {"RUNNING_MODAL"}

        if event.type in {"BACK_SPACE", "DEL"} and event.value == "PRESS":
            self._step_back()
            self._update_preview()
            return {"RUNNING_MODAL"}

        if event.type == "ESC" and event.value == "PRESS":
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

    def _accept_start(self):
        if self.hover_snap is None:
            return {"RUNNING_MODAL"}
        self.start_snap = self._copy_snap(self.hover_snap)
        self.state = "PICK_END"
        self.distance_text = ""
        self.distance_input_valid = True
        self._update_preview()
        return {"RUNNING_MODAL"}

    def _accept_end(self, context):
        effective_end = self._effective_end_snap(context)
        if effective_end is None:
            if self.distance_text:
                self.report({"WARNING"}, f"Invalid distance: {self.distance_text}")
            return {"RUNNING_MODAL"}
        self.end_snap = effective_end
        if (self.end_snap["world_co"] - self.start_snap["world_co"]).length < 1e-6:
            self.report({"WARNING"}, "Choose a different end point")
            self.end_snap = None
            return {"RUNNING_MODAL"}

        self.distance_text = ""
        self.distance_input_valid = True
        self._begin_offset_stage(context)
        self.state = "SET_OFFSET"
        self._update_preview()
        return {"RUNNING_MODAL"}

    def _effective_end_snap(self, context):
        if self.start_snap is None or self.hover_snap is None:
            return None
        snap = self._copy_snap(self.hover_snap)
        direction = snap["world_co"] - self.start_snap["world_co"]
        if direction.length < 1e-8:
            return None
        if not self.distance_text.strip():
            self.distance_input_valid = True
            return snap
        try:
            direction.normalize()
            direction *= parse_distance_input(context, self.distance_text)
        except (TypeError, ValueError):
            self.distance_input_valid = False
            return None
        self.distance_input_valid = True
        snap["type"] = "WORLD"
        snap["label"] = "Typed Point"
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
        if self.state == "SET_OFFSET":
            self.state = "PICK_END"
            self.end_snap = None
            self.offset_plane_normal = None
        elif self.state == "PICK_END":
            self.state = "PICK_START"
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
        axis_direction = {
            "X": Vector((1.0, 0.0, 0.0)),
            "Y": Vector((0.0, 1.0, 0.0)),
            "Z": Vector((0.0, 0.0, 1.0)),
        }[self.dimension_type]
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
            self.report({"ERROR"}, "A dimension needs two different points")
            return False

        if self.offset_plane_normal is None:
            self._begin_offset_stage(context)
            if self.offset_plane_normal is None:
                self.report({"ERROR"}, "Could not determine a dimension offset plane")
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

        self.report({"INFO"}, "Created dimension")
        return True

    def _update_preview(self):
        preview = {
            "state": self.state,
            "axis": self.dimension_type,
            "dimension_type": self.dimension_type,
            "offset_distance": self.offset_distance,
            "distance_text": self.distance_text,
            "distance_input_valid": self.distance_input_valid,
            "axis_gesture_active": self.axis_gesture_active,
        }

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
