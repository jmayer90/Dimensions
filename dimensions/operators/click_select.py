import bpy

from ..drawing import find_dimension_hit, find_guide_hit


class DIMENSIONS_OT_ClickSelect(bpy.types.Operator):
    """Select a Dimensions annotation from the active Dimensions workspace tool."""

    bl_idname = "dimensions.click_select"
    bl_label = "Select Dimensions Annotation"
    bl_options = {"INTERNAL", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D" and context.mode == "OBJECT"

    def invoke(self, context, event):
        hit_object = find_dimension_hit(context, event.mouse_region_x, event.mouse_region_y)
        if hit_object is None:
            hit_object = find_guide_hit(context, event.mouse_region_x, event.mouse_region_y)
        if hit_object is None:
            return {"PASS_THROUGH"}

        if event.shift:
            hit_object.select_set(not hit_object.select_get())
            if hit_object.select_get():
                context.view_layer.objects.active = hit_object
            elif context.view_layer.objects.active == hit_object:
                remaining = list(context.selected_objects)
                context.view_layer.objects.active = remaining[-1] if remaining else None
        else:
            for selected_object in context.selected_objects:
                selected_object.select_set(False)
            hit_object.select_set(True)
            context.view_layer.objects.active = hit_object

        context.area.tag_redraw()
        return {"FINISHED"}
