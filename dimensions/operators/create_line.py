import bmesh
import bpy

from ..drawing import clear_measure_state, set_measure_state
from ..interaction import (
    axis_from_event,
    axis_from_mouse_direction,
    constrained_delta,
    is_confirm_event,
    is_navigation_event,
    update_distance_text,
)
from ..snapping import copy_snap, find_nearest_snap_point
from ..units import parse_distance_input


class CADDIM_OT_CreateLine(bpy.types.Operator):
    bl_idname = "dimensions.create_line"
    bl_label = "Draw Mesh Line"
    bl_description = "Draw connected pencil edges or knife-like surface cuts using logical snapping and typed distances"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.mode != "EDIT_MESH":
            self.report({"ERROR"}, "Draw Mesh Line works in Edit Mode from a 3D View")
            return {"CANCELLED"}

        self.state = "PICK_START"
        self.axis = "ALIGNED"
        self.start_snap = None
        self.start_vertex_index = None
        self.path_world_coords = []
        self.has_committed_segments = False
        self.hover_snap = self._find_snap(context, event)
        self.distance_text = ""
        self.distance_input_valid = True
        self.axis_gesture_active = False
        self._update_preview(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.mode != "EDIT_MESH":
            clear_measure_state()
            return {"CANCELLED"}

        if event.type == "MIDDLEMOUSE" and self.state == "PICK_END":
            if event.value == "PRESS":
                self.axis_gesture_active = True
                self._update_axis_gesture(context, event)
                self._update_preview(context)
                return {"RUNNING_MODAL"}
            if event.value == "RELEASE" and self.axis_gesture_active:
                self.axis_gesture_active = False
                self._update_preview(context)
                return {"RUNNING_MODAL"}

        axis = axis_from_event(event)
        if axis is not None:
            self.axis = axis
            self._update_preview(context)
            self.report({"INFO"}, f"Line direction: {self.axis.title()}")
            return {"RUNNING_MODAL"}

        if self.state == "PICK_END":
            new_text, handled = update_distance_text(self.distance_text, event)
            if handled:
                self.distance_text = new_text
                self._update_preview(context)
                return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            if self.axis_gesture_active:
                self._update_axis_gesture(context, event)
            self.hover_snap = self._find_snap(context, event)
            self._update_preview(context)
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.hover_snap is None:
                return {"RUNNING_MODAL"}

            if self.state == "PICK_START":
                self.start_snap = self._copy_snap(self.hover_snap)
                self.path_world_coords = [self.start_snap["world_co"].copy()]
                self.state = "PICK_END"
                self.distance_text = ""
                self._update_preview(context)
                return {"RUNNING_MODAL"}

            return self._commit_segment(context)

        if is_confirm_event(event):
            if self.state == "PICK_END":
                return self._commit_segment(context)
            clear_measure_state()
            return {"FINISHED"} if self.has_committed_segments else {"CANCELLED"}

        if event.type == "ESC" and event.value == "PRESS" and self.distance_text:
            self.distance_text = ""
            self.distance_input_valid = True
            self._update_preview(context)
            return {"RUNNING_MODAL"}

        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            clear_measure_state()
            return {"FINISHED"} if self.has_committed_segments else {"CANCELLED"}

        if is_navigation_event(event):
            return {"PASS_THROUGH"}

        return {"RUNNING_MODAL"}

    def _commit_segment(self, context):
        end_snap = self._effective_end_snap(context)
        if end_snap is None or (end_snap["world_co"] - self.start_snap["world_co"]).length < 1e-6:
            if self.distance_text:
                self.report({"WARNING"}, f"Invalid distance: {self.distance_text}")
            return {"RUNNING_MODAL"}

        end_vertex_index = self._create_edge(
            context,
            self.start_snap,
            end_snap,
            start_vertex_index=self.start_vertex_index,
        )
        if end_vertex_index is None:
            self.report({"WARNING"}, "Could not create a valid mesh segment")
            return {"RUNNING_MODAL"}

        self.has_committed_segments = True
        self.path_world_coords.append(end_snap["world_co"].copy())
        path_finalized = False
        closing_path = (
            len(self.path_world_coords) >= 4
            and (self.path_world_coords[-1] - self.path_world_coords[0]).length <= 1e-5
        )
        if closing_path:
            finalized_index = self._finalize_closed_path(context, self.path_world_coords)
            if finalized_index is not None:
                end_vertex_index = finalized_index
                path_finalized = True
            else:
                self.report({"WARNING"}, "Closed path kept as edges because a face could not be created")
        else:
            finalized_index = self._finalize_open_surface_path(context, self.path_world_coords)
            if finalized_index is not None:
                end_vertex_index = finalized_index
                path_finalized = True

        if path_finalized:
            self.path_world_coords = [end_snap["world_co"].copy()]

        self.start_snap = self._copy_snap(end_snap)
        self.start_snap["type"] = "VERTEX"
        self.start_snap["label"] = "Vertex"
        self.start_snap["object"] = context.edit_object
        self.start_snap["vertex_index"] = end_vertex_index
        self.start_vertex_index = end_vertex_index
        self.hover_snap = self.start_snap
        self.distance_text = ""
        self.distance_input_valid = True
        self._update_preview(context)
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

    def _effective_end_snap(self, context=None):
        if self.hover_snap is None:
            return None

        snap = self._copy_snap(self.hover_snap)
        if self.start_snap is None:
            return snap

        direction = snap["world_co"] - self.start_snap["world_co"]
        original_direction = direction.copy()
        _surface_bmesh, surface_face, surface_normal = CADDIM_OT_CreateLine._surface_face_for_snap(
            context,
            snap,
        )
        if self.axis in {"X", "Y", "Z"} and surface_normal is not None:
            direction = CADDIM_OT_CreateLine._axis_delta_on_face(
                direction,
                self.axis,
                surface_normal,
            )
            if direction is None:
                return None
        else:
            direction = constrained_delta(direction, self.axis)

        if direction.length < 1e-6:
            return None

        if self.distance_text:
            try:
                direction.normalize()
                direction *= parse_distance_input(context, self.distance_text)
            except (TypeError, ValueError):
                self.distance_input_valid = False
                return None
        self.distance_input_valid = True

        constrained = (direction - original_direction).length >= 1e-6
        if not constrained:
            return snap

        candidate_world = self.start_snap["world_co"] + direction
        remains_on_active_surface = False
        if surface_face is not None and context is not None:
            candidate_local = context.edit_object.matrix_world.inverted_safe() @ candidate_world
            remains_on_active_surface = CADDIM_OT_CreateLine._point_in_face(
                surface_face,
                candidate_local,
            )
            preserves_edge_snap = (
                snap.get("type") == "EDGE"
                and (candidate_world - snap["world_co"]).length <= 1e-5
            )
            preserves_vertex_snap = (
                snap.get("type") == "VERTEX"
                and (candidate_world - snap["world_co"]).length <= 1e-5
            )
            if remains_on_active_surface and not (preserves_edge_snap or preserves_vertex_snap):
                snap["type"] = "FACE"
                snap["label"] = "On Face"
                snap["object"] = context.edit_object
                snap["face_index"] = surface_face.index
                snap["vertex_index"] = -1
                for key in ("edge_index", "edge_vertices", "edge_factor"):
                    snap.pop(key, None)
        if not remains_on_active_surface:
            snap["type"] = "WORLD"
            snap["label"] = "Constrained Point"
            snap["object"] = None
            snap["vertex_index"] = -1
            for key in ("edge_index", "edge_vertices", "edge_factor", "face_index"):
                snap.pop(key, None)
        snap["world_co"] = candidate_world
        return snap

    @staticmethod
    def _surface_face_for_snap(context, snap):
        if (
            context is None
            or context.edit_object is None
            or snap.get("object") != context.edit_object
            or snap.get("type") not in {"FACE", "EDGE", "VERTEX"}
        ):
            return None, None, None
        bm = bmesh.from_edit_mesh(context.edit_object.data)
        bm.faces.ensure_lookup_table()
        bm.faces.index_update()
        face_index = snap.get("face_index", -1)
        if not (0 <= face_index < len(bm.faces)):
            return None, None, None
        face = bm.faces[face_index]
        normal = context.edit_object.matrix_world.to_3x3().inverted_safe().transposed() @ face.normal
        if normal.length < 1e-8:
            return bm, face, None
        return bm, face, normal.normalized()

    @staticmethod
    def _axis_delta_on_face(raw_delta, axis, face_normal):
        axis_vector = CADDIM_OT_CreateLine._axis_vector(axis)
        face_normal = face_normal.normalized()
        tangent = axis_vector - face_normal * axis_vector.dot(face_normal)
        axis_component = tangent.dot(axis_vector)
        if tangent.length < 1e-8 or abs(axis_component) < 1e-8:
            return None
        return tangent * (raw_delta.dot(axis_vector) / axis_component)

    def _update_axis_gesture(self, context, event):
        axis = axis_from_mouse_direction(
            context,
            self.start_snap["world_co"] if self.start_snap is not None else None,
            event.mouse_region_x,
            event.mouse_region_y,
        )
        if axis is not None:
            self.axis = axis

    def _create_edge(self, context, start_snap, end_snap, start_vertex_index=None):
        obj = context.edit_object
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.verts.index_update()
        bm.edges.index_update()
        bm.faces.index_update()

        start_local_co = obj.matrix_world.inverted_safe() @ start_snap["world_co"]
        start_vertex = None
        if start_vertex_index is not None and 0 <= start_vertex_index < len(bm.verts):
            candidate = bm.verts[start_vertex_index]
            if (candidate.co - start_local_co).length <= 1e-5:
                start_vertex = candidate
        if start_vertex is None:
            start_vertex = self._find_bmesh_vertex_at(bm, start_local_co)
        if start_vertex is None:
            start_vertex = self._get_or_create_bmesh_vertex(obj, bm, start_snap)
        end_vertex = self._get_or_create_bmesh_vertex(obj, bm, end_snap)
        end_local_co = end_vertex.co.copy()

        if start_vertex is not end_vertex:
            existing_edge = bm.edges.get((start_vertex, end_vertex))
            if existing_edge is None:
                try:
                    existing_edge = bm.edges.new((start_vertex, end_vertex))
                except ValueError:
                    existing_edge = bm.edges.get((start_vertex, end_vertex))

            if existing_edge is not None:
                existing_edge.select = True

        if not end_vertex.is_valid:
            end_vertex = self._find_bmesh_vertex_at(bm, end_local_co)
        if end_vertex is None:
            return None

        bm.verts.index_update()
        bm.edges.index_update()
        bm.faces.index_update()
        end_vertex_index = end_vertex.index
        bmesh.update_edit_mesh(mesh, loop_triangles=True, destructive=True)
        return end_vertex_index

    @staticmethod
    def _find_bmesh_vertex_at(bm, local_co, tolerance=1e-5):
        best = None
        for vertex in bm.verts:
            distance = (vertex.co - local_co).length
            if best is None or distance < best[0]:
                best = (distance, vertex)

        if best is None or best[0] > tolerance:
            return None
        return best[1]

    @staticmethod
    def _get_or_create_bmesh_vertex(obj, bm, snap):
        if snap.get("type") == "VERTEX" and snap.get("object") == obj:
            vertex_index = snap.get("vertex_index", -1)
            if 0 <= vertex_index < len(bm.verts):
                candidate = bm.verts[vertex_index]
                local_co = obj.matrix_world.inverted_safe() @ snap["world_co"]
                if (candidate.co - local_co).length <= 1e-5:
                    return candidate

            local_co = obj.matrix_world.inverted_safe() @ snap["world_co"]
            existing = CADDIM_OT_CreateLine._find_bmesh_vertex_at(bm, local_co)
            if existing is not None:
                return existing

        local_co = obj.matrix_world.inverted_safe() @ snap["world_co"]
        if snap.get("type") == "EDGE" and snap.get("object") == obj:
            edge, factor = CADDIM_OT_CreateLine._find_bmesh_edge_for_snap(bm, snap, local_co)
            if edge is not None:
                if factor <= 1e-6:
                    return edge.verts[0]
                if factor >= 1.0 - 1e-6:
                    return edge.verts[1]
                _new_edge, vertex = bmesh.utils.edge_split(edge, edge.verts[0], factor)
                vertex.co = local_co
                bm.verts.ensure_lookup_table()
                bm.edges.ensure_lookup_table()
                return vertex

        vertex = bm.verts.new(local_co)
        bm.verts.ensure_lookup_table()
        return vertex

    @staticmethod
    def _find_bmesh_edge_for_snap(bm, snap, local_co):
        edge_index = snap.get("edge_index", -1)
        if 0 <= edge_index < len(bm.edges):
            edge = bm.edges[edge_index]
            distance, factor = CADDIM_OT_CreateLine._point_segment_distance_factor(
                local_co,
                edge.verts[0].co,
                edge.verts[1].co,
            )
            if distance <= 1e-5:
                return edge, factor

        best = None
        for edge in bm.edges:
            distance, factor = CADDIM_OT_CreateLine._point_segment_distance_factor(
                local_co,
                edge.verts[0].co,
                edge.verts[1].co,
            )
            if best is None or distance < best[0]:
                best = (distance, edge, factor)

        if best is None or best[0] > 1e-5:
            return None, 0.0
        return best[1], best[2]

    @staticmethod
    def _find_bmesh_face_for_snap(bm, snap, local_co):
        face_index = snap.get("face_index", -1)
        if 0 <= face_index < len(bm.faces):
            face = bm.faces[face_index]
            if CADDIM_OT_CreateLine._point_in_face(face, local_co):
                return face

        for face in bm.faces:
            if CADDIM_OT_CreateLine._point_in_face(face, local_co):
                return face
        return None

    @staticmethod
    def _point_in_face(face, point, tolerance=1e-5):
        from mathutils.geometry import closest_point_on_tri, intersect_point_tri, tessellate_polygon

        if not face.is_valid or len(face.verts) < 3:
            return False

        coordinates = [vertex.co for vertex in face.verts]
        triangles = tessellate_polygon([coordinates])
        center = face.calc_center_median()
        surface_tolerance = tolerance + 2.0 * max(
            abs((coordinate - center).dot(face.normal))
            for coordinate in coordinates
        )
        for triangle in triangles:
            start = coordinates[triangle[0]]
            middle = coordinates[triangle[1]]
            end = coordinates[triangle[2]]
            if intersect_point_tri(point, start, middle, end) is None:
                continue
            closest = closest_point_on_tri(point, start, middle, end)
            if (point - closest).length <= surface_tolerance:
                return True
        return False

    @staticmethod
    def _point_segment_distance_factor(point, start, end):
        segment = end - start
        if segment.length_squared <= 1e-12:
            return (point - start).length, 0.0

        factor = max(
            0.0,
            min(1.0, (point - start).dot(segment) / segment.length_squared),
        )
        closest = start + segment * factor
        return (point - closest).length, factor

    @staticmethod
    def _finalize_open_surface_path(context, world_points):
        obj = context.edit_object
        if obj is None or len(world_points) < 2:
            return None

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        local_points = [obj.matrix_world.inverted_safe() @ point for point in world_points]
        path_vertices = [
            CADDIM_OT_CreateLine._find_bmesh_vertex_at(bm, point)
            for point in local_points
        ]
        if any(vertex is None for vertex in path_vertices):
            return None

        start_vertex = path_vertices[0]
        end_vertex = path_vertices[-1]
        if start_vertex is end_vertex:
            return None

        common_faces = [
            face
            for face in start_vertex.link_faces
            if face in end_vertex.link_faces
            and all(CADDIM_OT_CreateLine._point_in_face(face, point) for point in local_points)
        ]
        if not common_faces:
            return None

        face = min(common_faces, key=lambda candidate: candidate.calc_area())
        existing_surface_edge = bm.edges.get((start_vertex, end_vertex))
        if len(local_points) == 2 and existing_surface_edge is not None and existing_surface_edge.link_faces:
            # Keep an existing boundary edge in the active path. It may be the
            # reused side of a face the user is about to outline.
            return None

        try:
            new_face, split_loop = bmesh.utils.face_split(
                face,
                start_vertex,
                end_vertex,
                coords=local_points[1:-1],
                use_exist=True,
            )
        except (TypeError, ValueError):
            return None
        if new_face is None or split_loop is None:
            return None

        # Keep the user's loose stroke intact until face_split has succeeded.
        # This makes unsupported or numerically invalid cuts non-destructive.
        CADDIM_OT_CreateLine._remove_loose_path_edges(bm, path_vertices)
        for vertex in path_vertices[1:-1]:
            if vertex.is_valid and not vertex.link_edges and not vertex.link_faces:
                bm.verts.remove(vertex)
        split_loop.edge.select = True
        new_face.select = True
        face.select = True
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.verts.index_update()
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
        end_vertex = CADDIM_OT_CreateLine._find_bmesh_vertex_at(bm, local_points[-1])
        return None if end_vertex is None else end_vertex.index

    @staticmethod
    def _finalize_closed_path(context, world_points):
        obj = context.edit_object
        if obj is None or len(world_points) < 4:
            return None

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        local_points = [obj.matrix_world.inverted_safe() @ point for point in world_points[:-1]]
        loop_vertices = [
            CADDIM_OT_CreateLine._find_bmesh_vertex_at(bm, point)
            for point in local_points
        ]
        if any(vertex is None for vertex in loop_vertices) or len(set(loop_vertices)) < 3:
            return None

        containing_faces = [
            face
            for face in bm.faces
            if all(CADDIM_OT_CreateLine._point_in_face(face, point) for point in local_points)
        ]
        surface_face = min(containing_faces, key=lambda face: face.calc_area()) if containing_faces else None
        shared_boundary_vertices = (
            set(loop_vertices).intersection(surface_face.verts)
            if surface_face is not None
            else set()
        )
        if surface_face is not None and len(shared_boundary_vertices) <= 1:
            created_face = CADDIM_OT_CreateLine._cut_closed_loop_in_face(
                bm,
                surface_face,
                loop_vertices,
            )
        elif surface_face is not None:
            created_face = CADDIM_OT_CreateLine._split_face_with_reused_boundary_path(
                bm,
                surface_face,
                loop_vertices,
            )
        elif surface_face is None:
            created_face = CADDIM_OT_CreateLine._create_isolated_face(bm, loop_vertices)

        if created_face is None:
            return None
        created_face.select = True
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.verts.index_update()
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
        closure_vertex = CADDIM_OT_CreateLine._find_bmesh_vertex_at(bm, local_points[0])
        return None if closure_vertex is None else closure_vertex.index

    @staticmethod
    def _split_face_with_reused_boundary_path(bm, surface_face, loop_vertices):
        """Split a face when a closed stroke reuses one contiguous boundary chain."""
        vertex_count = len(loop_vertices)
        boundary_edges = []
        for index, vertex in enumerate(loop_vertices):
            edge = bm.edges.get((vertex, loop_vertices[(index + 1) % vertex_count]))
            boundary_edges.append(edge is not None and edge in surface_face.edges)

        if not any(boundary_edges) or all(boundary_edges):
            return None

        path_starts = [
            index
            for index, on_boundary in enumerate(boundary_edges)
            if not on_boundary and boundary_edges[index - 1]
        ]
        if len(path_starts) != 1:
            return None

        path_indices = [path_starts[0]]
        edge_index = path_starts[0]
        while not boundary_edges[edge_index]:
            edge_index = (edge_index + 1) % vertex_count
            path_indices.append(edge_index)
            if edge_index == path_starts[0]:
                return None

        path_vertices = [loop_vertices[index] for index in path_indices]
        start_vertex = path_vertices[0]
        end_vertex = path_vertices[-1]
        if (
            start_vertex is end_vertex
            or start_vertex not in surface_face.verts
            or end_vertex not in surface_face.verts
        ):
            return None

        try:
            new_face, split_loop = bmesh.utils.face_split(
                surface_face,
                start_vertex,
                end_vertex,
                coords=[vertex.co.copy() for vertex in path_vertices[1:-1]],
                use_exist=True,
            )
        except (TypeError, ValueError):
            return None
        if new_face is None or split_loop is None:
            return None

        closed_vertices = list(loop_vertices) + [loop_vertices[0]]
        CADDIM_OT_CreateLine._remove_loose_path_edges(bm, closed_vertices)
        for vertex in path_vertices[1:-1]:
            if vertex.is_valid and not vertex.link_edges and not vertex.link_faces:
                bm.verts.remove(vertex)
        split_loop.edge.select = True
        new_face.select = True
        surface_face.select = True
        return new_face

    @staticmethod
    def _cut_closed_loop_in_face(bm, surface_face, loop_vertices):
        from mathutils.geometry import tessellate_polygon

        outer_vertices = list(surface_face.verts)
        inner_vertices = CADDIM_OT_CreateLine._oriented_loop(loop_vertices, surface_face.normal)
        hole_vertices = list(reversed(inner_vertices))
        coordinates = [vertex.co.copy() for vertex in outer_vertices + hole_vertices]
        outer_count = len(outer_vertices)
        triangles = tessellate_polygon(
            [coordinates[:outer_count], coordinates[outer_count:]]
        )
        if not triangles:
            return None

        material_index = surface_face.material_index
        use_smooth = surface_face.smooth
        flat_vertices = outer_vertices + hole_vertices
        original_faces = set(bm.faces)
        original_edges = set(bm.edges)
        ring_faces = []
        inner_face = None
        try:
            for triangle in triangles:
                face = bm.faces.new([flat_vertices[index] for index in triangle])
                face.material_index = material_index
                face.smooth = use_smooth
                ring_faces.append(face)
            inner_face = bm.faces.new(inner_vertices)
            inner_face.material_index = material_index
            inner_face.smooth = use_smooth
        except ValueError:
            for created_face in reversed(ring_faces + ([inner_face] if inner_face is not None else [])):
                if created_face is not None and created_face.is_valid:
                    bm.faces.remove(created_face)
            for edge in list(bm.edges):
                if edge not in original_edges and not edge.link_faces:
                    bm.edges.remove(edge)
            return None

        # Only remove the source face after the complete replacement topology
        # exists. If construction failed above, the original face and stroke
        # remain untouched.
        bm.faces.remove(surface_face)

        protected_edges = set()
        for vertices in (outer_vertices, inner_vertices):
            for index, vertex in enumerate(vertices):
                edge = bm.edges.get((vertex, vertices[(index + 1) % len(vertices)]))
                if edge is not None:
                    protected_edges.add(edge)

        ring_face_set = set(ring_faces)
        internal_edges = [
            edge
            for edge in bm.edges
            if edge not in protected_edges
            and edge.link_faces
            and all(face in ring_face_set for face in edge.link_faces)
        ]
        outer_set = set(outer_vertices)
        inner_set = set(inner_vertices)
        bridge_edges = [
            edge
            for edge in internal_edges
            if (
                (edge.verts[0] in outer_set and edge.verts[1] in inner_set)
                or (edge.verts[1] in outer_set and edge.verts[0] in inner_set)
            )
        ]
        kept_bridges = CADDIM_OT_CreateLine._most_separated_edge_pair(bridge_edges)
        dissolve_edges = [edge for edge in internal_edges if edge not in kept_bridges]
        if dissolve_edges:
            bmesh.ops.dissolve_edges(
                bm,
                edges=dissolve_edges,
                use_verts=False,
                use_face_split=False,
            )
        for face in bm.faces:
            if face not in original_faces:
                face.material_index = material_index
                face.smooth = use_smooth
        return inner_face if inner_face.is_valid else None

    @staticmethod
    def _create_isolated_face(bm, loop_vertices):
        normal = CADDIM_OT_CreateLine._polygon_normal(loop_vertices)
        if normal is None:
            return None
        try:
            return bm.faces.new(loop_vertices)
        except ValueError:
            return next(
                (
                    face
                    for face in loop_vertices[0].link_faces
                    if len(face.verts) == len(loop_vertices)
                    and set(face.verts) == set(loop_vertices)
                ),
                None,
            )

    @staticmethod
    def _remove_loose_path_edges(bm, path_vertices):
        for start, end in zip(path_vertices, path_vertices[1:]):
            edge = bm.edges.get((start, end))
            if edge is not None and not edge.link_faces:
                bm.edges.remove(edge)

    @staticmethod
    def _polygon_normal(vertices):
        if len(vertices) < 3:
            return None
        normal = vertices[0].co.copy()
        normal.zero()
        for index, vertex in enumerate(vertices):
            next_vertex = vertices[(index + 1) % len(vertices)]
            normal.x += (vertex.co.y - next_vertex.co.y) * (vertex.co.z + next_vertex.co.z)
            normal.y += (vertex.co.z - next_vertex.co.z) * (vertex.co.x + next_vertex.co.x)
            normal.z += (vertex.co.x - next_vertex.co.x) * (vertex.co.y + next_vertex.co.y)
        if normal.length <= 1e-8:
            return None
        return normal.normalized()

    @staticmethod
    def _oriented_loop(vertices, target_normal):
        oriented = list(vertices)
        normal = CADDIM_OT_CreateLine._polygon_normal(oriented)
        if normal is not None and normal.dot(target_normal) < 0.0:
            oriented.reverse()
        return oriented

    @staticmethod
    def _most_separated_edge_pair(edges):
        if len(edges) <= 2:
            return set(edges)
        best_pair = None
        best_score = -1.0
        for first_index, first in enumerate(edges[:-1]):
            first_midpoint = (first.verts[0].co + first.verts[1].co) * 0.5
            for second in edges[first_index + 1:]:
                second_midpoint = (second.verts[0].co + second.verts[1].co) * 0.5
                score = (second_midpoint - first_midpoint).length_squared
                if not set(first.verts).isdisjoint(second.verts):
                    score *= 0.25
                if score > best_score:
                    best_score = score
                    best_pair = {first, second}
        return set() if best_pair is None else best_pair

    def _update_preview(self, context=None):
        state = {
            "state": self.state,
            "axis": self.axis,
            "distance_text": self.distance_text,
            "distance_input_valid": self.distance_input_valid,
            "axis_gesture_active": self.axis_gesture_active,
        }
        if self.hover_snap is not None:
            state["hover_screen"] = self.hover_snap["screen_co"]
            state["hover_type"] = self.hover_snap.get("type", "WORLD")
            state["hover_label"] = self.hover_snap.get("label", "Point")
            state["hover_snap"] = self._copy_snap(self.hover_snap)
        if self.start_snap is not None:
            state["start_world"] = self.start_snap["world_co"]
            state["axis_origin_world"] = self.start_snap["world_co"]
            state["locked_snaps"] = [self._copy_snap(self.start_snap)]
            end_snap = self._effective_end_snap(context)
            if end_snap is not None:
                state["end_world"] = end_snap["world_co"]
        set_measure_state(state)

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
        return copy_snap(snap)
