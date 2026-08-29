import bmesh
import bpy

from mathutils import Vector

from .. import messages
from ..angle_binding import derive_angle_from_world_edges, set_angle_edge
from ..collections import create_dimension_object
from ..drawing import clear_preview_state, set_preview_state
from ..interaction import (
    continuous_placement_enabled,
    push_undo_step,
    remember_session_context,
    session_context_changed,
)
from ..manipulation import angle_radius_from_world
from ..properties import is_dimension_object, is_read_only_dimensions_object
from ..snap_targets import handle_snap_target_event
from ..snapping import copy_snap, find_nearest_snap_point, has_view3d_window_region


def _selected_edge_snap(obj, edge):
    vertices = tuple(vertex.index for vertex in edge.verts)
    return {
        "type": "EDGE",
        "label": "Selected Edge",
        "object": obj,
        "edge_index": edge.index,
        "edge_vertices": vertices,
        "world_points": tuple(obj.matrix_world @ vertex.co for vertex in edge.verts),
        "world_co": obj.matrix_world @ ((edge.verts[0].co + edge.verts[1].co) * 0.5),
        "screen_co": Vector((0.0, 0.0)),
    }


def _edge_world_points(snap):
    if snap is None:
        return None
    if "world_points" in snap:
        return tuple(Vector(point) for point in snap["world_points"])
    obj = snap.get("object")
    vertices = snap.get("edge_vertices")
    if obj is None or vertices is None or len(vertices) != 2:
        return None
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        return tuple(obj.matrix_world @ bm.verts[index].co for index in vertices)
    return tuple(obj.matrix_world @ obj.data.vertices[index].co for index in vertices)


def _valid_edge_snap(snap):
    return bool(
        snap
        and snap.get("type") == "EDGE"
        and snap.get("object") is not None
        and snap.get("edge_vertices") is not None
        and len(snap["edge_vertices"]) == 2
    )


