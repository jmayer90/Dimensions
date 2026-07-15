import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import bmesh
import bpy
from mathutils import Matrix, Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import dimensions
from dimensions.collections import (
    create_guide_object,
    create_measurement_object,
    ensure_measurement_snap_proxy,
    get_or_create_dimension_collection,
    get_or_create_guide_collection,
)
from dimensions.anchors import resolve_anchor, set_anchor_from_snap, set_world_anchor
from dimensions.drawing import _snap_highlight_geometry
from dimensions.interaction import (
    axis_from_event,
    constrained_delta,
    is_confirm_event,
    nearest_axis_from_screen_vectors,
    update_distance_text,
)
from dimensions.operators.create_dimension import CADDIM_OT_CreateDimension
from dimensions.operators.create_guide import CADDIM_OT_CreateGuide
from dimensions.operators.create_line import CADDIM_OT_CreateLine
from dimensions.snapping import (
    _best_snap_candidate,
    _edit_mesh_projected_vertex_priority,
    _nearest_projected_edit_mesh_element,
    _nearest_measurement_segment_snap,
    _perspective_correct_segment_factor,
    construction_segment_world,
    guide_is_visible,
    guide_line_world,
    raycast_from_mouse,
)
from dimensions.units import format_volume, parse_distance_input
from dimensions.volume import (
    VOLUME_APPROXIMATE,
    VOLUME_EXACT,
    VOLUME_UNAVAILABLE,
    clear_volume_cache,
    get_mesh_volume,
)
from dimensions.workflow import initialize_scene_mesh_workflow


def _line_operator_adapter():
    return SimpleNamespace(
        _get_or_create_bmesh_vertex=CADDIM_OT_CreateLine._get_or_create_bmesh_vertex,
        _find_bmesh_vertex_at=CADDIM_OT_CreateLine._find_bmesh_vertex_at,
    )


def _world_snap(x, y=0.0, z=0.0):
    return {
        "type": "WORLD",
        "label": "Point",
        "object": None,
        "vertex_index": -1,
        "world_co": Vector((x, y, z)),
        "screen_co": Vector((0.0, 0.0)),
    }


def _edge_snap(obj, x, y, z=0.0):
    snap = _world_snap(x, y, z)
    snap.update(
        {
            "type": "EDGE",
            "label": "Edge",
            "object": obj,
            "edge_index": -1,
        }
    )
    return snap


def _face_snap(obj, x, y, z=0.0):
    snap = _world_snap(x, y, z)
    snap.update(
        {
            "type": "FACE",
            "label": "Face",
            "object": obj,
            "face_index": -1,
        }
    )
    return snap


def _vertex_snap(obj, x, y, z=0.0):
    snap = _world_snap(x, y, z)
    snap.update(
        {
            "type": "VERTEX",
            "label": "Vertex",
            "object": obj,
            "vertex_index": -1,
        }
    )
    return snap


