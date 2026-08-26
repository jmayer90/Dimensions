import sys
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bmesh
import bpy
from mathutils import Matrix, Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import dimensions
from dimensions import drawing, keymaps
from dimensions.collections import (
    create_dimension_object,
    create_guide_object,
    create_measurement_object,
    ensure_measurement_snap_proxy,
    get_or_create_dimension_collection,
    get_or_create_guide_collection,
)
from dimensions.anchors import resolve_anchor, set_anchor, set_anchor_from_snap, set_world_anchor
from dimensions.constants import CURRENT_SCHEMA_VERSION
from dimensions.area_binding import bind_area_face_indices, evaluate_area_binding
from dimensions.angle_binding import derive_angle_from_world_edges, resolve_angle_source
from dimensions.dimension_geometry import get_angle_world_geometry
from dimensions.collections import get_scene_collection
from dimensions.drawing import _snap_highlight_geometry
from dimensions.properties import is_dimension_object
from support import make_context
from dimensions.interaction import (
    axis_from_event,
    constrained_delta,
    is_confirm_event,
    nearest_axis_from_screen_vectors,
    update_distance_text,
)
from dimensions.migrations import migrate_scene
from dimensions.modal_state import PointPlacementState
from dimensions.operators.create_dimension import CADDIM_OT_CreateDimension
from dimensions.operators.create_area import _constrained_label_world
from dimensions.operators.create_guide import CADDIM_OT_CreateGuide
from dimensions.projected_snap import _is_visible
from dimensions.scene_sync import sync_scene_objects
from dimensions.snapping import (
    _best_snap_candidate,
    _edit_mesh_projected_vertex_priority,
    _nearest_projected_edit_mesh_element,
    _nearest_projected_vertex,
    _nearest_measurement_segment_snap,
    _perspective_correct_segment_factor,
    _raycast_edit_mesh,
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
from dimensions.viewport_state import clear_all_states, get_state, set_state


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
    def test_operator_reports_use_the_shared_message_catalog(self):
        for source_path in (REPOSITORY_ROOT / "dimensions" / "operators").glob("*.py"):
            source = source_path.read_text(encoding="utf-8")
            for line in source.splitlines():
                if "self.report(" in line:
                    self.assertIn("messages.", line, f"{source_path.name}: {line.strip()}")

    def test_point_placement_state_machine_covers_shared_escape_and_step_back_contract(self):
        state = PointPlacementState()
        self.assertEqual(state.accept_point(), "PICK_START_ACCEPTED")
        self.assertEqual(state.stage, PointPlacementState.PICK_END)
        state.set_numeric_text("25mm")
        self.assertEqual(state.escape(), "NUMERIC_CLEARED")
        self.assertEqual(state.stage, PointPlacementState.PICK_END)
        self.assertEqual(state.step_back(), "STEPPED_BACK")
        self.assertEqual(state.stage, PointPlacementState.PICK_START)
        self.assertEqual(state.step_back(), "CANCELLED")
    def test_schema_migration_stamps_legacy_dimension_data_once(self):
        mesh_object = self._make_object(
            "Schema Migration Source",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
            [(0, 1)],
        )
        dimension = bpy.data.objects.new("Schema Migration Dimension", None)
        bpy.context.scene.collection.objects.link(dimension)
        self.addCleanup(bpy.data.objects.remove, dimension, do_unlink=True)
        dimension.dimension_props.enabled = True
        set_anchor(dimension.dimension_props.start, mesh_object, 0)
        dimension.dimension_props.start.vertex_id = 0
        settings = bpy.context.scene.dimensions_settings
        original_version = settings.schema_version
        settings.schema_version = 0

        self.assertTrue(migrate_scene(bpy.context.scene))
        self.assertEqual(settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertGreater(dimension.dimension_props.start.vertex_id, 0)
        self.assertFalse(migrate_scene(bpy.context.scene))

        settings.schema_version = original_version

    def test_newer_schema_is_not_modified(self):
        dimension = bpy.data.objects.new("Future Schema Dimension", None)
        bpy.context.scene.collection.objects.link(dimension)
        self.addCleanup(bpy.data.objects.remove, dimension, do_unlink=True)
        dimension.dimension_props.enabled = True
        settings = bpy.context.scene.dimensions_settings
        original_version = settings.schema_version
        settings.schema_version = CURRENT_SCHEMA_VERSION + 1

        self.assertFalse(migrate_scene(bpy.context.scene))
        self.assertEqual(settings.schema_version, CURRENT_SCHEMA_VERSION + 1)

        settings.schema_version = original_version

    def test_manifest_compatibility_includes_running_blender(self):
        manifest_path = REPOSITORY_ROOT / "dimensions" / "blender_manifest.toml"
        with manifest_path.open("rb") as manifest_file:
            manifest = tomllib.load(manifest_file)

        running_version = bpy.app.version[:3]
        minimum_version = tuple(
            int(component) for component in manifest["blender_version_min"].split(".")
        )
        self.assertGreaterEqual(running_version, minimum_version)

        maximum = manifest.get("blender_version_max")
        if maximum is not None:
            maximum_version = tuple(int(component) for component in maximum.split("."))
            self.assertLess(running_version, maximum_version)

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
        self.assertEqual(axis_from_event(axis_event), "X")
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
        world = resolve_anchor(dimension.guide_props.start)
        self.assertEqual(world, Vector((4.0, 4.0, 5.0)))

    def test_vertex_anchor_uses_persistent_id_after_reindexing(self):
        guide = create_guide_object(bpy.context, "DimensionsPersistentAnchorSmoke")
        self.addCleanup(bpy.data.objects.remove, guide, do_unlink=True)
        target = self._make_object(
            "DimensionsPersistentAnchorTargetSmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)],
        )
        anchor = guide.guide_props.start
        set_anchor(anchor, target, 1)
        persistent_id = anchor.vertex_id
        attribute = target.data.attributes["dimensions_anchor_id"]
        attribute.data[1].value = 0
        attribute.data[2].value = persistent_id

        world = resolve_anchor(anchor)

        self.assertEqual(world, Vector((2.0, 0.0, 0.0)))

        attribute.data[1].value = persistent_id
        world = resolve_anchor(anchor)
        self.assertEqual(world, Vector((1.0, 0.0, 0.0)))

    def test_transient_state_is_isolated_per_viewport(self):
        from unittest.mock import patch

        class Pointer:
            def __init__(self, value):
                self.value = value

            def as_pointer(self):
                return self.value

        first = SimpleNamespace(window=Pointer(1), area=Pointer(2), region=Pointer(3))
        second = SimpleNamespace(window=Pointer(1), area=Pointer(4), region=Pointer(5))
        with patch("dimensions.viewport_state.tag_redraw_all_view3d"):
            clear_all_states()
            set_state("MEASURE", {"value": "first"}, first)
            set_state("MEASURE", {"value": "second"}, second)
            self.assertEqual(get_state("MEASURE", first)["value"], "first")
            self.assertEqual(get_state("MEASURE", second)["value"], "second")
            clear_all_states()

    def test_projected_vertex_depth_check_rejects_occlusion(self):
        from unittest.mock import patch

        candidate = {
            "screen_co": Vector((10.0, 20.0)),
            "world_co": Vector((0.0, 0.0, 10.0)),
        }
        scene = SimpleNamespace(
            ray_cast=lambda *_args, **_kwargs: (
                True,
                Vector((0.0, 0.0, 5.0)),
                Vector((0.0, 0.0, 1.0)),
                0,
                None,
                Matrix.Identity(4),
            )
        )
        context = SimpleNamespace(
            region=object(),
            region_data=object(),
            scene=scene,
            evaluated_depsgraph_get=lambda: object(),
        )
        with (
            patch("dimensions.projected_snap.view3d_utils.region_2d_to_origin_3d", return_value=Vector((0, 0, 0))),
            patch("dimensions.projected_snap.view3d_utils.region_2d_to_vector_3d", return_value=Vector((0, 0, 1))),
        ):
            self.assertFalse(_is_visible(context, candidate))

    def test_registration_failure_rolls_back_cleanly(self):
        original_components = dimensions._COMPONENTS

        def fail_registration():
            raise RuntimeError("intentional registration failure")

        dimensions.unregister()
        try:
            dimensions._COMPONENTS = (
                original_components[0],
                (fail_registration, lambda: None),
                *original_components[1:],
            )
            with self.assertRaises(RuntimeError):
                dimensions.register()
            self.assertFalse(dimensions._registered_classes)
            self.assertFalse(dimensions._registered_components)
            self.assertFalse(hasattr(bpy.types.Object, "dimension_props"))
        finally:
            dimensions._COMPONENTS = original_components
            dimensions.register()

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


    def test_edit_selection_creates_length_area_and_angle_annotations(self):
        obj, mesh = self._make_edit_object(
            "DimensionsSelectionAnnotationsSmoke",
            [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            faces=[(0, 1, 2, 3)],
        )
        created = []
        try:
            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            for element in (*bm.verts, *bm.edges, *bm.faces):
                element.select = False
            bm.edges[0].select = True
            invoke_context = SimpleNamespace(
                area=SimpleNamespace(type="VIEW_3D"),
                mode="EDIT_MESH",
                edit_object=obj,
                scene=bpy.context.scene,
                region_data=None,
            )
            operator = SimpleNamespace(report=lambda *_args: None)
            with patch(
                "dimensions.operators.create_dimension.continuous_placement_enabled",
                return_value=False,
            ):
                self.assertEqual(
                    CADDIM_OT_CreateDimension.invoke(operator, invoke_context, None),
                    {"FINISHED"},
                )
            created.append(next(obj for obj in bpy.data.objects if obj.name.startswith("DIM Selected Edge")))
            self.assertEqual(created[-1].dimension_props.annotation_kind, "LINEAR")

            bm.edges.ensure_lookup_table()
            for edge in bm.edges:
                edge.select = False
            bm.edges[0].select = True
            connected = next(edge for edge in bm.edges if edge != bm.edges[0] and set(edge.verts) & set(bm.edges[0].verts))
            connected.select = True
            self.assertEqual(bpy.ops.dimensions.angle_selected_edges(), {"FINISHED"})
            created.append(next(obj for obj in bpy.data.objects if obj.name.startswith("ANGLE Selected Edges")))
            self.assertEqual(created[-1].dimension_props.annotation_kind, "ANGLE")
            self.assertEqual(created[-1].dimension_props.measurement_state, "LIVE")
            self.assertEqual(created[-1].dimension_props.angle_source_mode, "EDGES")
            self.assertGreater(created[-1].dimension_props.angle_radius, 0.0)

            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            for edge in bm.edges:
                edge.select = False
            bm.faces[0].select = True
            self.assertEqual(bpy.ops.dimensions.area_selected_faces(), {"FINISHED"})
            created.append(next(obj for obj in bpy.data.objects if obj.name.startswith("AREA Selected Faces")))
            self.assertEqual(created[-1].dimension_props.annotation_kind, "AREA")
            self.assertAlmostEqual(created[-1].dimension_props.area_value, 2.0)
            self.assertEqual(created[-1].dimension_props.measurement_state, "LIVE")
            self.assertEqual(created[-1].dimension_props.area_face_count, 1)
            self.assertEqual(len(created[-1].dimension_props.area_faces), 1)

            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.verts[2].co.y = 2.0
            bm.verts[3].co.y = 2.0
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
            result = evaluate_area_binding(created[-1].dimension_props)
            self.assertIsNotNone(result)
            self.assertAlmostEqual(result["area"], 4.0)
            sync_scene_objects(bpy.context.scene)
            self.assertAlmostEqual(created[-1].dimension_props.area_value, 4.0)

            bm = bmesh.from_edit_mesh(mesh)
            bm.faces.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.faces[0]], context="FACES")
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=True)
            sync_scene_objects(bpy.context.scene)
            self.assertEqual(created[-1].dimension_props.measurement_state, "NEEDS_REPAIR")
        finally:
            for annotation in created:
                bpy.data.objects.remove(annotation, do_unlink=True)
            self._remove_edit_object(obj, mesh)

    def test_angle_geometry_is_world_space_and_supports_reflex_values(self):
        start = Vector((2.0, 0.0, 0.0))
        center = Vector((0.0, 0.0, 0.0))
        end = Vector((0.0, 3.0, 0.0))
        minor = get_angle_world_geometry(start, center, end, 0.75, "MINOR")
        reflex = get_angle_world_geometry(start, center, end, 0.75, "REFLEX")

        self.assertIsNotNone(minor)
        self.assertAlmostEqual(minor["value"], 0.5 * 3.141592653589793)
        self.assertAlmostEqual(reflex["value"], 1.5 * 3.141592653589793)
        for point in (*minor["arc_points_world"], *reflex["arc_points_world"]):
            self.assertAlmostEqual(point.z, 0.0)
            self.assertAlmostEqual((point - center).length, 0.75, places=6)
        self.assertLess((minor["arc_points_world"][-1] - end.normalized() * 0.75).length, 1e-6)
        self.assertLess((reflex["arc_points_world"][-1] - end.normalized() * 0.75).length, 1e-6)

    def test_two_edge_angles_support_disconnected_skew_and_supplement_solutions(self):
        connected = derive_angle_from_world_edges(
            Vector((0.0, 0.0, 0.0)), Vector((2.0, 0.0, 0.0)),
            Vector((0.0, 0.0, 0.0)), Vector((0.0, 3.0, 0.0)),
        )
        disconnected = derive_angle_from_world_edges(
            Vector((-2.0, 0.0, 0.0)), Vector((2.0, 0.0, 0.0)),
            Vector((0.0, -2.0, 0.0)), Vector((0.0, 2.0, 0.0)),
        )
        skew = derive_angle_from_world_edges(
            Vector((-2.0, 0.0, 0.0)), Vector((2.0, 0.0, 0.0)),
            Vector((0.0, -2.0, 1.0)), Vector((0.0, 2.0, 1.0)),
        )
        supplement = derive_angle_from_world_edges(
            Vector((0.0, 0.0, 0.0)), Vector((2.0, 0.0, 0.0)),
            Vector((0.0, 0.0, 0.0)), Vector((1.0, 1.0, 0.0)),
            "SUPPLEMENT",
        )
        self.assertTrue(connected["connected"])
        self.assertFalse(disconnected["connected"])
        self.assertFalse(skew["connected"])
        self.assertEqual(disconnected["center"], Vector((0.0, 0.0, 0.0)))
        self.assertAlmostEqual(skew["center"].z, 0.5)
        self.assertAlmostEqual(supplement["value"], 3.0 * 3.141592653589793 / 4.0)

    def test_disconnected_selected_edges_create_a_live_angle(self):
        obj, mesh = self._make_edit_object(
            "DimensionsDisconnectedAngleSmoke",
            [(-2.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, -2.0, 0.0), (0.0, 2.0, 0.0)],
            edges=[(0, 1), (2, 3)],
        )
        annotation = None
        try:
            bm = bmesh.from_edit_mesh(mesh)
            for edge in bm.edges:
                edge.select = True
            self.assertEqual(bpy.ops.dimensions.angle_selected_edges(), {"FINISHED"})
            annotation = next(obj for obj in bpy.data.objects if obj.name.startswith("ANGLE Selected Edges"))
            source = resolve_angle_source(annotation.dimension_props)
            self.assertIsNotNone(source)
            self.assertFalse(source["connected"])
            self.assertAlmostEqual(source["value"], 0.5 * 3.141592653589793)

            bm.verts.ensure_lookup_table()
            bm.verts[3].co.x = 2.0
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
            source = resolve_angle_source(annotation.dimension_props)
            self.assertIsNotNone(source)
            self.assertNotAlmostEqual(source["value"], 0.5 * 3.141592653589793)
        finally:
            if annotation is not None:
                bpy.data.objects.remove(annotation, do_unlink=True)
            self._remove_edit_object(obj, mesh)

    def test_area_axis_distance_constraint_matches_linear_style_input(self):
        center = Vector((1.0, 2.0, 3.0))
        normal = Vector((0.0, 0.0, 1.0))
        self.assertEqual(
            _constrained_label_world(center, normal, Vector((-5.0, 8.0, 9.0)), "X", 2.5),
            Vector((-1.5, 2.0, 3.0)),
        )
        aligned = _constrained_label_world(center, normal, center + Vector((3.0, 4.0, 0.0)), "ALIGNED", 10.0)
        self.assertEqual(aligned, center + Vector((6.0, 8.0, 0.0)))

    def test_annotation_transform_offset_survives_source_changes(self):
        from dimensions.dimension_geometry import get_dimension_world_geometry

        annotation = create_dimension_object(bpy.context, "DIM Transform Offset Smoke")
        try:
            props = annotation.dimension_props
            props.annotation_kind = "LINEAR"
            set_world_anchor(props.start, Vector((0.0, 0.0, 0.0)))
            set_world_anchor(props.end, Vector((2.0, 0.0, 0.0)))
            props.offset_plane_normal = (0.0, 0.0, 1.0)
            props.offset_distance = 0.25
            base = get_dimension_world_geometry("ALIGNED", Vector((0.0, 0.0, 0.0)), Vector((2.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0)), 0.25)
            annotation.location = base["line_mid_world"]
            sync_scene_objects(bpy.context.scene)

            user_offset = Vector((0.0, 1.5, 0.75))
            annotation.location += user_offset
            sync_scene_objects(bpy.context.scene)
            self.assertLess((Vector(props.presentation_offset) - user_offset).length, 1e-6)

            set_world_anchor(props.end, Vector((4.0, 0.0, 0.0)))
            moved = get_dimension_world_geometry("ALIGNED", Vector((0.0, 0.0, 0.0)), Vector((4.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0)), 0.25)
            sync_scene_objects(bpy.context.scene)
            self.assertLess((annotation.location - (moved["line_mid_world"] + user_offset)).length, 1e-6)
        finally:
            bpy.data.objects.remove(annotation, do_unlink=True)

    def test_object_mode_area_binding_updates_after_geometry_changes(self):
        mesh = bpy.data.meshes.new("DimensionsObjectAreaBindingMesh")
        mesh.from_pydata(
            [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            [],
            [(0, 1, 2, 3)],
        )
        obj = bpy.data.objects.new("DimensionsObjectAreaBinding", mesh)
        bpy.context.scene.collection.objects.link(obj)
        annotation = create_dimension_object(bpy.context, "AREA Object Binding Smoke")
        try:
            props = annotation.dimension_props
            props.annotation_kind = "AREA"
            result = bind_area_face_indices(props, obj, [0])
            self.assertIsNotNone(result)
            self.assertAlmostEqual(result["area"], 2.0)
            self.assertEqual(props.measurement_state, "LIVE")

            mesh.vertices[2].co.y = 2.0
            mesh.vertices[3].co.y = 2.0
            mesh.update()
            result = evaluate_area_binding(props)
            self.assertIsNotNone(result)
            self.assertAlmostEqual(result["area"], 4.0)
        finally:
            bpy.data.objects.remove(annotation, do_unlink=True)
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(mesh)

    def test_linear_dimensions_support_axis_projected_values(self):
        from dimensions.dimension_geometry import get_dimension_world_geometry

        start = Vector((1.0, 2.0, 3.0))
        end = Vector((5.0, 8.0, 15.0))
        geometry = get_dimension_world_geometry(
            "ALIGNED",
            start,
            end,
            Vector((0.0, 0.0, 1.0)),
            0.25,
            measurement_mode="DELTA_Y",
        )
        self.assertIsNotNone(geometry)
        self.assertAlmostEqual(geometry["value"], 6.0)
        self.assertEqual(geometry["measure_start_world"], start)
        self.assertEqual(geometry["measure_end_world"], Vector((1.0, 8.0, 3.0)))

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

    def test_native_measurement_proxy_is_not_an_addon_mesh_snap_target(self):
        from unittest.mock import patch

        measurement = create_measurement_object(bpy.context, "DimensionsProxyIsolationSmoke")
        self.addCleanup(bpy.data.objects.remove, measurement, do_unlink=True)
        set_world_anchor(measurement.guide_props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(measurement.guide_props.end, Vector((2.0, 0.0, 0.0)))
        proxy = ensure_measurement_snap_proxy(measurement, bpy.context.scene)
        self.addCleanup(bpy.data.meshes.remove, proxy.data)
        self.addCleanup(bpy.data.objects.remove, proxy, do_unlink=True)
        context = SimpleNamespace(
            mode="OBJECT",
            edit_object=None,
            visible_objects=[proxy],
            region=object(),
            region_data=object(),
        )
        with patch("dimensions.snapping.has_view3d_window_region", return_value=True):
            snap = _nearest_projected_vertex(context, 0.0, 0.0, 28.0)
        self.assertIsNone(snap)

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

    def test_edit_mode_raycast_ignores_hidden_faces(self):
        obj, mesh = self._make_edit_object(
            "DimensionsHiddenFaceRaycastSmoke",
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
                (1.0, 0.0, 1.0),
                (1.0, 1.0, 1.0),
                (0.0, 1.0, 1.0),
            ],
            faces=[(0, 1, 2, 3), (4, 5, 6, 7)],
        )
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()
        bm.faces[1].hide_set(True)
        context = SimpleNamespace(edit_object=obj)
        try:
            hit = _raycast_edit_mesh(
                context,
                Vector((0.5, 0.5, 2.0)),
                Vector((0.0, 0.0, -1.0)),
            )
            self.assertIsNotNone(hit)
            self.assertEqual(hit["face_index"], 0)
            self.assertAlmostEqual(hit["location"].z, 0.0)
        finally:
            self._remove_edit_object(obj, mesh)

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

    def test_hidden_edit_vertex_is_not_a_projected_snap_target(self):
        from unittest.mock import patch

        obj, mesh = self._make_edit_object(
            "DimensionsHiddenProjectedVertexSmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
        )
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.verts[0].hide_set(True)
        context = SimpleNamespace(
            mode="EDIT_MESH",
            edit_object=obj,
            region=object(),
            region_data=object(),
        )
        try:
            with (
                patch("dimensions.snapping.has_view3d_window_region", return_value=True),
                patch(
                    "dimensions.snapping.view3d_utils.location_3d_to_region_2d",
                    side_effect=lambda _region, _region_data, world: Vector((world.x, world.y)),
                ),
            ):
                snap = _nearest_projected_vertex(context, 0.0, 0.0, 2.0)
            self.assertEqual(snap["vertex_index"], 1)
        finally:
            self._remove_edit_object(obj, mesh)


class DimensionsDrawCacheTests(unittest.TestCase):
    """FND-03: draw cost must scale with annotations, not with scene size."""

    def setUp(self):
        self.context = make_context(scene=bpy.context.scene)
        self.context.view_layer = bpy.context.view_layer
        self.created = []
        drawing.invalidate_dimension_geometry_cache()

    def tearDown(self):
        for obj in self.created:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        drawing.invalidate_dimension_geometry_cache()

    def _make_dimension(self, start=(0.0, 0.0, 0.0), end=(1.0, 0.0, 0.0)):
        obj = create_dimension_object(self.context, "DIM Cache Test")
        set_world_anchor(obj.dimension_props.start, Vector(start))
        set_world_anchor(obj.dimension_props.end, Vector(end))
        self.created.append(obj)
        return obj

    def test_geometry_is_not_rebuilt_when_neither_sources_nor_view_changed(self):
        dimension = self._make_dimension()
        drawing.get_cached_dimension_geometry(self.context, dimension)
        after_first = drawing.geometry_build_count()

        for _repeat in range(5):
            drawing.get_cached_dimension_geometry(self.context, dimension)
        self.assertEqual(drawing.geometry_build_count(), after_first)

    def test_a_view_change_rebuilds_geometry_for_that_viewport_only(self):
        dimension = self._make_dimension()
        drawing.get_cached_dimension_geometry(self.context, dimension)
        before = drawing.geometry_build_count()

        self.context.region_data.perspective_matrix = Matrix.Translation(Vector((0.0, 0.0, 5.0)))
        drawing.get_cached_dimension_geometry(self.context, dimension)
        self.assertEqual(drawing.geometry_build_count(), before + 1)

    def test_the_cache_stays_bounded_across_repeated_view_changes(self):
        dimension = self._make_dimension()
        for step in range(25):
            self.context.region_data.perspective_matrix = Matrix.Translation(
                Vector((0.0, 0.0, float(step)))
            )
            drawing.get_cached_dimension_geometry(self.context, dimension)
        # One viewport means one cache entry, however far the view was orbited.
        self.assertEqual(len(drawing._dimension_geometry_cache), 1)

    def test_depsgraph_invalidation_forces_a_rebuild(self):
        dimension = self._make_dimension()
        drawing.get_cached_dimension_geometry(self.context, dimension)
        before = drawing.geometry_build_count()

        drawing.invalidate_dimension_geometry_cache()
        drawing.get_cached_dimension_geometry(self.context, dimension)
        self.assertEqual(drawing.geometry_build_count(), before + 1)

    def test_two_viewports_do_not_share_cached_geometry(self):
        dimension = self._make_dimension()
        other = make_context(scene=bpy.context.scene)
        drawing.get_cached_dimension_geometry(self.context, dimension)
        before = drawing.geometry_build_count()

        drawing.get_cached_dimension_geometry(other, dimension)
        self.assertEqual(drawing.geometry_build_count(), before + 1)
        self.assertEqual(len(drawing._dimension_geometry_cache), 2)

    def test_annotations_sharing_a_color_collapse_into_one_batch(self):
        batcher = drawing.SegmentBatcher(shader=None)
        selected = (1.0, 0.6, 0.0, 1.0)
        unselected = (0.1, 0.7, 1.0, 1.0)
        for index in range(50):
            color = selected if index % 2 else unselected
            batcher.add_segments(
                [Vector((0.0, float(index))), Vector((10.0, float(index)))],
                color,
                2.0,
            )
        self.assertEqual(batcher.batch_count, 2)

    def test_differing_line_widths_stay_in_separate_batches(self):
        batcher = drawing.SegmentBatcher(shader=None)
        color = (1.0, 1.0, 1.0, 1.0)
        batcher.add_segments([Vector((0.0, 0.0)), Vector((1.0, 0.0))], color, 1.0)
        batcher.add_segments([Vector((0.0, 1.0)), Vector((1.0, 1.0))], color, 3.0)
        self.assertEqual(batcher.batch_count, 2)

    def test_text_metrics_are_measured_once_per_font_size(self):
        drawing._text_metrics_cache.clear()
        first = drawing._text_dimensions("1.000 m", 14)
        self.assertEqual(len(drawing._text_metrics_cache), 1)
        for _repeat in range(10):
            drawing._text_dimensions("1.000 m", 14)
        self.assertEqual(len(drawing._text_metrics_cache), 1)
        self.assertEqual(drawing._text_dimensions("1.000 m", 14), first)

    def test_viewport_presentation_sizes_ignore_view_and_source_transforms(self):
        """UX-08: world projection changes positions, never configured pixel sizes."""
        source = bpy.data.meshes.new("DimensionsStableSizingSourceMesh")
        source.from_pydata(
            [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0)],
            [(0, 1)],
            [],
        )
        source_object = bpy.data.objects.new("DimensionsStableSizingSource", source)
        bpy.context.scene.collection.objects.link(source_object)
        self.addCleanup(bpy.data.meshes.remove, source)
        parent = bpy.data.objects.new("DimensionsStableSizingParent", None)
        bpy.context.scene.collection.objects.link(parent)
        self.addCleanup(bpy.data.objects.remove, parent, do_unlink=True)
        self.addCleanup(bpy.data.objects.remove, source_object, do_unlink=True)

        dimension = create_dimension_object(self.context, "DIM Stable Sizing")
        self.created.append(dimension)
        props = dimension.dimension_props
        set_anchor(props.start, source_object, 0)
        set_anchor(props.end, source_object, 1)
        props.text_size = 21
        props.arrow_size = 13.0

        def projected_with_zoom(zoom):
            def project(_context, world):
                # Include depth so this exercises a perspective-like projection,
                # while keeping the test independent of a foreground window.
                depth = max(0.25, 1.0 + (0.15 * world.z))
                return Vector((zoom * world.x / depth, zoom * world.y / depth))

            with patch("dimensions.drawing._project_world_to_screen", side_effect=project):
                geometry = drawing.build_dimension_geometry_for_object(self.context, dimension)
            label = "12.345 m"
            layout = drawing._build_text_layout(
                label,
                geometry,
                "INLINE",
                text_size=props.text_size,
                arrow_size=props.arrow_size,
            )
            arrow_segments = drawing._build_arrow_segments(
                geometry["line_start_screen"],
                geometry["line_direction_screen"],
                props.arrow_size,
            )
            arrow_extent = max(
                (arrow_segments[index + 1] - arrow_segments[index]).length
                for index in (0, 2)
            )
            text_extent = drawing._text_dimensions(label, props.text_size)
            return geometry, layout, arrow_extent, text_extent

        identity_geometry, identity_layout, identity_arrow, identity_text = projected_with_zoom(1.0)

        # A source transform changes anchor positions and the annotation Empty's
        # transform is deliberately unrelated to presentation sizing.
        source_object.location = (4.0, -3.0, 2.0)
        source_object.rotation_euler[2] = 0.65
        source_object.scale = (3.0, 1.5, 2.0)
        parent.location = (-2.0, 5.0, 1.0)
        parent.rotation_euler[2] = -0.3
        parent.scale = (0.75, 2.0, 1.25)
        source_object.parent = parent
        dimension.location = (8.0, 9.0, 10.0)
        dimension.rotation_euler[2] = -0.4
        dimension.scale = (4.0, 0.5, 2.0)
        bpy.context.view_layer.update()
        transformed_geometry, transformed_layout, transformed_arrow, transformed_text = projected_with_zoom(0.35)

        self.assertGreater(
            (transformed_geometry["line_start_screen"] - identity_geometry["line_start_screen"]).length,
            0.1,
        )
        self.assertNotEqual(
            identity_layout["text_position"],
            transformed_layout["text_position"],
        )
        self.assertAlmostEqual(identity_arrow, props.arrow_size * (1.0 + 0.45**2) ** 0.5, places=5)
        self.assertAlmostEqual(transformed_arrow, identity_arrow, places=5)
        self.assertEqual(transformed_text, identity_text)

        # Selection only changes color; both draw collection paths retain the
        # same configured screen-space text size and arrowhead geometry.
        for color in ((0.2, 0.7, 1.0, 1.0), (1.0, 0.72, 0.25, 1.0)):
            batcher = drawing.SegmentBatcher(shader=None)
            drawing._collect_dimension_geometry(
                self.context,
                batcher,
                transformed_geometry,
                color,
                3,
            )
            self.assertEqual(batcher._text_items[0][3], props.text_size)
            line_segments = next(iter(batcher._segments.values()))
            self.assertAlmostEqual(
                (line_segments[-7] - line_segments[-8]).length,
                transformed_arrow,
                places=5,
            )

    def test_viewport_size_property_descriptions_state_pixel_contract(self):
        dimension = self._make_dimension()
        properties = dimension.dimension_props.bl_rna.properties
        self.assertIn("pixel", properties["text_size"].description.lower())
        self.assertIn("pixel", properties["arrow_size"].description.lower())
        scene_properties = bpy.context.scene.dimensions_settings.bl_rna.properties
        self.assertIn("pixel", scene_properties["dimension_text_size"].description.lower())
        self.assertIn("pixel", scene_properties["dimension_arrow_size"].description.lower())

    def test_the_draw_loop_reads_only_the_dimensions_collection(self):
        collection = get_or_create_dimension_collection(self.context)
        self.assertIsNotNone(get_scene_collection(bpy.context.scene, "DIMENSIONS"))
        bystanders = []
        try:
            for index in range(20):
                mesh = bpy.data.meshes.new(f"Bystander {index}")
                obj = bpy.data.objects.new(f"Bystander {index}", mesh)
                bpy.context.scene.collection.objects.link(obj)
                bystanders.append(obj)
            drawn = [obj for obj in collection.all_objects if is_dimension_object(obj)]
            self.assertTrue(all(obj not in drawn for obj in bystanders))
        finally:
            for obj in bystanders:
                mesh = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.meshes.remove(mesh)


