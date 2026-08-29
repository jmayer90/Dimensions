"""Creation operators for named datums, coordinate, and elevation annotations."""

import bpy

from .. import messages
from ..anchors import set_anchor, set_world_anchor
from ..collections import create_dimension_object, create_guide_point_object
from ..coordinate_dimensions import is_datum_object
from ..properties import is_guide_object


def _selected_vertex(context):
    if context.mode != "EDIT_MESH" or context.edit_object is None:
        return None
    import bmesh

    mesh = bmesh.from_edit_mesh(context.edit_object.data)
    selected = [vertex for vertex in mesh.verts if vertex.select and not vertex.hide]
    return None if len(selected) != 1 else (context.edit_object, selected[0].index)


def _set_source_anchor(context, anchor):
    selected = _selected_vertex(context)
    if selected is None:
        set_world_anchor(anchor, context.scene.cursor.location)
    else:
        set_anchor(anchor, *selected)


def _find_datum(context, name=""):
    if name:
        candidate = context.scene.objects.get(name)
        if is_datum_object(candidate):
            return candidate
    active = context.view_layer.objects.active
    if is_datum_object(active):
        return active
    return next((obj for obj in context.scene.objects if is_datum_object(obj)), None)


class DIMENSIONS_OT_CreateDatum(bpy.types.Operator):
    bl_idname = "dimensions.create_datum"
    bl_label = "Create / Promote Datum"
    bl_description = "Create an oriented datum at the cursor or promote the active guide point"
    bl_options = {"REGISTER", "UNDO"}

    datum_name: bpy.props.StringProperty(name="Name", default="Datum")

    def execute(self, context):
        obj = context.view_layer.objects.active
        if not (is_guide_object(obj) and obj.guide_props.kind == "POINT"):
            obj = create_guide_point_object(context, "DATUM Datum")
            _set_source_anchor(context, obj.guide_props.start)
        obj.guide_props.is_datum = True
        obj.guide_props.datum_name = self.datum_name.strip() or "Datum"
        obj.name = f"DATUM {obj.guide_props.datum_name}"
        obj.select_set(True)
        context.view_layer.objects.active = obj
        self.report(messages.INFO, messages.CREATED_DATUM)
        return {"FINISHED"}


class _CreateDatumAnnotation:
    annotation_kind = "COORDINATE"

    datum_name: bpy.props.StringProperty(name="Datum Object", default="")

    def execute(self, context):
        datum = _find_datum(context, self.datum_name)
        if datum is None:
            self.report(messages.WARNING, messages.DATUM_REQUIRED)
            return {"CANCELLED"}
        obj = create_dimension_object(context, f"DIM {self.annotation_kind.title()}")
        props = obj.dimension_props
        props.annotation_kind = self.annotation_kind
        props.datum_object = datum
        _set_source_anchor(context, props.start)
        label = context.scene.cursor.location.copy()
        label.x += 0.5
        set_world_anchor(props.end, label)
        obj.location = label
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        self.report(messages.INFO, messages.CREATED_COORDINATE if self.annotation_kind == "COORDINATE" else messages.CREATED_ELEVATION)
        return {"FINISHED"}


class DIMENSIONS_OT_CreateCoordinate(_CreateDatumAnnotation, bpy.types.Operator):
    bl_idname = "dimensions.create_coordinate"
    bl_label = "Create Coordinate Dimension"
    bl_description = "Create an ordinate label for one point relative to a named datum"
    bl_options = {"REGISTER", "UNDO"}
    annotation_kind = "COORDINATE"


class DIMENSIONS_OT_CreateElevation(_CreateDatumAnnotation, bpy.types.Operator):
    bl_idname = "dimensions.create_elevation"
    bl_label = "Create Elevation Dimension"
    bl_description = "Create a level annotation for one point relative to a named datum"
    bl_options = {"REGISTER", "UNDO"}
    annotation_kind = "ELEVATION"


classes = (DIMENSIONS_OT_CreateDatum, DIMENSIONS_OT_CreateCoordinate, DIMENSIONS_OT_CreateElevation)