class DIMENSIONS_OT_CreateAngle(bpy.types.Operator):
    bl_idname = "dimensions.create_angle"
    bl_label = "Create Angle Dimension"
    bl_description = "Pick two edges, then place the angle arc"
    bl_options = {"REGISTER", "UNDO"}

    replace_active: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})

    def invoke(self, context, _event):
        if not has_view3d_window_region(context):
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        if context.mode not in {"OBJECT", "EDIT_MESH"}:
            self.report(messages.WARNING, messages.ANGLE_REQUIRE_SUPPORTED_MODE)
            return {"CANCELLED"}
        self.target_name = ""
        self.continuous_placement = continuous_placement_enabled(context)
        self.angle_mode = "MINOR"
        if self.replace_active:
            active = context.view_layer.objects.active
            if not is_dimension_object(active) or active.dimension_props.annotation_kind != "ANGLE":
                self.report(messages.WARNING, messages.SELECT_ANGLE_DIMENSION)
                return {"CANCELLED"}
            self.target_name = active.name
            self.angle_mode = active.dimension_props.angle_mode

        self.state = "PICK_EDGE_A"
        self.edge_a_snap = None
        self.edge_b_snap = None
        self.hover_snap = None
        self.radius = 0.25
        if context.mode == "EDIT_MESH" and context.edit_object is not None:
            bm = bmesh.from_edit_mesh(context.edit_object.data)
            bm.edges.ensure_lookup_table()
            selected = [edge for edge in bm.edges if edge.select and not edge.hide]
            if len(selected) == 2:
                self.edge_a_snap = _selected_edge_snap(context.edit_object, selected[0])
                self.edge_b_snap = _selected_edge_snap(context.edit_object, selected[1])
                source = self._derived_source()
                if source is not None:
                    self.radius = max(0.001, min(
                        (source["start"] - source["center"]).length,
                        (source["end"] - source["center"]).length,
                    ) * 0.35)
                    self.state = "PICK_RADIUS"
        remember_session_context(self, context)
        self._update_preview()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if not has_view3d_window_region(context):
            clear_preview_state()
            return {"CANCELLED"}
        if self.continuous_placement and session_context_changed(self, context):
            clear_preview_state()
            return {"CANCELLED"}
        if handle_snap_target_event(context, event):
            self._update_preview()
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            if self.state in {"PICK_EDGE_A", "PICK_EDGE_B"}:
                snap = find_nearest_snap_point(
                    context,
                    event.mouse_region_x,
                    event.mouse_region_y,
                    include_guides=False,
                    include_free=False,
                )
                self.hover_snap = copy_snap(snap) if _valid_edge_snap(snap) else None
            else:
                source = self._derived_source()
                self.hover_snap = find_nearest_snap_point(
                    context,
                    event.mouse_region_x,
                    event.mouse_region_y,
                    include_free=True,
                    plane_point=source["center"] if source else None,
                )
                if source is not None and self.hover_snap is not None:
                    self.radius = angle_radius_from_world(source["center"], self.hover_snap["world_co"])
            self._update_preview()
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.state == "PICK_EDGE_A":
                if self.hover_snap is None:
                    self.report(messages.WARNING, messages.POINT_FIRST_EDGE)
                    return {"RUNNING_MODAL"}
                self.edge_a_snap = copy_snap(self.hover_snap)
                self.state = "PICK_EDGE_B"
            elif self.state == "PICK_EDGE_B":
                if self.hover_snap is None:
                    self.report(messages.WARNING, messages.POINT_SECOND_EDGE)
                    return {"RUNNING_MODAL"}
                self.edge_b_snap = copy_snap(self.hover_snap)
                source = self._derived_source()
                if source is None:
                    self.report(messages.WARNING, messages.POINT_NON_PARALLEL_EDGES)
                    return {"RUNNING_MODAL"}
                self.radius = max(0.001, min(
                    (source["start"] - source["center"]).length,
                    (source["end"] - source["center"]).length,
                ) * 0.35)
                self.state = "PICK_RADIUS"
            else:
                return self._commit(context)
            self._update_preview()
            return {"RUNNING_MODAL"}
        if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS" and self.state == "PICK_RADIUS":
            return self._commit(context)
        if event.type == "ESC" and event.value == "PRESS":
            if self.continuous_placement:
                clear_preview_state()
                return {"CANCELLED"}
            if self.state == "PICK_RADIUS":
                self.edge_b_snap = None
                self.state = "PICK_EDGE_B"
            elif self.state == "PICK_EDGE_B":
                self.edge_a_snap = None
                self.state = "PICK_EDGE_A"
            else:
                clear_preview_state()
                return {"CANCELLED"}
            self._update_preview()
            return {"RUNNING_MODAL"}
        if event.type == "RIGHTMOUSE" and event.value == "PRESS":
            clear_preview_state()
            return {"CANCELLED"}
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def cancel(self, _context):
        clear_preview_state()

    def _derived_source(self):
        a = _edge_world_points(self.edge_a_snap)
        b = _edge_world_points(self.edge_b_snap)
        if a is None or b is None:
            return None
        return derive_angle_from_world_edges(a[0], a[1], b[0], b[1], self.angle_mode)

    def _commit(self, context):
        source = self._derived_source()
        if source is None:
            return {"RUNNING_MODAL"}
        annotation = bpy.data.objects.get(self.target_name) if self.target_name else None
        if annotation is None:
            annotation = create_dimension_object(context, "ANGLE Two Edges")
        props = annotation.dimension_props
        props.annotation_kind = "ANGLE"
        props.measurement_state = "LIVE"
        props.angle_mode = self.angle_mode
        props.angle_radius = self.radius
        props.presentation_offset = (0.0, 0.0, 0.0)
        props.placement_initialized = False
        set_angle_edge(props, "A", self.edge_a_snap["object"], self.edge_a_snap["edge_vertices"])
        set_angle_edge(props, "B", self.edge_b_snap["object"], self.edge_b_snap["edge_vertices"])
        annotation.location = source["center"]
        if context.mode == "OBJECT":
            for selected in context.selected_objects:
                selected.select_set(False)
            annotation.select_set(True)
            context.view_layer.objects.active = annotation
        self.report(messages.INFO, messages.created_angle(bool(self.target_name)))
        return self._after_commit(context)

    def _after_commit(self, context):
        if not self.continuous_placement or self.target_name:
            clear_preview_state()
            return {"FINISHED"}
        push_undo_step("Create Angle Dimension")
        self.state = "PICK_EDGE_A"
        self.edge_a_snap = None
        self.edge_b_snap = None
        self.hover_snap = None
        self.radius = 0.25
        remember_session_context(self, context)
        self._update_preview()
        return {"RUNNING_MODAL"}

    def _update_preview(self):
        source = self._derived_source()
        preview = {
            "state": self.state,
            "annotation_kind": "ANGLE",
            "angle_radius": self.radius,
            "angle_mode": "REFLEX" if self.angle_mode == "REFLEX" else "MINOR",
            "continuous_placement": self.continuous_placement,
        }
        if self.hover_snap is not None:
            preview["hover_screen"] = self.hover_snap["screen_co"]
            preview["hover_type"] = self.hover_snap.get("type", "WORLD")
            preview["hover_label"] = self.hover_snap.get("label", "Edge")
        if source is not None:
            preview["start_world"] = source["start"]
            preview["center_world"] = source["center"]
            preview["end_world"] = source["end"]
        set_preview_state(preview)