class DimensionsKeymapTests(unittest.TestCase):
    """FND-05: registered keymaps that leak nothing and collide with nothing."""

    def test_registered_items_cover_every_documented_modal_key(self):
        bound = {
            item.properties.action
            for _keymap, item in keymaps._modal_keymap_items
        }
        self.assertEqual(
            bound,
            {
                "CONSTRAIN_ALIGNED",
                "CONSTRAIN_X",
                "CONSTRAIN_Y",
                "CONSTRAIN_Z",
                "CONFIRM",
                "STEP_BACK",
                "CANCEL",
                "CANCEL_IMMEDIATE",
            },
        )

    def test_no_default_binding_can_collide_with_blender(self):
        """The collision check the ticket asks to be documented, run as a test.

        Nothing this add-on registers can shadow a Blender preset binding: the
        invocation entries ship unbound and inactive, and the modal actions live in a
        private map Blender never dispatches from.
        """
        for _keymap, item in keymaps._keymap_items:
            self.assertEqual(item.type, "NONE")
            self.assertFalse(item.active)
        for keymap, item in keymaps._modal_keymap_items:
            self.assertEqual(keymap.name, keymaps.MODAL_KEYMAP_NAME)
            self.assertEqual(item.idname, "dimensions.modal_action")

    def test_repeated_enable_and_disable_cycles_leak_no_items(self):
        keymaps.unregister_keymaps()
        self.assertEqual(len(keymaps.registered_keymap_items()), 0)
        for _cycle in range(3):
            keymaps.register_keymaps()
            first = len(keymaps.registered_keymap_items())
            keymaps.unregister_keymaps()
            self.assertEqual(len(keymaps.registered_keymap_items()), 0)
        keymaps.register_keymaps()
        self.assertEqual(len(keymaps.registered_keymap_items()), first)

    def test_disabling_removes_the_private_action_map_container(self):
        keymaps.unregister_keymaps()
        keyconfig = bpy.context.window_manager.keyconfigs.addon
        self.assertIsNone(keyconfig.keymaps.get(keymaps.MODAL_KEYMAP_NAME))
        keymaps.register_keymaps()
        self.assertIsNotNone(keyconfig.keymaps.get(keymaps.MODAL_KEYMAP_NAME))

    def test_modal_actions_resolve_through_the_keymap_not_hard_coded_types(self):
        for _keymap, item in keymaps._modal_keymap_items:
            event = SimpleNamespace(type=item.type, value=item.value)
            self.assertEqual(
                keymaps.modal_action_from_event(event),
                item.properties.action,
            )


