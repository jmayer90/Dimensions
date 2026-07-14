import bpy
from mathutils.geometry import intersect_line_plane
from mathutils import Vector

from ..anchors import set_anchor
from ..collections import create_dimension_object
from ..constants import DEFAULT_OFFSET_DISTANCE
from ..drawing import (
    clear_preview_state,
    get_dimension_world_geometry,
    get_measure_world_points,
    get_offset_basis,
    set_preview_state,
)
from ..snapping import find_nearest_face_vertex, get_mouse_ray


class CADDIM_OT_CreateDimension(bpy.types.Operator):
    bl_idname = "dimensions.create_dimension"
    bl_label = "Create Dimension"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            self.report({"ERROR"}, "Run this operator from a 3D View")
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            self.report({"ERROR"}, "Dimensions currently works only in Object Mode")
            return {"CANCELLED"}

        self.state = "PICK_START"
        self.hover_snap = None
        self.start_snap = None
        self.end_snap = None
        self.dimension_type = "ALIGNED"
        self.offset_distance = DEFAULT_OFFSET_DISTANCE
        self.offset_plane_normal = None

        self._update_preview()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            clear_preview_state()
            return {"CANCELLED"}

        if (
            self.state == "SET_OFFSET"
            and event.type in {"A", "X", "Y", "Z"}
            and event.value == "PRESS"
        ):
            self.dimension_type = "ALIGNED" if event.type == "A" else event.type
            self._configure_offset_plane(context)
            self._update_offset(context, event.mouse_region_x, event.mouse_region_y)
            self._update_preview()
            axis_label = "Auto" if self.dimension_type == "ALIGNED" else self.dimension_type
            self.report({"INFO"}, f"Extension axis: {axis_label}")
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            if self.state in {"PICK_START", "PICK_END"}:
                self.hover_snap = find_nearest_face_vertex(
                    context,
                    event.mouse_region_x,
                    event.mouse_region_y,
                )
            elif self.state == "SET_OFFSET":
                self._update_offset(context, event.mouse_region_x, event.mouse_region_y)

            self._update_preview()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.state == "PICK_START":
                if self.hover_snap is None:
                    return {"RUNNING_MODAL"}

                self.start_snap = self._copy_snap(self.hover_snap)
                self.state = "PICK_END"
                self._update_preview()
                return {"RUNNING_MODAL"}

            if self.state == "PICK_END":
                if self.hover_snap is None:
                    return {"RUNNING_MODAL"}

                self.end_snap = self._copy_snap(self.hover_snap)
                self._begin_offset_stage(context)
                self.state = "SET_OFFSET"
                self._update_preview()
                return {"RUNNING_MODAL"}

            if self.state == "SET_OFFSET":
                self._create_dimension(context)
                clear_preview_state()
                return {"FINISHED"}

        if event.type in {"RIGHTMOUSE", "ESC"}:
            clear_preview_state()
            return {"CANCELLED"}

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}

        return {"RUNNING_MODAL"}

    def _update_offset(self, context, mouse_x, mouse_y):
        if self.start_snap is None or self.end_snap is None:
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
        dimension_object = create_dimension_object(context, "DIM Dimension")

        set_anchor(
            dimension_object.dimension_props.start,
            self.start_snap["object"],
            self.start_snap["vertex_index"],
        )
        set_anchor(
            dimension_object.dimension_props.end,
            self.end_snap["object"],
            self.end_snap["vertex_index"],
        )
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

        for selected_object in context.selected_objects:
            selected_object.select_set(False)

        dimension_object.select_set(True)
        context.view_layer.objects.active = dimension_object

        self.report({"INFO"}, "Created dimension")

    def _update_preview(self):
        preview = {
            "state": self.state,
            "dimension_type": self.dimension_type,
            "offset_distance": self.offset_distance,
        }

        if self.hover_snap is not None:
            preview["hover_screen"] = self.hover_snap["screen_co"]

        if self.start_snap is not None:
            preview["start_world"] = self.start_snap["world_co"]

        if self.state == "PICK_END" and self.start_snap is not None and self.hover_snap is not None:
            preview["end_world"] = self.hover_snap["world_co"]
        elif self.end_snap is not None:
            preview["end_world"] = self.end_snap["world_co"]

        if self.offset_plane_normal is not None:
            preview["offset_plane_normal"] = tuple(self.offset_plane_normal)

        set_preview_state(preview)

    @staticmethod
    def _copy_snap(snap):
        return {
            "object": snap["object"],
            "vertex_index": snap["vertex_index"],
            "world_co": snap["world_co"].copy(),
            "screen_co": snap["screen_co"].copy(),
        }
