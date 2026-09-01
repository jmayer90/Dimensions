"""Creation and activation operators for non-destructive construction planes."""

import bpy
import bmesh
from mathutils import Vector

from .. import messages
from ..anchors import set_anchor, set_anchor_from_snap, set_world_anchor
from ..collections import create_guide_plane_object
from ..derived_guides import bind_face_source, bind_guide_source
from ..guide_planes import resolve_guide_plane, would_create_plane_cycle
from ..properties import is_read_only_dimensions_object
from ..snapping import find_nearest_snap_point, raycast_from_mouse


def _selected_vertex_indices(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return obj, ()
    if context.mode == "EDIT_MESH":
        bm = bmesh.from_edit_mesh(obj.data)
        return obj, tuple(vertex.index for vertex in bm.verts if vertex.select and not vertex.hide)
    return obj, tuple(vertex.index for vertex in obj.data.vertices if vertex.select)


def _selected_face_index(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return obj, -1
    if context.mode == "EDIT_MESH":
        bm = bmesh.from_edit_mesh(obj.data)
        active = bm.faces.active
        if active is not None and active.select and not active.hide:
            return obj, active.index
        selected = next((face for face in bm.faces if face.select and not face.hide), None)
        return obj, -1 if selected is None else selected.index
    selected = next((face for face in obj.data.polygons if face.select), None)
    return obj, -1 if selected is None else selected.index


class DIMENSIONS_OT_CreateGuidePlane(bpy.types.Operator):
    bl_idname = "dimensions.create_guide_plane"
    bl_label = "Create Guide Plane"
    bl_description = "Create a persistent construction plane without modifying mesh geometry"
    bl_options = {"REGISTER", "UNDO"}

    definition: bpy.props.EnumProperty(
        items=[
            ("THREE_POINTS", "Three Selected Points", "Use exactly three selected mesh vertices"),
            ("POINT_NORMAL", "Cursor + Normal", "Use the 3D cursor and entered normal"),
            ("FACE", "Selected Face", "Follow the active selected base-mesh face"),
            ("OFFSET", "Offset Selected Plane", "Offset the active guide plane"),
        ], default="THREE_POINTS",
    )
    normal: bpy.props.FloatVectorProperty(name="Normal", size=3, subtype="DIRECTION", default=(0.0, 0.0, 1.0))
    offset: bpy.props.FloatProperty(name="Offset", default=0.25, subtype="DISTANCE")
    extent: bpy.props.FloatProperty(name="Grid Extent", default=2.0, min=0.01, subtype="DISTANCE")

    def execute(self, context):
        plane = create_guide_plane_object(context)
        props = plane.guide_props
        props.plane_definition = self.definition
        props.plane_extent = self.extent
        valid = False
        if self.definition == "THREE_POINTS":
            obj, indices = _selected_vertex_indices(context)
            if obj is not None and len(indices) == 3:
                for anchor, index in zip(
                    (props.plane_point_a, props.plane_point_b, props.plane_point_c), indices,
                ):
                    set_anchor(anchor, obj, index)
                valid = True
        elif self.definition == "POINT_NORMAL":
            normal = Vector(self.normal)
            valid = normal.length > 1e-6
            if valid:
                source, indices = _selected_vertex_indices(context)
                if source is not None and len(indices) == 1:
                    set_anchor(props.plane_point_a, source, indices[0])
                else:
                    set_world_anchor(props.plane_point_a, context.scene.cursor.location)
                props.plane_normal = tuple(normal.normalized())
        elif self.definition == "FACE":
            obj, face_index = _selected_face_index(context)
            valid = bind_face_source(props.source_a, obj, face_index)
        elif self.definition == "OFFSET":
            source = context.view_layer.objects.active
            valid = (
                source is not None
                and getattr(getattr(source, "guide_props", None), "kind", "") == "PLANE"
                and bind_guide_source(props.source_a, source)
            )
            props.offset_distance = abs(self.offset)
            props.offset_side = -1 if self.offset < 0.0 else 1
        frame = resolve_guide_plane(plane) if valid else None
        if frame is None:
            bpy.data.objects.remove(plane, do_unlink=True)
            self.report(messages.WARNING, messages.GUIDE_PLANE_DEFINITION_INVALID)
            return {"CANCELLED"}
        plane.location = frame[0]
        for selected in context.selected_objects:
            selected.select_set(False)
        plane.select_set(True)
        context.view_layer.objects.active = plane
        self.report(messages.INFO, messages.CREATED_GUIDE_PLANE)
        return {"FINISHED"}


class DIMENSIONS_OT_SetActiveGuidePlane(bpy.types.Operator):
    bl_idname = "dimensions.set_active_guide_plane"
    bl_label = "Use Selected Plane"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.view_layer.objects.active
        if resolve_guide_plane(obj) is None:
            self.report(messages.WARNING, messages.SELECT_GUIDE_PLANE)
            return {"CANCELLED"}
        settings = context.scene.dimensions_settings
        settings.active_plane_object = obj
        settings.active_plane_mode = "GUIDE"
        self.report(messages.INFO, messages.ACTIVE_GUIDE_PLANE_SET)
        return {"FINISHED"}


class DIMENSIONS_OT_SetActiveFacePlane(bpy.types.Operator):
    bl_idname = "dimensions.set_active_face_plane"
    bl_label = "Use Selected Face"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj, face_index = _selected_face_index(context)
        if obj is None or face_index < 0:
            self.report(messages.WARNING, messages.SELECT_FACE_FOR_PLANE)
            return {"CANCELLED"}
        polygon = obj.data.polygons[face_index]
        normal = obj.matrix_world.to_3x3().inverted_safe().transposed() @ polygon.normal
        edge = obj.matrix_world.to_3x3() @ (
            obj.data.vertices[polygon.vertices[1]].co - obj.data.vertices[polygon.vertices[0]].co
        )
        settings = context.scene.dimensions_settings
        settings.active_plane_origin = tuple(obj.matrix_world @ polygon.center)
        settings.active_plane_normal = tuple(normal.normalized())
        settings.active_plane_axis_u = tuple(edge.normalized())
        settings.active_plane_object = None
        settings.active_plane_mode = "FACE"
        self.report(messages.INFO, messages.ACTIVE_FACE_PLANE_SET)
        return {"FINISHED"}


class DIMENSIONS_OT_SetWorldPlane(bpy.types.Operator):
    bl_idname = "dimensions.set_world_plane"
    bl_label = "Use World Plane"
    bl_options = {"REGISTER", "UNDO"}

    plane: bpy.props.EnumProperty(items=[
        ("WORLD_XY", "XY", "World XY plane"),
        ("WORLD_YZ", "YZ", "World YZ plane"),
        ("WORLD_ZX", "ZX", "World ZX plane"),
    ], default="WORLD_XY")

    def execute(self, context):
        context.scene.dimensions_settings.active_plane_object = None
        context.scene.dimensions_settings.active_plane_mode = self.plane
        self.report(messages.INFO, messages.ACTIVE_WORLD_PLANE_SET)
        return {"FINISHED"}


class DIMENSIONS_OT_SetViewPlane(bpy.types.Operator):
    bl_idname = "dimensions.set_view_plane"
    bl_label = "Use Current View"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        region_data = getattr(context, "region_data", None)
        if region_data is None:
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        rotation = region_data.view_rotation
        settings = context.scene.dimensions_settings
        settings.active_plane_origin = tuple(region_data.view_location)
        settings.active_plane_normal = tuple(rotation @ Vector((0.0, 0.0, 1.0)))
        settings.active_plane_axis_u = tuple(rotation @ Vector((1.0, 0.0, 0.0)))
        settings.active_plane_object = None
        settings.active_plane_mode = "VIEW"
        self.report(messages.INFO, messages.ACTIVE_VIEW_PLANE_SET)
        return {"FINISHED"}


class DIMENSIONS_OT_ClearActivePlane(bpy.types.Operator):
    bl_idname = "dimensions.clear_active_plane"
    bl_label = "Clear Active Plane"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.dimensions_settings
        settings.active_plane_mode = "NONE"
        settings.active_plane_object = None
        self.report(messages.INFO, messages.ACTIVE_PLANE_CLEARED)
        return {"FINISHED"}


class DIMENSIONS_OT_RepairGuidePlane(bpy.types.Operator):
    bl_idname = "dimensions.repair_guide_plane"
    bl_label = "Repair Guide Plane Source"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()

    def invoke(self, context, _event):
        self.plane = context.scene.objects.get(self.object_name)
        if (
            self.plane is None
            or getattr(getattr(self.plane, "guide_props", None), "kind", "") != "PLANE"
            or is_read_only_dimensions_object(self.plane)
        ):
            self.report(messages.WARNING, messages.SELECT_GUIDE_PLANE)
            return {"CANCELLED"}
        if context.area is None or context.area.type != "VIEW_3D":
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        self.pending_snaps = []
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"}:
            return {"CANCELLED"}
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"RUNNING_MODAL"}
        props = self.plane.guide_props
        changed = False
        if props.plane_definition == "FACE":
            hit = raycast_from_mouse(context, event.mouse_region_x, event.mouse_region_y)
            source = None if hit is None else hit.get("object")
            face_index = -1 if hit is None else hit.get("face_index", -1)
            changed = (
                source is not None
                and 0 <= face_index < len(source.data.polygons)
                and Vector(source.data.polygons[face_index].normal).length > 1e-6
                and bind_face_source(props.source_a, source, face_index)
            )
        elif props.plane_definition == "OFFSET":
            snap = find_nearest_snap_point(
                context, event.mouse_region_x, event.mouse_region_y,
                include_free=False, include_guides=True,
            )
            source = None if snap is None else snap.get("guide_object")
            changed = (
                source is not self.plane
                and resolve_guide_plane(source) is not None
                and not would_create_plane_cycle(self.plane, source)
            )
            if changed:
                bind_guide_source(props.source_a, source)
        else:
            snap = find_nearest_snap_point(
                context, event.mouse_region_x, event.mouse_region_y, include_free=True,
            )
            if snap is not None:
                if props.plane_definition == "THREE_POINTS":
                    self.pending_snaps.append(snap)
                    if len(self.pending_snaps) < 3:
                        self.report(messages.INFO, messages.guide_plane_repair_points(len(self.pending_snaps)))
                        return {"RUNNING_MODAL"}
                    points = [Vector(item["world_co"]) for item in self.pending_snaps]
                    if (points[1] - points[0]).cross(points[2] - points[0]).length < 1e-6:
                        self.pending_snaps.clear()
                        self.report(messages.WARNING, messages.GUIDE_PLANE_REPAIR_INVALID)
                        return {"RUNNING_MODAL"}
                    for anchor, pending in zip(
                        (props.plane_point_a, props.plane_point_b, props.plane_point_c),
                        self.pending_snaps,
                    ):
                        set_anchor_from_snap(anchor, pending)
                    changed = True
                else:
                    if Vector(props.plane_normal).length < 1e-6:
                        self.report(messages.WARNING, messages.GUIDE_PLANE_REPAIR_INVALID)
                        return {"RUNNING_MODAL"}
                    set_anchor_from_snap(props.plane_point_a, snap)
                    changed = True
        if not changed or resolve_guide_plane(self.plane) is None:
            self.report(messages.WARNING, messages.GUIDE_PLANE_REPAIR_INVALID)
            return {"RUNNING_MODAL"}
        from ..scene_sync import sync_scene_objects

        sync_scene_objects(context.scene)
        self.report(messages.INFO, messages.GUIDE_PLANE_REPAIRED)
        return {"FINISHED"}


classes = (
    DIMENSIONS_OT_CreateGuidePlane,
    DIMENSIONS_OT_SetActiveGuidePlane,
    DIMENSIONS_OT_SetActiveFacePlane,
    DIMENSIONS_OT_SetWorldPlane,
    DIMENSIONS_OT_SetViewPlane,
    DIMENSIONS_OT_ClearActivePlane,
    DIMENSIONS_OT_RepairGuidePlane,
)