class DimensionsPackagingTests(unittest.TestCase):
    """Guard the differences between running from the repository and from an install.

    The suite imports the add-on as a top-level ``dimensions`` package, while Blender
    installs it as ``bl_ext.<repository>.dimensions`` and registers it under a
    restricted ``bpy.data``. Both differences have hidden real registration failures.
    """

    def test_addon_id_is_the_full_package_name(self):
        from dimensions import preferences

        self.assertEqual(preferences.ADDON_ID, preferences.__package__)

    def test_preferences_bl_idname_matches_the_addon_id(self):
        from dimensions import preferences

        self.assertEqual(
            preferences.DIMENSIONS_AddonPreferences.bl_idname,
            preferences.ADDON_ID,
        )

    def test_get_preferences_never_raises_without_a_registered_addon(self):
        from dimensions.preferences import DEFAULT_PREFERENCES, get_preferences

        self.assertIs(get_preferences(SimpleNamespace()), DEFAULT_PREFERENCES)
        self.assertIsNotNone(get_preferences(None))

    def test_registering_migrations_survives_restricted_blend_data(self):
        from dimensions import migrations

        class _RestrictedData:
            @property
            def scenes(self):
                raise AttributeError("'_RestrictData' object has no attribute 'scenes'")

        registered = []
        fake_bpy = SimpleNamespace(
            data=_RestrictedData(),
            app=SimpleNamespace(
                handlers=SimpleNamespace(load_post=[]),
                timers=SimpleNamespace(
                    register=lambda function, first_interval=0.0: registered.append(function),
                    is_registered=lambda _function: False,
                ),
            ),
        )
        with patch.object(migrations, "bpy", fake_bpy):
            migrations.register_migrations()
        self.assertEqual(registered, [migrations._run_deferred_migration])


def main():
    dimensions.register()
    try:
        loader = unittest.defaultTestLoader
        suite = unittest.TestSuite(
            loader.loadTestsFromTestCase(case)
            for case in (
                DimensionsBlenderSmokeTests,
                DimensionsDrawCacheTests,
                DimensionsKeymapTests,
                DimensionsPackagingTests,
            )
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        dimensions.unregister()

    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
