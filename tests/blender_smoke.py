import sys
import time
import tomllib
import unittest
from math import floor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bmesh
import bpy
import numpy as np
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import dimensions
from dimensions import drawing, keymaps
from dimensions import inference
from dimensions import area_binding as area_binding_module
from dimensions.measurement_query import format_measurement_query, measurement_components
from dimensions.collections import (
    create_dimension_object,
    create_guide_object,
    create_guide_point_object,
    create_guide_plane_object,
    create_measurement_object,
    ensure_guide_point_snap_proxy,
    ensure_measurement_snap_proxy,
    get_or_create_dimension_collection,
    get_or_create_guide_collection,
    remove_guide_point_snap_proxies,
)
from dimensions.anchors import anchor_resolution, resolve_anchor, set_anchor, set_anchor_from_snap, set_world_anchor
from dimensions.constants import CURRENT_SCHEMA_VERSION
from dimensions.area_binding import bind_area_face_indices, evaluate_area_binding
from dimensions.annotation_manager import (
    annotation_references_object,
    filtered_manager_objects,
    registry_rebuild_count,
    sync_annotation_manager,
)
from dimensions.angle_binding import derive_angle_from_world_edges, resolve_angle_source
from dimensions.dimension_geometry import get_angle_world_geometry
from dimensions.output_geometry import WorldSizingPolicy, area_dimension_output_spec
from dimensions.coordinate_dimensions import (
    coordinate_label,
    coordinate_values,
    datum_dependents,
    elevation_value,
    signed_number,
)
from dimensions.transform_policy import annotation_world_location, enforce_annotation_transform_policy, has_ignored_rotation_or_scale
from dimensions.snapping import _guide_line_snap_candidate
from dimensions.derived_guides import (
    bind_edge_source,
    bind_face_source,
    bind_guide_source,
    centerline_preview,
    detach_derived_guide,
    resolve_derived_guide,
    would_create_cycle,
    angular_preview_line,
    spacing_definition,
    spaced_guide_lines,
)
from dimensions.units import parse_angle_input
from dimensions.guide_planes import (
    active_plane_frame,
    constrain_point_to_plane,
    plane_frame,
    plane_space_delta,
    point_within_plane_extent,
    resolve_guide_plane,
    would_create_plane_cycle,
)
from dimensions.collections import get_scene_collection
from dimensions.drawing import (
    _annotation_handle_segments,
    _build_arrow_segments,
    _build_text_layout,
    _extension_line_segment,
    _snap_highlight_geometry,
    find_annotation_handle_hit,
    selected_annotation_handles,
    guide_point_marker_segments,
)
from dimensions.properties import (
    apply_dimension_style_to_scene,
    apply_scene_style_to_dimension,
    clear_dimension_style_overrides,
    configured_scene_unit_style,
    is_dimension_object,
    resolve_dimension_style,
)
from support import make_context, make_event, make_operator_harness
from dimensions.interaction import (
    axis_from_event,
    constrained_delta,
    is_confirm_event,
    nearest_axis_from_screen_vectors,
    update_distance_text,
)
from dimensions.migrations import migrate_scene
from dimensions.modal_state import HandleManipulationState, PointPlacementState
from dimensions.operators.create_dimension import CADDIM_OT_CreateDimension
from dimensions.operators.create_area import _constrained_label_world
from dimensions.operators.selection_annotations import DIMENSIONS_OT_CaptureArea
from dimensions.operators.create_guide import CADDIM_OT_CreateGuide
from dimensions.operators.create_guide_point import DIMENSIONS_OT_CreateGuidePoint, selection_centroid
from dimensions.operators.offset_guide import DIMENSIONS_OT_CreateDerivedGuide
from dimensions.operators.annotation_manager import isolate_annotations, restore_annotation_visibility
from dimensions.projected_snap import (
    _build_sources,
    _cell_source_indices,
    _is_visible,
    _materialize_candidate,
    _full_spatial_grid,
    _project_sources,
)
from dimensions.scene_sync import sync_scene_objects
from dimensions.repair import apply_suggested_repairs, repair_issues
from dimensions.manipulation import angle_radius_from_world, linear_offset_from_world
from dimensions.snapping import (
    _add_edge_snap_candidates,
    _best_snap_candidate,
    _best_acquisition_candidate,
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
    find_nearest_snap_point,
    find_nearest_guide_point,
    find_nearest_mesh_snap_point,
)
from dimensions.snap_targets import TARGET_IDS, enabled_snap_targets
from dimensions.units import format_dual_length, format_volume, parse_distance_input
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

    def test_output_settings_migrate_additively_from_schema_v1(self):
        mesh_object = self._make_object(
            "Output Schema Migration Source",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
            [(0, 1)],
        )
        dimension = bpy.data.objects.new("Output Schema Migration Dimension", None)
        bpy.context.scene.collection.objects.link(dimension)
        self.addCleanup(bpy.data.objects.remove, dimension, do_unlink=True)
        dimension.dimension_props.enabled = True
        set_anchor(dimension.dimension_props.start, mesh_object, 0)
        set_anchor(dimension.dimension_props.end, mesh_object, 1)
        settings = bpy.context.scene.dimensions_settings
        original_version = settings.schema_version
        original_values = (
            settings.output_sizing_mode,
            settings.output_line_width,
            settings.output_scope,
        )
        settings.schema_version = 1
        settings.output_sizing_mode = "WORLD"
        settings.output_line_width = 3.5
        settings.output_scope = "SELECTED"
        preserved_binding = settings.output_source_bindings.add()
        preserved_binding.source = dimension
        preserved_binding.key = "preserved-output-key"
        incomplete_binding = settings.output_source_bindings.add()
        incomplete_binding.source = dimension

        self.assertTrue(migrate_scene(bpy.context.scene))
        self.assertEqual(settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(settings.output_sizing_mode, "WORLD")
        self.assertAlmostEqual(settings.output_line_width, 3.5)
        self.assertEqual(settings.output_scope, "SELECTED")
        self.assertEqual(len(settings.output_source_bindings), 1)
        self.assertEqual(settings.output_source_bindings[0].key, "preserved-output-key")
        self.assertFalse(migrate_scene(bpy.context.scene))

        settings.schema_version = original_version
        settings.output_sizing_mode, settings.output_line_width, settings.output_scope = original_values
        settings.output_source_bindings.clear()

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

    def test_vector_export_settings_migrate_from_schema_v5_without_rewriting_v5_data(self):
        dimension = bpy.data.objects.new("Vector Schema Migration Dimension", None)
        bpy.context.scene.collection.objects.link(dimension)
        self.addCleanup(bpy.data.objects.remove, dimension, do_unlink=True)
        dimension.dimension_props.enabled = True
        set_world_anchor(dimension.dimension_props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(dimension.dimension_props.end, Vector((0.1, 0.0, 0.0)))
        dimension.dimension_props.start.resolution_status = "BY_FALLBACK"
        dimension.dimension_props.start.source_object_name = "Preserved v5 Source"
        settings = bpy.context.scene.dimensions_settings
        original = (
            settings.schema_version,
            settings.vector_paper_size,
            settings.vector_orientation,
            settings.vector_scale_denominator,
            settings.vector_line_width_mm,
            settings.vector_text_height_mm,
            settings.vector_arrow_size_mm,
        )
        settings.schema_version = 5
        settings.vector_paper_size = "A3"
        settings.vector_orientation = "LANDSCAPE"
        settings.vector_scale_denominator = 25.0
        settings.vector_line_width_mm = 0.35
        settings.vector_text_height_mm = 4.0
        settings.vector_arrow_size_mm = 3.0

        self.assertTrue(migrate_scene(bpy.context.scene))
        self.assertEqual(settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(settings.vector_paper_size, "A3")
        self.assertEqual(settings.vector_orientation, "LANDSCAPE")
        self.assertAlmostEqual(settings.vector_scale_denominator, 25.0)
        self.assertAlmostEqual(settings.vector_line_width_mm, 0.35)
        self.assertAlmostEqual(settings.vector_text_height_mm, 4.0)
        self.assertAlmostEqual(settings.vector_arrow_size_mm, 3.0)
        self.assertEqual(dimension.dimension_props.start.resolution_status, "BY_FALLBACK")
        self.assertEqual(dimension.dimension_props.start.source_object_name, "Preserved v5 Source")

        (
            settings.schema_version,
            settings.vector_paper_size,
            settings.vector_orientation,
            settings.vector_scale_denominator,
            settings.vector_line_width_mm,
            settings.vector_text_height_mm,
            settings.vector_arrow_size_mm,
        ) = original

    def test_derived_guide_schema_v10_migration_is_additive_and_idempotent(self):
        guide = create_guide_object(bpy.context, "Dimensions Schema 10 Guide")
        self.addCleanup(bpy.data.objects.remove, guide, do_unlink=True)
        settings = bpy.context.scene.dimensions_settings
        settings.schema_version = 10
        self.assertTrue(migrate_scene(bpy.context.scene))
        self.assertEqual(settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertFalse(guide.guide_props.derived)
        self.assertEqual(guide.guide_props.derivation_mode, "NONE")
        self.assertEqual(guide.guide_props.derived_state, "LIVE")
        self.assertFalse(migrate_scene(bpy.context.scene))

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
                dimension_type="ALIGNED",
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

    def test_projected_vertex_cache_preserves_object_and_vertex_identity(self):
        mesh = bpy.data.meshes.new("Dimensions Projected Cache Mesh")
        mesh.from_pydata(
            [(0.0, 0.0, 0.0), (-3.0, -2.0, 0.0), (0.0, 0.0, 2.0)],
            [],
            [],
        )
        obj = bpy.data.objects.new("Dimensions Projected Cache", mesh)
        bpy.context.scene.collection.objects.link(obj)
        self.addCleanup(bpy.data.meshes.remove, mesh)
        self.addCleanup(bpy.data.objects.remove, obj, do_unlink=True)
        obj.matrix_world = Matrix.Translation((1.0, 0.0, 0.0))

        sources = _build_sources(SimpleNamespace(visible_objects=[obj]), None)
        region = SimpleNamespace(width=200, height=100)
        perspective_matrix = Matrix.Identity(4)
        perspective_matrix[3][2] = -1.0
        region_data = SimpleNamespace(perspective_matrix=perspective_matrix)
        grid = _project_sources(region, region_data, sources)

        positive_cell = tuple(_cell_source_indices(grid, 4, 1))
        negative_cell = tuple(_cell_source_indices(grid, -3, -2))
        self.assertEqual(positive_cell, (0,))
        self.assertEqual(negative_cell, (1,))
        candidate = _materialize_candidate(sources, grid, positive_cell[0])
        self.assertEqual(candidate["object"], obj)
        self.assertEqual(candidate["vertex_index"], 0)
        self.assertEqual(candidate["world_co"], Vector((1.0, 0.0, 0.0)))
        self.assertEqual(candidate["screen_co"], Vector((200.0, 50.0)))
        self.assertEqual(set(grid["source_indices"]), {0, 1})
        self.assertNotEqual(grid["screen_coordinates"][2, 0], grid["screen_coordinates"][2, 0])

    def test_out_of_view_sources_remain_available_to_exact_fallback_queries(self):
        sources = {
            "objects": (object(),),
            "object_starts": np.array((0, 1), dtype=np.int64),
            "world_coordinates": np.array(((10.0, 0.0, 0.0),), dtype=np.float32),
        }
        region = SimpleNamespace(width=200, height=100)
        region_data = SimpleNamespace(perspective_matrix=Matrix.Identity(4))
        grid = _project_sources(region, region_data, sources)
        cell_x = floor(grid["screen_coordinates"][0, 0] / 48.0)
        cell_y = floor(grid["screen_coordinates"][0, 1] / 48.0)

        self.assertEqual(tuple(_cell_source_indices(grid, cell_x, cell_y)), ())
        full_grid = _full_spatial_grid(grid)
        self.assertEqual(tuple(_cell_source_indices(full_grid, cell_x, cell_y)), (0,))

    def test_bulk_projection_matches_blender_for_transformed_sources(self):
        mesh = bpy.data.meshes.new("Dimensions Projection Parity Mesh")
        mesh.from_pydata(
            [(-1.0, -0.5, -2.0), (0.25, 1.0, -5.0), (2.0, -1.0, 1.0)],
            [],
            [],
        )
        obj = bpy.data.objects.new("Dimensions Projection Parity", mesh)
        bpy.context.scene.collection.objects.link(obj)
        self.addCleanup(bpy.data.meshes.remove, mesh)
        self.addCleanup(bpy.data.objects.remove, obj, do_unlink=True)
        obj.matrix_world = (
            Matrix.Translation((0.35, -0.2, 0.0))
            @ Matrix.Rotation(0.31, 4, "Z")
            @ Matrix.Diagonal((1.4, 0.75, 1.2, 1.0))
        )

        sources = _build_sources(SimpleNamespace(visible_objects=[obj]), None)
        region = SimpleNamespace(width=641, height=359)

        orthographic = Matrix.Identity(4)
        orthographic[0][0] = 0.45
        orthographic[1][1] = 0.7
        orthographic[0][3] = 0.12
        orthographic[1][3] = -0.08

        perspective = Matrix.Identity(4)
        perspective[0][0] = 1.35
        perspective[1][1] = 1.8
        perspective[2][2] = -1.01
        perspective[2][3] = -0.2
        perspective[3][2] = -1.0
        perspective[3][3] = 0.0

        for label, projection in (
            ("orthographic", orthographic),
            ("perspective", perspective),
        ):
            with self.subTest(projection=label):
                region_data = SimpleNamespace(perspective_matrix=projection)
                grid = _project_sources(region, region_data, sources)
                visible_indices = set(int(index) for index in grid["source_indices"])
                for index, world_values in enumerate(sources["world_coordinates"]):
                    world_co = Vector(world_values)
                    expected = view3d_utils.location_3d_to_region_2d(
                        region, region_data, world_co, default=None
                    )
                    if expected is None:
                        self.assertNotIn(index, visible_indices)
                        self.assertNotEqual(
                            grid["screen_coordinates"][index, 0],
                            grid["screen_coordinates"][index, 0],
                        )
                        continue
                    self.assertIn(index, visible_indices)
                    actual = Vector(grid["screen_coordinates"][index])
                    self.assertAlmostEqual(actual.x, expected.x, places=3)
                    self.assertAlmostEqual(actual.y, expected.y, places=3)

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

    def test_annotation_rotation_and_scale_are_locked_and_ignored(self):
        annotation = create_dimension_object(bpy.context, "DIM Transform Policy")
        try:
            props = annotation.dimension_props
            set_world_anchor(props.start, Vector((0.0, 0.0, 0.0)))
            set_world_anchor(props.end, Vector((2.0, 0.0, 0.0)))
            props.offset_distance = 0.25
            sync_scene_objects(bpy.context.scene)
            original_offset = Vector(props.presentation_offset)
            original_location = annotation_world_location(annotation)
            self.assertEqual(tuple(annotation.lock_rotation), (True, True, True))
            self.assertEqual(tuple(annotation.lock_scale), (True, True, True))

            # Scripted/legacy values are retained for file compatibility, but
            # must never enter canonical geometry or presentation translation.
            annotation.rotation_euler = (0.2, -0.4, 0.8)
            annotation.scale = (4.0, 0.5, 2.0)
            self.assertTrue(has_ignored_rotation_or_scale(annotation))
            sync_scene_objects(bpy.context.scene)
            for actual, expected in zip(annotation.rotation_euler, (0.2, -0.4, 0.8)):
                self.assertAlmostEqual(actual, expected, places=5)
            for actual, expected in zip(annotation.scale, (4.0, 0.5, 2.0)):
                self.assertAlmostEqual(actual, expected, places=5)
            self.assertLess((Vector(props.presentation_offset) - original_offset).length, 1e-6)
            self.assertLess((annotation_world_location(annotation) - original_location).length, 1e-6)
        finally:
            bpy.data.objects.remove(annotation, do_unlink=True)

    def test_annotation_translation_is_the_only_captured_transform_delta(self):
        annotation = create_dimension_object(bpy.context, "DIM Translation Policy")
        try:
            props = annotation.dimension_props
            set_world_anchor(props.start, Vector((0.0, 0.0, 0.0)))
            set_world_anchor(props.end, Vector((2.0, 0.0, 0.0)))
            props.offset_distance = 0.25
            sync_scene_objects(bpy.context.scene)
            translation = Vector((1.25, -2.0, 0.75))
            annotation.location += translation
            annotation.rotation_euler[2] = 1.0
            annotation.scale = (3.0, 3.0, 3.0)
            sync_scene_objects(bpy.context.scene)
            self.assertLess((Vector(props.presentation_offset) - translation).length, 1e-6)
            self.assertTrue(has_ignored_rotation_or_scale(annotation))
            self.assertFalse(enforce_annotation_transform_policy(annotation))
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
            self.assertEqual(result["evaluation_mode"], "BASE")
            self.assertEqual(result["state"], "LIVE")
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

    def test_area_evaluated_faces_require_unique_propagated_identity(self):
        def polygon(area, center, vertices=(0, 1, 2, 3)):
            return SimpleNamespace(
                area=area, center=Vector(center), normal=Vector((0.0, 0.0, 1.0)), vertices=vertices,
            )

        def mesh(polygons, ids=None):
            attribute = None if ids is None else SimpleNamespace(
                data_type="INT", domain="FACE",
                data=[SimpleNamespace(value=value) for value in ids],
            )
            return SimpleNamespace(
                polygons=polygons,
                attributes={} if attribute is None else {area_binding_module.FACE_ID_ATTRIBUTE: attribute},
            )

        base_mesh = mesh([polygon(2.0, (1.0, 0.5, 0.0))], [17])
        evaluated_mesh = mesh([polygon(3.0, (1.0, 0.5, 0.25))], [17])
        evaluated = SimpleNamespace(data=evaluated_mesh, matrix_world=Matrix.Identity(4))
        source = SimpleNamespace(
            type="MESH", mode="OBJECT", data=base_mesh, matrix_world=Matrix.Identity(4),
            modifiers=[SimpleNamespace(show_viewport=True, show_in_editmode=False)],
            evaluated_get=lambda _depsgraph: evaluated,
        )
        props = SimpleNamespace(
            area_source_object=source,
            area_faces=[SimpleNamespace(face_id=17, vertex_count=4)],
        )
        fake_bpy = SimpleNamespace(
            context=SimpleNamespace(evaluated_depsgraph_get=lambda: object()),
        )
        with patch.object(area_binding_module, "bpy", fake_bpy):
            result = evaluate_area_binding(props)
            self.assertEqual(result["state"], "LIVE")
            self.assertEqual(result["evaluation_mode"], "EVALUATED")
            self.assertAlmostEqual(result["area"], 3.0)

            evaluated.data = mesh([
                polygon(1.5, (0.5, 0.5, 0.0)), polygon(1.5, (1.5, 0.5, 0.0)),
            ], [17, 17])
            result = evaluate_area_binding(props)
            self.assertEqual(result["state"], "FALLBACK")
            self.assertEqual(result["evaluation_mode"], "BASE_FALLBACK")
            self.assertAlmostEqual(result["area"], 2.0)
            self.assertIn("unique face identity", result["evaluation_reason"])

            evaluated.data = mesh([polygon(3.0, (1.0, 0.5, 0.25))], None)
            self.assertEqual(evaluate_area_binding(props)["state"], "FALLBACK")

    def test_topology_duplicating_modifier_marks_live_area_fallback(self):
        mesh = bpy.data.meshes.new("Dimensions Evaluated Area Mesh")
        mesh.from_pydata(
            [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)],
        )
        source = bpy.data.objects.new("Dimensions Evaluated Area", mesh)
        bpy.context.scene.collection.objects.link(source)
        annotation = create_dimension_object(bpy.context, "AREA Evaluated Modifier")
        try:
            props = annotation.dimension_props
            props.annotation_kind = "AREA"
            self.assertEqual(bind_area_face_indices(props, source, [0])["evaluation_mode"], "BASE")
            set_world_anchor(props.start, Vector((1.0, 0.5, 0.0)))
            set_world_anchor(props.end, Vector((1.0, 1.5, 0.0)))
            modifier = source.modifiers.new("Duplicate Bound Face", "ARRAY")
            modifier.count = 2
            modifier.relative_offset_displace = (2.0, 0.0, 0.0)
            bpy.context.view_layer.update()
            result = evaluate_area_binding(props)
            self.assertEqual(result["state"], "FALLBACK")
            self.assertEqual(result["evaluation_mode"], "BASE_FALLBACK")
            self.assertAlmostEqual(result["area"], 2.0)
            sync_scene_objects(bpy.context.scene)
            self.assertEqual(props.measurement_state, "FALLBACK")
            self.assertIsNone(area_dimension_output_spec(
                annotation, "modifier-fallback", WorldSizingPolicy(0.01, 0.1),
            ))
            bpy.context.view_layer.objects.active = annotation
            annotation.select_set(True)
            self.assertTrue(DIMENSIONS_OT_CaptureArea.poll(bpy.context))
            source.modifiers.remove(modifier)
            bpy.context.view_layer.update()
            sync_scene_objects(bpy.context.scene)
            self.assertEqual(props.measurement_state, "LIVE")
            self.assertIsNotNone(area_dimension_output_spec(
                annotation, "modifier-live", WorldSizingPolicy(0.01, 0.1),
            ))
        finally:
            bpy.data.objects.remove(annotation, do_unlink=True)
            bpy.data.objects.remove(source, do_unlink=True)
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

    def test_guide_point_anchor_follows_vertex_transform_and_mesh_edit(self):
        mesh = bpy.data.meshes.new("DimensionsGuidePointAnchorMesh")
        mesh.from_pydata([(1.0, 2.0, 3.0)], [], [])
        source = bpy.data.objects.new("DimensionsGuidePointAnchorSource", mesh)
        bpy.context.scene.collection.objects.link(source)
        point = create_guide_point_object(bpy.context, "DimensionsGuidePointAnchor")
        point_name, source_name, mesh_name = point.name, source.name, mesh.name
        self.addCleanup(lambda: bpy.data.meshes.remove(bpy.data.meshes[mesh_name]) if mesh_name in bpy.data.meshes else None)
        self.addCleanup(lambda: bpy.data.objects.remove(bpy.data.objects[source_name], do_unlink=True) if source_name in bpy.data.objects else None)
        self.addCleanup(lambda: bpy.data.objects.remove(bpy.data.objects[point_name], do_unlink=True) if point_name in bpy.data.objects else None)
        set_anchor(point.guide_props.start, source, 0)

        source.location = (5.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        sync_scene_objects(bpy.context.scene)
        self.assertEqual(resolve_anchor(point.guide_props.start), Vector((6.0, 2.0, 3.0)))
        mesh.vertices[0].co = (2.0, 4.0, 6.0)
        mesh.update()
        bpy.context.view_layer.update()
        sync_scene_objects(bpy.context.scene)
        self.assertEqual(resolve_anchor(point.guide_props.start), Vector((7.0, 4.0, 6.0)))

    def test_guide_point_has_one_vertex_native_proxy_and_constant_pixel_marker(self):
        point = create_guide_point_object(bpy.context, "DimensionsGuidePointProxy")
        self.addCleanup(bpy.data.objects.remove, point, do_unlink=True)
        set_world_anchor(point.guide_props.start, Vector((1.0, 2.0, 3.0)))
        proxy = ensure_guide_point_snap_proxy(point, bpy.context.scene)
        self.addCleanup(bpy.data.meshes.remove, proxy.data)
        self.addCleanup(bpy.data.objects.remove, proxy, do_unlink=True)
        self.assertEqual(len(proxy.data.vertices), 1)
        self.assertEqual(proxy.matrix_world @ proxy.data.vertices[0].co, Vector((1.0, 2.0, 3.0)))
        segments = guide_point_marker_segments(Vector((100.0, 200.0)), size=6.0)
        xs = [value.x for value in segments]
        ys = [value.y for value in segments]
        self.assertEqual((max(xs) - min(xs), max(ys) - min(ys)), (12.0, 12.0))

    def test_guide_point_snap_generation_respects_its_own_target(self):
        point = create_guide_point_object(bpy.context, "DimensionsGuidePointSnap")
        self.addCleanup(bpy.data.objects.remove, point, do_unlink=True)
        set_world_anchor(point.guide_props.start, Vector((10.0, 20.0, 0.0)))
        context = SimpleNamespace(scene=SimpleNamespace(objects=[point]), region=object(), region_data=object())
        with (
            patch("dimensions.snapping.has_view3d_window_region", return_value=True),
            patch("dimensions.snapping.get_mouse_ray", return_value=(Vector(), Vector((0.0, 0.0, -1.0)))),
            patch("dimensions.snapping.guide_is_visible", return_value=True),
            patch("dimensions.snapping.view3d_utils.location_3d_to_region_2d", return_value=Vector((10.0, 20.0))),
        ):
            self.assertEqual(
                find_nearest_guide_point(context, 10.0, 20.0, enabled_targets={"guide_point"})["type"],
                "GUIDE_POINT",
            )
            self.assertIsNone(find_nearest_guide_point(context, 10.0, 20.0, enabled_targets={"guide"}))

    def test_selection_centroid_uses_selected_object_origins(self):
        first = bpy.data.objects.new("DimensionsGuidePointCentroidA", None)
        second = bpy.data.objects.new("DimensionsGuidePointCentroidB", None)
        bpy.context.scene.collection.objects.link(first)
        bpy.context.scene.collection.objects.link(second)
        self.addCleanup(bpy.data.objects.remove, first, do_unlink=True)
        self.addCleanup(bpy.data.objects.remove, second, do_unlink=True)
        first.location = (0.0, 0.0, 0.0)
        second.location = (4.0, 2.0, 0.0)
        bpy.context.view_layer.update()
        context = SimpleNamespace(mode="OBJECT", selected_objects=[first, second])
        self.assertEqual(selection_centroid(context), Vector((2.0, 1.0, 0.0)))

    def test_surface_snap_creation_uses_existing_anchor_model_and_one_undo_step(self):
        source = self._make_object(
            "DimensionsGuidePointSurfaceSource",
            [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 2.0, 0.0)],
            faces=[(0, 1, 2)],
        )
        operator = make_operator_harness(DIMENSIONS_OT_CreateGuidePoint)
        operator._create_from_snap(bpy.context, _face_snap(source, 0.5, 0.5, 0.0))
        point = bpy.context.view_layer.objects.active
        self.addCleanup(bpy.data.objects.remove, point, do_unlink=True)
        self.addCleanup(remove_guide_point_snap_proxies, point)
        self.assertEqual(point.guide_props.kind, "POINT")
        self.assertEqual(point.guide_props.start.anchor_type, "OBJECT_POINT")
        self.assertIn("UNDO", DIMENSIONS_OT_CreateGuidePoint.bl_options)
        source.location.x = 3.0
        bpy.context.view_layer.update()
        self.assertEqual(resolve_anchor(point.guide_props.start), Vector((3.5, 0.5, 0.0)))

    def test_offset_guide_point_reuses_typed_axis_acquisition(self):
        operator = SimpleNamespace(
            start_snap=_world_snap(1.0, 2.0, 3.0),
            hover_snap=_world_snap(8.0, 6.0, 3.0),
            axis="Y", distance_text="2.5", distance_input_valid=True,
            _copy_snap=lambda snap: dict(snap),
        )
        end_snap = DIMENSIONS_OT_CreateGuidePoint._effective_end_snap(operator, bpy.context)
        self.assertEqual(end_snap["world_co"], Vector((1.0, 4.5, 3.0)))

    def test_edge_and_face_derived_guides_follow_their_sources(self):
        source = self._make_object(
            "DimensionsDerivedSource",
            [(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 3.0, 0.0), (0.0, 3.0, 0.0)],
            edges=[(0, 1), (1, 2), (2, 3), (3, 0)], faces=[(0, 1, 2, 3)],
        )
        edge_guide = create_guide_object(bpy.context, "Dimensions Edge Offset")
        face_guide = create_guide_object(bpy.context, "Dimensions Face Offset")
        self.addCleanup(bpy.data.objects.remove, edge_guide, do_unlink=True)
        self.addCleanup(bpy.data.objects.remove, face_guide, do_unlink=True)
        for guide in (edge_guide, face_guide):
            guide.guide_props.derived = True
            guide.guide_props.derivation_mode = "OFFSET"
            guide.guide_props.offset_distance = 2.0
            guide.guide_props.offset_side = 1
        edge_guide.guide_props.derived_direction = (0.0, 1.0, 0.0)
        self.assertTrue(bind_edge_source(edge_guide.guide_props.source_a, source, 0))
        face_guide.guide_props.derived_direction = (1.0, 0.0, 0.0)
        self.assertTrue(bind_face_source(face_guide.guide_props.source_a, source, 0))

        self.assertEqual(resolve_derived_guide(edge_guide)[0], Vector((0.0, 2.0, 0.0)))
        self.assertEqual(resolve_derived_guide(face_guide)[0], Vector((2.0, 1.5, 2.0)))
        source.location = (0.0, 5.0, 1.0)
        bpy.context.view_layer.update()
        self.assertEqual(resolve_derived_guide(edge_guide)[0], Vector((0.0, 7.0, 1.0)))
        self.assertEqual(resolve_derived_guide(face_guide)[0], Vector((2.0, 6.5, 3.0)))

    def test_centerline_chaining_detach_and_cycle_refusal(self):
        first = create_guide_object(bpy.context, "Dimensions Centerline A")
        second = create_guide_object(bpy.context, "Dimensions Centerline B")
        center = create_guide_object(bpy.context, "Dimensions Centerline")
        chained = create_guide_object(bpy.context, "Dimensions Chained Offset")
        for obj in (first, second, center, chained):
            self.addCleanup(bpy.data.objects.remove, obj, do_unlink=True)
        for guide, y in ((first, 0.0), (second, 4.0)):
            set_world_anchor(guide.guide_props.start, Vector((0.0, y, 0.0)))
            set_world_anchor(guide.guide_props.end, Vector((1.0, y, 0.0)))
        center.guide_props.derived = True
        center.guide_props.derivation_mode = "CENTERLINE"
        center.guide_props.derived_direction = (0.0, 1.0, 0.0)
        bind_guide_source(center.guide_props.source_a, first)
        bind_guide_source(center.guide_props.source_b, second)
        self.assertEqual(resolve_derived_guide(center)[0], Vector((0.0, 2.0, 0.0)))

        chained.guide_props.derived = True
        chained.guide_props.derivation_mode = "OFFSET"
        chained.guide_props.offset_distance = 1.0
        chained.guide_props.derived_direction = (0.0, 1.0, 0.0)
        bind_guide_source(chained.guide_props.source_a, center)
        self.assertEqual(resolve_derived_guide(chained)[0], Vector((0.0, 3.0, 0.0)))
        self.assertTrue(would_create_cycle(center, (chained,)))
        before = resolve_derived_guide(chained)
        self.assertTrue(detach_derived_guide(chained))
        self.assertFalse(chained.guide_props.derived)
        self.assertEqual(resolve_derived_guide(chained), before)

        cycle_a = create_guide_object(bpy.context, "Dimensions Cycle A")
        cycle_b = create_guide_object(bpy.context, "Dimensions Cycle B")
        for obj in (cycle_a, cycle_b):
            self.addCleanup(bpy.data.objects.remove, obj, do_unlink=True)
            obj.guide_props.derived = True
            obj.guide_props.derivation_mode = "OFFSET"
            obj.guide_props.offset_distance = 1.0
            obj.guide_props.derived_direction = (0.0, 1.0, 0.0)
        bind_guide_source(cycle_a.guide_props.source_a, cycle_b)
        bind_guide_source(cycle_b.guide_props.source_a, cycle_a)
        self.assertIsNone(resolve_derived_guide(cycle_a))
        self.assertIn(cycle_a.guide_props.derived_state, {"CYCLE", "NEEDS_REPAIR"})

    def test_deleted_derived_source_is_truthfully_needs_repair(self):
        source = self._make_object(
            "Dimensions Lost Derived Source", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], edges=[(0, 1)],
        )
        guide = create_guide_object(bpy.context, "Dimensions Broken Offset")
        self.addCleanup(bpy.data.objects.remove, guide, do_unlink=True)
        guide.guide_props.derived = True
        guide.guide_props.derivation_mode = "OFFSET"
        guide.guide_props.offset_distance = 1.0
        guide.guide_props.derived_direction = (0.0, 1.0, 0.0)
        bind_edge_source(guide.guide_props.source_a, source, 0)
        self.assertIsNotNone(resolve_derived_guide(guide))
        guide.guide_props.source_a.target_object = None
        guide.guide_props.source_a.start.target_object = None
        guide.guide_props.source_a.end.target_object = None
        self.assertIsNone(resolve_derived_guide(guide))
        self.assertEqual(guide.guide_props.derived_state, "NEEDS_REPAIR")

    def test_derived_guide_uses_standard_units_flip_action_and_one_undo_step(self):
        operator = make_operator_harness(
            DIMENSIONS_OT_CreateDerivedGuide,
            state="OFFSET", offset_side=1, distance_text="400mm",
            distance_input_valid=True,
        )
        operator._update_preview = lambda _context: None
        self.assertAlmostEqual(operator._distance(bpy.context), 0.4)
        self.assertIn("UNDO", DIMENSIONS_OT_CreateDerivedGuide.bl_options)
        context = SimpleNamespace(area=SimpleNamespace(type="VIEW_3D"))
        result = operator.modal(context, make_event("F"))
        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertEqual(operator.offset_side, -1)

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
        self.context.scene.dimensions_settings.annotation_styles.clear()

    def _make_dimension(self, start=(0.0, 0.0, 0.0), end=(1.0, 0.0, 0.0)):
        obj = create_dimension_object(self.context, "DIM Cache Test")
        set_world_anchor(obj.dimension_props.start, Vector(start))
        set_world_anchor(obj.dimension_props.end, Vector(end))
        self.created.append(obj)
        return obj

    def test_named_style_resolution_is_cached_and_invalidated_as_one_snapshot(self):
        settings = self.context.scene.dimensions_settings
        settings.annotation_styles.clear()
        style = settings.annotation_styles.add()
        style.name = "Detail"
        style.line_width = 3.0
        dimension = self._make_dimension()
        dimension.dimension_props.style_name = style.name

        geometry = drawing.get_cached_dimension_geometry(self.context, dimension)
        self.assertAlmostEqual(geometry["line_width"], 3.0)
        build_count = drawing.geometry_build_count()
        drawing.get_cached_dimension_geometry(self.context, dimension)
        self.assertEqual(drawing.geometry_build_count(), build_count)

        style.line_width = 5.0
        geometry = drawing.get_cached_dimension_geometry(self.context, dimension)
        self.assertAlmostEqual(geometry["line_width"], 5.0)
        self.assertEqual(drawing.geometry_build_count(), build_count + 1)

    def test_extension_gap_and_overshoot_trim_screen_geometry(self):
        segment = _extension_line_segment(Vector((0.0, 0.0)), Vector((0.0, 20.0)), 3.0, 4.0)
        self.assertEqual(segment, [Vector((0.0, 3.0)), Vector((0.0, 24.0))])
        self.assertEqual(
            _extension_line_segment(Vector((0.0, 0.0)), Vector((0.0, 20.0)), 0.0, 0.0),
            [Vector((0.0, 0.0)), Vector((0.0, 20.0))],
        )

    def test_all_endpoint_variants_are_distinct_and_per_end_styles_resolve_independently(self):
        point = Vector((0.0, 0.0))
        direction = Vector((1.0, 0.0))
        counts = {
            style: len(_build_arrow_segments(point, direction, 10.0, style))
            for style in ("OPEN", "FILLED", "ARCHITECTURAL_TICK", "DOT", "NONE")
        }
        self.assertEqual(counts, {"OPEN": 4, "FILLED": 8, "ARCHITECTURAL_TICK": 2, "DOT": 28, "NONE": 0})
        dimension = self._make_dimension()
        props = dimension.dimension_props
        props.override_start_end_style = True
        props.override_end_end_style = True
        props.start_end_style = "DOT"
        props.end_end_style = "NONE"
        resolved = resolve_dimension_style(self.context.scene.dimensions_settings, props)
        self.assertEqual((resolved.start_end_style, resolved.end_end_style), ("DOT", "NONE"))

    def test_dual_units_have_independent_precision_and_arrangement(self):
        context = bpy.context
        self.assertEqual(
            format_dual_length(context, 0.1, 1, "MILLIMETERS", "INCH_DECIMAL", 3, "BRACKETS"),
            '100.0 mm [3.937"]',
        )
        self.assertEqual(
            format_dual_length(context, 0.1, 0, "MILLIMETERS", "INCH_DECIMAL", 1, "STACKED"),
            '100 mm\n3.9"',
        )

    def test_label_modes_and_tight_space_use_deterministic_end_leader(self):
        geometry = {
            "line_start_screen": Vector((0.0, 0.0)),
            "line_end_screen": Vector((30.0, 0.0)),
            "line_mid_screen": Vector((15.0, 0.0)),
            "line_direction_screen": Vector((1.0, 0.0)),
            "label_orientation": "ALIGNED",
        }
        tight = _build_text_layout("A VERY LONG LABEL", geometry, "INLINE", text_size=14, arrow_size=10)
        self.assertGreater(tight["text_position"].x, geometry["line_end_screen"].x)
        self.assertEqual(tight["line_segments"][-2], geometry["line_end_screen"])
        self.assertEqual(tight["text_rotation"], 0.0)
        for row_y in (20.0, 40.0, 60.0):
            row = dict(geometry)
            row["line_start_screen"] = Vector((0.0, row_y))
            row["line_end_screen"] = Vector((30.0, row_y))
            row["line_mid_screen"] = Vector((15.0, row_y))
            layout = _build_text_layout("A VERY LONG LABEL", row, "INLINE", text_size=14, arrow_size=10)
            self.assertGreater(layout["text_position"].x, row["line_end_screen"].x)
        geometry["line_direction_screen"] = Vector((0.0, 1.0))
        geometry["label_orientation"] = "ALIGNED"
        aligned = _build_text_layout("10", geometry, "ABOVE", text_size=14, arrow_size=10)
        self.assertAlmostEqual(abs(aligned["text_rotation"]), 1.57079632679)
        geometry["label_orientation"] = "HORIZONTAL"
        horizontal = _build_text_layout("10", geometry, "ABOVE", text_size=14, arrow_size=10)
        self.assertEqual(horizontal["text_rotation"], 0.0)


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

    def test_architectural_tick_is_a_single_diagonal_screen_space_segment(self):
        point = Vector((20.0, 30.0))
        arrow_segments = drawing._build_arrow_segments(
            point,
            Vector((1.0, 0.0)),
            12.0,
        )
        tick_segments = drawing._build_arrow_segments(
            point,
            Vector((1.0, 0.0)),
            12.0,
            "ARCHITECTURAL_TICK",
        )

        self.assertEqual(
            arrow_segments,
            drawing._build_arrow_segments(point, Vector((1.0, 0.0)), 12.0, "ARROW"),
        )
        self.assertEqual(len(tick_segments), 2)
        self.assertEqual((tick_segments[0] + tick_segments[1]) * 0.5, point)
        self.assertAlmostEqual((tick_segments[1] - tick_segments[0]).length, 12.0, places=5)
        self.assertNotAlmostEqual((tick_segments[1] - tick_segments[0]).x, 0.0)
        self.assertNotAlmostEqual((tick_segments[1] - tick_segments[0]).y, 0.0)

    def test_outside_start_text_layout_is_opposite_outside_end(self):
        geometry = {
            "line_start_screen": Vector((10.0, 30.0)),
            "line_end_screen": Vector((110.0, 30.0)),
            "line_mid_screen": Vector((60.0, 30.0)),
            "line_direction_screen": Vector((1.0, 0.0)),
        }
        outside_end = drawing._build_text_layout(
            "100 mm", geometry, "OUTSIDE", text_size=14.0, arrow_size=10.0
        )
        outside_start = drawing._build_text_layout(
            "100 mm", geometry, "OUTSIDE_START", text_size=14.0, arrow_size=10.0
        )

        self.assertGreater(outside_end["text_position"].x, geometry["line_end_screen"].x)
        self.assertLess(outside_start["text_position"].x, geometry["line_start_screen"].x)

        reversed_geometry = dict(geometry)
        reversed_geometry["line_start_screen"] = Vector((110.0, 30.0))
        reversed_geometry["line_end_screen"] = Vector((10.0, 30.0))
        reversed_geometry["line_direction_screen"] = Vector((-1.0, 0.0))
        reversed_start = drawing._build_text_layout(
            "100 mm", reversed_geometry, "OUTSIDE_START", text_size=14.0, arrow_size=10.0
        )
        self.assertGreater(reversed_start["text_position"].x, reversed_geometry["line_start_screen"].x)

    def test_arrow_end_style_defaults_to_arrows_and_applies_to_new_dimensions(self):
        settings = bpy.context.scene.dimensions_settings
        original_style = settings.dimension_arrow_end_style
        try:
            settings.dimension_arrow_end_style = "ARROW"
            self.assertEqual(self._make_dimension().dimension_props.arrow_end_style, "ARROW")
            settings.dimension_arrow_end_style = "ARCHITECTURAL_TICK"
            self.assertEqual(
                self._make_dimension().dimension_props.arrow_end_style,
                "ARCHITECTURAL_TICK",
            )
        finally:
            settings.dimension_arrow_end_style = original_style

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
        props.override_text_size = True
        props.override_arrow_size = True
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


class DimensionsNamedStyleTests(unittest.TestCase):
    def setUp(self):
        self.settings = bpy.context.scene.dimensions_settings
        self.settings.annotation_styles.clear()
        self.created = []
        self.global_style = {
            name: tuple(getattr(self.settings, name)) if name in {"dimension_color", "selected_dimension_color"} else getattr(self.settings, name)
            for name in (
                "dimension_color", "selected_dimension_color", "dimension_line_width",
                "dimension_text_size", "precision", "dimension_arrow_size",
                "dimension_arrow_end_style", "unit_style", "metric_unit_style",
                "imperial_unit_style",
            )
        }

    def tearDown(self):
        for obj in self.created:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        self.settings.annotation_styles.clear()
        for name, value in self.global_style.items():
            setattr(self.settings, name, value)

    def _dimension(self, name):
        obj = create_dimension_object(bpy.context, name)
        self.created.append(obj)
        return obj

    def test_resolution_is_per_property_override_then_style_then_scene(self):
        self.settings.dimension_line_width = 2.0
        self.settings.dimension_text_size = 14
        style = self.settings.annotation_styles.add()
        style.name = "Structural"
        style.line_width = 4.0
        style.text_size = 18
        props = self._dimension("DIM Style Resolution").dimension_props
        props.style_name = style.name
        props.text_size = 26
        props.override_text_size = True

        resolved = resolve_dimension_style(self.settings, props)
        self.assertAlmostEqual(resolved.line_width, 4.0)
        self.assertEqual(resolved.text_size, 26)
        self.assertEqual(resolved.value_prefix, "")

        props.style_name = "Missing"
        resolved = resolve_dimension_style(self.settings, props)
        self.assertAlmostEqual(resolved.line_width, 2.0)
        self.assertEqual(resolved.text_size, 26)

    def test_clear_overrides_makes_every_property_inherit(self):
        props = self._dimension("DIM Clear Style Overrides").dimension_props
        for name in ("color", "line_width", "precision", "tolerance"):
            setattr(props, f"override_{name}", True)
        clear_dimension_style_overrides(props)
        self.assertFalse(any(
            getattr(props, f"override_{name}")
            for name in (
                "color", "selected_color", "line_width", "text_size", "precision",
                "arrow_size", "arrow_end_style", "value_prefix", "value_suffix",
                "tolerance", "unit_style",
            )
        ))

    def test_reset_and_copy_global_cover_the_complete_resolved_style(self):
        props = self._dimension("DIM Global Style Round Trip").dimension_props
        props.value_prefix = "OLD"
        props.value_suffix = "OLD"
        props.tolerance_mode = "DEVIATION"
        props.tolerance_upper = 0.5
        props.tolerance_lower = 0.25
        self.settings.precision = 5
        self.settings.dimension_line_width = 3.0

        apply_scene_style_to_dimension(self.settings, props)
        resolved = resolve_dimension_style(self.settings, props)
        self.assertEqual(resolved.precision, 5)
        self.assertAlmostEqual(resolved.line_width, 3.0)
        self.assertEqual(resolved.value_prefix, "")
        self.assertEqual(resolved.value_suffix, "")
        self.assertEqual(resolved.tolerance_mode, "NONE")
        self.assertTrue(all(
            getattr(props, f"override_{name}")
            for name in (
                "color", "selected_color", "line_width", "text_size", "precision",
                "arrow_size", "arrow_end_style", "value_prefix", "value_suffix",
                "tolerance", "unit_style",
            )
        ))

        props.precision = 2
        props.unit_style = "BLENDER"
        apply_dimension_style_to_scene(props, self.settings)
        self.assertEqual(self.settings.precision, 2)
        self.assertEqual(configured_scene_unit_style(self.settings), "BLENDER")

    def test_delete_reassigns_users_without_dangling_reference(self):
        style = self.settings.annotation_styles.add()
        style.name = "Temporary"
        self.settings.active_annotation_style_index = 0
        dimension = self._dimension("DIM Delete Style")
        dimension.dimension_props.style_name = style.name

        self.assertEqual(bpy.ops.dimensions.delete_annotation_style(), {"FINISHED"})
        self.assertEqual(dimension.dimension_props.style_name, "")
        self.assertEqual(len(self.settings.annotation_styles), 0)

    def test_create_duplicate_rename_assign_and_select_users(self):
        self.assertEqual(bpy.ops.dimensions.create_annotation_style(), {"FINISHED"})
        self.settings.annotation_styles[0].line_width = 4.5
        self.assertEqual(bpy.ops.dimensions.duplicate_annotation_style(), {"FINISHED"})
        self.assertEqual(len(self.settings.annotation_styles), 2)
        self.assertAlmostEqual(self.settings.annotation_styles[1].line_width, 4.5)
        self.assertEqual(
            bpy.ops.dimensions.rename_annotation_style(name="Details"),
            {"FINISHED"},
        )
        self.assertEqual(self.settings.annotation_styles[1].name, "Details")

        dimension = self._dimension("DIM Assigned Style")
        bpy.ops.object.select_all(action="DESELECT")
        dimension.select_set(True)
        bpy.context.view_layer.objects.active = dimension
        dimension.dimension_props.override_line_width = True
        self.assertEqual(bpy.ops.dimensions.assign_annotation_style(), {"FINISHED"})
        self.assertEqual(dimension.dimension_props.style_name, "Details")
        self.assertFalse(dimension.dimension_props.override_line_width)

        bpy.ops.object.select_all(action="DESELECT")
        self.assertEqual(bpy.ops.dimensions.select_annotation_style_users(), {"FINISHED"})
        self.assertTrue(dimension.select_get())

    def test_scene_fallback_uses_the_active_metric_or_imperial_format(self):
        unit_settings = bpy.context.scene.unit_settings
        original_system = unit_settings.system
        original_metric = self.settings.metric_unit_style
        original_imperial = self.settings.imperial_unit_style
        original_schema = self.settings.schema_version
        props = self._dimension("DIM Unit Style Migration").dimension_props
        try:
            unit_settings.system = "METRIC"
            self.settings.metric_unit_style = "MILLIMETERS"
            self.assertEqual(configured_scene_unit_style(self.settings), "MILLIMETERS")
            self.assertEqual(resolve_dimension_style(self.settings, props).unit_style, "MILLIMETERS")
            self.settings.schema_version = 3
            self.assertTrue(migrate_scene(bpy.context.scene))
            self.assertTrue(props.override_unit_style)
            self.assertEqual(props.unit_style, "MILLIMETERS")

            unit_settings.system = "IMPERIAL"
            self.settings.imperial_unit_style = "INCH_FRACTION"
            self.assertEqual(configured_scene_unit_style(self.settings), "INCH_FRACTION")
            props.override_unit_style = False
            self.assertEqual(resolve_dimension_style(self.settings, props).unit_style, "INCH_FRACTION")
            self.settings.schema_version = 3
            self.assertTrue(migrate_scene(bpy.context.scene))
            self.assertEqual(props.unit_style, "INCH_FRACTION")
        finally:
            self.settings.schema_version = original_schema
            unit_settings.system = original_system
            self.settings.metric_unit_style = original_metric
            self.settings.imperial_unit_style = original_imperial


class DimensionsAnnotationManagerTests(unittest.TestCase):
    def setUp(self):
        self.scene = bpy.context.scene
        self.settings = self.scene.dimensions_settings
        self.created = []
        self.settings.annotation_styles.clear()
        self.settings.active_annotation_manager_index = -1
        self.settings.annotation_manager_search = ""
        for kind in ("linear", "angle", "area", "measurement", "guide"):
            setattr(self.settings, f"annotation_manager_kind_{kind}", True)
        for state in ("live", "fallback", "captured", "needs_repair"):
            setattr(self.settings, f"annotation_manager_state_{state}", True)
        self.settings.annotation_manager_references_active = False
        self.settings.annotation_manager_reference_object = None
        if self.settings.annotation_manager_isolate_active:
            restore_annotation_visibility(bpy.context)

    def tearDown(self):
        if self.settings.annotation_manager_isolate_active:
            restore_annotation_visibility(bpy.context)
        for obj in self.created:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        sync_annotation_manager(self.scene)
        self.settings.annotation_styles.clear()

    def _dimension(self, name, kind="LINEAR"):
        obj = create_dimension_object(bpy.context, name)
        obj.dimension_props.annotation_kind = kind
        self.created.append(obj)
        return obj

    def _guide(self, name, measurement=False):
        obj = create_measurement_object(bpy.context, name) if measurement else create_guide_object(bpy.context, name)
        self.created.append(obj)
        return obj

    def test_registry_reflects_external_create_rename_delete_without_redraw_rebuilds(self):
        dimension = self._dimension("DIM Manager External")
        guide = self._guide("GUIDE Manager External")
        before = registry_rebuild_count()
        self.assertTrue(sync_annotation_manager(self.scene))
        self.assertEqual(
            {item.annotation for item in self.settings.annotation_manager_items},
            {dimension, guide},
        )
        after_build = registry_rebuild_count()
        self.assertGreater(after_build, before)
        self.assertFalse(sync_annotation_manager(self.scene))
        self.assertEqual(registry_rebuild_count(), after_build)

        dimension.name = "DIM Renamed Outside Manager"
        sync_annotation_manager(self.scene)
        self.assertIn("DIM Renamed Outside Manager", {item.name for item in self.settings.annotation_manager_items})
        bpy.data.objects.remove(guide, do_unlink=True)
        self.created.remove(guide)
        self.assertTrue(sync_annotation_manager(self.scene))
        self.assertEqual(tuple(item.annotation for item in self.settings.annotation_manager_items), (dimension,))

    def test_combined_kind_state_search_and_reference_filters(self):
        source = self._make_mesh_source("Manager Filter Source")
        linear = self._dimension("DIM Filter Linear")
        area = self._dimension("AREA Filter Repair", "AREA")
        area.dimension_props.measurement_state = "NEEDS_REPAIR"
        area.dimension_props.area_source_object = source
        self._guide("GUIDE Filter")
        sync_annotation_manager(self.scene)
        for kind in ("linear", "angle", "measurement", "guide"):
            setattr(self.settings, f"annotation_manager_kind_{kind}", False)
        self.settings.annotation_manager_search = "repair"
        self.settings.annotation_manager_state_live = False
        self.settings.annotation_manager_state_captured = False
        self.settings.annotation_manager_references_active = True
        self.settings.annotation_manager_reference_object = source

        self.assertEqual(filtered_manager_objects(self.settings), (area,))
        self.assertTrue(annotation_references_object(area, source))
        self.assertFalse(annotation_references_object(linear, source))

    def _make_mesh_source(self, name):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([(0.0, 0.0, 0.0)], [], [])
        obj = bpy.data.objects.new(name, mesh)
        self.scene.collection.objects.link(obj)
        self.created.append(obj)
        return obj

    def test_isolate_exit_restores_the_exact_prior_visibility(self):
        first = self._dimension("DIM Isolate First")
        second = self._dimension("DIM Isolate Second")
        third = self._guide("GUIDE Isolate Hidden")
        third.hide_set(True)
        third.guide_props.visible = False
        sync_annotation_manager(self.scene)

        isolate_annotations(bpy.context, (first,))
        self.assertFalse(first.hide_get())
        self.assertTrue(second.hide_get())
        self.assertTrue(third.hide_get())
        self.assertFalse(third.guide_props.visible)
        restore_annotation_visibility(bpy.context)
        self.assertFalse(first.hide_get())
        self.assertFalse(second.hide_get())
        self.assertTrue(third.hide_get())

    def test_row_delete_removes_measurement_proxy_and_registry_entry(self):
        measurement = self._guide("MEASURE Manager Delete", measurement=True)
        set_world_anchor(measurement.guide_props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(measurement.guide_props.end, Vector((2.0, 0.0, 0.0)))
        proxy = ensure_measurement_snap_proxy(measurement, self.scene)
        measurement_name = measurement.name
        proxy_name = proxy.name
        sync_annotation_manager(self.scene)

        self.assertEqual(
            bpy.ops.dimensions.manager_delete(object_name=measurement_name),
            {"FINISHED"},
        )
        self.created.remove(measurement)
        self.assertNotIn(measurement_name, bpy.data.objects)
        self.assertNotIn(proxy_name, bpy.data.objects)
        self.assertNotIn(measurement_name, {item.name for item in self.settings.annotation_manager_items})

    def test_filtered_bulk_named_style_finishes_out_03_assignment(self):
        first = self._dimension("DIM Bulk Styled")
        second = self._dimension("AREA Bulk Unstyled", "AREA")
        sync_annotation_manager(self.scene)
        style = self.settings.annotation_styles.add()
        style.name = "Manager Style"
        self.settings.active_annotation_style_index = len(self.settings.annotation_styles) - 1
        for kind in ("angle", "area", "measurement", "guide"):
            setattr(self.settings, f"annotation_manager_kind_{kind}", False)
        self.settings.annotation_manager_bulk_scope = "FILTERED"

        self.assertEqual(bpy.ops.dimensions.manager_bulk_style(), {"FINISHED"})
        self.assertEqual(first.dimension_props.style_name, "Manager Style")
        self.assertEqual(second.dimension_props.style_name, "")

    def test_every_bulk_operation_is_one_blender_undo_transaction(self):
        from dimensions.operators import annotation_manager as manager_operators

        bulk_classes = (
            manager_operators.DIMENSIONS_OT_ManagerBulkVisibility,
            manager_operators.DIMENSIONS_OT_ManagerBulkDelete,
            manager_operators.DIMENSIONS_OT_ManagerBulkStyle,
            manager_operators.DIMENSIONS_OT_ManagerBulkResetStyle,
        )
        self.assertTrue(all("UNDO" in operator.bl_options for operator in bulk_classes))
        source = Path(manager_operators.__file__).read_text(encoding="utf-8")
        self.assertNotIn("undo_push", source)

    def test_active_manager_index_selects_and_viewport_active_syncs_back(self):
        first = self._dimension("DIM Manager Select A")
        second = self._dimension("DIM Manager Select B")
        sync_annotation_manager(self.scene)
        self.assertEqual(
            bpy.ops.dimensions.manager_select(object_name=first.name),
            {"FINISHED"},
        )
        self.assertEqual(bpy.context.view_layer.objects.active, first)
        self.assertTrue(first.select_get())

        bpy.context.view_layer.objects.active = second
        from dimensions.annotation_manager import set_active_index_from_viewport
        set_active_index_from_viewport(self.settings, second)
        self.assertEqual(
            self.settings.annotation_manager_items[self.settings.active_annotation_manager_index].annotation,
            second,
        )

    def test_500_item_registry_is_reused(self):
        for index in range(500):
            self._dimension(f"DIM Manager Performance {index:03d}")
        start = time.perf_counter()
        sync_annotation_manager(self.scene)
        build_elapsed = time.perf_counter() - start
        before = registry_rebuild_count()
        start = time.perf_counter()
        sync_annotation_manager(self.scene)
        reuse_elapsed = time.perf_counter() - start
        self.assertEqual(registry_rebuild_count(), before)
        self.assertEqual(len(self.settings.annotation_manager_items), 500)
        self.assertLess(reuse_elapsed, build_elapsed + 0.05)


class DimensionsGuidedRepairTests(unittest.TestCase):
    def setUp(self):
        self.scene = bpy.context.scene
        self.created = []

    def tearDown(self):
        for obj in self.created:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        sync_annotation_manager(self.scene)

    def _mesh(self, name, vertices=None, faces=()):
        mesh = bpy.data.meshes.new(f"{name} Mesh")
        mesh.from_pydata(vertices or [(0, 0, 0), (1, 0, 0), (3, 0, 0)], [], faces)
        obj = bpy.data.objects.new(name, mesh)
        self.scene.collection.objects.link(obj)
        self.created.append(obj)
        return obj

    def _dimension(self, name, source, start_index=0):
        annotation = create_dimension_object(bpy.context, name)
        set_anchor(annotation.dimension_props.start, source, start_index)
        set_world_anchor(annotation.dimension_props.end, (5.0, 0.0, 0.0))
        self.created.append(annotation)
        return annotation

    def _remove_anchor_id(self, anchor):
        attribute = anchor.target_object.data.attributes["dimensions_anchor_id"]
        for item in attribute.data:
            if item.value == anchor.vertex_id:
                item.value = 0

    def test_anchor_resolution_distinguishes_id_fallback_duplicate_and_deleted_source(self):
        source = self._mesh("Repair Status Source")
        annotation = self._dimension("DIM Repair Status", source)
        anchor = annotation.dimension_props.start
        clean_world, clean_status = anchor_resolution(anchor)
        clean_value = (resolve_anchor(annotation.dimension_props.end) - clean_world).length
        self.assertEqual(clean_status, "BY_ID")

        self._remove_anchor_id(anchor)
        fallback_world, fallback_status = anchor_resolution(anchor)
        self.assertEqual(fallback_status, "BY_FALLBACK")
        self.assertEqual(tuple(fallback_world), tuple(clean_world))
        self.assertEqual(
            (resolve_anchor(annotation.dimension_props.end) - fallback_world).length,
            clean_value,
        )
        sync_scene_objects(self.scene)
        self.assertEqual(anchor.resolution_status, "BY_FALLBACK")
        self.assertEqual(annotation.dimension_props.measurement_state, "FALLBACK")
        manager_item = next(
            item for item in self.scene.dimensions_settings.annotation_manager_items
            if item.annotation == annotation
        )
        self.assertEqual(manager_item.state, "FALLBACK")

        set_anchor(anchor, source, 0)
        attribute = source.data.attributes["dimensions_anchor_id"]
        attribute.data[1].value = anchor.vertex_id
        duplicate_world, duplicate_status = anchor_resolution(anchor)
        self.assertEqual(duplicate_status, "BY_FALLBACK")
        self.assertEqual(tuple(duplicate_world), tuple(clean_world))

        source_name = source.name
        bpy.data.objects.remove(source, do_unlink=True)
        self.created.remove(source)
        _world, missing_status = anchor_resolution(anchor)
        self.assertEqual(missing_status, "UNRESOLVABLE")
        self.assertEqual(anchor.source_object_name, source_name)

    def test_vertex_suggestion_repairs_only_the_broken_anchor(self):
        source = self._mesh("Repair Candidate Source")
        annotation = self._dimension("DIM Repair Candidate", source)
        original_end = tuple(annotation.dimension_props.end.world_co)
        self._remove_anchor_id(annotation.dimension_props.start)
        issues = repair_issues(annotation)
        self.assertEqual(issues[0]["candidate"]["vertex_index"], 0)

        self.assertEqual(apply_suggested_repairs(annotation), 1)
        self.assertEqual(anchor_resolution(annotation.dimension_props.start)[1], "BY_ID")
        self.assertEqual(tuple(annotation.dimension_props.end.world_co), original_end)

    def test_angle_suggestion_preserves_presentation_and_other_sources(self):
        source = self._mesh("Repair Angle Source")
        annotation = create_dimension_object(bpy.context, "ANGLE Repair")
        self.created.append(annotation)
        props = annotation.dimension_props
        props.annotation_kind = "ANGLE"
        set_anchor(props.start, source, 0)
        set_anchor(props.center, source, 1)
        set_anchor(props.end, source, 2)
        props.presentation_offset = (2.0, 3.0, 4.0)
        start_id, end_id = props.start.vertex_id, props.end.vertex_id
        self._remove_anchor_id(props.center)

        self.assertEqual(apply_suggested_repairs(annotation), 1)
        self.assertEqual(anchor_resolution(props.center)[1], "BY_ID")
        self.assertEqual((props.start.vertex_id, props.end.vertex_id), (start_id, end_id))
        self.assertEqual(tuple(props.presentation_offset), (2.0, 3.0, 4.0))

    def test_area_suggestion_rebinds_face_without_resetting_presentation(self):
        source = self._mesh(
            "Repair Area Source",
            [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
            [(0, 1, 2), (0, 2, 3)],
        )
        annotation = create_dimension_object(bpy.context, "AREA Repair")
        self.created.append(annotation)
        props = annotation.dimension_props
        props.annotation_kind = "AREA"
        result = bind_area_face_indices(props, source, (0,))
        set_world_anchor(props.end, (4.0, 5.0, 0.0))
        props.presentation_offset = (0.5, 0.25, 0.0)
        source.data.attributes["dimensions_area_face_id"].data[0].value = 0
        props.measurement_state = "NEEDS_REPAIR"

        issue = next(item for item in repair_issues(annotation) if item["type"] == "AREA")
        self.assertEqual(issue["candidate"]["face_indices"], (0,))
        self.assertEqual(apply_suggested_repairs(annotation), 1)
        self.assertIsNotNone(evaluate_area_binding(props))
        self.assertEqual(tuple(props.presentation_offset), (0.5, 0.25, 0.0))
        self.assertAlmostEqual(props.area_value, result["area"])

    def test_bulk_repair_matches_cause_and_leaves_other_source_broken(self):
        shared = self._mesh("Repair Shared Source")
        other = self._mesh("Repair Other Source")
        first = self._dimension("DIM Repair Bulk A", shared)
        second = self._dimension("DIM Repair Bulk B", shared)
        untouched = self._dimension("DIM Repair Bulk Other", other)
        self._remove_anchor_id(first.dimension_props.start)
        self._remove_anchor_id(untouched.dimension_props.start)
        sync_annotation_manager(self.scene)

        self.assertEqual(
            bpy.ops.dimensions.repair_bulk_cause(object_name=first.name),
            {"FINISHED"},
        )
        self.assertEqual(anchor_resolution(first.dimension_props.start)[1], "BY_ID")
        self.assertEqual(anchor_resolution(second.dimension_props.start)[1], "BY_ID")
        self.assertEqual(anchor_resolution(untouched.dimension_props.start)[1], "BY_FALLBACK")

    def test_deleted_source_can_be_explicitly_converted_to_world(self):
        source = self._mesh("Repair Deleted Source")
        annotation = self._dimension("DIM Repair Convert", source)
        fallback = tuple(annotation.dimension_props.start.world_co)
        bpy.data.objects.remove(source, do_unlink=True)
        self.created.remove(source)

        self.assertEqual(
            bpy.ops.dimensions.repair_convert_world(
                object_name=annotation.name, anchor_name="START",
            ),
            {"FINISHED"},
        )
        self.assertEqual(annotation.dimension_props.start.anchor_type, "WORLD")
        self.assertEqual(tuple(annotation.dimension_props.start.world_co), fallback)

    def test_repair_mutations_are_single_undo_operators_without_nested_pushes(self):
        from dimensions.operators import repair as repair_operators

        mutation_classes = (
            repair_operators.DIMENSIONS_OT_RepairAcceptSuggestion,
            repair_operators.DIMENSIONS_OT_RepairConvertWorld,
            repair_operators.DIMENSIONS_OT_RepairPickAreaSource,
            repair_operators.DIMENSIONS_OT_RepairBulkCause,
        )
        self.assertTrue(all("UNDO" in operator.bl_options for operator in mutation_classes))
        source = Path(repair_operators.__file__).read_text(encoding="utf-8")
        self.assertNotIn("undo_push", source)

    def test_linked_guard_and_manual_cancel_leave_broken_binding_unchanged(self):
        from dimensions.operators import repair as repair_operators

        source = self._mesh("Repair Read Only Source")
        annotation = self._dimension("DIM Repair Read Only", source)
        self._remove_anchor_id(annotation.dimension_props.start)
        before = annotation.dimension_props.start.vertex_id
        with patch.object(repair_operators, "is_read_only_dimensions_object", return_value=True):
            self.assertEqual(
                bpy.ops.dimensions.repair_accept_suggestion(object_name=annotation.name),
                {"CANCELLED"},
            )
        self.assertEqual(annotation.dimension_props.start.vertex_id, before)
        self.assertEqual(anchor_resolution(annotation.dimension_props.start)[1], "BY_FALLBACK")

        fake_operator = SimpleNamespace(annotation_name=annotation.name)
        fake_context = SimpleNamespace(area=SimpleNamespace(type="VIEW_3D"))
        cancel_event = SimpleNamespace(type="ESC", value="PRESS")
        self.assertEqual(
            repair_operators.DIMENSIONS_OT_RepairPickAreaSource.modal(
                fake_operator, fake_context, cancel_event,
            ),
            {"CANCELLED"},
        )
        self.assertEqual(annotation.dimension_props.start.vertex_id, before)


class DimensionsDirectHandleTests(unittest.TestCase):
    def setUp(self):
        self.scene = bpy.context.scene
        self.created = []

    def tearDown(self):
        for obj in self.created:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)

    def _dimension(self, name="DIM Handle"):
        annotation = create_dimension_object(bpy.context, name)
        set_world_anchor(annotation.dimension_props.start, (0.0, 0.0, 0.0))
        set_world_anchor(annotation.dimension_props.end, (2.0, 0.0, 0.0))
        self.created.append(annotation)
        for selected in bpy.context.selected_objects:
            selected.select_set(False)
        annotation.select_set(True)
        bpy.context.view_layer.objects.active = annotation
        return annotation

    def test_handle_linework_has_constant_pixel_extent_for_every_kind(self):
        for kind in ("LINEAR_OFFSET", "ANGLE_RADIUS", "AREA_LABEL"):
            first = _annotation_handle_segments(kind, Vector((10.0, 20.0)))
            second = _annotation_handle_segments(kind, Vector((410.0, 620.0)))
            first_offsets = [point - Vector((10.0, 20.0)) for point in first]
            second_offsets = [point - Vector((410.0, 620.0)) for point in second]
            for first_offset, second_offset in zip(first_offsets, second_offsets):
                self.assertAlmostEqual(first_offset.x, second_offset.x, places=4)
                self.assertAlmostEqual(first_offset.y, second_offset.y, places=4)
            self.assertLessEqual(max(offset.length for offset in first_offsets), 10.0)

    def test_handles_are_active_selected_only_and_linked_data_is_excluded(self):
        annotation = self._dimension()
        context = bpy.context
        geometry = {"line_mid_screen": Vector((100.0, 100.0))}
        with patch("dimensions.drawing.get_cached_dimension_geometry", return_value=geometry):
            handles = selected_annotation_handles(context)
            self.assertEqual(handles[0]["kind"], "LINEAR_OFFSET")
            annotation.select_set(False)
            self.assertEqual(selected_annotation_handles(context), ())
            annotation.select_set(True)
            with patch("dimensions.drawing.is_read_only_dimensions_object", return_value=True):
                self.assertEqual(selected_annotation_handles(context), ())

    def test_handle_hit_uses_constant_pixel_threshold(self):
        annotation = self._dimension()
        geometry = {"line_mid_screen": Vector((100.0, 100.0))}
        with patch("dimensions.drawing.get_cached_dimension_geometry", return_value=geometry):
            self.assertEqual(
                find_annotation_handle_hit(bpy.context, 106.0, 100.0)["object"],
                annotation,
            )
            self.assertIsNone(find_annotation_handle_hit(bpy.context, 120.0, 100.0))

    def test_click_selection_dispatches_handle_before_annotation_body(self):
        from dimensions.operators import click_select

        annotation = self._dimension()
        dispatched = []
        fake_bpy = SimpleNamespace(ops=SimpleNamespace(dimensions=SimpleNamespace(
            drag_annotation_handle=lambda *args, **kwargs: dispatched.append((args, kwargs)) or {"RUNNING_MODAL"},
        )))
        event = SimpleNamespace(mouse_region_x=10, mouse_region_y=20, shift=False)
        with (
            patch.object(click_select, "find_annotation_handle_hit", return_value={
                "object": annotation, "kind": "LINEAR_OFFSET",
            }),
            patch.object(click_select, "find_dimension_hit", side_effect=AssertionError("body hit must not run")),
            patch.object(click_select, "bpy", fake_bpy),
        ):
            result = click_select.DIMENSIONS_OT_ClickSelect.invoke(SimpleNamespace(), bpy.context, event)
        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(dispatched[0][1]["handle_kind"], "LINEAR_OFFSET")

    def test_cancel_leaves_the_exact_original_value_and_operator_owns_one_undo(self):
        from dimensions.operators import drag_handle

        DIMENSIONS_OT_DragAnnotationHandle = drag_handle.DIMENSIONS_OT_DragAnnotationHandle

        annotation = self._dimension()
        annotation.dimension_props.offset_distance = -1.234567
        original = annotation.dimension_props.offset_distance
        operator = make_operator_harness(
            DIMENSIONS_OT_DragAnnotationHandle,
            annotation_name=annotation.name,
            handle_kind="LINEAR_OFFSET",
            state=HandleManipulationState(),
        )
        context = make_context(scene=self.scene)
        context.view_layer = bpy.context.view_layer
        self.assertEqual(operator.modal(context, make_event("RIGHTMOUSE", "PRESS")), {"CANCELLED"})
        self.assertEqual(annotation.dimension_props.offset_distance, original)
        self.assertIn("UNDO", DIMENSIONS_OT_DragAnnotationHandle.bl_options)
        source = Path(drag_handle.__file__).read_text(encoding="utf-8")
        self.assertNotIn("undo_push", source)

    def test_shared_manipulation_matches_creation_and_sidebar_paths(self):
        from dimensions.operators import create_angle, create_area, drag_handle
        from dimensions.manipulation import apply_area_label_position

        self.assertIs(create_angle.angle_radius_from_world, drag_handle.angle_radius_from_world)
        self.assertIs(create_area.apply_area_label_position, drag_handle.apply_area_label_position)
        self.assertIs(create_area.apply_area_label_position, apply_area_label_position)
        self.assertEqual(angle_radius_from_world((0, 0, 0), (0, 3, 4)), 5.0)

        annotation = self._dimension("DIM Handle Offset")
        annotation.dimension_props.offset_plane_normal = (0.0, 0.0, 1.0)
        value = linear_offset_from_world(annotation.dimension_props, (1.0, 2.5, 0.0))
        self.assertAlmostEqual(abs(value), 2.5)


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
                "CYCLE_SNAP_TARGETS",
                "TOGGLE_INFERENCE_LOCK",
                "FLIP_OFFSET",
                "SAVE_TRANSIENT_MEASURE",
                "COPY_TRANSIENT_MEASURE",
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
            event = SimpleNamespace(
                type=item.type,
                value=item.value,
                shift=item.shift,
                ctrl=item.ctrl,
                alt=item.alt,
            )
            self.assertEqual(
                keymaps.modal_action_from_event(event),
                item.properties.action,
            )


class DimensionsSnapTargetTests(unittest.TestCase):
    def _context(self, enabled=()):
        values = {f"snap_{identifier}": identifier in enabled for identifier in TARGET_IDS}
        settings = SimpleNamespace(use_snap_target_override=True, snap_pixel_radius=28, **values)
        return SimpleNamespace(
            scene=SimpleNamespace(dimensions_settings=settings),
            region=None,
            region_data=None,
        )

    def test_each_target_can_be_enabled_independently(self):
        for identifier in TARGET_IDS:
            with self.subTest(identifier=identifier):
                self.assertEqual(enabled_snap_targets(self._context((identifier,))), {identifier})

    def test_edge_and_midpoint_are_skipped_before_generation(self):
        obj = SimpleNamespace(matrix_world=Matrix.Identity(4))
        context = SimpleNamespace(
            region=None,
            region_data=SimpleNamespace(perspective_matrix=Matrix.Identity(4)),
        )
        with patch(
            "dimensions.snapping.view3d_utils.location_3d_to_region_2d",
            side_effect=lambda _region, _region_data, world: Vector((world.x, world.y)),
        ):
            candidates = []
            _add_edge_snap_candidates(
                context, obj, Vector((0, 0, 0)), Vector((2, 0, 0)),
                Vector((0.5, 0)), candidates, enabled_targets={"midpoint"},
            )
            self.assertEqual([candidate["label"] for candidate in candidates], ["Midpoint"])

            candidates = []
            _add_edge_snap_candidates(
                context, obj, Vector((0, 0, 0)), Vector((2, 0, 0)),
                Vector((0.5, 0)), candidates, enabled_targets={"edge"},
            )
            self.assertEqual([candidate["label"] for candidate in candidates], ["Edge"])

    def test_disabling_all_targets_skips_generators_and_keeps_free_placement(self):
        context = self._context()
        with patch("dimensions.snapping.raycast_from_mouse") as raycast:
            self.assertIsNone(find_nearest_mesh_snap_point(context, 10, 20, enabled_targets=set()))
        raycast.assert_not_called()
        with (
            patch("dimensions.snapping.find_nearest_mesh_snap_point", return_value=None),
            patch("dimensions.snapping.find_nearest_guide_point") as guide_generator,
            patch("dimensions.snapping.project_mouse_to_plane", return_value=Vector((1, 2, 3))),
            patch("dimensions.snapping.view3d_utils.location_3d_to_region_2d", return_value=None),
        ):
            snap = find_nearest_snap_point(context, 10, 20, include_free=True)
        guide_generator.assert_not_called()
        self.assertEqual(snap["type"], "WORLD")
        self.assertEqual(snap["world_co"], Vector((1, 2, 3)))

    def test_measurement_subtargets_are_generated_independently(self):
        context = SimpleNamespace(region=None, region_data=None)
        start = Vector((0, 0, 0))
        end = Vector((100, 0, 0))
        project = lambda _region, _region_data, world: Vector((world.x, world.y))
        with (
            patch("dimensions.snapping.construction_segment_world", return_value=(start, end)),
            patch("dimensions.snapping.view3d_utils.location_3d_to_region_2d", side_effect=project),
            patch("dimensions.snapping._perspective_correct_segment_factor", return_value=0.25),
        ):
            endpoint = _nearest_measurement_segment_snap(
                context, object(), Vector((1, 0)), 10, {"measurement_endpoint"}
            )
            midpoint = _nearest_measurement_segment_snap(
                context, object(), Vector((50, 0)), 10, {"measurement_midpoint"}
            )
            segment = _nearest_measurement_segment_snap(
                context, object(), Vector((25, 0)), 10, {"measurement_segment"}
            )
        self.assertEqual(endpoint["label"], "Measurement Start")
        self.assertEqual(midpoint["label"], "Measurement Midpoint")
        self.assertEqual(segment["label"], "Measurement")


class DimensionsInferenceTests(unittest.TestCase):
    def test_lock_freezes_references_until_explicitly_released(self):
        session = inference.InferenceSession()
        source = SimpleNamespace(type="MESH")
        first = {"label": "First", "object": source, "edge_index": 0, "reference_line": (Vector((0, 0, 0)), Vector((1, 0, 0)))}
        second = {"label": "Second", "object": source, "edge_index": 1, "reference_line": (Vector((0, 0, 0)), Vector((0, 1, 0)))}
        session.observe(first, {"edge"})
        self.assertTrue(session.toggle_lock())
        session.observe(second, {"edge"})
        self.assertEqual(session.reference_label, "First")
        self.assertTrue(session.locked)
        self.assertTrue(session.toggle_lock())
        session.observe(second, {"edge"})
        self.assertEqual(session.reference_label, "Second")
        self.assertFalse(session.locked)

    def test_repeated_axis_cycles_global_local_global(self):
        context = SimpleNamespace()
        with patch("dimensions.inference.enabled_inference_types", return_value={"local_axis"}):
            self.assertEqual(inference.cycle_local_axis("ALIGNED", "X", context), "X")
            self.assertEqual(inference.cycle_local_axis("X", "X", context), "LOCAL_X")
            self.assertEqual(inference.cycle_local_axis("LOCAL_X", "X", context), "X")

    def test_existing_geometry_wins_at_comparable_distance_but_not_when_farther(self):
        base = {"screen_co": Vector((3.0, 0.0))}
        derived = {"screen_co": Vector((1.5, 0.0)), "derived": True, "inference_type": "EXTENSION"}
        self.assertIs(_best_acquisition_candidate((base, derived), Vector((0.0, 0.0))), base)
        derived["screen_co"] = Vector((0.1, 0.0))
        self.assertIs(_best_acquisition_candidate((base, derived), Vector((0.0, 0.0))), derived)

    def test_face_reference_defines_active_plane(self):
        snap = {
            "type": "FACE",
            "world_co": Vector((1, 2, 3)),
            "normal": Vector((0, 0, 2)),
        }
        point, normal = inference.snap_plane(snap)
        self.assertEqual(point, Vector((1, 2, 3)))
        self.assertEqual(normal, Vector((0, 0, 1)))

    def test_degenerate_directions_and_parallel_intersection_are_skipped(self):
        self.assertIsNone(inference._perpendicular_direction(Vector((0, 0, 1)), Vector((0, 0, -1))))
        context = SimpleNamespace(region=object(), region_data=object(), active_object=None)
        references = [
            {"reference_line": (Vector((0, 0, 0)), Vector((1, 0, 0)))},
            {"reference_line": (Vector((0, 1, 0)), Vector((1, 0, 0)))},
        ]
        with (
            patch("dimensions.inference.enabled_inference_types", return_value={"intersection"}),
            patch("dimensions.inference._mouse_ray", return_value=(Vector((0, 0, 5)), Vector((0, 0, -1)))),
            patch("dimensions.inference.view3d_utils.location_3d_to_region_2d", return_value=Vector((0, 0))),
        ):
            self.assertEqual(inference.generate_inference_candidates(context, 0, 0, references), [])

    def test_ux05_target_filtering_happens_when_references_are_observed(self):
        session = inference.InferenceSession()
        edge = {
            "object": SimpleNamespace(type="MESH"),
            "reference_line": (Vector((0, 0, 0)), Vector((1, 0, 0))),
        }
        face = {"world_co": Vector((0, 0, 0)), "normal": Vector((0, 0, 1))}
        session.observe(edge, {"vertex"})
        session.observe(face, {"edge"})
        self.assertEqual(session.references, [])
        session.observe(edge, {"edge"})
        self.assertEqual(session.references, [edge])

    def test_all_six_candidate_types_share_deterministic_generation(self):
        context = SimpleNamespace(
            region=object(),
            region_data=object(),
            active_object=SimpleNamespace(matrix_world=Matrix.Identity(4)),
        )
        references = [
            {"reference_line": (Vector((0, 0, 0)), Vector((1, 0, 0)))},
            {"reference_line": (Vector((0, 0, 0)), Vector((0, 1, 0)))},
            {"world_co": Vector((0, 0, 0)), "normal": Vector((0, 0, 1))},
        ]
        with (
            patch("dimensions.inference.enabled_inference_types", return_value={identifier for identifier, _label in inference.INFERENCE_TYPES}),
            patch("dimensions.inference._mouse_ray", return_value=(Vector((0.25, 0.3, 5)), Vector((0, 0, -1)))),
            patch("dimensions.inference.view3d_utils.location_3d_to_region_2d", side_effect=lambda _r, _rv, point: Vector((point.x, point.y))),
        ):
            candidates = inference.generate_inference_candidates(
                context, 0.25, 0.3, references,
                origin=Vector((0, 0, 0)), axis="LOCAL_X", enabled_targets={"edge", "face_point"},
            )
        self.assertEqual(
            {candidate["inference_type"] for candidate in candidates},
            {"PARALLEL", "PERPENDICULAR", "EXTENSION", "INTERSECTION", "LOCAL_AXIS", "ACTIVE_PLANE"},
        )
        ordered = inference._nearest_candidate(candidates, 0.25, 0.3, 100.0)
        self.assertEqual(ordered["inference_type"], "ACTIVE_PLANE")

    def test_candidate_scoring_cost_is_bounded(self):
        candidates = [
            {"screen_co": Vector((float(index % 100), float(index // 100))), "inference_type": "EXTENSION"}
            for index in range(10000)
        ]
        started = time.perf_counter()
        result = inference._nearest_candidate(candidates, 50.0, 50.0, 200.0)
        self.assertIsNotNone(result)
        self.assertLess(time.perf_counter() - started, 0.1)


class DimensionsCoordinateElevationTests(unittest.TestCase):
    def setUp(self):
        self.datum = create_guide_point_object(bpy.context, "DATUM Test")
        self.datum.guide_props.is_datum = True
        self.datum.guide_props.datum_name = "Test"
        set_world_anchor(self.datum.guide_props.start, Vector((10.0, 20.0, 30.0)))
        self.annotation = create_dimension_object(bpy.context, "DIM Coordinate Test")
        self.annotation.dimension_props.annotation_kind = "COORDINATE"
        self.annotation.dimension_props.datum_object = self.datum
        set_world_anchor(self.annotation.dimension_props.start, Vector((12.0, 23.0, 34.0)))
        set_world_anchor(self.annotation.dimension_props.end, Vector((13.0, 24.0, 34.0)))

    def tearDown(self):
        for obj in (self.annotation, self.datum):
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)

    def test_coordinate_components_at_world_datum(self):
        result = coordinate_values(self.annotation.dimension_props)
        self.assertEqual(result["values"], (2.0, 3.0, 4.0))
        expected_labels = {
            "X": "X 2.0",
            "Y": "Y 3.0",
            "XY": "X 2.0\nY 3.0",
            "XYZ": "X 2.0\nY 3.0\nZ 4.0",
        }
        for components, expected in expected_labels.items():
            self.annotation.dimension_props.coordinate_components = components
            self.assertEqual(
                coordinate_label(
                    self.annotation.dimension_props,
                    result["values"],
                    lambda value: f"{value:.1f}",
                ),
                expected,
            )

    def test_oriented_datum_and_reversed_sign(self):
        self.datum.guide_props.datum_orientation = (0.0, 0.0, 1.5707963267948966)
        result = coordinate_values(self.annotation.dimension_props)
        self.assertAlmostEqual(result["values"][0], 3.0, places=5)
        self.assertAlmostEqual(result["values"][1], -2.0, places=5)
        self.annotation.dimension_props.coordinate_sign = "REVERSED"
        reversed_result = coordinate_values(self.annotation.dimension_props)
        self.assertAlmostEqual(reversed_result["values"][0], -3.0, places=5)

    def test_moving_datum_updates_all_dependents(self):
        self.assertEqual(datum_dependents(bpy.context.scene, self.datum), (self.annotation,))
        before = coordinate_values(self.annotation.dimension_props)["values"]
        set_world_anchor(self.datum.guide_props.start, Vector((11.0, 20.0, 30.0)))
        after = coordinate_values(self.annotation.dimension_props)["values"]
        self.assertNotEqual(before, after)

    def test_elevation_absolute_relative_and_formatting(self):
        self.annotation.dimension_props.annotation_kind = "ELEVATION"
        absolute = elevation_value(self.annotation.dimension_props)
        self.assertAlmostEqual(absolute["value"], 4.0)
        reference = create_dimension_object(bpy.context, "DIM Elevation Reference")
        try:
            reference.dimension_props.annotation_kind = "ELEVATION"
            reference.dimension_props.datum_object = self.datum
            set_world_anchor(reference.dimension_props.start, Vector((10.0, 20.0, 31.5)))
            self.annotation.dimension_props.elevation_mode = "RELATIVE"
            self.annotation.dimension_props.elevation_reference = reference
            relative = elevation_value(self.annotation.dimension_props)
            self.assertAlmostEqual(relative["value"], 2.5)
            self.assertEqual(signed_number(relative["value"], 3, True), "+2.500")
            self.assertEqual(signed_number(-0.25, 2, True), "-0.25")
        finally:
            bpy.data.objects.remove(reference, do_unlink=True)

    def test_elevation_supports_each_world_axis_and_oriented_datum_z(self):
        props = self.annotation.dimension_props
        props.annotation_kind = "ELEVATION"
        for axis, expected in (("WORLD_X", 2.0), ("WORLD_Y", 3.0), ("WORLD_Z", 4.0)):
            props.elevation_axis = axis
            self.assertAlmostEqual(elevation_value(props)["value"], expected)
        self.datum.guide_props.datum_orientation = (0.0, 1.5707963267948966, 0.0)
        props.elevation_axis = "DATUM_Z"
        self.assertAlmostEqual(elevation_value(props)["value"], 2.0, places=5)

    def test_lost_datum_anchor_propagates_truthful_dependent_state(self):
        mesh = bpy.data.meshes.new("Datum Repair Source")
        mesh.from_pydata([(10.0, 20.0, 30.0)], [], [])
        source = bpy.data.objects.new("Datum Repair Source", mesh)
        bpy.context.scene.collection.objects.link(source)
        try:
            set_anchor(self.datum.guide_props.start, source, 0)
            source.data.attributes["dimensions_anchor_id"].data[0].value += 1
            self.assertEqual(coordinate_values(self.annotation.dimension_props)["state"], "FALLBACK")
            self.datum.guide_props.start.target_object = None
            self.assertEqual(coordinate_values(self.annotation.dimension_props)["state"], "NEEDS_REPAIR")
        finally:
            bpy.data.objects.remove(source, do_unlink=True)
            bpy.data.meshes.remove(mesh)

    def test_relative_elevation_keeps_the_least_authoritative_source_state(self):
        self.annotation.dimension_props.annotation_kind = "ELEVATION"
        self.annotation.dimension_props.start.anchor_type = "VERTEX"
        self.annotation.dimension_props.start.source_object_name = "Deleted Primary Source"
        reference = create_dimension_object(bpy.context, "DIM Elevation Fallback Reference")
        mesh = bpy.data.meshes.new("Elevation Fallback Source")
        mesh.from_pydata([(0.0, 0.0, 31.5)], [], [])
        source = bpy.data.objects.new("Elevation Fallback Source", mesh)
        bpy.context.scene.collection.objects.link(source)
        try:
            reference.dimension_props.annotation_kind = "ELEVATION"
            reference.dimension_props.datum_object = self.datum
            set_anchor(reference.dimension_props.start, source, 0)
            source.data.attributes["dimensions_anchor_id"].data[0].value += 1
            self.annotation.dimension_props.elevation_mode = "RELATIVE"
            self.annotation.dimension_props.elevation_reference = reference

            result = elevation_value(self.annotation.dimension_props)

            self.assertEqual(result["state"], "NEEDS_REPAIR")
        finally:
            bpy.data.objects.remove(reference, do_unlink=True)
            bpy.data.objects.remove(source, do_unlink=True)
            bpy.data.meshes.remove(mesh)

    def test_zero_precision_is_preserved_in_the_viewport_elevation_label(self):
        batcher = drawing.SegmentBatcher(shader=None)
        drawing._collect_dimension_geometry(
            bpy.context,
            batcher,
            {
                "annotation_kind": "ELEVATION",
                "leader_start_screen": Vector((0.0, 0.0)),
                "leader_end_screen": Vector((10.0, 0.0)),
                "value": 3.25,
                "elevation_precision": 0,
                "elevation_show_plus": True,
            },
            (1.0, 1.0, 1.0, 1.0),
            3,
        )

        self.assertEqual(batcher._text_items[0][0], "+3")


class DimensionsGuidePlaneTests(unittest.TestCase):
    def setUp(self):
        self.created = []
        self.settings = bpy.context.scene.dimensions_settings
        self.old_active = (
            self.settings.active_plane_mode,
            self.settings.active_plane_object,
            tuple(self.settings.active_plane_origin),
            tuple(self.settings.active_plane_normal),
            tuple(self.settings.active_plane_axis_u),
        )

    def tearDown(self):
        (
            self.settings.active_plane_mode,
            self.settings.active_plane_object,
            self.settings.active_plane_origin,
            self.settings.active_plane_normal,
            self.settings.active_plane_axis_u,
        ) = self.old_active
        for obj in reversed(self.created):
            if obj.name in bpy.data.objects:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data is not None and data.users == 0:
                    bpy.data.meshes.remove(data)

    def _mesh(self, name, vertices, faces=()):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        self.created.append(obj)
        return obj

    def _plane(self, name="PLANE Test"):
        obj = create_guide_plane_object(bpy.context, name)
        self.created.append(obj)
        return obj

    def test_three_point_plane_follows_sources_and_rejects_collinear_definition(self):
        source = self._mesh("Plane Source", [(0, 0, 0), (2, 0, 0), (0, 3, 0)])
        plane = self._plane()
        self.assertTrue(any(
            collection.get("dimensions_collection_role") == "GUIDES"
            for collection in plane.users_collection
        ))
        plane.guide_props.plane_definition = "THREE_POINTS"
        for anchor, index in zip(
            (plane.guide_props.plane_point_a, plane.guide_props.plane_point_b, plane.guide_props.plane_point_c),
            range(3),
        ):
            set_anchor(anchor, source, index)
        frame = resolve_guide_plane(plane)
        self.assertIsNotNone(frame)
        self.assertAlmostEqual(frame[3].dot(Vector((0, 0, 1))), 1.0)
        source.location.z = 4.0
        bpy.context.view_layer.update()
        moved = resolve_guide_plane(plane)
        self.assertAlmostEqual(moved[0].z, 4.0)
        source.data.vertices[2].co = (4.0, 0.0, 0.0)
        self.assertIsNone(resolve_guide_plane(plane))
        self.assertEqual(plane.guide_props.plane_state, "NEEDS_REPAIR")

    def test_point_normal_face_and_offset_definitions(self):
        point_plane = self._plane("PLANE Point Normal")
        point_plane.guide_props.plane_definition = "POINT_NORMAL"
        set_world_anchor(point_plane.guide_props.plane_point_a, Vector((1, 2, 3)))
        point_plane.guide_props.plane_normal = (1, 1, 1)
        base = resolve_guide_plane(point_plane)
        self.assertIsNotNone(base)

        offset = self._plane("PLANE Offset")
        offset.guide_props.plane_definition = "OFFSET"
        bind_guide_source(offset.guide_props.source_a, point_plane)
        offset.guide_props.offset_distance = 2.0
        shifted = resolve_guide_plane(offset)
        self.assertAlmostEqual((shifted[0] - base[0]).dot(base[3]), 2.0, places=6)
        set_world_anchor(point_plane.guide_props.plane_point_a, Vector((4, 5, 6)))
        self.assertAlmostEqual(
            (resolve_guide_plane(offset)[0] - Vector((4, 5, 6))).length,
            2.0,
            places=6,
        )
        self.assertTrue(would_create_plane_cycle(point_plane, offset))
        self.assertFalse(would_create_plane_cycle(offset, point_plane))

        source = self._mesh("Plane Face", [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [(0, 1, 2, 3)])
        face_plane = self._plane("PLANE Face")
        face_plane.guide_props.plane_definition = "FACE"
        self.assertTrue(bind_face_source(face_plane.guide_props.source_a, source, 0))
        self.assertIsNotNone(resolve_guide_plane(face_plane))
        source.location.z = 7.0
        bpy.context.view_layer.update()
        self.assertAlmostEqual(resolve_guide_plane(face_plane)[0].z, 7.0)
        self.created.remove(source)
        bpy.data.objects.remove(source, do_unlink=True)
        self.assertIsNone(resolve_guide_plane(face_plane))
        self.assertEqual(face_plane.guide_props.plane_state, "NEEDS_REPAIR")

    def test_active_plane_axes_projection_extent_and_clear_restore_world_contract(self):
        plane = self._plane()
        plane.guide_props.plane_definition = "POINT_NORMAL"
        set_world_anchor(plane.guide_props.plane_point_a, Vector((0, 0, 2)))
        plane.guide_props.plane_normal = (0, 1, 1)
        frame_before = resolve_guide_plane(plane)
        plane.guide_props.plane_extent = 25.0
        frame_after = resolve_guide_plane(plane)
        self.assertEqual(tuple(frame_before[0]), tuple(frame_after[0]))
        self.assertEqual(tuple(frame_before[3]), tuple(frame_after[3]))

        self.settings.active_plane_object = plane
        self.settings.active_plane_mode = "GUIDE"
        frame = active_plane_frame(bpy.context.scene)
        point = constrain_point_to_plane(Vector((3, 5, 7)), frame)
        self.assertAlmostEqual((point - frame[0]).dot(frame[3]), 0.0, places=6)
        raw = Vector((2, 3, 4))
        for axis, direction in (("X", frame[1]), ("Y", frame[2]), ("Z", frame[3])):
            delta = plane_space_delta(raw, axis, frame)
            self.assertAlmostEqual(delta.cross(direction).length, 0.0, places=6)

        dimension = SimpleNamespace(
            start_snap=_world_snap(0.0, 0.0, 0.0),
            hover_snap=_world_snap(2.0, 3.0, 4.0),
            dimension_type="Y",
            distance_text="2",
            distance_input_valid=True,
            _copy_snap=lambda snap: dict(snap),
        )
        end_snap = CADDIM_OT_CreateDimension._effective_end_snap(dimension, bpy.context)
        dimension_delta = end_snap["world_co"] - dimension.start_snap["world_co"]
        self.assertAlmostEqual(dimension_delta.length, 2.0, places=6)
        self.assertAlmostEqual(dimension_delta.cross(frame[2]).length, 0.0, places=6)
        self.assertAlmostEqual(inference.axis_direction(bpy.context, "Y").cross(frame[2]).length, 0.0, places=6)

        area_world = _constrained_label_world(
            frame[0], frame[3], frame[0] + frame[1] * -3.0,
            "X", 1.5, bpy.context,
        )
        self.assertAlmostEqual((area_world - frame[0]).length, 1.5, places=6)
        self.assertLess((area_world - frame[0]).dot(frame[1]), 0.0)
        self.settings.active_plane_mode = "NONE"
        self.settings.active_plane_object = None
        self.assertIsNone(active_plane_frame(bpy.context.scene))
        self.assertEqual(constrained_delta(raw, "Y", bpy.context), Vector((0, 3, 0)))

        self.settings.active_plane_origin = (4, 5, 6)
        self.settings.active_plane_normal = (1, 0, 0)
        self.settings.active_plane_axis_u = (0, 1, 0)
        self.settings.active_plane_mode = "VIEW"
        view_frame = active_plane_frame(bpy.context.scene)
        self.assertEqual(tuple(view_frame[0]), (4.0, 5.0, 6.0))
        self.assertEqual(tuple(view_frame[3]), (1.0, 0.0, 0.0))
        self.settings.active_plane_mode = "WORLD_XY"
        world_frame = active_plane_frame(bpy.context.scene)
        self.assertEqual(tuple(world_frame[3]), (0.0, 0.0, 1.0))

    def test_surface_snap_extent_matches_the_displayed_square_grid(self):
        frame = plane_frame((1, 2, 3), (1, 1, 1), (1, -1, 0))
        self.assertIsNotNone(frame)
        origin, axis_u, axis_v, _normal = frame
        self.assertTrue(point_within_plane_extent(origin + axis_u * 2 + axis_v * 2, frame, 2))
        self.assertFalse(point_within_plane_extent(origin + axis_u * 2.01, frame, 2))
        self.assertFalse(point_within_plane_extent(origin + axis_v * -2.01, frame, 2))


class DimensionsAngularSpacingTests(unittest.TestCase):
    def test_angle_parsing_degrees_radians_and_invalid(self):
        self.assertAlmostEqual(parse_angle_input(bpy.context, "90 deg"), 1.5707963267948966)
        self.assertAlmostEqual(parse_angle_input(bpy.context, "1.25 rad"), 1.25)
        previous = bpy.context.scene.unit_settings.system_rotation
        try:
            bpy.context.scene.unit_settings.system_rotation = "RADIANS"
            self.assertAlmostEqual(parse_angle_input(bpy.context, "0.75"), 0.75)
        finally:
            bpy.context.scene.unit_settings.system_rotation = previous
        with self.assertRaises(ValueError):
            parse_angle_input(bpy.context, "roof")

    def test_angular_lines_cover_cardinal_and_negative_angles(self):
        source = {"kind": "LINE", "origin": Vector(), "direction": Vector((1, 0, 0))}
        for angle, expected in ((0.0, (1, 0)), (1.5707963267948966, (0, 1)), (3.141592653589793, (-1, 0)), (-1.5707963267948966, (0, -1))):
            line = angular_preview_line(source, Vector(), angle, Vector((0, 0, 1)))
            self.assertAlmostEqual(line[1].x, expected[0], places=5)
            self.assertAlmostEqual(line[1].y, expected[1], places=5)

    def test_spacing_modes_and_edit_update_all_lines(self):
        source = create_guide_object(bpy.context, "GUIDE Spacing Source Test")
        spaced = create_guide_object(bpy.context, "GUIDE Spacing Test")
        try:
            set_world_anchor(source.guide_props.start, Vector((0, 0, 0)))
            set_world_anchor(source.guide_props.end, Vector((1, 0, 0)))
            props = spaced.guide_props
            props.derived = True
            props.derivation_mode = "SPACING"
            bind_guide_source(props.source_a, source)
            set_world_anchor(props.construction_pivot, Vector((0, 0, 0)))
            props.derived_direction = (0, 1, 0)
            props.spacing_interval, props.spacing_count = 2.0, 4
            self.assertEqual(spacing_definition(props), (2.0, 4))
            self.assertEqual([round(line[0].y, 5) for line in spaced_guide_lines(spaced)], [0, 2, 4, 6])
            props.spacing_interval = 1.0
            self.assertEqual([round(line[0].y, 5) for line in spaced_guide_lines(spaced)], [0, 1, 2, 3])
            props.spacing_mode, props.spacing_extent = "EXTENT", 2.5
            self.assertEqual(spacing_definition(props), (1.0, 3))
            props.spacing_mode, props.spacing_count, props.spacing_extent = "DISTRIBUTE", 3, 10.0
            self.assertEqual(spacing_definition(props), (5.0, 3))
            set_world_anchor(props.spacing_end, Vector((3, 8, 0)))
            distributed = spaced_guide_lines(spaced)
            self.assertEqual([round(line[0].y, 5) for line in distributed], [0, 4, 8])
            self.assertEqual(props.spacing_extent, 10.0)
            props.spacing_mode, props.spacing_count, props.spacing_interval = "COUNT", 200, 0.4
            started = time.perf_counter()
            lines = spaced_guide_lines(spaced)
            self.assertEqual(len(lines), 200)
            self.assertLess(time.perf_counter() - started, 0.05)
            context = SimpleNamespace(region=object(), region_data=object())
            with patch("dimensions.snapping.view3d_utils.location_3d_to_region_2d", side_effect=lambda _region, _data, point: Vector((point.x, point.y))):
                candidates = [
                    _guide_line_snap_candidate(
                        context, Vector((0, index)), Vector((0, index, 5)), Vector((0, 0, -1)),
                        spaced, line, f"Guide {index + 1}",
                    )
                    for index, line in enumerate(lines)
                ]
            self.assertEqual(len(candidates), 200)
            self.assertTrue(all(candidate is not None for candidate in candidates))
        finally:
            bpy.data.objects.remove(spaced, do_unlink=True)
            bpy.data.objects.remove(source, do_unlink=True)

    def test_spacing_lost_origin_is_needs_repair(self):
        mesh = bpy.data.meshes.new("Spacing Origin Source")
        mesh.from_pydata([(0, 0, 0)], [], [])
        origin_source = bpy.data.objects.new("Spacing Origin Source", mesh)
        bpy.context.scene.collection.objects.link(origin_source)
        source = create_guide_object(bpy.context, "GUIDE Spacing Direction")
        spaced = create_guide_object(bpy.context, "GUIDE Spacing Lost Origin")
        try:
            set_world_anchor(source.guide_props.start, Vector((0, 0, 0)))
            set_world_anchor(source.guide_props.end, Vector((1, 0, 0)))
            props = spaced.guide_props
            props.derived = True
            props.derivation_mode = "SPACING"
            bind_guide_source(props.source_a, source)
            set_anchor(props.construction_pivot, origin_source, 0)
            props.derived_direction = (0, 1, 0)
            self.assertEqual(len(spaced_guide_lines(spaced)), props.spacing_count)

            bpy.data.objects.remove(origin_source, do_unlink=True)

            self.assertEqual(spaced_guide_lines(spaced), ())
            self.assertEqual(props.derived_state, "NEEDS_REPAIR")
        finally:
            for name in (
                "GUIDE Spacing Lost Origin",
                "GUIDE Spacing Direction",
                "Spacing Origin Source",
            ):
                obj = bpy.data.objects.get(name)
                if obj is not None:
                    bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.name in bpy.data.meshes:
                bpy.data.meshes.remove(mesh)


class DimensionsTransientMeasurementTests(unittest.TestCase):
    def test_components_preserve_sign_and_total(self):
        values = measurement_components(Vector((1, 5, 2)), Vector((4, 1, 14)))
        self.assertEqual(values["x"], 3.0)
        self.assertEqual(values["y"], -4.0)
        self.assertEqual(values["z"], 12.0)
        self.assertAlmostEqual(values["total"], 13.0)

    def test_component_formatting_honors_scene_unit_scale(self):
        scene = bpy.context.scene
        unit_settings = scene.unit_settings
        settings = scene.dimensions_settings
        original = (
            unit_settings.system,
            unit_settings.length_unit,
            unit_settings.scale_length,
            settings.metric_unit_style,
        )
        try:
            unit_settings.system = "METRIC"
            unit_settings.length_unit = "MILLIMETERS"
            unit_settings.scale_length = 0.1
            settings.metric_unit_style = "MILLIMETERS"
            result = format_measurement_query(
                bpy.context,
                Vector((1, 5, 2)),
                Vector((4, 1, 14)),
                1,
            )
            self.assertEqual(result["formatted"]["total"], "1300.0 mm")
            self.assertEqual(result["formatted"]["x"], "300.0 mm")
            self.assertEqual(result["formatted"]["y"], "-400.0 mm")
            self.assertEqual(result["formatted"]["z"], "1200.0 mm")
        finally:
            unit_settings.system, unit_settings.length_unit, unit_settings.scale_length, settings.metric_unit_style = original


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
                DimensionsNamedStyleTests,
                DimensionsAnnotationManagerTests,
                DimensionsGuidedRepairTests,
                DimensionsDirectHandleTests,
                DimensionsKeymapTests,
                DimensionsSnapTargetTests,
                DimensionsInferenceTests,
                DimensionsCoordinateElevationTests,
                DimensionsAngularSpacingTests,
                DimensionsGuidePlaneTests,
                DimensionsTransientMeasurementTests,
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
