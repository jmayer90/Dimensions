"""Persistent guide-point creation through shared acquisition."""

import bpy
from mathutils import Vector

from .. import messages
from ..anchors import set_anchor_from_snap, set_world_anchor
from ..collections import create_guide_point_object, ensure_guide_point_snap_proxy
from ..scene_sync import sync_scene_objects
from ..snapping import find_nearest_snap_point
from .create_guide import CADDIM_OT_CreateGuide


def selection_centroid(context):
    """Return the world centroid of the current mesh/object selection."""
    if context.mode == "EDIT_MESH" and context.edit_object is not None:
        import bmesh

        obj = context.edit_object
        mesh = bmesh.from_edit_mesh(obj.data)
        selected = [vertex for vertex in mesh.verts if vertex.select and not vertex.hide]
        if not selected:
            return None
        return sum((obj.matrix_world @ vertex.co for vertex in selected), Vector()) / len(selected)
    selected = [obj.matrix_world.translation.copy() for obj in context.selected_objects]
    return None if not selected else sum(selected, Vector()) / len(selected)


class DIMENSIONS_OT_CreateGuidePoint(CADDIM_OT_CreateGuide):
    bl_idname = "dimensions.create_guide_point"
    bl_label = "Add Guide Point"
    bl_description = "Place a persistent construction point"

    placement_mode: bpy.props.EnumProperty(
        name="Placement",
        items=(
            ("DIRECT", "Snapped Point", "Place at one snapped or free position"),
            ("OFFSET", "Offset Point", "Place at a typed or constrained distance from a reference"),
            ("SELECTION", "Selection Centroid", "Place at the midpoint or centroid of the current selection"),
        ),
        default="DIRECT",
        options={"SKIP_SAVE"},
    )

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.mode not in {"OBJECT", "EDIT_MESH"}:
            self.report(messages.WARNING, messages.GUIDE_POINT_REQUIRE_SUPPORTED_MODE)
            return {"CANCELLED"}
        if self.placement_mode == "SELECTION":
            point = selection_centroid(context)
            if point is None:
                self.report(messages.WARNING, messages.GUIDE_POINT_SELECTION_REQUIRED)
                return {"CANCELLED"}
            self._create_at_world(context, point)
            return {"FINISHED"}
        if context.mode != "OBJECT":
            self.report(messages.WARNING, messages.GUIDE_REQUIRE_OBJECT_MODE)
            return {"CANCELLED"}
        return super().invoke(context, event)

    def modal(self, context, event):
        if (
            self.placement_mode == "DIRECT" and self.state == "PICK_START"
            and event.type == "LEFTMOUSE" and event.value == "PRESS"
        ):
            snap = self.hover_snap or find_nearest_snap_point(
                context, event.mouse_region_x, event.mouse_region_y,
                include_free=True, inference_session=self.inference_session,
            )
            if snap is None:
                return {"RUNNING_MODAL"}
            self._create_from_snap(context, snap)
            from ..drawing import clear_guide_preview_state

            clear_guide_preview_state()
            return {"FINISHED"}
        return super().modal(context, event)

    def _create(self, context, end_snap):
        self._create_from_snap(context, end_snap)

    def _create_from_snap(self, context, snap):
        obj = create_guide_point_object(context)
        set_anchor_from_snap(obj.guide_props.start, snap)
        self._finish_object(context, obj, Vector(snap["world_co"]))

    def _create_at_world(self, context, world_co):
        obj = create_guide_point_object(context)
        set_world_anchor(obj.guide_props.start, world_co)
        self._finish_object(context, obj, Vector(world_co))

    def _finish_object(self, context, obj, world_co):
        obj.location = world_co
        ensure_guide_point_snap_proxy(obj, context.scene)
        if context.mode == "OBJECT":
            for selected in context.selected_objects:
                selected.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
        sync_scene_objects(context.scene)
        self.report(messages.INFO, messages.CREATED_GUIDE_POINT)


classes = (DIMENSIONS_OT_CreateGuidePoint,)