class DimensionsBlenderSmokeTests(unittest.TestCase):
    def test_mesh_workflow_defaults_initialize_once_per_scene(self):
        scene = bpy.data.scenes.new("DimensionsMeshWorkflowDefaultsSmoke")
        self.addCleanup(bpy.data.scenes.remove, scene)
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1.0
        scene.dimensions_settings.mesh_workflow_initialized = False
        scene.tool_settings.use_mesh_automerge = False
        scene.tool_settings.use_mesh_automerge_and_split = False

        self.assertTrue(initialize_scene_mesh_workflow(scene))
        self.assertTrue(scene.tool_settings.use_mesh_automerge)
        self.assertTrue(scene.tool_settings.use_mesh_automerge_and_split)
        self.assertAlmostEqual(scene.tool_settings.double_threshold, 0.0001, places=7)

        scene.tool_settings.use_mesh_automerge = False
        scene.tool_settings.use_mesh_automerge_and_split = False
        scene.tool_settings.double_threshold = 0.01

        self.assertFalse(initialize_scene_mesh_workflow(scene))
        self.assertFalse(scene.tool_settings.use_mesh_automerge)
        self.assertFalse(scene.tool_settings.use_mesh_automerge_and_split)
        self.assertAlmostEqual(scene.tool_settings.double_threshold, 0.01, places=6)

    def _make_edit_object(self, name, vertices, edges=(), faces=()):
        mesh = bpy.data.meshes.new(f"{name}Mesh")
        mesh.from_pydata(vertices, edges, faces)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        return obj, mesh

    def _remove_edit_object(self, obj, mesh):
        if bpy.context.mode == "EDIT_MESH":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)

    def _make_object(self, name, vertices, edges=(), faces=()):
        mesh = bpy.data.meshes.new(f"{name}Mesh")
        mesh.from_pydata(vertices, edges, faces)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        self.addCleanup(bpy.data.meshes.remove, mesh)
        self.addCleanup(bpy.data.objects.remove, obj, do_unlink=True)
        return obj

    def test_closed_mesh_volume_includes_object_scale(self):
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        obj = bpy.context.object
        mesh = obj.data
        self.addCleanup(bpy.data.meshes.remove, mesh)
        self.addCleanup(bpy.data.objects.remove, obj, do_unlink=True)
        obj.scale = (2.0, 3.0, 4.0)
        bpy.context.view_layer.update()

        clear_volume_cache()
        volume, status = get_mesh_volume(obj, bpy.context.evaluated_depsgraph_get())

        self.assertEqual(status, VOLUME_EXACT)
        self.assertAlmostEqual(volume, 192.0, places=5)

    def test_shared_numeric_input_uses_blender_style_confirm_and_axis_rules(self):
        number_event = SimpleNamespace(value="PRESS", type="TWO", ascii="2")
        axis_event = SimpleNamespace(value="PRESS", type="X", ascii="x")
        enter_event = SimpleNamespace(value="PRESS", type="RET", ascii="")

        text, handled = update_distance_text("", number_event)
        self.assertTrue(handled)
        self.assertEqual(text, "2")
        self.assertEqual(axis_from_event(axis_event, text), "X")
        self.assertEqual(axis_from_event(axis_event, ""), "X")
        self.assertTrue(is_confirm_event(enter_event))
        self.assertEqual(constrained_delta(Vector((2.0, 3.0, 4.0)), "Y"), Vector((0.0, 3.0, 0.0)))
        self.assertEqual(
            nearest_axis_from_screen_vectors(
                Vector((8.0, 1.0)),
                {"X": Vector((1.0, 0.0)), "Y": Vector((0.0, 1.0))},
            ),
            "X",
        )

    def test_dimension_and_guide_apply_typed_scene_unit_distances(self):
        unit_settings = bpy.context.scene.unit_settings
        previous_system = unit_settings.system
        previous_scale = unit_settings.scale_length
        try:
            unit_settings.system = "NONE"
            unit_settings.scale_length = 1.0

            dimension = SimpleNamespace(
                start_snap=_world_snap(1.0, 1.0, 1.0),
                hover_snap=_world_snap(1.0, 4.0, 1.0),
                distance_text="2",
                distance_input_valid=True,
                _copy_snap=lambda snap: dict(snap),
            )
            end_snap = CADDIM_OT_CreateDimension._effective_end_snap(dimension, bpy.context)
            self.assertAlmostEqual(
                (end_snap["world_co"] - dimension.start_snap["world_co"]).length,
                2.0,
                places=5,
            )
            self.assertEqual(end_snap["type"], "WORLD")

            guide = SimpleNamespace(
                start_snap=_world_snap(2.0, 2.0, 2.0),
                hover_snap=_world_snap(5.0, 6.0, 2.0),
                axis="X",
                distance_text="2",
                distance_input_valid=True,
                _copy_snap=lambda snap: dict(snap),
            )
            end_snap = CADDIM_OT_CreateGuide._effective_end_snap(guide, bpy.context)
            self.assertEqual(end_snap["world_co"], Vector((4.0, 2.0, 2.0)))
            self.assertEqual(end_snap["type"], "WORLD")
        finally:
            unit_settings.system = previous_system
            unit_settings.scale_length = previous_scale

    def test_mesh_line_axis_constraint_stays_on_a_sloped_face(self):
        obj, mesh = self._make_edit_object(
            "DimensionsSlopedFaceAxisSmoke",
            [(-1.0, -1.0, -1.0), (1.0, -1.0, 1.0), (1.0, 1.0, 1.0), (-1.0, 1.0, -1.0)],
            faces=[(0, 1, 2, 3)],
        )
        try:
            hover = _vertex_snap(obj, 1.0, 1.0, 1.0)
            hover["vertex_index"] = 2
            hover["face_index"] = 0
            operator = SimpleNamespace(
                start_snap=_world_snap(-1.0, 0.0, -1.0),
                hover_snap=hover,
                axis="X",
                distance_text="",
                distance_input_valid=True,
                _copy_snap=lambda snap: dict(snap),
            )
            effective = CADDIM_OT_CreateLine._effective_end_snap(operator, bpy.context)
            self.assertEqual(effective["type"], "FACE")
            self.assertLess((effective["world_co"] - Vector((1.0, 0.0, 1.0))).length, 1e-5)
            bm = bmesh.from_edit_mesh(mesh)
            self.assertTrue(
                CADDIM_OT_CreateLine._point_in_face(
                    bm.faces[0],
                    obj.matrix_world.inverted_safe() @ effective["world_co"],
                )
            )
        finally:
            self._remove_edit_object(obj, mesh)

    def test_snap_highlight_geometry_resolves_vertex_edge_and_face(self):
        obj = self._make_object(
            "DimensionsHighlightSmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            edges=[(0, 1), (1, 2), (2, 0)],
            faces=[(0, 1, 2)],
        )
        context = SimpleNamespace(edit_object=None)
        vertex_snap = _vertex_snap(obj, 0.0, 0.0, 0.0)
        vertex_snap["vertex_index"] = 0
        edge_snap = _edge_snap(obj, 0.5, 0.0, 0.0)
        edge_snap["edge_vertices"] = (0, 1)
        face_snap = _face_snap(obj, 0.25, 0.25, 0.0)
        face_snap["face_index"] = 0

        vertex_geometry = _snap_highlight_geometry(context, vertex_snap)
        self.assertEqual(vertex_geometry["kind"], "VERTEX")
        self.assertEqual(len(vertex_geometry["connected_edges"]), 4)
        self.assertEqual(len(vertex_geometry["object_edges"]), 6)
        self.assertEqual(len(vertex_geometry["object_vertices"]), 3)
        self.assertEqual(len(_snap_highlight_geometry(context, edge_snap)["points"]), 2)
        self.assertEqual(len(_snap_highlight_geometry(context, face_snap)["points"]), 3)

    def test_edge_and_face_anchors_follow_object_transforms(self):
        dimension = create_guide_object(bpy.context, "DimensionsObjectPointAnchorSmoke")
        self.addCleanup(bpy.data.objects.remove, dimension, do_unlink=True)
        target = self._make_object(
            "DimensionsObjectPointTargetSmoke",
            [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 2.0, 0.0)],
            edges=[(0, 1), (1, 2), (2, 0)],
            faces=[(0, 1, 2)],
        )
        snap = _edge_snap(target, 1.0, 0.0, 0.0)
        set_anchor_from_snap(dimension.guide_props.start, snap)
        self.assertEqual(dimension.guide_props.start.anchor_type, "OBJECT_POINT")

        target.location = (3.0, 4.0, 5.0)
        bpy.context.view_layer.update()
        world, status = resolve_anchor(dimension.guide_props.start)
        self.assertEqual(status, "LINKED")
        self.assertEqual(world, Vector((4.0, 4.0, 5.0)))

    def test_open_mesh_volume_is_unavailable(self):
        obj = self._make_object(
            "DimensionsOpenVolumeSmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            faces=[(0, 1, 2)],
        )

        clear_volume_cache()
        volume, status = get_mesh_volume(obj, bpy.context.evaluated_depsgraph_get())

        self.assertIsNone(volume)
        self.assertEqual(status, VOLUME_UNAVAILABLE)

    def test_disconnected_closed_shells_are_approximate(self):
        vertices = [
            (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
        ]
        faces = [
            (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
            (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
        ]
        shifted_vertices = [(x + 4.0, y, z) for x, y, z in vertices]
        shifted_faces = [tuple(index + 8 for index in face) for face in faces]
        obj = self._make_object(
            "DimensionsDisconnectedVolumeSmoke",
            vertices + shifted_vertices,
            faces=faces + shifted_faces,
        )

        clear_volume_cache()
        volume, status = get_mesh_volume(obj, bpy.context.evaluated_depsgraph_get())

        self.assertEqual(status, VOLUME_APPROXIMATE)
        self.assertAlmostEqual(volume, 16.0, places=5)

    def test_evaluated_volume_includes_viewport_modifiers(self):
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        obj = bpy.context.object
        mesh = obj.data
        self.addCleanup(bpy.data.meshes.remove, mesh)
        self.addCleanup(bpy.data.objects.remove, obj, do_unlink=True)
        modifier = obj.modifiers.new("DimensionsArrayVolumeSmoke", "ARRAY")
        modifier.count = 2
        modifier.relative_offset_displace = (2.0, 0.0, 0.0)
        bpy.context.view_layer.update()

        clear_volume_cache()
        volume, status = get_mesh_volume(obj, bpy.context.evaluated_depsgraph_get())

        self.assertEqual(status, VOLUME_APPROXIMATE)
        self.assertAlmostEqual(volume, 16.0, places=5)

    def test_volume_formatting_cubes_scene_unit_scale(self):
        unit_settings = bpy.context.scene.unit_settings
        settings = bpy.context.scene.dimensions_settings
        previous_system = unit_settings.system
        previous_scale = unit_settings.scale_length
        previous_style = settings.metric_unit_style
        try:
            unit_settings.system = "METRIC"
            unit_settings.scale_length = 0.001
            settings.metric_unit_style = "MILLIMETERS"
            self.assertEqual(format_volume(bpy.context, 1.0, 3), "1.000 mm\u00b3")
        finally:
            unit_settings.system = previous_system
            unit_settings.scale_length = previous_scale
            settings.metric_unit_style = previous_style

    def test_annotation_collections_are_isolated_per_scene(self):
        first_scene = bpy.context.scene
        second_scene = bpy.data.scenes.new("DimensionsSmokeOtherScene")
        self.addCleanup(bpy.data.scenes.remove, second_scene)

        first_context = SimpleNamespace(scene=first_scene)
        second_context = SimpleNamespace(scene=second_scene)
        first_dimensions = get_or_create_dimension_collection(first_context)
        second_dimensions = get_or_create_dimension_collection(second_context)
        first_guides = get_or_create_guide_collection(first_context)
        second_guides = get_or_create_guide_collection(second_context)

        self.assertIsNot(first_dimensions, second_dimensions)
        self.assertIsNot(first_guides, second_guides)

    def test_chained_segments_share_the_committed_endpoint(self):
        obj, mesh = self._make_edit_object("DimensionsChainSmoke", [])
        try:
            operator = _line_operator_adapter()
            junction_index = CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _world_snap(0.0),
                _world_snap(1.0),
            )
            CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _world_snap(1.0),
                _world_snap(2.0),
                start_vertex_index=junction_index,
            )

            bm = bmesh.from_edit_mesh(mesh)
            self.assertEqual(len(bm.verts), 3)
            self.assertEqual(len(bm.edges), 2)
            self.assertEqual(sum(1 for vertex in bm.verts if len(vertex.link_edges) == 2), 1)
        finally:
            self._remove_edit_object(obj, mesh)

    def test_edge_to_edge_segment_splits_a_face(self):
        obj, mesh = self._make_edit_object(
            "DimensionsFaceCutSmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        try:
            CADDIM_OT_CreateLine._create_edge(
                _line_operator_adapter(),
                bpy.context,
                _edge_snap(obj, 0.5, 0.0),
                _edge_snap(obj, 0.5, 1.0),
            )
            CADDIM_OT_CreateLine._finalize_open_surface_path(
                bpy.context,
                [Vector((0.5, 0.0, 0.0)), Vector((0.5, 1.0, 0.0))],
            )

            bm = bmesh.from_edit_mesh(mesh)
            self.assertEqual(len(bm.verts), 6)
            self.assertEqual(len(bm.edges), 7)
            self.assertEqual(len(bm.faces), 2)
        finally:
            self._remove_edit_object(obj, mesh)

    def test_face_interior_segment_does_not_create_a_vertex_fan(self):
        obj, mesh = self._make_edit_object(
            "DimensionsInteriorCutSmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        try:
            CADDIM_OT_CreateLine._create_edge(
                _line_operator_adapter(),
                bpy.context,
                _face_snap(obj, 0.25, 0.5),
                _face_snap(obj, 0.75, 0.5),
            )

            bm = bmesh.from_edit_mesh(mesh)
            self.assertEqual(len(bm.faces), 1)
            for coordinate in (Vector((0.25, 0.5, 0.0)), Vector((0.75, 0.5, 0.0))):
                vertex = CADDIM_OT_CreateLine._find_bmesh_vertex_at(bm, coordinate)
                self.assertIsNotNone(vertex)
                self.assertEqual(len(vertex.link_faces), 0)
                self.assertEqual(len(vertex.link_edges), 1)
        finally:
            self._remove_edit_object(obj, mesh)

    def test_face_membership_rejects_a_point_away_from_the_surface(self):
        obj, mesh = self._make_edit_object(
            "DimensionsFaceMembershipSmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        try:
            bm = bmesh.from_edit_mesh(mesh)
            bm.faces.ensure_lookup_table()
            self.assertFalse(
                CADDIM_OT_CreateLine._point_in_face(
                    bm.faces[0],
                    Vector((0.5, 0.5, 1.0)),
                )
            )
        finally:
            self._remove_edit_object(obj, mesh)

    def test_boundary_path_with_interior_point_cuts_without_a_fan(self):
        obj, mesh = self._make_edit_object(
            "DimensionsDeferredKnifeSmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        points = [Vector((0.5, 0.0, 0.0)), Vector((0.5, 0.5, 0.0)), Vector((0.5, 1.0, 0.0))]
        try:
            operator = _line_operator_adapter()
            center_index = CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _edge_snap(obj, *points[0]),
                _face_snap(obj, *points[1]),
            )
            CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _vertex_snap(obj, *points[1]),
                _edge_snap(obj, *points[2]),
                start_vertex_index=center_index,
            )
            CADDIM_OT_CreateLine._finalize_open_surface_path(bpy.context, points)

            bm = bmesh.from_edit_mesh(mesh)
            center = CADDIM_OT_CreateLine._find_bmesh_vertex_at(bm, points[1])
            self.assertEqual(len(bm.faces), 2)
            self.assertIsNotNone(center)
            self.assertEqual(len(center.link_edges), 2)
            self.assertEqual(len(center.link_faces), 2)
        finally:
            self._remove_edit_object(obj, mesh)

    def test_path_returning_to_same_boundary_edge_splits_the_face(self):
        obj, mesh = self._make_edit_object(
            "DimensionsSameBoundaryEdgeSmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        points = [
            Vector((0.2, 0.0, 0.0)),
            Vector((0.3, 0.45, 0.0)),
            Vector((0.7, 0.65, 0.0)),
            Vector((0.8, 0.0, 0.0)),
        ]
        try:
            operator = _line_operator_adapter()
            end_index = None
            for index in range(len(points) - 1):
                start_snap = (
                    _edge_snap(obj, *points[index])
                    if index == 0
                    else _vertex_snap(obj, *points[index])
                )
                end_snap = (
                    _edge_snap(obj, *points[index + 1])
                    if index == len(points) - 2
                    else _face_snap(obj, *points[index + 1])
                )
                end_index = CADDIM_OT_CreateLine._create_edge(
                    operator,
                    bpy.context,
                    start_snap,
                    end_snap,
                    start_vertex_index=end_index,
                )

            CADDIM_OT_CreateLine._finalize_open_surface_path(bpy.context, points)

            bm = bmesh.from_edit_mesh(mesh)
            self.assertEqual(len(bm.faces), 2)
            self.assertTrue(
                any(
                    all(
                        CADDIM_OT_CreateLine._find_bmesh_vertex_at(bm, point) in face.verts
                        for point in points
                    )
                    for face in bm.faces
                )
            )
        finally:
            self._remove_edit_object(obj, mesh)

    def test_path_from_boundary_corner_back_to_its_edge_splits_the_face(self):
        obj, mesh = self._make_edit_object(
            "DimensionsCornerToBoundarySmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        points = [
            Vector((0.0, 0.0, 0.0)),
            Vector((0.35, 0.45, 0.0)),
            Vector((0.7, 0.65, 0.0)),
            Vector((0.8, 0.0, 0.0)),
        ]
        try:
            operator = _line_operator_adapter()
            end_index = None
            for index in range(len(points) - 1):
                start_snap = (
                    _vertex_snap(obj, *points[index])
                    if index == 0
                    else _vertex_snap(obj, *points[index])
                )
                end_snap = (
                    _edge_snap(obj, *points[index + 1])
                    if index == len(points) - 2
                    else _face_snap(obj, *points[index + 1])
                )
                end_index = CADDIM_OT_CreateLine._create_edge(
                    operator,
                    bpy.context,
                    start_snap,
                    end_snap,
                    start_vertex_index=end_index,
                )

            CADDIM_OT_CreateLine._finalize_open_surface_path(bpy.context, points)
            bm = bmesh.from_edit_mesh(mesh)
            self.assertEqual(len(bm.faces), 2)
        finally:
            self._remove_edit_object(obj, mesh)

    def test_path_across_a_nonplanar_visible_face_splits_the_face(self):
        obj, mesh = self._make_edit_object(
            "DimensionsNonplanarFaceSmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.2), (0.0, 1.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        points = [
            Vector((0.2, 0.0, 0.0)),
            Vector((0.5, 0.5, 0.1)),
            Vector((0.8, 1.0, 0.16)),
        ]
        try:
            operator = _line_operator_adapter()
            center_index = CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _edge_snap(obj, *points[0]),
                _face_snap(obj, *points[1]),
            )
            CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _vertex_snap(obj, *points[1]),
                _edge_snap(obj, *points[2]),
                start_vertex_index=center_index,
            )

            CADDIM_OT_CreateLine._finalize_open_surface_path(bpy.context, points)
            bm = bmesh.from_edit_mesh(mesh)
            self.assertEqual(len(bm.faces), 2)
        finally:
            self._remove_edit_object(obj, mesh)

    def test_closed_surface_path_creates_an_extrudable_inner_face(self):
        obj, mesh = self._make_edit_object(
            "DimensionsClosedFaceSmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        points = [
            Vector((0.2, 0.2, 0.0)),
            Vector((0.8, 0.2, 0.0)),
            Vector((0.8, 0.8, 0.0)),
            Vector((0.2, 0.8, 0.0)),
            Vector((0.2, 0.2, 0.0)),
        ]
        try:
            operator = _line_operator_adapter()
            end_index = None
            for index in range(len(points) - 1):
                start_snap = (
                    _face_snap(obj, *points[index])
                    if index == 0
                    else _vertex_snap(obj, *points[index])
                )
                end_snap = (
                    _vertex_snap(obj, *points[index + 1])
                    if index == len(points) - 2
                    else _face_snap(obj, *points[index + 1])
                )
                end_index = CADDIM_OT_CreateLine._create_edge(
                    operator,
                    bpy.context,
                    start_snap,
                    end_snap,
                    start_vertex_index=end_index,
                )

            CADDIM_OT_CreateLine._finalize_closed_path(bpy.context, points)
            bm = bmesh.from_edit_mesh(mesh)
            areas = [face.calc_area() for face in bm.faces]
            self.assertTrue(any(abs(area - 0.36) < 1e-5 for area in areas))
            self.assertTrue(all(area > 1e-8 for area in areas))
            outer_vertices = {
                vertex
                for vertex in bm.verts
                if vertex.co.x in {0.0, 1.0} and vertex.co.y in {0.0, 1.0}
            }
            inner_vertices = {
                vertex
                for vertex in bm.verts
                if 0.19 < vertex.co.x < 0.81 and 0.19 < vertex.co.y < 0.81
            }
            bridges = [
                edge
                for edge in bm.edges
                if any(vertex in outer_vertices for vertex in edge.verts)
                and any(vertex in inner_vertices for vertex in edge.verts)
            ]
            self.assertEqual(len(bridges), 2)
        finally:
            self._remove_edit_object(obj, mesh)

    def test_closed_surface_path_can_share_a_vertex_with_an_existing_cut(self):
        obj, mesh = self._make_edit_object(
            "DimensionsTouchingClosedFaceSmoke",
            [(-2.0, -2.0, 0.0), (2.0, -2.0, 0.0), (2.0, 2.0, 0.0), (-2.0, 2.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        first_cut = [
            Vector((-1.0, 2.0, 0.0)),
            Vector((0.0, 0.0, 0.0)),
            Vector((1.0, 2.0, 0.0)),
        ]
        closed_points = [
            Vector((0.0, 0.0, 0.0)),
            Vector((1.5, -0.2, 0.0)),
            Vector((1.0, -1.5, 0.0)),
            Vector((-1.0, -1.5, 0.0)),
            Vector((-1.5, -0.2, 0.0)),
            Vector((0.0, 0.0, 0.0)),
        ]
        try:
            operator = _line_operator_adapter()
            start_index = CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _edge_snap(obj, *first_cut[0]),
                _face_snap(obj, *first_cut[1]),
            )
            CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _vertex_snap(obj, *first_cut[1]),
                _edge_snap(obj, *first_cut[2]),
                start_vertex_index=start_index,
            )
            self.assertIsNotNone(
                CADDIM_OT_CreateLine._finalize_open_surface_path(bpy.context, first_cut)
            )

            end_index = None
            for index in range(len(closed_points) - 1):
                start_snap = _vertex_snap(obj, *closed_points[index])
                end_snap = (
                    _vertex_snap(obj, *closed_points[index + 1])
                    if index == len(closed_points) - 2
                    else _face_snap(obj, *closed_points[index + 1])
                )
                end_index = CADDIM_OT_CreateLine._create_edge(
                    operator,
                    bpy.context,
                    start_snap,
                    end_snap,
                    start_vertex_index=end_index,
                )

            self.assertIsNotNone(
                CADDIM_OT_CreateLine._finalize_closed_path(bpy.context, closed_points)
            )
            bm = bmesh.from_edit_mesh(mesh)
            expected = {tuple(point) for point in closed_points[:-1]}
            created = [
                face
                for face in bm.faces
                if {tuple(vertex.co) for vertex in face.verts} == expected
            ]
            self.assertEqual(len(created), 1)
            self.assertAlmostEqual(created[0].calc_area(), 3.55, places=5)
        finally:
            self._remove_edit_object(obj, mesh)

    def test_closed_surface_path_can_reuse_an_existing_cut_edge(self):
        obj, mesh = self._make_edit_object(
            "DimensionsReusedCutEdgeSmoke",
            [(-2.0, -2.0, 0.0), (2.0, -2.0, 0.0), (2.0, 2.0, 0.0), (-2.0, 2.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        first_cut = [
            Vector((-1.0, 2.0, 0.0)),
            Vector((0.0, 0.0, 0.0)),
            Vector((1.0, 2.0, 0.0)),
        ]
        reused_edge_loop = [
            Vector((-1.0, 2.0, 0.0)),
            Vector((0.0, 0.0, 0.0)),
            Vector((-0.7, -1.2, 0.0)),
            Vector((-1.6, 0.0, 0.0)),
            Vector((-1.0, 2.0, 0.0)),
        ]
        try:
            operator = _line_operator_adapter()
            start_index = CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _edge_snap(obj, *first_cut[0]),
                _face_snap(obj, *first_cut[1]),
            )
            CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _vertex_snap(obj, *first_cut[1]),
                _edge_snap(obj, *first_cut[2]),
                start_vertex_index=start_index,
            )
            self.assertIsNotNone(
                CADDIM_OT_CreateLine._finalize_open_surface_path(bpy.context, first_cut)
            )

            end_index = None
            for index in range(len(reused_edge_loop) - 1):
                end_index = CADDIM_OT_CreateLine._create_edge(
                    operator,
                    bpy.context,
                    _vertex_snap(obj, *reused_edge_loop[index]),
                    _vertex_snap(obj, *reused_edge_loop[index + 1]),
                    start_vertex_index=end_index,
                )
                if index < len(reused_edge_loop) - 2:
                    self.assertIsNone(
                        CADDIM_OT_CreateLine._finalize_open_surface_path(
                            bpy.context,
                            reused_edge_loop[: index + 2],
                        )
                    )

            self.assertIsNotNone(
                CADDIM_OT_CreateLine._finalize_closed_path(bpy.context, reused_edge_loop)
            )
            bm = bmesh.from_edit_mesh(mesh)
            expected = {tuple(point) for point in reused_edge_loop[:-1]}
            created = [
                face
                for face in bm.faces
                if {tuple(vertex.co) for vertex in face.verts} == expected
            ]
            self.assertEqual(len(created), 1)
            for start, end in zip(reused_edge_loop, reused_edge_loop[1:]):
                start_vertex = CADDIM_OT_CreateLine._find_bmesh_vertex_at(bm, start)
                end_vertex = CADDIM_OT_CreateLine._find_bmesh_vertex_at(bm, end)
                edge = bm.edges.get((start_vertex, end_vertex))
                self.assertIsNotNone(edge)
                self.assertTrue(edge.link_faces)
        finally:
            self._remove_edit_object(obj, mesh)

    def test_path_cuts_the_cap_of_a_face_created_by_extrusion(self):
        obj, mesh = self._make_edit_object(
            "DimensionsExtrudedCapCutSmoke",
            [(-2.0, -2.0, 0.0), (2.0, -2.0, 0.0), (2.0, 2.0, 0.0), (-2.0, 2.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        inset_loop = [
            Vector((-1.0, -1.0, 0.0)),
            Vector((1.0, -1.0, 0.0)),
            Vector((1.0, 1.0, 0.0)),
            Vector((-1.0, 1.0, 0.0)),
            Vector((-1.0, -1.0, 0.0)),
        ]
        cap_cut = [
            Vector((-1.0, 0.0, 1.0)),
            Vector((0.0, 0.35, 1.0)),
            Vector((1.0, 0.0, 1.0)),
        ]
        try:
            operator = _line_operator_adapter()
            end_index = None
            for index in range(len(inset_loop) - 1):
                end_index = CADDIM_OT_CreateLine._create_edge(
                    operator,
                    bpy.context,
                    _face_snap(obj, *inset_loop[index]),
                    _face_snap(obj, *inset_loop[index + 1]),
                    start_vertex_index=end_index,
                )
            self.assertIsNotNone(
                CADDIM_OT_CreateLine._finalize_closed_path(bpy.context, inset_loop)
            )

            bm = bmesh.from_edit_mesh(mesh)
            inner_coordinates = {tuple(point) for point in inset_loop[:-1]}
            inner_face = next(
                face
                for face in bm.faces
                if {tuple(vertex.co) for vertex in face.verts} == inner_coordinates
            )
            extruded = bmesh.ops.extrude_discrete_faces(bm, faces=[inner_face])
            cap_face = extruded["faces"][0]
            bmesh.ops.translate(
                bm,
                verts=list(cap_face.verts),
                vec=Vector((0.0, 0.0, 1.0)),
            )
            bmesh.update_edit_mesh(mesh, loop_triangles=True, destructive=True)

            middle_index = CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _edge_snap(obj, *cap_cut[0]),
                _face_snap(obj, *cap_cut[1]),
            )
            CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _vertex_snap(obj, *cap_cut[1]),
                _edge_snap(obj, *cap_cut[2]),
                start_vertex_index=middle_index,
            )
            face_count_before = len(bmesh.from_edit_mesh(mesh).faces)
            self.assertIsNotNone(
                CADDIM_OT_CreateLine._finalize_open_surface_path(bpy.context, cap_cut)
            )
            bm = bmesh.from_edit_mesh(mesh)
            self.assertEqual(len(bm.faces), face_count_before + 1)
            middle = CADDIM_OT_CreateLine._find_bmesh_vertex_at(bm, cap_cut[1])
            self.assertIsNotNone(middle)
            self.assertEqual(len(middle.link_faces), 2)
        finally:
            self._remove_edit_object(obj, mesh)

    def test_failed_open_surface_finalization_preserves_the_loose_path(self):
        from unittest.mock import patch

        obj, mesh = self._make_edit_object(
            "DimensionsFailedSurfaceCutSmoke",
            [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 2.0, 0.0), (0.0, 2.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        points = [
            Vector((0.0, 1.0, 0.0)),
            Vector((1.0, 1.0, 0.0)),
            Vector((2.0, 1.0, 0.0)),
        ]
        try:
            operator = _line_operator_adapter()
            end_index = CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _edge_snap(obj, *points[0]),
                _face_snap(obj, *points[1]),
            )
            CADDIM_OT_CreateLine._create_edge(
                operator,
                bpy.context,
                _vertex_snap(obj, *points[1]),
                _edge_snap(obj, *points[2]),
                start_vertex_index=end_index,
            )
            bm = bmesh.from_edit_mesh(mesh)
            before = (len(bm.verts), len(bm.edges), len(bm.faces))

            with patch.object(bmesh.utils, "face_split", side_effect=ValueError("forced failure")):
                result = CADDIM_OT_CreateLine._finalize_open_surface_path(bpy.context, points)

            self.assertIsNone(result)
            bm = bmesh.from_edit_mesh(mesh)
            self.assertEqual((len(bm.verts), len(bm.edges), len(bm.faces)), before)
            path_vertices = [
                CADDIM_OT_CreateLine._find_bmesh_vertex_at(bm, point)
                for point in points
            ]
            self.assertTrue(all(vertex is not None for vertex in path_vertices))
            self.assertTrue(
                all(bm.edges.get(pair) is not None for pair in zip(path_vertices, path_vertices[1:]))
            )
        finally:
            self._remove_edit_object(obj, mesh)

    def test_closed_free_space_path_creates_a_face(self):
        obj, mesh = self._make_edit_object("DimensionsFreeFaceSmoke", [])
        points = [
            Vector((0.0, 0.0, 0.0)),
            Vector((1.0, 0.0, 0.0)),
            Vector((1.0, 1.0, 0.0)),
            Vector((0.0, 1.0, 0.0)),
            Vector((0.0, 0.0, 0.0)),
        ]
        try:
            operator = _line_operator_adapter()
            end_index = None
            for index in range(len(points) - 1):
                end_index = CADDIM_OT_CreateLine._create_edge(
                    operator,
                    bpy.context,
                    _world_snap(*points[index]),
                    _vertex_snap(obj, *points[index + 1]) if index == 3 else _world_snap(*points[index + 1]),
                    start_vertex_index=end_index,
                )
            CADDIM_OT_CreateLine._finalize_closed_path(bpy.context, points)

            bm = bmesh.from_edit_mesh(mesh)
            self.assertEqual(len(bm.faces), 1)
            self.assertAlmostEqual(bm.faces[0].calc_area(), 1.0)
        finally:
            self._remove_edit_object(obj, mesh)

    def test_unmodified_vertex_snap_stays_bound(self):
        start = _world_snap(0.0)
        end = _world_snap(1.0)
        end.update({"type": "VERTEX", "label": "Vertex", "vertex_index": 7})
        operator = SimpleNamespace(
            start_snap=start,
            hover_snap=end,
            axis="ALIGNED",
            distance_text="",
            _copy_snap=CADDIM_OT_CreateLine._copy_snap,
            _axis_vector=CADDIM_OT_CreateLine._axis_vector,
        )

        effective = CADDIM_OT_CreateLine._effective_end_snap(operator)
        self.assertEqual(effective["type"], "VERTEX")
        self.assertEqual(effective["vertex_index"], 7)

    def test_zero_axis_projection_is_not_accepted_unconstrained(self):
        operator = SimpleNamespace(
            start_snap=_world_snap(0.0),
            hover_snap=_world_snap(0.0, 1.0),
            axis="X",
            distance_text="",
            _copy_snap=CADDIM_OT_CreateLine._copy_snap,
            _axis_vector=CADDIM_OT_CreateLine._axis_vector,
        )

        self.assertIsNone(CADDIM_OT_CreateLine._effective_end_snap(operator))

    def test_hidden_guides_are_not_snap_targets(self):
        guide = create_guide_object(bpy.context, "DimensionsHiddenGuideSmoke")
        self.addCleanup(bpy.data.objects.remove, guide, do_unlink=True)
        settings = bpy.context.scene.dimensions_settings

        settings.show_construction_guides = False
        self.assertFalse(guide_is_visible(bpy.context, guide))
        settings.show_construction_guides = True
        guide.guide_props.visible = False
        self.assertFalse(guide_is_visible(bpy.context, guide))

    def test_axis_guide_does_not_depend_on_its_unused_end_anchor(self):
        guide = create_guide_object(bpy.context, "DimensionsAxisGuideSmoke")
        self.addCleanup(bpy.data.objects.remove, guide, do_unlink=True)
        set_world_anchor(guide.guide_props.start, Vector((1.0, 2.0, 3.0)))
        guide.guide_props.end.anchor_type = "VERTEX"
        guide.guide_props.end.target_object = None
        guide.guide_props.axis = "X"

        origin, direction = guide_line_world(guide)
        self.assertEqual(origin, Vector((1.0, 2.0, 3.0)))
        self.assertEqual(direction, Vector((1.0, 0.0, 0.0)))

    def test_measurements_are_fixed_finite_construction_segments(self):
        measurement = create_measurement_object(bpy.context, "DimensionsMeasurementSmoke")
        self.addCleanup(bpy.data.objects.remove, measurement, do_unlink=True)
        set_world_anchor(measurement.guide_props.start, Vector((1.0, 2.0, 3.0)))
        set_world_anchor(measurement.guide_props.end, Vector((4.0, 6.0, 3.0)))

        segment = construction_segment_world(measurement)
        self.assertEqual(measurement.guide_props.kind, "MEASUREMENT")
        self.assertEqual(segment[0], Vector((1.0, 2.0, 3.0)))
        self.assertEqual(segment[1], Vector((4.0, 6.0, 3.0)))

    def test_measurement_endpoints_have_native_vertex_snap_geometry(self):
        measurement = create_measurement_object(bpy.context, "DimensionsMeasurementNativeSnapSmoke")
        self.addCleanup(bpy.data.objects.remove, measurement, do_unlink=True)
        start = Vector((1.0, 2.0, 3.0))
        end = Vector((4.0, 6.0, 3.0))
        set_world_anchor(measurement.guide_props.start, start)
        set_world_anchor(measurement.guide_props.end, end)
        measurement.location = (start + end) * 0.5

        proxy = ensure_measurement_snap_proxy(measurement, bpy.context.scene)
        proxy_mesh = proxy.data
        self.addCleanup(bpy.data.meshes.remove, proxy_mesh)
        self.addCleanup(bpy.data.objects.remove, proxy, do_unlink=True)

        self.assertEqual(proxy.type, "MESH")
        self.assertTrue(proxy.hide_select)
        self.assertIs(proxy.parent, measurement)
        self.assertEqual(len(proxy.data.vertices), 2)
        world_vertices = [proxy.matrix_world @ vertex.co for vertex in proxy.data.vertices]
        self.assertEqual(world_vertices, [start, end])

    def test_measurement_midpoint_is_an_explicit_snap_target(self):
        from unittest.mock import patch

        measurement = create_measurement_object(bpy.context, "DimensionsMeasurementSnapSmoke")
        self.addCleanup(bpy.data.objects.remove, measurement, do_unlink=True)
        set_world_anchor(measurement.guide_props.start, Vector((10.0, 10.0, 0.0)))
        set_world_anchor(measurement.guide_props.end, Vector((100.0, 10.0, 0.0)))
        context = SimpleNamespace(region=object(), region_data=object())
        with patch(
            "dimensions.snapping.view3d_utils.location_3d_to_region_2d",
            side_effect=lambda _region, _region_data, world: Vector((world.x, world.y)),
        ):
            snap = _nearest_measurement_segment_snap(
                context,
                measurement,
                Vector((58.0, 10.0)),
                pixel_threshold=28.0,
            )
        self.assertEqual(snap["label"], "Measurement Midpoint")
        self.assertEqual(snap["world_co"], Vector((55.0, 10.0, 0.0)))

    def test_logical_vertex_owns_the_full_snap_radius(self):
        mouse = Vector((0.0, 0.0))
        face = {"priority": 10, "screen_co": mouse.copy()}
        vertex = {"priority": 0, "screen_co": Vector((27.0, 0.0))}
        self.assertIs(_best_snap_candidate([face, vertex], mouse, 28.0), vertex)

    def test_off_face_projected_vertex_does_not_steal_an_edit_mesh_edge(self):
        obj, mesh = self._make_edit_object(
            "DimensionsOffFaceVertexPrioritySmoke",
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.5, 0.5, 1.0),
            ],
            faces=[(0, 1, 2, 3)],
        )
        try:
            candidate = {"object": obj, "vertex_index": 4}
            priority = _edit_mesh_projected_vertex_priority(obj, 0, candidate)
            edge = {"priority": 2, "screen_co": Vector((0.0, 0.0))}
            candidate.update({"priority": priority, "screen_co": Vector((1.0, 0.0))})

            self.assertEqual(priority, 4)
            self.assertIs(
                _best_snap_candidate([candidate, edge], Vector((0.0, 0.0)), 28.0),
                edge,
            )
        finally:
            self._remove_edit_object(obj, mesh)

    def test_typed_distances_accept_explicit_scene_units(self):
        unit_settings = bpy.context.scene.unit_settings
        previous_system = unit_settings.system
        previous_scale = unit_settings.scale_length
        try:
            unit_settings.system = "NONE"
            unit_settings.scale_length = 1.0
            self.assertAlmostEqual(parse_distance_input(bpy.context, '5"'), 0.127)
            self.assertAlmostEqual(parse_distance_input(bpy.context, "25mm"), 0.025)
        finally:
            unit_settings.system = previous_system
            unit_settings.scale_length = previous_scale

    def test_perspective_edge_factor_reprojects_to_the_marker(self):
        perspective = Matrix(
            (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
            )
        )
        context = SimpleNamespace(
            region_data=SimpleNamespace(perspective_matrix=perspective)
        )
        start = Vector((0.0, 0.0, 1.0))
        end = Vector((2.0, 0.0, 2.0))
        factor = _perspective_correct_segment_factor(context, start, end, 0.5)
        point = start + (end - start) * factor
        clip = perspective @ point.to_4d()

        self.assertAlmostEqual(clip.x / clip.w, 0.5)

    def test_edit_mode_raycast_does_not_fall_through_to_another_object(self):
        from unittest.mock import Mock, patch

        scene = SimpleNamespace(ray_cast=Mock())
        context = SimpleNamespace(
            mode="EDIT_MESH",
            edit_object=object(),
            scene=scene,
        )
        with (
            patch("dimensions.snapping.has_view3d_window_region", return_value=True),
            patch(
                "dimensions.snapping.get_mouse_ray",
                return_value=(Vector((0.0, 0.0, 1.0)), Vector((0.0, 0.0, -1.0))),
            ),
            patch("dimensions.snapping._raycast_edit_mesh", return_value=None),
        ):
            self.assertIsNone(raycast_from_mouse(context, 10.0, 10.0))
        scene.ray_cast.assert_not_called()

    def test_edit_mode_boundary_edge_is_available_when_face_raycast_misses(self):
        from unittest.mock import patch

        obj, mesh = self._make_edit_object(
            "DimensionsProjectedBoundarySmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
            edges=[(0, 1)],
        )
        context = SimpleNamespace(
            edit_object=obj,
            region=object(),
            region_data=SimpleNamespace(perspective_matrix=Matrix.Identity(4)),
        )
        try:
            with patch(
                "dimensions.snapping.view3d_utils.location_3d_to_region_2d",
                side_effect=lambda _region, _region_data, world: Vector((world.x, world.y)),
            ):
                snap = _nearest_projected_edit_mesh_element(
                    context,
                    0.5,
                    0.0,
                    pixel_threshold=0.25,
                )
            self.assertEqual(snap["type"], "EDGE")
            self.assertEqual(snap["object"], obj)
            self.assertEqual(snap["world_co"], Vector((0.5, 0.0, 0.0)))
        finally:
            self._remove_edit_object(obj, mesh)


def main():
    dimensions.register()
    try:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(DimensionsBlenderSmokeTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        dimensions.unregister()

    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
