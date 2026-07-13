import bpy

from ..collections import create_dimension_object


class CADDIM_OT_AddTestDimension(bpy.types.Operator):
    bl_idname = "caddim.add_test_dimension"
    bl_label = "Add Test Dimension"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        dimension_object = create_dimension_object(context, "DIM Test")

        for selected_object in context.selected_objects:
            selected_object.select_set(False)

        dimension_object.select_set(True)
        context.view_layer.objects.active = dimension_object

        self.report({"INFO"}, "Created test CAD dimension")
        return {"FINISHED"}
