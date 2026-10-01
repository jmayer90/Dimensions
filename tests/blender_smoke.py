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
)
from dimensions.anchors import anchor_resolution, resolve_anchor, set_anchor, set_anchor_from_snap, set_world_anchor
from dimensions.constants import CURRENT_SCHEMA_VERSION
from dimensions.area_binding import bind_area_face_indices, evaluate_area_binding
from dimensions.annotation_manager import (
    annotation_references_object,
    filtered_manager_objects,
    manager_item_matches,
    registry_rebuild_count,
    sync_annotation_manager,
)
from dimensions.angle_binding import derive_angle_from_world_edges, resolve_angle_source
from dimensions.dimension_geometry import get_angle_world_geometry
from dimensions.output_geometry import WorldSizingPolicy, area_dimension_output_spec
from dimensions.transform_policy import annotation_world_location, enforce_annotation_transform_policy, has_ignored_rotation_or_scale
from dimensions.construction import (
    GUIDE_PLANE_FLAG,
    MAX_GRID_CELLS_PER_SIDE,
    grid_coordinates,
    guide_plane_frame,
    guide_point_world,
    plane_frame,
    plane_frame_from_face,
    plane_frame_from_points,
    point_within_plane_extent,
    set_guide_line_transform,
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
    update_distance_text,
)
from dimensions.migrations import migrate_scene
from dimensions.modal_state import HandleManipulationState, PointPlacementState
from dimensions.operators.create_dimension import CADDIM_OT_CreateDimension
from dimensions.operators.create_area import _constrained_label_world
from dimensions.operators.selection_annotations import DIMENSIONS_OT_CaptureArea
from dimensions.operators.construction_tools import DIMENSIONS_OT_CreateGuide, selection_centroid
from dimensions.operators.measure import CADDIM_OT_Measure
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
from dimensions.repair import (
    apply_suggested_repairs,
    repair_issues,
    rebind_area_preserving_presentation,
    suggest_area_candidate,
    suggest_vertex_candidate,
)
from dimensions.manipulation import angle_radius_from_world, linear_offset_from_world
from dimensions.snapping import (
    _add_edge_snap_candidates,
    _best_snap_candidate,
    _best_acquisition_candidate,
    _configured_snap_pixel_threshold,
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
    scene_mesh_hits,
    find_nearest_snap_point,
    find_nearest_guide_point,
    find_nearest_mesh_snap_point,
)
from dimensions.snap_targets import TARGET_IDS, enabled_snap_targets
from dimensions.preferences import (
    DEFAULT_PREFERENCES,
    remember_preferences_for_reregister,
    restore_preferences_after_reregister,
)
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

            guide = make_operator_harness(
                DIMENSIONS_OT_CreateGuide,
                picked=[_world_snap(2.0, 2.0, 2.0)],
                hover_snap=_world_snap(5.0, 6.0, 2.0),
                axis="X",
                distance_text="2",
                distance_input_valid=True,
            )
            end_snap = guide._effective_snap(bpy.context)
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

    def test_anchor_attribute_collisions_bind_and_resolve_through_fallback(self):
        guide = create_guide_object(bpy.context, "DimensionsAnchorCollisionSmoke")
        self.addCleanup(bpy.data.objects.remove, guide, do_unlink=True)
        target = self._make_object(
            "DimensionsAnchorCollisionTargetSmoke",
            [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
            edges=[(0, 1)],
        )
        anchor = guide.guide_props.start
        set_anchor(anchor, target, 0)
        attribute = target.data.attributes["dimensions_anchor_id"]
        target.data.attributes.remove(attribute)

        for data_type, domain in (("FLOAT", "POINT"), ("INT", "EDGE")):
            with self.subTest(data_type=data_type, domain=domain):
                collision = target.data.attributes.new("dimensions_anchor_id", data_type, domain)
                set_anchor(anchor, target, 1)
                world, status = anchor_resolution(anchor)
                self.assertEqual(anchor.vertex_id, 0)
                self.assertEqual(anchor.resolution_status, "BY_FALLBACK")
                self.assertEqual(world, Vector((4.0, 5.0, 6.0)))
                self.assertEqual(status, "BY_FALLBACK")
                target.data.attributes.remove(collision)

    def test_edit_mode_anchor_accepts_vertex_created_in_live_bmesh(self):
        guide = create_guide_object(bpy.context, "DimensionsNewEditVertexAnchorSmoke")
        self.addCleanup(bpy.data.objects.remove, guide, do_unlink=True)
        target, mesh = self._make_edit_object(
            "DimensionsNewEditVertexTargetSmoke",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            faces=[(0, 1, 2)],
        )
        try:
            bm = bmesh.from_edit_mesh(mesh)
            new_vertex = bm.verts.new((2.0, 3.0, 0.0))
            bm.verts.index_update()
            bm.verts.ensure_lookup_table()
            self.assertEqual(len(mesh.vertices), 3)
            self.assertEqual(new_vertex.index, 3)
            new_vertex_index = new_vertex.index
            new_vertex_co = new_vertex.co.copy()

            anchor = guide.guide_props.start
            set_anchor(anchor, target, new_vertex_index)

            self.assertEqual(anchor.vertex_index, new_vertex_index)
            self.assertGreater(anchor.vertex_id, 0)
            self.assertEqual(Vector(anchor.fallback_local_co), new_vertex_co)
            self.assertEqual(resolve_anchor(anchor), new_vertex_co)
        finally:
            self._remove_edit_object(target, mesh)

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
            operator = SimpleNamespace(report=lambda *_args: None, chain=False)
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
            with patch(
                "dimensions.operators.selection_annotations.is_read_only_dimensions_object",
                return_value=True,
            ):
                self.assertFalse(DIMENSIONS_OT_CaptureArea.poll(bpy.context))
                capture = make_operator_harness(DIMENSIONS_OT_CaptureArea)
                self.assertEqual(capture.execute(bpy.context), {"CANCELLED"})
            self.assertEqual(props.measurement_state, "LIVE")
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

    def test_guide_point_has_one_vertex_native_proxy_and_constant_pixel_marker(self):
        point = create_guide_point_object(bpy.context, "DimensionsGuidePointProxy", location=Vector((1.0, 2.0, 3.0)))
        self.addCleanup(bpy.data.objects.remove, point, do_unlink=True)
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
        point = create_guide_point_object(bpy.context, "DimensionsGuidePointSnap", location=Vector((10.0, 20.0, 0.0)))
        self.addCleanup(bpy.data.objects.remove, point, do_unlink=True)
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

    def test_snap_ranking_balances_proximity_with_logical_target_bias(self):
        mouse = Vector((0.0, 0.0))
        face = {"priority": 10, "screen_co": mouse.copy()}
        vertex = {"priority": 0, "screen_co": Vector((27.0, 0.0))}
        edge = {"priority": 2, "screen_co": mouse.copy()}
        self.assertIs(_best_snap_candidate([face, vertex], mouse, 28.0), face)
        self.assertIs(_best_snap_candidate([edge, vertex], mouse, 28.0), edge)
        vertex["screen_co"] = Vector((3.0, 0.0))
        self.assertIs(_best_snap_candidate([edge, vertex], mouse, 28.0), vertex)

    def test_snap_radius_uses_preferences_until_the_scene_override_is_enabled(self):
        settings = SimpleNamespace(use_snap_target_override=False, snap_pixel_radius=9)
        context = SimpleNamespace(scene=SimpleNamespace(dimensions_settings=settings))
        preferences = SimpleNamespace(snap_pixel_threshold=64)
        with patch("dimensions.snapping.get_preferences", return_value=preferences):
            self.assertEqual(_configured_snap_pixel_threshold(context, None), 64.0)
            settings.use_snap_target_override = True
            self.assertEqual(_configured_snap_pixel_threshold(context, None), 9.0)

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

    @staticmethod
    def _as_pre_v4_annotation(props):
        """Make an annotation look like one saved before schema v4 introduced style overrides."""
        props.schema_version = 0
        raw = props.id_data.bl_system_properties_get()["dimension_props"]
        for key in [key for key in raw.keys() if key.startswith("override_")]:
            del raw[key]

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
            self._as_pre_v4_annotation(props)
            self.settings.schema_version = 3
            self.assertTrue(migrate_scene(bpy.context.scene))
            self.assertTrue(props.override_unit_style)
            self.assertEqual(props.unit_style, "MILLIMETERS")

            unit_settings.system = "IMPERIAL"
            self.settings.imperial_unit_style = "INCH_FRACTION"
            self.assertEqual(configured_scene_unit_style(self.settings), "INCH_FRACTION")
            props.override_unit_style = False
            self.assertEqual(resolve_dimension_style(self.settings, props).unit_style, "INCH_FRACTION")
            self._as_pre_v4_annotation(props)
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
        item = next(item for item in self.settings.annotation_manager_items if item.annotation == area)
        area.dimension_props.measurement_state = "LIVE"
        self.assertEqual(item.state, "NEEDS_REPAIR")
        self.assertTrue(manager_item_matches(self.settings, item))
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

    def test_isolate_restores_property_visibility_when_collection_is_excluded(self):
        dimension = self._dimension("DIM Isolate Excluded")
        dimension.dimension_props.visible = False
        sync_annotation_manager(self.scene)
        layer_collection = bpy.context.view_layer.layer_collection.children.get("Dimensions")
        self.assertIsNotNone(layer_collection)
        isolate_annotations(bpy.context, (dimension,))
        self.assertTrue(dimension.dimension_props.visible)
        try:
            layer_collection.exclude = True
            excluded_context = SimpleNamespace(
                scene=self.scene,
                view_layer=SimpleNamespace(objects={}),
            )
            restore_annotation_visibility(excluded_context)
            self.assertFalse(dimension.dimension_props.visible)
            self.assertFalse(self.settings.annotation_manager_isolate_active)
        finally:
            layer_collection.exclude = False

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
        sync_scene_objects(self.scene)
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

    def test_live_edit_repair_candidates_update_new_bmesh_indices(self):
        source = self._mesh(
            "Repair Live BMesh Source",
            vertices=[(0, 0, 0), (2, 0, 0), (0, 2, 0)],
            faces=[(0, 1, 2)],
        )
        annotation = self._dimension("DIM Repair Live BMesh", source)
        anchor = annotation.dimension_props.start
        self._remove_anchor_id(anchor)
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = source
        source.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            bm = bmesh.from_edit_mesh(source.data)
            first, second = bm.verts[0], bm.verts[1]
            first.co = (10, 0, 0)
            new_vertex = bm.verts.new((0, 1, 0))
            new_face = bm.faces.new((first, second, new_vertex))
            bm.normal_update()

            vertex_candidate = suggest_vertex_candidate(anchor)
            self.assertGreaterEqual(vertex_candidate["vertex_index"], 0)
            self.assertEqual(vertex_candidate["vertex_index"], new_vertex.index)
            set_anchor(anchor, source, vertex_candidate["vertex_index"])
            self.assertEqual(anchor_resolution(anchor)[1], "BY_ID")

            props = annotation.dimension_props
            props.annotation_kind = "AREA"
            props.area_source_object = source
            binding = props.area_faces.add()
            binding.vertex_count = 3
            binding.fallback_center = tuple(new_face.calc_center_median())
            binding.fallback_normal = tuple(new_face.normal)
            binding.fallback_area = new_face.calc_area()
            area_candidate = suggest_area_candidate(props)
            self.assertTrue(area_candidate["face_indices"])
            self.assertTrue(all(index >= 0 for index in area_candidate["face_indices"]))
            self.assertEqual(area_candidate["face_indices"], (new_face.index,))
            self.assertTrue(rebind_area_preserving_presentation(
                props, source, area_candidate["face_indices"],
            ))
            self.assertEqual(props.area_faces[0].vertex_count, 3)
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")

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
                "SAVE_TRANSIENT_MEASURE",
                "COPY_TRANSIENT_MEASURE",
            },
        )

    def test_every_modal_action_has_a_readable_preferences_label(self):
        # The carrier operator's own label would name every row "Dimensions Modal Action".
        for _keymap, item in keymaps._modal_keymap_items:
            self.assertIn(item.properties.action, keymaps._ACTION_LABELS)

    def test_every_bound_action_is_read_by_a_tool(self):
        # A binding nothing reads shows in Preferences but does nothing when rebound.
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPOSITORY_ROOT / "dimensions").rglob("*.py")
            if path.name != "keymaps.py"
        )
        for _keymap, item in keymaps._modal_keymap_items:
            self.assertIn(f'"{item.properties.action}"', sources, item.properties.action)

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

    def test_existing_geometry_owns_the_snap_radius_unless_inference_is_locked(self):
        base = {"screen_co": Vector((27.0, 0.0))}
        derived = {"screen_co": Vector((1.5, 0.0)), "derived": True, "inference_type": "EXTENSION"}
        self.assertIs(_best_acquisition_candidate((base, derived), Vector((0.0, 0.0))), base)
        derived["inference_locked"] = True
        self.assertIs(_best_acquisition_candidate((base, derived), Vector((0.0, 0.0))), derived)

    def test_face_reference_defines_face_plane(self):
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
            {"PARALLEL", "PERPENDICULAR", "EXTENSION", "INTERSECTION", "LOCAL_AXIS", "FACE_PLANE"},
        )
        ordered = inference._nearest_candidate(candidates, 0.25, 0.3, 100.0)
        self.assertEqual(ordered["inference_type"], "FACE_PLANE")

    def test_candidate_scoring_cost_is_bounded(self):
        candidates = [
            {"screen_co": Vector((float(index % 100), float(index // 100))), "inference_type": "EXTENSION"}
            for index in range(10000)
        ]
        started = time.perf_counter()
        result = inference._nearest_candidate(candidates, 50.0, 50.0, 200.0)
        self.assertIsNotNone(result)
        self.assertLess(time.perf_counter() - started, 0.1)


class DimensionsConstructionTests(unittest.TestCase):
    """Guide lines, points, and grid planes are ordinary movable objects."""

    def setUp(self):
        self.before_objects = set(bpy.data.objects)
        self.before_meshes = set(bpy.data.meshes)

    def tearDown(self):
        for obj in list(bpy.data.objects):
            if obj not in self.before_objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in list(bpy.data.meshes):
            if mesh not in self.before_meshes and mesh.users == 0:
                bpy.data.meshes.remove(mesh)

    def _plane(self, origin=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0), extent=1.0, spacing=0.5):
        frame = plane_frame(origin, normal, (1.0, 0.0, 0.0))
        return create_guide_plane_object(bpy.context, frame, extent, spacing, "PLANE Test Grid")

    def _cube(self, location):
        mesh = bpy.data.meshes.new("Construction Cube")
        mesh.from_pydata(
            [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)],
            [],
            [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
        )
        obj = bpy.data.objects.new("Construction Cube", mesh)
        obj.location = location
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.update()
        return obj

    def test_grid_lines_sit_on_spacing_multiples_from_the_center_plus_the_border(self):
        self.assertEqual(grid_coordinates(1.0, 0.5), [-1.0, -0.5, 0.0, 0.5, 1.0])
        self.assertEqual(grid_coordinates(1.2, 0.5), [-1.2, -1.0, -0.5, 0.0, 0.5, 1.0, 1.2])
        coarse = grid_coordinates(100.0, 0.001)
        self.assertLessEqual(len(coarse), MAX_GRID_CELLS_PER_SIDE + 3)
        self.assertEqual((coarse[0], coarse[-1]), (-100.0, 100.0))

    def test_plane_frames_from_points_and_face_are_coplanar(self):
        origin, axis_u, _axis_v, normal = plane_frame_from_points(
            [Vector((1, 1, 2)), Vector((4, 1, 2)), Vector((1, 5, 2))],
        )
        self.assertEqual(origin, Vector((1, 1, 2)))
        self.assertLess((axis_u - Vector((1, 0, 0))).length, 1e-6)
        self.assertAlmostEqual(abs(normal.z), 1.0)
        self.assertIsNone(plane_frame_from_points([Vector(), Vector((1, 0, 0)), Vector((2, 0, 0))]))
        face = [Vector((2, 0, 0)), Vector((2, 4, 0)), Vector((2, 4, 1)), Vector((2, 0, 1))]
        center, face_u, _face_v, face_normal = plane_frame_from_face(face, Vector((1, 0, 0)))
        self.assertEqual(center, Vector((2, 2, 0.5)))
        self.assertLess((face_u - Vector((0, 1, 0))).length, 1e-6)
        self.assertLess((face_normal - Vector((1, 0, 0))).length, 1e-6)

    def test_guide_plane_is_a_selectable_wire_grid_excluded_from_render(self):
        plane = self._plane(extent=1.0, spacing=0.5)
        self.assertEqual(plane.type, "MESH")
        self.assertTrue(plane.get(GUIDE_PLANE_FLAG))
        self.assertEqual(plane.display_type, "WIRE")
        self.assertTrue(plane.hide_render)
        self.assertFalse(plane.hide_select)
        self.assertEqual(len(plane.data.vertices), 25)
        self.assertEqual(len(plane.data.polygons), 16)
        self.assertTrue(any(
            collection.get("dimensions_collection_role") == "GUIDES" for collection in plane.users_collection
        ))

    def test_changing_size_or_spacing_rebuilds_the_grid(self):
        plane = self._plane(extent=1.0, spacing=0.5)
        plane.guide_props.plane_spacing = 0.25
        self.assertEqual(len(plane.data.vertices), 81)
        plane.guide_props.plane_extent = 0.5
        self.assertEqual(len(plane.data.vertices), 25)

    def test_moving_and_rotating_a_plane_moves_its_frame(self):
        plane = self._plane()
        plane.location = (0.0, 0.0, 3.0)
        plane.rotation_euler = (1.5707963267948966, 0.0, 0.0)
        bpy.context.view_layer.update()
        sync_scene_objects(bpy.context.scene)
        origin, _axis_u, _axis_v, normal = guide_plane_frame(plane)
        self.assertLess((origin - Vector((0, 0, 3))).length, 1e-6)
        self.assertLess((normal - Vector((0, -1, 0))).length, 1e-6)
        self.assertAlmostEqual(plane.location.z, 3.0)

    def test_ray_hits_a_grid_and_looks_through_it_when_grids_are_not_snappable(self):
        # Away from the factory-startup cube at the origin.
        self._cube((20.0, 0.0, -3.0))
        self._plane(origin=(20.0, 0.0, 0.0), extent=2.0)
        bpy.context.view_layer.update()
        origin, direction = Vector((20.2, 0.3, 10.0)), Vector((0.0, 0.0, -1.0))
        with_grid = scene_mesh_hits(bpy.context, origin, direction, include_guide_planes=True)
        self.assertTrue(with_grid[0]["guide_plane"])
        self.assertAlmostEqual(with_grid[0]["location"].z, 0.0, places=5)
        without_grid = scene_mesh_hits(bpy.context, origin, direction, include_guide_planes=False)
        self.assertFalse(without_grid[0]["guide_plane"])
        self.assertAlmostEqual(without_grid[0]["location"].z, -2.0, places=5)

    def test_a_grid_on_a_model_face_keeps_the_face_snappable(self):
        self._cube((20.0, 0.0, 0.0))
        self._plane(origin=(20.0, 0.0, 1.0), extent=2.0)
        bpy.context.view_layer.update()
        hits = scene_mesh_hits(bpy.context, Vector((20.2, 0.3, 10.0)), Vector((0.0, 0.0, -1.0)))
        self.assertEqual({hit["guide_plane"] for hit in hits}, {True, False})

    def test_grid_snaps_follow_the_plane_and_survive_a_grid_rebuild(self):
        plane = self._plane(extent=1.0, spacing=0.5)
        bpy.context.view_layer.update()
        dimension = create_dimension_object(bpy.context, "DIM Grid Anchor")
        snap = _vertex_snap(plane, 0.5, 0.5, 0.0)
        snap["vertex_index"] = 18
        set_anchor_from_snap(dimension.dimension_props.start, snap)
        self.assertEqual(dimension.dimension_props.start.anchor_type, "OBJECT_POINT")
        plane.location.z = 2.0
        bpy.context.view_layer.update()
        self.assertEqual(resolve_anchor(dimension.dimension_props.start), Vector((0.5, 0.5, 2.0)))
        plane.guide_props.plane_spacing = 0.25
        self.assertEqual(resolve_anchor(dimension.dimension_props.start), Vector((0.5, 0.5, 2.0)))
        self.assertIsNone(plane.data.attributes.get("dimensions_anchor_id"))

    def test_grid_candidates_are_named_for_the_grid(self):
        plane = self._plane()
        candidate = {"object": plane, "label": "Vertex"}
        from dimensions.snapping import _label_grid_candidate

        self.assertEqual(_label_grid_candidate(candidate)["label"], "Grid Point")
        self.assertTrue(candidate["guide_plane"])
        self.assertEqual(_label_grid_candidate({"object": None, "label": "Vertex"})["label"], "Vertex")

    def test_guide_line_follows_its_object_transform(self):
        guide = create_guide_object(bpy.context, "GUIDE Transform")
        set_guide_line_transform(guide, Vector((1.0, 2.0, 3.0)), Vector((0.0, 0.0, 2.0)))
        origin, direction = guide_line_world(guide)
        self.assertEqual(origin, Vector((1.0, 2.0, 3.0)))
        self.assertLess((direction - Vector((0.0, 0.0, 1.0))).length, 1e-6)
        guide.location = (0.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        sync_scene_objects(bpy.context.scene)
        self.assertEqual(guide_line_world(guide)[0], Vector((0.0, 0.0, 0.0)))

    def test_moving_a_world_measurement_moves_both_ends(self):
        measurement = create_measurement_object(bpy.context, "MEASURE Move")
        set_world_anchor(measurement.guide_props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(measurement.guide_props.end, Vector((2.0, 0.0, 0.0)))
        measurement.location = (1.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        sync_scene_objects(bpy.context.scene)
        measurement.location = (1.0, 5.0, 0.0)
        bpy.context.view_layer.update()
        sync_scene_objects(bpy.context.scene)
        self.assertEqual(construction_segment_world(measurement), (Vector((0.0, 5.0, 0.0)), Vector((2.0, 5.0, 0.0))))

    def test_guide_point_is_its_object_origin(self):
        point = create_guide_point_object(bpy.context, "POINT Origin", location=Vector((1.0, 1.0, 1.0)))
        self.assertEqual(guide_point_world(point), Vector((1.0, 1.0, 1.0)))
        point.location = (4.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        sync_scene_objects(bpy.context.scene)
        self.assertEqual(guide_point_world(point), Vector((4.0, 0.0, 0.0)))
        self.assertTrue(point_within_plane_extent(Vector((0.5, 0.5, 0.0)), plane_frame((0, 0, 0), (0, 0, 1)), 1.0))


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

    def test_saving_transient_measurement_pushes_its_own_undo_step(self):
        operator = make_operator_harness(
            CADDIM_OT_Measure,
            start_world=None,
            end_world=None,
            completed_start_world=Vector((0.0, 0.0, 0.0)),
            completed_end_world=Vector((2.0, 0.0, 0.0)),
        )
        before = set(bpy.data.objects)
        with patch("dimensions.operators.measure.push_undo_step") as push_undo:
            self.assertEqual(operator._save_transient(bpy.context), {"RUNNING_MODAL"})
        created = set(bpy.data.objects) - before
        self.assertEqual(len(created), 2)  # Measurement Empty plus its native snap proxy.
        push_undo.assert_called_once_with("Save Measurement")
        for obj in sorted(created, key=lambda item: bool(item.parent)):
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)


class DimensionsPackagingTests(unittest.TestCase):
    """Guard the differences between running from the repository and from an install.

    The suite imports the add-on as a top-level ``dimensions`` package, while Blender
    installs it as ``bl_ext.<repository>.dimensions`` and registers it under a
    restricted ``bpy.data``. Both differences have hidden real registration failures.
    """

    def test_addon_id_is_the_full_package_name(self):
        from dimensions import preferences

        self.assertEqual(preferences.ADDON_ID, preferences.__package__)

    def test_every_interface_icon_exists_in_this_blender(self):
        # An unknown icon name makes the whole panel fail to draw.
        import re

        valid = {
            item.identifier
            for item in bpy.types.UILayout.bl_rna.functions["operator"].parameters["icon"].enum_items
        }
        for path in sorted((REPOSITORY_ROOT / "dimensions").rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            icons = set(re.findall(r'icon="([A-Z0-9_]+)"', source))
            icons.update(re.findall(r'^    "[A-Z_]+": "([A-Z0-9_]+)",$', source, re.M) if "_ICONS = {" in source else ())
            for icon in sorted(icons):
                with self.subTest(file=path.name, icon=icon):
                    self.assertIn(icon, valid)

    def test_every_operator_resolves_to_its_class_and_has_a_tooltip(self):
        # A registered operator subclassing another registered operator once left
        # Measure and Guide Line without a Python class, so invoking them did nothing,
        # and operators without a description show "Undocumented" on hover.
        classes = tuple(cls for cls in dimensions.CLASSES if issubclass(cls, bpy.types.Operator))

        for operator_class in classes:
            with self.subTest(operator=operator_class.bl_idname):
                group, name = operator_class.bl_idname.split(".")
                rna_type = getattr(getattr(bpy.ops, group), name).get_rna_type()
                self.assertIs(getattr(bpy.types, rna_type.identifier, None), operator_class)
                self.assertTrue(getattr(operator_class, "bl_description", "").strip())
                for base in operator_class.__mro__[1:]:
                    self.assertFalse(
                        base in classes,
                        f"{operator_class.__name__} subclasses registered operator {base.__name__}",
                    )

    def test_preferences_bl_idname_matches_the_addon_id(self):
        from dimensions import preferences

        self.assertEqual(
            preferences.DIMENSIONS_AddonPreferences.bl_idname,
            preferences.ADDON_ID,
        )

    def test_sidebar_uses_the_installed_addon_id_and_never_syncs_selection_during_draw(self):
        from dimensions import ui

        source = Path(ui.__file__).read_text(encoding="utf-8")
        self.assertIn("preferences.module = ADDON_ID", source)
        self.assertNotIn("set_active_index_from_viewport", source)

    def test_get_preferences_never_raises_without_a_registered_addon(self):
        from dimensions.preferences import DEFAULT_PREFERENCES, get_preferences

        self.assertIs(get_preferences(SimpleNamespace()), DEFAULT_PREFERENCES)
        self.assertIsNotNone(get_preferences(None))

    def test_default_and_reset_preferences_cover_every_snap_target(self):
        for identifier in TARGET_IDS:
            self.assertTrue(getattr(DEFAULT_PREFERENCES, f"snap_{identifier}"))

    def test_preferences_survive_an_in_session_reregister(self):
        before = SimpleNamespace(**vars(DEFAULT_PREFERENCES))
        after = SimpleNamespace(**vars(DEFAULT_PREFERENCES))
        before.snap_vertex = False
        before.snap_guide_plane = False
        with patch("dimensions.preferences.get_preferences", side_effect=(before, after)):
            remember_preferences_for_reregister()
            restore_preferences_after_reregister()
        self.assertFalse(after.snap_vertex)
        self.assertFalse(after.snap_guide_plane)

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


class DimensionsBindingRegressionTests(unittest.TestCase):
    """Area and Angle source binding defects found in the 0.7 release review."""

    class _RecordingLayout:
        def __init__(self, root=None):
            self.root = root or self
            self.enabled = True
            if root is None:
                self.labels = []
                self.operators = []

        def label(self, text="", icon="NONE"):
            self.root.labels.append(text)

        def operator(self, idname, text="", icon="NONE"):
            self.root.operators.append((idname, self.enabled))
            return SimpleNamespace()

        def box(self):
            return type(self)(self.root)

        def row(self, align=False):
            return type(self)(self.root)

        def column(self, align=False):
            return type(self)(self.root)

    def setUp(self):
        self.before_objects = set(bpy.data.objects)
        self.before_meshes = set(bpy.data.meshes)
        self.before_libraries = set(bpy.data.libraries)
        self.created_collections = []

    def tearDown(self):
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for library in list(bpy.data.libraries):
            if library not in self.before_libraries:
                bpy.data.libraries.remove(library)
        for obj in list(bpy.data.objects):
            if obj not in self.before_objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in list(bpy.data.meshes):
            if mesh not in self.before_meshes and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        for collection in self.created_collections:
            bpy.data.collections.remove(collection)
        sync_scene_objects(bpy.context.scene)

    def _mesh(self, name, location=(0.0, 0.0, 0.0)):
        # Two adjacent quads sharing an edge: face 0 has area 1, face 1 has area 3.
        mesh = bpy.data.meshes.new(f"{name} Mesh")
        mesh.from_pydata(
            [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (4, 0, 0), (4, 1, 0)],
            [],
            [(0, 1, 2, 3), (1, 4, 5, 2)],
        )
        obj = bpy.data.objects.new(name, mesh)
        obj.location = location
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.update()
        return obj

    def _area(self, name, source, face_indices):
        from dimensions.anchors import set_object_anchor

        annotation = create_dimension_object(bpy.context, name)
        props = annotation.dimension_props
        props.annotation_kind = "AREA"
        result = bind_area_face_indices(props, source, face_indices)
        set_object_anchor(props.start, source, result["center"])
        set_object_anchor(props.end, source, result["center"] + Vector((0.0, 2.0, 0.0)))
        return annotation

    def _select_only(self, objects, active):
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = active

    def _area_with_face_id(self, name, source, face_id):
        annotation = create_dimension_object(bpy.context, name)
        props = annotation.dimension_props
        props.annotation_kind = "AREA"
        props.area_source_object = source
        binding = props.area_faces.add()
        binding.face_id = face_id
        binding.vertex_count = 4
        return props

    def test_linked_area_source_is_refused_without_changing_the_binding(self):
        import os
        import tempfile
        from dimensions.area_binding import FACE_ID_ATTRIBUTE, area_source_is_read_only

        local = self._mesh("Binding Local Source")
        props = self._area("AREA Linked Refusal", local, [0]).dimension_props
        bound_ids = [item.face_id for item in props.area_faces]
        library_mesh = bpy.data.meshes.new("Binding Library Mesh")
        library_mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
        library_object = bpy.data.objects.new("Binding Library Plane", library_mesh)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "binding_library.blend")
            bpy.data.libraries.write(path, {library_object, library_mesh})
            bpy.data.objects.remove(library_object)
            bpy.data.meshes.remove(library_mesh)
            with bpy.data.libraries.load(path, link=True) as (_source, target):
                target.objects = ["Binding Library Plane"]
            linked = target.objects[0]
            bpy.context.scene.collection.objects.link(linked)

            self.assertTrue(area_source_is_read_only(linked))
            self.assertFalse(area_source_is_read_only(local))
            # Face IDs written to linked data are lost on reload, so binding is refused.
            self.assertIsNone(bind_area_face_indices(props, linked, [0]))
            self.assertEqual(props.area_source_object, local)
            self.assertEqual([item.face_id for item in props.area_faces], bound_ids)
            self.assertIsNone(linked.data.attributes.get(FACE_ID_ATTRIBUTE))

    def test_new_area_renumbers_every_copy_of_a_duplicated_face_id(self):
        from dimensions.area_binding import FACE_ID_ATTRIBUTE

        source = self._mesh("Binding Duplicate Source")
        attribute = source.data.attributes.new(FACE_ID_ATTRIBUTE, "INT", "FACE")
        attribute.data[0].value = 7
        attribute.data[1].value = 7
        existing = self._area_with_face_id("AREA Duplicate Existing", source, 7)
        self.assertIsNone(evaluate_area_binding(existing))

        created = create_dimension_object(bpy.context, "AREA Duplicate New").dimension_props
        created.annotation_kind = "AREA"
        self.assertAlmostEqual(bind_area_face_indices(created, source, [0])["area"], 1.0)
        values = [item.value for item in source.data.attributes[FACE_ID_ATTRIBUTE].data]
        self.assertNotIn(7, values)
        self.assertEqual(len(set(values)), 2)
        # The existing Area must stay unresolved rather than adopt the surviving copy.
        self.assertIsNone(evaluate_area_binding(existing))

    def test_new_edit_mode_area_renumbers_every_copy_of_a_duplicated_face_id(self):
        from dimensions.area_binding import FACE_ID_ATTRIBUTE

        source = self._mesh("Binding Duplicate Edit Source")
        existing = self._area_with_face_id("AREA Duplicate Edit Existing", source, 7)
        self._select_only([source], source)
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(source.data)
        layer = bm.faces.layers.int.new(FACE_ID_ATTRIBUTE)
        for face in bm.faces:
            face[layer] = 7
        self.assertIsNone(evaluate_area_binding(existing))

        created = create_dimension_object(bpy.context, "AREA Duplicate Edit New").dimension_props
        created.annotation_kind = "AREA"
        self.assertAlmostEqual(bind_area_face_indices(created, source, [1])["area"], 3.0)
        bm = bmesh.from_edit_mesh(source.data)
        layer = bm.faces.layers.int.get(FACE_ID_ATTRIBUTE)
        values = [face[layer] for face in bm.faces]
        self.assertNotIn(7, values)
        self.assertEqual(len(set(values)), 2)
        self.assertIsNone(evaluate_area_binding(existing))

    def test_apply_faces_targets_the_selected_area_and_rebinds_its_label(self):
        first = self._mesh("Binding Rebind First")
        second = self._mesh("Binding Rebind Second", location=(10.0, 0.0, 0.0))
        area_a = self._area("AREA Rebind A", first, [0])
        area_b = self._area("AREA Rebind B", second, [0])
        a_faces = [item.face_id for item in area_a.dimension_props.area_faces]

        self._select_only([area_a], area_a)
        self.assertEqual(bpy.ops.dimensions.select_area_source(), {"FINISHED"})
        self.assertTrue(area_a.select_get())
        bpy.ops.object.mode_set(mode="OBJECT")

        # Later the user selects Area B with the first mesh; A was only inspected earlier.
        self._select_only([area_b, first], first)
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(first.data)
        for face in bm.faces:
            face.select = True
        bmesh.update_edit_mesh(first.data)
        self.assertEqual(bpy.ops.dimensions.rebind_area_from_selection(), {"FINISHED"})

        props_b = area_b.dimension_props
        self.assertEqual(props_b.area_source_object, first)
        self.assertEqual(props_b.end.target_object, first)
        self.assertAlmostEqual(props_b.area_value, 4.0)
        self.assertEqual(area_a.dimension_props.area_source_object, first)
        self.assertEqual([item.face_id for item in area_a.dimension_props.area_faces], a_faces)

        area_b.select_set(False)
        self.assertFalse(bpy.ops.dimensions.rebind_area_from_selection.poll())

    def test_guided_repair_panel_reads_stored_state_without_searching_the_mesh(self):
        from dimensions.area_binding import FACE_ID_ATTRIBUTE
        from dimensions.repair import stored_repair_issues
        from dimensions.ui import CADDIM_PT_GuidedRepair

        source = self._mesh("Binding Repair Source")
        area = self._area("AREA Binding Repair", source, [0])
        source.data.attributes[FACE_ID_ATTRIBUTE].data[0].value = 0
        dimension = create_dimension_object(bpy.context, "DIM Binding Repair")
        set_anchor(dimension.dimension_props.start, source, 0)
        set_anchor(dimension.dimension_props.end, source, 4)
        source.data.attributes["dimensions_anchor_id"].data[0].value = 0
        sync_scene_objects(bpy.context.scene)

        for annotation, expected in ((area, [("AREA", "BY_FALLBACK")]), (dimension, [("ANCHOR", "BY_FALLBACK")])):
            live = [(issue["type"], issue["status"]) for issue in repair_issues(annotation)]
            stored = [(issue["type"], issue["status"]) for issue in stored_repair_issues(annotation)]
            self.assertEqual(live, expected)
            self.assertEqual(stored, expected)

        self._select_only([area], area)
        context = SimpleNamespace(view_layer=bpy.context.view_layer)
        layout = self._RecordingLayout()
        searched = AssertionError("the sidebar scanned the source mesh")
        with patch("dimensions.repair.suggest_area_candidate", side_effect=searched), \
                patch("dimensions.repair.suggest_vertex_candidate", side_effect=searched), \
                patch("dimensions.repair.anchor_resolution", side_effect=searched), \
                patch("dimensions.repair.evaluate_area_binding", side_effect=searched):
            self.assertTrue(CADDIM_PT_GuidedRepair.poll(context))
            CADDIM_PT_GuidedRepair.draw(SimpleNamespace(layout=layout), context)
        self.assertIn("Area: Fallback", layout.labels)
        self.assertIn(("dimensions.repair_accept_suggestion", True), layout.operators)

    def test_annotations_on_a_shared_mesh_stay_live_while_its_twin_is_edited(self):
        source = self._mesh("Binding Shared Source")
        twin = bpy.data.objects.new("Binding Shared Twin", source.data)
        bpy.context.scene.collection.objects.link(twin)
        area = self._area("AREA Binding Shared", source, [0])
        dimension = create_dimension_object(bpy.context, "DIM Binding Shared")
        set_anchor(dimension.dimension_props.start, source, 0)
        set_anchor(dimension.dimension_props.end, source, 4)

        self._select_only([twin], twin)
        bpy.ops.object.mode_set(mode="EDIT")
        self.assertEqual(source.mode, "OBJECT")
        self.assertIsNotNone(evaluate_area_binding(area.dimension_props))
        self.assertEqual(anchor_resolution(dimension.dimension_props.start)[1], "BY_ID")

    def test_select_area_source_warns_for_hidden_sources_and_flushes_selection(self):
        source = self._mesh("Binding Select Source")
        area = self._area("AREA Binding Select", source, [0])
        self._select_only([area], area)

        source.hide_viewport = True
        self.assertEqual(bpy.ops.dimensions.select_area_source(), {"CANCELLED"})
        source.hide_viewport = False
        collection = bpy.data.collections.new("Binding Excluded")
        self.created_collections.append(collection)
        bpy.context.scene.collection.children.link(collection)
        collection.objects.link(source)
        bpy.context.scene.collection.objects.unlink(source)
        bpy.context.view_layer.layer_collection.children[collection.name].exclude = True
        self.assertEqual(bpy.ops.dimensions.select_area_source(), {"CANCELLED"})
        self.assertEqual(bpy.context.mode, "OBJECT")
        self.assertEqual(bpy.context.view_layer.objects.active, area)
        self.assertTrue(area.select_get())

        bpy.context.view_layer.layer_collection.children[collection.name].exclude = False
        tool_settings = bpy.context.scene.tool_settings
        select_mode = tuple(tool_settings.mesh_select_mode)
        tool_settings.mesh_select_mode = (True, False, False)
        try:
            self.assertEqual(bpy.ops.dimensions.select_area_source(), {"FINISHED"})
            self.assertTrue(area.select_get())
            bm = bmesh.from_edit_mesh(source.data)
            bm.faces.ensure_lookup_table()
            # Face 1 shares an edge with the bound face; deselecting it once cleared that edge.
            self.assertTrue(all(vertex.select for vertex in bm.faces[0].verts))
            self.assertEqual([face.index for face in bm.faces if face.select], [0])
        finally:
            tool_settings.mesh_select_mode = select_mode

    def test_disconnected_angle_rays_point_toward_their_edges(self):
        from math import degrees

        # An L with a gap at the corner, with every stored vertex order.
        for a_start, a_end, b_start, b_end in (
            ((1, 0, 0), (3, 0, 0), (0, 1, 0), (0, 3, 0)),
            ((3, 0, 0), (1, 0, 0), (0, 1, 0), (0, 3, 0)),
            ((3, 0, 0), (1, 0, 0), (0, 3, 0), (0, 1, 0)),
        ):
            source = derive_angle_from_world_edges(
                Vector(a_start), Vector(a_end), Vector(b_start), Vector(b_end), "MINOR",
            )
            self.assertGreater((source["start"] - source["center"]).x, 0.5)
            self.assertGreater((source["end"] - source["center"]).y, 0.5)
            self.assertAlmostEqual(degrees(source["value"]), 90.0, places=4)
        # A 45-degree gap whose corner lies at (-1, 0), away from both edges.
        source = derive_angle_from_world_edges(
            Vector((3, 0, 0)), Vector((1, 0, 0)), Vector((2, 3, 0)), Vector((0, 1, 0)), "MINOR",
        )
        self.assertGreater((source["start"] - source["center"]).x, 0.5)
        self.assertGreater((source["end"] - source["center"]).y, 0.5)
        self.assertAlmostEqual(degrees(source["value"]), 45.0, places=4)


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
                DimensionsConstructionTests,
                DimensionsTransientMeasurementTests,
                DimensionsPackagingTests,
                DimensionsBindingRegressionTests,
            )
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        dimensions.unregister()

    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
