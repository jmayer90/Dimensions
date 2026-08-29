"""Selection-based radial, diameter, and arc-length creation."""

import bpy
from mathutils import Vector

from .. import messages
from ..circle_binding import bind_circle_vertices, circle_geometry, store_circle_fit
from ..collections import create_dimension_object
from ..properties import is_dimension_object, is_read_only_dimensions_object


def selected_circle_source(context):
    obj = context.edit_object if context.mode == "EDIT_MESH" else context.view_layer.objects.active
    if obj is None or obj.type != "MESH":
        return None
    if context.mode == "EDIT_MESH":
        import bmesh

        bm = bmesh.from_edit_mesh(obj.data)
        vertices = {vertex.index for vertex in bm.verts if vertex.select and not vertex.hide}
        selected_edges = [edge for edge in bm.edges if edge.select and not edge.hide]
        selected_faces = [face for face in bm.faces if face.select and not face.hide]
        for edge in selected_edges:
            vertices.update(vertex.index for vertex in edge.verts)
        for face in selected_faces:
            vertices.update(vertex.index for vertex in face.verts)
        degrees = {index: 0 for index in vertices}
        for edge in selected_edges:
            indices = tuple(vertex.index for vertex in edge.verts)
            if all(index in degrees for index in indices):
                degrees[indices[0]] += 1
                degrees[indices[1]] += 1
        closed = bool(selected_faces) or not selected_edges or bool(degrees) and all(value == 2 for value in degrees.values())
        return obj, tuple(sorted(vertices)), closed
    selected_vertices = {
        vertex.index for vertex in obj.data.vertices if vertex.select and not vertex.hide
    }
    selected_edges = [edge for edge in obj.data.edges if edge.select and not edge.hide]
    selected_faces = [face for face in obj.data.polygons if face.select and not face.hide]
    for edge in selected_edges:
        selected_vertices.update(edge.vertices)
    for face in selected_faces:
        selected_vertices.update(face.vertices)
    if len(selected_vertices) >= 3:
        degrees = {index: 0 for index in selected_vertices}
        for edge in selected_edges:
            if all(index in degrees for index in edge.vertices):
                degrees[edge.vertices[0]] += 1
                degrees[edge.vertices[1]] += 1
        closed = bool(selected_faces) or not selected_edges or all(value == 2 for value in degrees.values())
        return obj, tuple(sorted(selected_vertices)), closed
    return obj, tuple(vertex.index for vertex in obj.data.vertices if not vertex.hide), True


class DIMENSIONS_OT_CreateCircleDimension(bpy.types.Operator):
    bl_idname = "dimensions.create_circle_dimension"
    bl_label = "Create Circular Dimension"
    bl_description = "Fit a radial, diameter, or arc-length annotation to selected mesh points"
    bl_options = {"REGISTER", "UNDO"}

    circle_kind: bpy.props.EnumProperty(items=[
        ("RADIUS", "Radius", "Create an R dimension"),
        ("DIAMETER", "Diameter", "Create a diameter dimension"),
        ("ARC_LENGTH", "Arc Length", "Create an arc-length dimension"),
    ], default="RADIUS")

    def execute(self, context):
        selection = selected_circle_source(context)
        if selection is None or len(selection[1]) < 3:
            self.report(messages.WARNING, messages.CIRCLE_SELECTION_REQUIRED)
            return {"CANCELLED"}
        source, indices, closed = selection
        obj = create_dimension_object(context, f"DIM {self.circle_kind.replace('_', ' ').title()}")
        props = obj.dimension_props
        props.annotation_kind = "CIRCLE"
        props.circle_kind = self.circle_kind
        fit = bind_circle_vertices(props, source, indices, closed)
        if fit is None:
            bpy.data.objects.remove(obj, do_unlink=True)
            self.report(messages.WARNING, messages.CIRCLE_FIT_INVALID)
            return {"CANCELLED"}
        store_circle_fit(props, fit)
        direction = fit["axis_u"] + fit["axis_v"]
        direction.normalize()
        props.circle_leader_angle = 0.7853981633974483
        props.circle_label_distance = fit["radius"] * 1.35
        obj.location = fit["center"] + direction * props.circle_label_distance
        if context.mode == "OBJECT":
            for selected in context.selected_objects:
                selected.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
        self.report(messages.INFO, messages.CREATED_CIRCLE_DIMENSION)
        return {"FINISHED"}


class DIMENSIONS_OT_CaptureCircleDimension(bpy.types.Operator):
    bl_idname = "dimensions.capture_circle_dimension"
    bl_label = "Capture Circular Value"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.view_layer.objects.active
        if not is_dimension_object(obj) or obj.dimension_props.annotation_kind != "CIRCLE" or is_read_only_dimensions_object(obj):
            self.report(messages.WARNING, messages.SELECT_DIMENSION_FIRST)
            return {"CANCELLED"}
        fit = circle_geometry(obj.dimension_props)
        if fit is None:
            self.report(messages.WARNING, messages.CIRCLE_FIT_INVALID)
            return {"CANCELLED"}
        if fit["fit_warning"]:
            self.report(messages.WARNING, messages.CIRCLE_CAPTURE_POOR_FIT)
            return {"CANCELLED"}
        store_circle_fit(obj.dimension_props, fit)
        obj.dimension_props.measurement_state = "CAPTURED"
        self.report(messages.INFO, messages.CAPTURED_CIRCLE_VALUE)
        return {"FINISHED"}


classes = (DIMENSIONS_OT_CreateCircleDimension, DIMENSIONS_OT_CaptureCircleDimension)
