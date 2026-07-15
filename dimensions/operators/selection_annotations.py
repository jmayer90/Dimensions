import bmesh
import bpy
from mathutils import Vector

from ..anchors import set_anchor, set_object_anchor
from ..area_binding import FACE_ID_ATTRIBUTE, bind_area_faces, evaluate_area_binding
from ..angle_binding import derive_angle_from_world_edges, set_angle_edge
from ..collections import create_dimension_object
from ..constants import DEFAULT_OFFSET_DISTANCE
from ..dimension_geometry import get_dimension_world_geometry


_pending_area_annotation_name = ""


def _selected_bmesh(context):
    obj = context.edit_object
    if obj is None or obj.type != "MESH":
        return None, None
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.verts.index_update()
    return obj, bm


def _view_direction(context):
    if context.region_data is None:
        return Vector((0.0, 0.0, 1.0))
    return (context.region_data.view_rotation @ Vector((0.0, 0.0, -1.0))).normalized()


def create_dimension_from_selected_edge(context):
    obj, bm = _selected_bmesh(context)
    if bm is None:
        return None
    selected = [edge for edge in bm.edges if edge.select and not edge.hide]
    if len(selected) != 1:
        return None
    edge = selected[0]
    dimension = create_dimension_object(context, "DIM Selected Edge")
    props = dimension.dimension_props
    props.annotation_kind = "LINEAR"
    set_anchor(props.start, obj, edge.verts[0].index)
    set_anchor(props.end, obj, edge.verts[1].index)
    start_world = obj.matrix_world @ edge.verts[0].co
    end_world = obj.matrix_world @ edge.verts[1].co
    props.offset_plane_normal = tuple(_view_direction(context))
    props.offset_distance = DEFAULT_OFFSET_DISTANCE
    geometry = get_dimension_world_geometry(
        "ALIGNED",
        start_world,
        end_world,
        Vector(props.offset_plane_normal),
        props.offset_distance,
    )
    dimension.location = geometry["line_mid_world"] if geometry else (start_world + end_world) * 0.5
    return dimension


class DIMENSIONS_OT_DimensionSelectedEdge(bpy.types.Operator):
    bl_idname = "dimensions.dimension_selected_edge"
    bl_label = "Dimension Selected Edge"
    bl_description = "Create a linear dimension from the single selected mesh edge"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH" and context.edit_object is not None

    def execute(self, context):
        dimension = create_dimension_from_selected_edge(context)
        if dimension is None:
            self.report({"ERROR"}, "Select exactly one edge")
            return {"CANCELLED"}
        self.report({"INFO"}, "Created dimension from selected edge")
        return {"FINISHED"}


