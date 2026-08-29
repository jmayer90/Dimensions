"""Angular and repeated-spacing construction guide operators."""

import bpy
from math import degrees
from mathutils import Vector

from .. import messages
from ..anchors import set_world_anchor
from ..collections import create_guide_object
from ..derived_guides import angular_preview_line, bind_edge_source, bind_guide_source, resolve_derived_guide, resolve_source, spaced_guide_lines
from ..drawing import clear_guide_preview_state, set_guide_preview_state
from ..interaction import is_confirm_event, is_navigation_event, update_distance_text
from ..keymaps import modal_action_from_event
from ..properties import is_guide_object, is_read_only_dimensions_object
from ..snapping import guide_line_world
from ..units import parse_angle_input


def active_source(context):
    obj = context.view_layer.objects.active
    if is_guide_object(obj) and obj.guide_props.kind in {"GUIDE", "PLANE"}:
        return ("GUIDE", obj)
    if context.mode == "EDIT_MESH" and context.edit_object is not None:
        import bmesh
        mesh = bmesh.from_edit_mesh(context.edit_object.data)
        edges = [edge for edge in mesh.edges if edge.select and not edge.hide]
        if len(edges) == 1:
            return ("EDGE", context.edit_object, edges[0].index)
    return None


def bind_active_source(binding, source):
    return bind_guide_source(binding, source[1]) if source[0] == "GUIDE" else bind_edge_source(binding, source[1], source[2])


def source_geometry(source):
    if source[0] == "GUIDE":
        obj = source[1]
        if obj.guide_props.kind == "PLANE":
            from ..guide_planes import resolve_guide_plane
            frame = resolve_guide_plane(obj)
            return None if frame is None else {"kind": "PLANE", "origin": frame[0], "normal": frame[3]}
        line = guide_line_world(obj)
        return None if line is None else {"kind": "LINE", "origin": line[0], "direction": line[1]}
    obj, edge_index = source[1], source[2]
    if obj.mode == "EDIT":
        import bmesh
        mesh = bmesh.from_edit_mesh(obj.data)
        mesh.edges.ensure_lookup_table()
        edge = mesh.edges[edge_index]
        start, end = (obj.matrix_world @ vertex.co for vertex in edge.verts)
    else:
        edge = obj.data.edges[edge_index]
        start, end = (obj.matrix_world @ obj.data.vertices[index].co for index in edge.vertices)
    return {"kind": "LINE", "origin": start, "direction": (end - start).normalized()}


def angular_preview_state(geometry, pivot, angle, flipped=False, plane_normal=(0.0, 0.0, 1.0)):
    signed_angle = -float(angle) if flipped else float(angle)
    line = angular_preview_line(geometry, Vector(pivot), signed_angle, Vector(plane_normal))
    if line is None:
        return None
    return {
        "state": "ANGULAR", "derived_guide": "ANGULAR", "axis": "ALIGNED",
        "start_world": line[0], "end_world": line[0] + line[1],
        "derived_label": f"{degrees(signed_angle):.3f}°",
        "angle": signed_angle, "flipped": bool(flipped),
    }


class DIMENSIONS_OT_CreateAngularGuide(bpy.types.Operator):
    bl_idname = "dimensions.create_angular_guide"
    bl_label = "Create Angular Guide"
    bl_options = {"REGISTER", "UNDO"}
    angle: bpy.props.FloatProperty(name="Angle", default=0.7853981633974483, subtype="ANGLE")
    flip: bpy.props.BoolProperty(name="Flip Direction", default=False)

    def invoke(self, context, _event):
        self._source = active_source(context)
        if self._source is None:
            self.report(messages.WARNING, messages.SELECT_GUIDE_SOURCE)
            return {"CANCELLED"}
        self.angle_text = ""
        self.angle_input_valid = True
        try:
            from ..guide_planes import active_plane_frame
            frame = active_plane_frame(context.scene)
        except (ImportError, RuntimeError):
            frame = None
        self._plane_normal = Vector((0.0, 0.0, 1.0)) if frame is None else Vector(frame[3])
        context.window_manager.modal_handler_add(self)
        self._update_preview(context)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if (
            (event.type == "F" and event.value == "PRESS")
            or modal_action_from_event(event) == "FLIP_OFFSET"
        ):
            self.flip = not self.flip
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        text, handled = update_distance_text(self.angle_text, event)
        if handled:
            self.angle_text = text
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        if (event.type == "LEFTMOUSE" and event.value == "PRESS") or is_confirm_event(event):
            if not self.angle_input_valid:
                return {"RUNNING_MODAL"}
            result = self.execute(context)
            clear_guide_preview_state()
            return result
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            clear_guide_preview_state()
            return {"CANCELLED"}
        if is_navigation_event(event):
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def cancel(self, _context):
        clear_guide_preview_state()

    def _resolved_angle(self, context):
        if not self.angle_text.strip():
            self.angle_input_valid = True
            return self.angle
        try:
            value = parse_angle_input(context, self.angle_text)
        except (TypeError, ValueError):
            self.angle_input_valid = False
            return self.angle
        self.angle_input_valid = True
        return value

    def _update_preview(self, context):
        geometry = source_geometry(self._source)
        angle = self._resolved_angle(context)
        state = None if geometry is None else angular_preview_state(
            geometry, context.scene.cursor.location, angle, self.flip, self._plane_normal,
        )
        if state is None:
            state = {"state": "ANGULAR", "derived_guide": "ANGULAR", "axis": "ALIGNED"}
        state["distance_text"] = self.angle_text
        state["distance_input_valid"] = self.angle_input_valid
        set_guide_preview_state(state)

    def execute(self, context):
        source = getattr(self, "_source", None) or active_source(context)
        if source is None:
            self.report(messages.WARNING, messages.SELECT_GUIDE_SOURCE)
            return {"CANCELLED"}
        obj = create_guide_object(context, "GUIDE Angular")
        props = obj.guide_props
        props.derived, props.derivation_mode = True, "ANGULAR"
        angle = self._resolved_angle(context) if hasattr(self, "angle_text") else self.angle
        props.guide_angle = -angle if self.flip else angle
        props.derived_direction = tuple(getattr(self, "_plane_normal", Vector((0.0, 0.0, 1.0))))
        set_world_anchor(props.construction_pivot, context.scene.cursor.location)
        bind_active_source(props.source_a, source)
        line = resolve_derived_guide(obj)
        if line is None:
            bpy.data.objects.remove(obj, do_unlink=True)
            self.report(messages.WARNING, messages.DERIVED_GUIDE_SOURCE_REQUIRED)
            return {"CANCELLED"}
        obj.location = line[0]
        context.view_layer.objects.active = obj
        obj.select_set(True)
        self.report(messages.INFO, messages.CREATED_ANGULAR_GUIDE)
        return {"FINISHED"}


