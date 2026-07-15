import bpy

from ..anchors import set_anchor_from_snap
from ..collections import create_guide_object, remove_measurement_snap_proxies
from ..drawing import clear_guide_preview_state, set_guide_preview_state
from ..snapping import copy_snap, find_nearest_snap_point


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
        self.state = "PICK_START"
        self._update_preview()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            clear_guide_preview_state()
            return {"CANCELLED"}

        if event.type in {"A", "X", "Y", "Z"} and event.value == "PRESS":
            self.axis = "ALIGNED" if event.type == "A" else event.type
            self._update_preview()
            self.report({"INFO"}, f"Guide direction: {self.axis.title()}")
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            plane_point = self.start_snap["world_co"] if self.start_snap is not None else None
            self.hover_snap = find_nearest_snap_point(
                context,
                event.mouse_region_x,
                event.mouse_region_y,
                include_free=True,
                plane_point=plane_point,
            )
            self._update_preview()
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
                self._update_preview()
                return {"RUNNING_MODAL"}

            if (self.hover_snap["world_co"] - self.start_snap["world_co"]).length < 1e-6:
                return {"RUNNING_MODAL"}
            self._create(context, self.hover_snap)
            clear_guide_preview_state()
            return {"FINISHED"}

        if event.type in {"RIGHTMOUSE", "ESC"}:
            clear_guide_preview_state()
            return {"CANCELLED"}
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def _create(self, context, end_snap):
        obj = create_guide_object(context)
        set_anchor_from_snap(obj.guide_props.start, self.start_snap)
        set_anchor_from_snap(obj.guide_props.end, end_snap)
        obj.guide_props.axis = self.axis
        obj.location = self.start_snap["world_co"]
        self.report({"INFO"}, "Created construction guide")

    def _update_preview(self):
        state = {"axis": self.axis}
        if self.hover_snap is not None:
            state["hover_screen"] = self.hover_snap["screen_co"]
            state["hover_type"] = self.hover_snap.get("type", "WORLD")
            state["hover_label"] = self.hover_snap.get("label", "Point")
        if self.start_snap is not None:
            state["start_world"] = self.start_snap["world_co"]
        if self.state == "PICK_END" and self.hover_snap is not None:
            state["end_world"] = self.hover_snap["world_co"]
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