class DIMENSIONS_OT_AreaSelectedFaces(bpy.types.Operator):
    bl_idname = "dimensions.area_selected_faces"
    bl_label = "Annotate Selected Face Area"
    bl_description = "Create a leader annotation for the combined area of selected faces"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH" and context.edit_object is not None

    def invoke(self, _context, _event):
        return bpy.ops.dimensions.create_area("INVOKE_DEFAULT")

    def execute(self, context):
        obj, bm = _selected_bmesh(context)
        faces = [face for face in bm.faces if face.select and not face.hide]
        if not faces:
            self.report({"ERROR"}, "Select one or more faces")
            return {"CANCELLED"}

        face_indices = [face.index for face in faces]
        annotation = create_dimension_object(context, "AREA Selected Faces")
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        faces = [bm.faces[index] for index in face_indices]
        props = annotation.dimension_props
        props.annotation_kind = "AREA"
        result = bind_area_faces(props, obj, faces)
        if result is None:
            bpy.data.objects.remove(annotation, do_unlink=True)
            self.report({"ERROR"}, "Selected faces have no measurable area")
            return {"CANCELLED"}

        total_area = result["area"]
        center = result["center"]
        normal = result["normal"]
        axes = (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
        tangent = max(
            (axis - normal * axis.dot(normal) for axis in axes),
            key=lambda value: value.length_squared,
        ).normalized()
        leader_length = max(DEFAULT_OFFSET_DISTANCE * 2.0, total_area ** 0.5 * 0.25)
        label_point = center + tangent * leader_length

        props.area_value = total_area
        props.area_face_count = result["face_count"]
        set_object_anchor(props.start, obj, center)
        set_object_anchor(props.end, obj, label_point)
        annotation.location = label_point
        self.report({"INFO"}, f"Created area annotation from {len(faces)} face(s)")
        return {"FINISHED"}


class DIMENSIONS_OT_RebindAreaFromSelection(bpy.types.Operator):
    bl_idname = "dimensions.rebind_area_from_selection"
    bl_label = "Rebind Area from Selection"
    bl_description = "Replace this Area's live source with the currently selected faces"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        source = context.edit_object
        if context.mode != "EDIT_MESH" or source is None:
            return False
        annotation = bpy.data.objects.get(_pending_area_annotation_name)
        return bool(
            annotation
            and hasattr(annotation, "dimension_props")
            and annotation.dimension_props.enabled
            and annotation.dimension_props.annotation_kind == "AREA"
        )

    def execute(self, context):
        global _pending_area_annotation_name
        source = context.edit_object
        annotation = bpy.data.objects.get(_pending_area_annotation_name) if source else None
        if source is None or annotation is None:
            self.report({"ERROR"}, "Use Select Source Faces from an Area annotation first")
            return {"CANCELLED"}
        bm = bmesh.from_edit_mesh(source.data)
        faces = [face for face in bm.faces if face.select and not face.hide]
        if not faces:
            self.report({"ERROR"}, "Select one or more source faces")
            return {"CANCELLED"}
        result = bind_area_faces(annotation.dimension_props, source, faces)
        if result is None:
            self.report({"ERROR"}, "Selected faces have no measurable area")
            return {"CANCELLED"}
        annotation.dimension_props.area_value = result["area"]
        annotation.dimension_props.area_face_count = result["face_count"]
        _pending_area_annotation_name = ""
        self.report({"INFO"}, f"Rebound Area to {len(faces)} face(s)")
        return {"FINISHED"}


class DIMENSIONS_OT_CaptureArea(bpy.types.Operator):
    bl_idname = "dimensions.capture_area"
    bl_label = "Capture Area Value"
    bl_description = "Freeze the current Area value as an intentional snapshot"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active
        return bool(
            obj
            and hasattr(obj, "dimension_props")
            and obj.dimension_props.enabled
            and obj.dimension_props.annotation_kind == "AREA"
            and obj.dimension_props.measurement_state == "LIVE"
        )

    def execute(self, context):
        props = context.view_layer.objects.active.dimension_props
        result = evaluate_area_binding(props)
        if result is not None:
            props.area_value = result["area"]
            props.area_face_count = result["face_count"]
        props.measurement_state = "CAPTURED"
        self.report({"INFO"}, "Captured Area value")
        return {"FINISHED"}


class DIMENSIONS_OT_SelectAreaSource(bpy.types.Operator):
    bl_idname = "dimensions.select_area_source"
    bl_label = "Select Area Source Faces"
    bl_description = "Enter Edit Mode on the source mesh and select the faces bound to this Area"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active
        return bool(
            context.mode == "OBJECT"
            and obj
            and hasattr(obj, "dimension_props")
            and obj.dimension_props.enabled
            and obj.dimension_props.annotation_kind == "AREA"
            and obj.dimension_props.area_source_object is not None
            and len(obj.dimension_props.area_faces) > 0
        )

    def execute(self, context):
        global _pending_area_annotation_name
        annotation = context.view_layer.objects.active
        props = annotation.dimension_props
        source = props.area_source_object
        for obj in context.selected_objects:
            obj.select_set(False)
        source.hide_set(False)
        source.select_set(True)
        context.view_layer.objects.active = source
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(source.data)
        layer = bm.faces.layers.int.get(FACE_ID_ATTRIBUTE)
        wanted = {binding.face_id for binding in props.area_faces}
        for face in bm.faces:
            face.select = bool(layer is not None and face[layer] in wanted)
        bmesh.update_edit_mesh(source.data, loop_triangles=False, destructive=False)
        _pending_area_annotation_name = annotation.name
        self.report({"INFO"}, f"Selected {sum(face.select for face in bm.faces)} bound face(s)")
        return {"FINISHED"}


class DIMENSIONS_OT_AngleSelectedEdges(bpy.types.Operator):
    bl_idname = "dimensions.angle_selected_edges"
    bl_label = "Dimension Selected Angle"
    bl_description = "Create an angle dimension from any two selected non-parallel edges"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH" and context.edit_object is not None

    def invoke(self, _context, _event):
        return bpy.ops.dimensions.create_angle("INVOKE_DEFAULT")

    def execute(self, context):
        obj, bm = _selected_bmesh(context)
        edges = [edge for edge in bm.edges if edge.select and not edge.hide]
        if len(edges) != 2:
            self.report({"ERROR"}, "Select exactly two edges")
            return {"CANCELLED"}
        world_edges = [tuple(obj.matrix_world @ vertex.co for vertex in edge.verts) for edge in edges]
        source = derive_angle_from_world_edges(*world_edges[0], *world_edges[1], "MINOR")
        if source is None:
            self.report({"ERROR"}, "Selected edges must define a non-parallel angle")
            return {"CANCELLED"}
        annotation = create_dimension_object(context, "ANGLE Selected Edges")
        props = annotation.dimension_props
        props.annotation_kind = "ANGLE"
        set_angle_edge(props, "A", obj, tuple(vertex.index for vertex in edges[0].verts))
        set_angle_edge(props, "B", obj, tuple(vertex.index for vertex in edges[1].verts))
        first_length = (source["start"] - source["center"]).length
        second_length = (source["end"] - source["center"]).length
        props.angle_radius = max(0.001, min(first_length, second_length) * 0.35)
        props.measurement_state = "LIVE"
        annotation.location = source["center"]
        self.report({"INFO"}, "Created angle dimension from selected edges")
        return {"FINISHED"}


classes = (
    DIMENSIONS_OT_DimensionSelectedEdge,
    DIMENSIONS_OT_AreaSelectedFaces,
    DIMENSIONS_OT_AngleSelectedEdges,
    DIMENSIONS_OT_RebindAreaFromSelection,
    DIMENSIONS_OT_CaptureArea,
    DIMENSIONS_OT_SelectAreaSource,
)