class DIMENSIONS_OT_CreateSpacingGuide(bpy.types.Operator):
    bl_idname = "dimensions.create_spacing_guide"
    bl_label = "Create Repeated Guides"
    bl_options = {"REGISTER", "UNDO"}
    mode: bpy.props.EnumProperty(name="Mode", items=[("COUNT", "Interval + Count", "Fixed count"), ("EXTENT", "Interval + Extent", "Repeat until extent"), ("DISTRIBUTE", "Distribute", "Evenly distribute over extent")], default="COUNT")
    interval: bpy.props.FloatProperty(name="Interval", default=1.0, min=0.000001, subtype="DISTANCE")
    count: bpy.props.IntProperty(name="Count", default=5, min=2, max=10000)
    extent: bpy.props.FloatProperty(name="Extent", default=4.0, min=0.000001, subtype="DISTANCE")

    def execute(self, context):
        source = active_source(context)
        if source is None:
            self.report(messages.WARNING, messages.SELECT_GUIDE_SOURCE)
            return {"CANCELLED"}
        obj = create_guide_object(context, "GUIDE Spaced Set")
        props = obj.guide_props
        props.derived, props.derivation_mode = True, "SPACING"
        props.spacing_mode, props.spacing_interval = self.mode, self.interval
        props.spacing_count, props.spacing_extent = self.count, self.extent
        props.derived_direction = (0.0, 1.0, 0.0)
        bind_active_source(props.source_a, source)
        resolved_source = resolve_source(props.source_a)
        origin = context.scene.cursor.location if resolved_source is None else resolved_source["origin"]
        set_world_anchor(props.construction_pivot, origin)
        set_world_anchor(props.spacing_end, context.scene.cursor.location)
        lines = spaced_guide_lines(obj)
        if not lines:
            bpy.data.objects.remove(obj, do_unlink=True)
            self.report(messages.WARNING, messages.DERIVED_GUIDE_SOURCE_REQUIRED)
            return {"CANCELLED"}
        obj.location = lines[0][0]
        context.view_layer.objects.active = obj
        obj.select_set(True)
        self.report(messages.INFO, messages.CREATED_SPACING_GUIDE)
        return {"FINISHED"}


class DIMENSIONS_OT_BakeSpacingGuide(bpy.types.Operator):
    bl_idname = "dimensions.bake_spacing_guide"
    bl_label = "Bake to Individual Guides"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        source = context.view_layer.objects.active
        if not is_guide_object(source) or source.guide_props.derivation_mode != "SPACING" or is_read_only_dimensions_object(source):
            self.report(messages.WARNING, messages.SELECT_SPACING_GUIDE)
            return {"CANCELLED"}
        lines = spaced_guide_lines(source)
        for index, (origin, direction) in enumerate(lines, 1):
            obj = create_guide_object(context, f"GUIDE Spaced {index:03d}")
            set_world_anchor(obj.guide_props.start, origin)
            set_world_anchor(obj.guide_props.end, origin + direction)
            obj.location = origin
        self.report(messages.INFO, messages.BAKED_SPACING_GUIDE.format(count=len(lines)))
        return {"FINISHED"}


classes = (DIMENSIONS_OT_CreateAngularGuide, DIMENSIONS_OT_CreateSpacingGuide, DIMENSIONS_OT_BakeSpacingGuide)
