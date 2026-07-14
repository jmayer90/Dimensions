import bmesh
import bpy

from ..drawing import clear_measure_state, set_measure_state
from ..snapping import find_nearest_snap_point


class CADDIM_OT_CreateLine(bpy.types.Operator):
    bl_idname = "dimensions.create_line"
    bl_label = "Draw Mesh Line"
    bl_description = "Create chained mesh edges in Edit Mode using Dimensions snapping"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.mode != "EDIT_MESH":
            self.report({"ERROR"}, "Draw Mesh Line works in Edit Mode from a 3D View")
            return {"CANCELLED"}

        self.state = "PICK_START"
        self.axis = "ALIGNED"
        self.start_snap = None
        self.hover_snap = self._find_snap(context, event)
        self.distance_text = ""
        self._update_preview()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.mode != "EDIT_MESH":
            clear_measure_state()
            return {"CANCELLED"}

        if event.type in {"A", "X", "Y", "Z"} and event.value == "PRESS":
            self.axis = "ALIGNED" if event.type == "A" else event.type
            self._update_preview()
            self.report({"INFO"}, f"Line direction: {self.axis.title()}")
            return {"RUNNING_MODAL"}

        if event.value == "PRESS" and self.state == "PICK_END" and self._handle_distance_key(event):
            self._update_preview()
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            self.hover_snap = self._find_snap(context, event)
            self._update_preview()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.hover_snap is None:
                return {"RUNNING_MODAL"}

            if self.state == "PICK_START":
                self.start_snap = self._copy_snap(self.hover_snap)
                self.state = "PICK_END"
                self.distance_text = ""
                self._update_preview()
                return {"RUNNING_MODAL"}

            end_snap = self._effective_end_snap()
            if end_snap is None or (end_snap["world_co"] - self.start_snap["world_co"]).length < 1e-6:
                return {"RUNNING_MODAL"}

            self._create_edge(context, self.start_snap, end_snap)
            self.start_snap = self._copy_snap(end_snap)
            self.hover_snap = self.start_snap
            self.distance_text = ""
            self._update_preview()
            return {"RUNNING_MODAL"}

        if event.type in {"RIGHTMOUSE", "ESC", "RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            clear_measure_state()
            return {"FINISHED"}

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}

        return {"RUNNING_MODAL"}

    def _find_snap(self, context, event):
        plane_point = self.start_snap["world_co"] if self.start_snap is not None else None
        return find_nearest_snap_point(
            context,
            event.mouse_region_x,
            event.mouse_region_y,
            include_free=True,
            plane_point=plane_point,
        )

    def _effective_end_snap(self):
        if self.hover_snap is None:
            return None

        snap = self._copy_snap(self.hover_snap)
        if self.start_snap is None:
            return snap

        end_world = snap["world_co"]
        direction = end_world - self.start_snap["world_co"]

        if self.axis == "X":
            direction = direction.project(self._axis_vector("X"))
        elif self.axis == "Y":
            direction = direction.project(self._axis_vector("Y"))
        elif self.axis == "Z":
            direction = direction.project(self._axis_vector("Z"))

        if direction.length < 1e-6:
            return snap

        if self.distance_text:
            try:
                direction.normalize()
                direction *= float(self.distance_text)
            except ValueError:
                pass

        snap["type"] = "WORLD"
        snap["object"] = None
        snap["vertex_index"] = -1
        snap["world_co"] = self.start_snap["world_co"] + direction
        return snap

    def _create_edge(self, context, start_snap, end_snap):
        obj = context.edit_object
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        start_vertex = self._get_or_create_bmesh_vertex(obj, bm, start_snap)
        end_vertex = self._get_or_create_bmesh_vertex(obj, bm, end_snap)

        if start_vertex is not end_vertex:
            try:
                bm.edges.new((start_vertex, end_vertex))
            except ValueError:
                pass

        bmesh.update_edit_mesh(mesh)

    @staticmethod
    def _get_or_create_bmesh_vertex(obj, bm, snap):
        if snap.get("type") == "VERTEX" and snap.get("object") == obj:
            vertex_index = snap.get("vertex_index", -1)
            if 0 <= vertex_index < len(bm.verts):
                return bm.verts[vertex_index]

        local_co = obj.matrix_world.inverted() @ snap["world_co"]
        vertex = bm.verts.new(local_co)
        bm.verts.ensure_lookup_table()
        return vertex

    def _update_preview(self):
        state = {"state": self.state, "axis": self.axis}
        if self.hover_snap is not None:
            state["hover_screen"] = self.hover_snap["screen_co"]
            state["hover_type"] = self.hover_snap.get("type", "WORLD")
            state["hover_label"] = self.hover_snap.get("label", "Point")
        if self.start_snap is not None:
            state["start_world"] = self.start_snap["world_co"]
            end_snap = self._effective_end_snap()
            if end_snap is not None:
                state["end_world"] = end_snap["world_co"]
        set_measure_state(state)

    def _handle_distance_key(self, event):
        key_map = {
            "ZERO": "0",
            "ONE": "1",
            "TWO": "2",
            "THREE": "3",
            "FOUR": "4",
            "FIVE": "5",
            "SIX": "6",
            "SEVEN": "7",
            "EIGHT": "8",
            "NINE": "9",
            "NUMPAD_0": "0",
            "NUMPAD_1": "1",
            "NUMPAD_2": "2",
            "NUMPAD_3": "3",
            "NUMPAD_4": "4",
            "NUMPAD_5": "5",
            "NUMPAD_6": "6",
            "NUMPAD_7": "7",
            "NUMPAD_8": "8",
            "NUMPAD_9": "9",
            "PERIOD": ".",
            "NUMPAD_PERIOD": ".",
        }

        if event.type in key_map:
            self.distance_text += key_map[event.type]
            return True

        if event.type == "BACK_SPACE":
            self.distance_text = self.distance_text[:-1]
            return True

        if event.type == "MINUS" and not self.distance_text:
            self.distance_text = "-"
            return True

        return False

    @staticmethod
    def _axis_vector(axis):
        from mathutils import Vector

        return {
            "X": Vector((1.0, 0.0, 0.0)),
            "Y": Vector((0.0, 1.0, 0.0)),
            "Z": Vector((0.0, 0.0, 1.0)),
        }[axis]

    @staticmethod
    def _copy_snap(snap):
        return {
            "type": snap.get("type", "WORLD"),
            "label": snap.get("label", "Point"),
            "object": snap.get("object"),
            "vertex_index": snap.get("vertex_index", -1),
            "world_co": snap["world_co"].copy(),
            "screen_co": snap["screen_co"].copy(),
        }
