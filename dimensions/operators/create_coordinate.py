"""Creation operators for named datums, coordinate, and elevation annotations."""

import bpy
from mathutils import Vector

from .. import messages
from ..anchors import set_anchor, set_anchor_from_snap, set_world_anchor
from ..collections import create_dimension_object, create_guide_point_object
from ..coordinate_dimensions import is_datum_object
from ..drawing import clear_preview_state, set_preview_state
from ..inference import InferenceSession, handle_inference_event, inference_status
from ..interaction import is_confirm_event, is_navigation_event, remember_session_context, session_context_changed
from ..properties import is_guide_object, is_read_only_dimensions_object
from ..snap_targets import handle_snap_target_event
from ..snapping import copy_snap, find_nearest_snap_point


def _selected_vertex(context):
    if context.mode != "EDIT_MESH" or context.edit_object is None:
        return None
    import bmesh

    mesh = bmesh.from_edit_mesh(context.edit_object.data)
    selected = [vertex for vertex in mesh.verts if vertex.select and not vertex.hide]
    return None if len(selected) != 1 else (
        context.edit_object,
        selected[0].index,
        context.edit_object.matrix_world @ selected[0].co,
    )


def _set_source_anchor(context, anchor):
    selected = _selected_vertex(context)
    if selected is None:
        world = context.scene.cursor.location.copy()
        set_world_anchor(anchor, world)
        return world
    obj, index, world = selected
    set_anchor(anchor, obj, index)
    return world


def _find_datum(context, name=""):
    if name:
        candidate = context.scene.objects.get(name)
        if is_datum_object(candidate):
            return candidate
    active = context.view_layer.objects.active
    if is_datum_object(active):
        return active
    datums = tuple(obj for obj in context.scene.objects if is_datum_object(obj))
    return datums[0] if len(datums) == 1 else None


def _datum_items(_self, context):
    if context is None or context.scene is None:
        return ()
    return tuple(
        (obj.name, obj.name, obj.guide_props.datum_name or "Datum")
        for obj in context.scene.objects
        if is_datum_object(obj)
    )


class DIMENSIONS_OT_CreateDatum(bpy.types.Operator):
    bl_idname = "dimensions.create_datum"
    bl_label = "Create / Promote Datum"
    bl_description = "Create an oriented datum at the cursor or promote the active guide point"
    bl_options = {"REGISTER", "UNDO"}

    datum_name: bpy.props.StringProperty(name="Name", default="Datum")

    def execute(self, context):
        obj = context.view_layer.objects.active
        if is_guide_object(obj) and obj.guide_props.kind == "POINT" and is_read_only_dimensions_object(obj):
            self.report(messages.WARNING, messages.MANAGER_LINKED_READ_ONLY)
            return {"CANCELLED"}
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
    datum_object_name: bpy.props.EnumProperty(
        name="Datum",
        items=_datum_items,
        options={"SKIP_SAVE"},
    )

    def invoke(self, context, _event):
        if context.area is None or context.area.type != "VIEW_3D":
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        if context.mode not in {"OBJECT", "EDIT_MESH"}:
            self.report(messages.WARNING, messages.DIMENSIONS_REQUIRE_SUPPORTED_MODE)
            return {"CANCELLED"}
        datum = _find_datum(context, self.datum_object_name or self.datum_name)
        if datum is not None:
            self.datum_object_name = datum.name
            return self.execute(context)
        datums = tuple(obj for obj in context.scene.objects if is_datum_object(obj))
        if not datums:
            self.report(messages.WARNING, messages.DATUM_REQUIRED)
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, _context):
        self.layout.prop(self, "datum_object_name")

    def execute(self, context):
        datum = _find_datum(context, self.datum_object_name or self.datum_name)
        if datum is not None and datum.name not in context.scene.objects:
            datum = None
        if datum is None:
            self.report(messages.WARNING, messages.DATUM_REQUIRED)
            return {"CANCELLED"}
        selected = _selected_vertex(context)
        if selected is not None:
            source, index, point = selected
            return self._create_annotation(context, datum, point, source=source, vertex_index=index)
        if context.mode == "EDIT_MESH":
            self.report(messages.WARNING, messages.DATUM_POINT_REQUIRED)
            return {"CANCELLED"}
        if context.area is not None and context.area.type == "VIEW_3D":
            return self._begin_point_acquisition(context, datum)
        return self._create_annotation(context, datum, context.scene.cursor.location)

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or session_context_changed(self, context):
            clear_preview_state()
            return {"CANCELLED"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            clear_preview_state()
            return {"CANCELLED"}
        if handle_snap_target_event(context, event):
            self._update_preview()
            return {"RUNNING_MODAL"}
        if handle_inference_event(self.inference_session, event):
            self._update_preview()
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            self.hover_snap = self._find_snap(context, event)
            self._update_preview()
            return {"RUNNING_MODAL"}
        if (event.type == "LEFTMOUSE" and event.value == "PRESS") or is_confirm_event(event):
            snap = self.hover_snap or self._find_snap(context, event)
            if snap is None:
                return {"RUNNING_MODAL"}
            datum = _find_datum(context, self.datum_object_name)
            if datum is None:
                clear_preview_state()
                self.report(messages.WARNING, messages.DATUM_REQUIRED)
                return {"CANCELLED"}
            result = self._create_annotation(context, datum, snap["world_co"], snap=snap)
            clear_preview_state()
            return result
        if is_navigation_event(event):
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def cancel(self, _context):
        clear_preview_state()

    def _begin_point_acquisition(self, context, datum):
        self.datum_object_name = datum.name
        self.hover_snap = None
        self.inference_session = InferenceSession()
        remember_session_context(self, context)
        self._update_preview()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _find_snap(self, context, event):
        from ..guide_planes import active_plane_frame

        frame = active_plane_frame(context.scene)
        return find_nearest_snap_point(
            context,
            event.mouse_region_x,
            event.mouse_region_y,
            include_free=True,
            plane_point=None if frame is None else frame[0],
            plane_normal=None if frame is None else frame[3],
            inference_session=self.inference_session,
        )

    def _update_preview(self):
        state = {
            "state": "PICK_DATUM_POINT",
            "annotation_kind": self.annotation_kind,
            "tool_label": "COORD" if self.annotation_kind == "COORDINATE" else "ELEV",
        }
        status = inference_status(self.inference_session)
        if status:
            state["inference_status"] = status
        if self.hover_snap is not None:
            state.update({
                "hover_screen": self.hover_snap.get("screen_co"),
                "hover_type": self.hover_snap.get("type", "WORLD"),
                "hover_label": self.hover_snap.get("label", "Point"),
                "hover_snap": copy_snap(self.hover_snap),
            })
        set_preview_state(state)

    def _create_annotation(self, context, datum, point, *, snap=None, source=None, vertex_index=-1):
        obj = create_dimension_object(context, f"DIM {self.annotation_kind.title()}")
        props = obj.dimension_props
        props.annotation_kind = self.annotation_kind
        props.datum_object = datum
        point = Vector(point)
        if snap is not None:
            set_anchor_from_snap(props.start, snap)
        elif source is not None:
            set_anchor(props.start, source, vertex_index)
        else:
            set_world_anchor(props.start, point)
        label = point.copy()
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