class DIMENSIONS_OT_ReplaceAngleEdge(bpy.types.Operator):
    bl_idname = "dimensions.replace_angle_edge"
    bl_label = "Replace Angle Edge"
    bl_description = "Replace one source edge while preserving the other edge and presentation"
    bl_options = {"REGISTER", "UNDO"}

    edge_slot: bpy.props.EnumProperty(items=[("A", "Edge A", "Replace Edge A"), ("B", "Edge B", "Replace Edge B")])

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active
        return bool(
            context.mode == "OBJECT"
            and is_dimension_object(obj)
            and not is_read_only_dimensions_object(obj)
            and obj.dimension_props.annotation_kind == "ANGLE"
        )

    def invoke(self, context, _event):
        self.annotation_name = context.view_layer.objects.active.name
        self.hover_snap = None
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        annotation = bpy.data.objects.get(self.annotation_name)
        if annotation is None or not has_view3d_window_region(context):
            clear_preview_state()
            return {"CANCELLED"}
        if handle_snap_target_event(context, event):
            set_preview_state({
                "state": f"REPLACE_EDGE_{self.edge_slot}",
                "hover_screen": None if self.hover_snap is None else self.hover_snap["screen_co"],
                "hover_type": "EDGE",
                "hover_label": f"Replacement Edge {self.edge_slot}",
            })
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            snap = find_nearest_snap_point(
                context,
                event.mouse_region_x,
                event.mouse_region_y,
                include_guides=False,
                include_free=False,
            )
            self.hover_snap = copy_snap(snap) if _valid_edge_snap(snap) else None
            set_preview_state({
                "state": f"REPLACE_EDGE_{self.edge_slot}",
                "hover_screen": None if self.hover_snap is None else self.hover_snap["screen_co"],
                "hover_type": "EDGE",
                "hover_label": f"Replacement Edge {self.edge_slot}",
            })
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS" and self.hover_snap is not None:
            set_angle_edge(
                annotation.dimension_props,
                self.edge_slot,
                self.hover_snap["object"],
                self.hover_snap["edge_vertices"],
            )
            annotation.dimension_props.measurement_state = "LIVE"
            clear_preview_state()
            return {"FINISHED"}
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            clear_preview_state()
            return {"CANCELLED"}
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}
