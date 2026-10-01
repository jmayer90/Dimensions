"""Headless coverage for modal interaction state, driven without a live viewport.

Run with ``blender --background --factory-startup --python tests/blender_modal.py``.

These tests exercise the interaction contract that the changelog keeps revisiting:
stage transitions, axis locks, typed distances, step-back, and cancellation. They use
``tests/support`` rather than a real 3D view, so a regression here is reported by the
suite instead of by a user.
"""

import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import dimensions
from dimensions.collections import get_or_create_dimension_collection, get_or_create_guide_collection
from dimensions.dimension_geometry import get_dimension_world_geometry
from dimensions.drawing import _draw_interaction_status
from dimensions.interaction import remember_session_context, session_axis, session_context_changed
from dimensions.inference import InferenceSession
from dimensions.modal_state import HandleManipulationState, PointPlacementState
from dimensions.operators.create_dimension import CADDIM_OT_CreateDimension
from dimensions.operators.reattach_anchor import CADDIM_OT_ReattachAnchor
from dimensions.operators.construction_tools import (
    DIMENSIONS_OT_CreateGuide,
    DIMENSIONS_OT_CreateGuidePlane,
    DIMENSIONS_OT_CreateGuidePoint,
    DIMENSIONS_OT_CreateOffsetGuide,
)
from dimensions.operators.create_angle import DIMENSIONS_OT_CreateAngle
from dimensions.operators.create_area import DIMENSIONS_OT_CreateArea
from dimensions.operators.measure import CADDIM_OT_Measure
from dimensions.construction import guide_line_world, guide_plane_frame, guide_point_world
from dimensions.viewport_state import _states, clear_state, get_state, set_state
from dimensions.ui import CADDIM_PT_ConstructionGuides, CADDIM_PT_MainPanel, CADDIM_PT_MeshSelection

from support import (
    EmptySnapProvider,
    ScriptedSnapProvider,
    make_context,
    make_event,
    make_operator_harness,
    make_snap,
    typing_events,
)


PICK_START = PointPlacementState.PICK_START
PICK_END = PointPlacementState.PICK_END
PLACE = PointPlacementState.PLACE

NAVIGATION_EVENT_TYPES = ("TRACKPADPAN", "TRACKPADZOOM", "NDOF_MOTION", "NUMPAD_7", "HOME")


def key_events(text):
    """Return key presses as Blender delivers them, with the key type and its character."""
    names = {" ": "SPACE", ".": "PERIOD"}
    return [
        make_event(names.get(character, character.upper()), "PRESS", ascii_character=character)
        for character in text
    ]


class ModalCleanupTests(unittest.TestCase):
    def tearDown(self):
        for states in _states.values():
            states.clear()

    def test_every_modal_operator_declares_external_cancel(self):
        for path in (REPOSITORY_ROOT / "dimensions" / "operators").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for item in tree.body:
                if not isinstance(item, ast.ClassDef):
                    continue
                methods = {
                    child.name for child in item.body if isinstance(child, ast.FunctionDef)
                }
                if "modal" in methods:
                    with self.subTest(operator=item.name):
                        self.assertIn("cancel", methods)
                        modal = next(
                            child for child in item.body
                            if isinstance(child, ast.FunctionDef) and child.name == "modal"
                        )
                        self.assertTrue(any(
                            isinstance(decorator, ast.Name)
                            and decorator.id == "modal_cleanup_on_exception"
                            for decorator in modal.decorator_list
                        ))

    def test_external_cancel_clears_only_owned_viewport_and_is_idempotent(self):
        owner = (1, 2, 3)
        neighbor = (4, 5, 6)
        for kind, operator_class in (
            ("DIMENSION", CADDIM_OT_ReattachAnchor),
            ("GUIDE", DIMENSIONS_OT_CreateGuide),
        ):
            with self.subTest(kind=kind):
                _states[kind][owner] = {"state": "PREVIEW"}
                _states[kind][neighbor] = {"state": "OTHER"}
                operator = make_operator_harness(operator_class, _session_viewport_key=owner)
                operator.cancel(None)
                operator.cancel(None)
                self.assertNotIn(owner, _states[kind])
                self.assertIn(neighbor, _states[kind])

    def test_editor_change_and_exception_clear_original_viewport(self):
        owner = (1, 2, 3)
        _states["DIMENSION"][owner] = {"state": "PREVIEW"}
        operator = make_operator_harness(CADDIM_OT_ReattachAnchor, _session_viewport_key=owner)
        context = make_context(scene=bpy.context.scene)
        result = operator.modal(context, make_event("MOUSEMOVE"))
        self.assertEqual(result, {"CANCELLED"})
        self.assertNotIn(owner, _states["DIMENSION"])

        _states["DIMENSION"][owner] = {"state": "PREVIEW"}
        operator = make_operator_harness(CADDIM_OT_ReattachAnchor, _session_viewport_key=owner)
        with patch("dimensions.operators.reattach_anchor.viewport_key", return_value=owner), patch(
            "dimensions.operators.reattach_anchor.handle_snap_target_event",
            side_effect=RuntimeError("injected modal failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "injected modal failure"):
                operator.modal(context, make_event("MOUSEMOVE"))
        self.assertNotIn(owner, _states["DIMENSION"])


class LayoutRecorder:
    """Small stand-in for the sidebar layout used by the UI contract test."""

    def __init__(self):
        self.labels = []
        self.properties = []
        self.enum_properties = []
        self.operators = []
        self.events = []
        self.enabled = True

    def box(self):
        return self

    def column(self, **_kwargs):
        self.events.append("COLUMN")
        return self

    def row(self, **_kwargs):
        return self

    def label(self, *, text, **_kwargs):
        self.labels.append(text)
        self.events.append(("LABEL", text))

    def prop(self, target, name, **kwargs):
        self.properties.append((target, name, kwargs))
        self.events.append(("PROPERTY", name))

    def prop_enum(self, target, name, value, **kwargs):
        self.enum_properties.append((target, name, value, kwargs))
        self.events.append(("PROPERTY_ENUM", name, value))

    def operator(self, identifier, **_kwargs):
        self.operators.append(identifier)
        self.events.append(("OPERATOR", identifier))
        return SimpleNamespace()


class PointPlacementStateTests(unittest.TestCase):
    """The pure contract, independent of any operator."""

    def setUp(self):
        self.state = PointPlacementState()

    def test_full_pick_pick_place_sequence(self):
        self.assertEqual(self.state.stage, PICK_START)
        self.assertEqual(self.state.accept_point(), "PICK_START_ACCEPTED")
        self.assertEqual(self.state.stage, PICK_END)
        self.assertEqual(self.state.accept_point(), "PICK_END_ACCEPTED")
        self.assertEqual(self.state.stage, PLACE)
        self.assertEqual(self.state.confirm(), "COMMITTED")

    def test_further_points_are_ignored_at_the_placement_stage(self):
        self.state.accept_point()
        self.state.accept_point()
        self.assertEqual(self.state.accept_point(), "NO_ACTION")
        self.assertEqual(self.state.stage, PLACE)

    def test_axis_mode_can_be_chosen_before_the_first_point(self):
        self.assertTrue(self.state.accepts_axis_lock)
        self.assertEqual(self.state.set_axis("X"), "AXIS_SET")
        self.assertEqual(self.state.axis, "X")

        self.state.accept_point()
        self.assertEqual(self.state.set_axis("Y"), "AXIS_IGNORED")
        self.assertEqual(self.state.axis, "X")

    def test_axis_lock_applies_after_both_points(self):
        self.state.accept_point()
        self.state.accept_point()
        self.assertTrue(self.state.accepts_axis_lock)
        self.assertEqual(self.state.set_axis("Z"), "AXIS_SET")
        self.assertEqual(self.state.axis, "Z")

    def test_typed_distance_is_offered_once_a_first_point_exists(self):
        self.assertFalse(self.state.accepts_numeric_input)
        self.state.accept_point()
        self.assertTrue(self.state.accepts_numeric_input)
        self.state.accept_point()
        self.assertTrue(self.state.accepts_numeric_input)

    def test_typed_distance_survives_a_later_axis_choice(self):
        self.state.accept_point()
        self.state.accept_point()
        self.state.set_numeric_text("2.5")
        self.state.set_axis("Y")
        self.assertEqual(self.state.numeric_text, "2.5")
        self.assertEqual(self.state.axis, "Y")

    def test_axis_chosen_before_typing_is_kept(self):
        self.state.accept_point()
        self.state.accept_point()
        self.state.set_axis("X")
        self.state.set_numeric_text("1.25")
        self.assertEqual(self.state.axis, "X")
        self.assertEqual(self.state.numeric_text, "1.25")

    def test_invalid_typed_input_refuses_to_commit_without_advancing(self):
        self.state.accept_point()
        self.state.accept_point()
        self.state.set_numeric_text("not a distance", valid=False)
        self.assertEqual(self.state.confirm(), "NUMERIC_INVALID")
        self.assertEqual(self.state.stage, PLACE)

    def test_blank_typed_input_is_never_treated_as_invalid(self):
        self.state.accept_point()
        self.state.set_numeric_text("   ", valid=False)
        self.assertTrue(self.state.numeric_valid)
        self.assertFalse(self.state.has_pending_numeric_input)

    def test_escape_clears_numeric_input_before_stepping_back(self):
        self.state.accept_point()
        self.state.accept_point()
        self.state.set_numeric_text("3")
        self.assertEqual(self.state.escape(), "NUMERIC_CLEARED")
        self.assertEqual(self.state.stage, PLACE)
        self.assertEqual(self.state.numeric_text, "")
        self.assertEqual(self.state.escape(), "STEPPED_BACK")
        self.assertEqual(self.state.stage, PICK_END)

    def test_step_back_from_every_stage(self):
        self.state.accept_point()
        self.state.accept_point()
        self.assertEqual(self.state.step_back(), "STEPPED_BACK")
        self.assertEqual(self.state.stage, PICK_END)
        self.assertEqual(self.state.step_back(), "STEPPED_BACK")
        self.assertEqual(self.state.stage, PICK_START)
        self.assertEqual(self.state.step_back(), "CANCELLED")

    def test_step_back_discards_pending_numeric_input(self):
        self.state.accept_point()
        self.state.accept_point()
        self.state.set_numeric_text("9", valid=False)
        self.state.step_back()
        self.assertEqual(self.state.numeric_text, "")
        self.assertTrue(self.state.numeric_valid)

    def test_accepting_a_point_clears_pending_numeric_input(self):
        self.state.accept_point()
        self.state.set_numeric_text("4")
        self.state.accept_point()
        self.assertEqual(self.state.numeric_text, "")

    def test_cancel_returns_to_the_initial_contract_from_any_stage(self):
        for stage_depth in range(3):
            state = PointPlacementState()
            for _ in range(stage_depth):
                state.accept_point()
            state.set_numeric_text("7", valid=False)
            state.set_axis("X")
            self.assertEqual(state.cancel(), "CANCELLED")
            self.assertEqual(state.stage, PICK_START)
            self.assertEqual(state.numeric_text, "")
            self.assertTrue(state.numeric_valid)
            self.assertEqual(state.axis, PointPlacementState.DEFAULT_AXIS)

    def test_restart_clears_transient_input_but_keeps_session_axis(self):
        self.state.set_axis("Z")
        self.state.accept_point()
        self.state.accept_point()
        self.state.set_numeric_text("3.5")
        self.assertEqual(self.state.restart(), "RESTARTED")
        self.assertEqual(self.state.stage, PICK_START)
        self.assertEqual(self.state.axis, "Z")
        self.assertEqual(self.state.numeric_text, "")
        self.assertTrue(self.state.numeric_valid)


class InteractionContextTests(unittest.TestCase):
    def test_tools_refuse_to_start_in_a_scene_saved_by_a_newer_dimensions(self):
        from dimensions.interaction import refuse_newer_scene
        from dimensions.migrations import CURRENT_SCHEMA_VERSION

        settings = bpy.context.scene.dimensions_settings
        original = settings.schema_version
        operator = SimpleNamespace(reports=[])
        operator.report = lambda severity, message: operator.reports.append((severity, message))
        try:
            self.assertFalse(refuse_newer_scene(operator, bpy.context))
            settings.schema_version = CURRENT_SCHEMA_VERSION + 1
            self.assertTrue(refuse_newer_scene(operator, bpy.context))
        finally:
            settings.schema_version = original
        self.assertEqual(len(operator.reports), 1)
        self.assertIn("newer", operator.reports[0][1])

    def test_session_context_tracks_mode_and_active_object(self):
        first = object()
        second = object()
        operator = SimpleNamespace()
        context = SimpleNamespace(
            mode="OBJECT",
            view_layer=SimpleNamespace(objects=SimpleNamespace(active=first)),
        )
        remember_session_context(operator, context)
        self.assertFalse(session_context_changed(operator, context))

        context.view_layer.objects.active = second
        self.assertTrue(session_context_changed(operator, context))
        context.view_layer.objects.active = first
        context.mode = "EDIT_MESH"
        self.assertTrue(session_context_changed(operator, context))

    def test_sidebar_exposes_full_width_direction_after_creation_tools(self):
        preferences = SimpleNamespace(default_axis_mode="Z")
        layout = LayoutRecorder()
        panel = SimpleNamespace(layout=layout)
        context = make_context(scene=bpy.context.scene)

        with (
            patch("dimensions.ui.get_preferences", return_value=preferences),
            patch("dimensions.preferences.get_preferences", return_value=preferences),
        ):
            CADDIM_PT_MainPanel.draw(panel, context)
            self.assertEqual(session_axis(context), "Z")

        self.assertIn("Direction", layout.labels)
        self.assertEqual(layout.enum_properties, [
            (preferences, "default_axis_mode", "ALIGNED", {"text": "Auto"}),
            (preferences, "default_axis_mode", "X", {"text": "X"}),
            (preferences, "default_axis_mode", "Y", {"text": "Y"}),
            (preferences, "default_axis_mode", "Z", {"text": "Z"}),
        ])
        direction_index = layout.events.index(("PROPERTY_ENUM", "default_axis_mode", "ALIGNED"))
        for tool in (
            "dimensions.create_dimension",
            "dimensions.create_angle",
            "dimensions.create_area",
            "dimensions.measure",
        ):
            self.assertLess(layout.events.index(("OPERATOR", tool)), direction_index)
        self.assertEqual(layout.operators.count("dimensions.create_dimension"), 2)
        for removed in (
            "dimensions.create_guide", "dimensions.create_guide_point", "dimensions.create_datum",
            "dimensions.create_dimension_set", "dimensions.create_circle_dimension",
            "dimensions.create_coordinate", "dimensions.create_elevation",
        ):
            self.assertNotIn(removed, layout.operators)

    def test_construction_tools_live_only_in_the_construction_panel(self):
        layout = LayoutRecorder()
        panel = SimpleNamespace(layout=layout)
        CADDIM_PT_ConstructionGuides.draw(panel, make_context(scene=bpy.context.scene))
        for tool in (
            "dimensions.create_guide",
            "dimensions.create_offset_guide",
            "dimensions.create_guide_point",
            "dimensions.create_guide_plane",
            "dimensions.clear_guides",
            "dimensions.clear_measurements",
        ):
            self.assertIn(tool, layout.operators)
        self.assertNotIn("dimensions.create_datum", layout.operators)
        self.assertEqual(CADDIM_PT_ConstructionGuides.bl_parent_id, CADDIM_PT_MainPanel.bl_idname)

    def test_mesh_selection_actions_use_an_edit_mode_child_panel(self):
        object_context = make_context(scene=bpy.context.scene)
        edit_context = make_context(scene=bpy.context.scene)
        edit_context.mode = "EDIT_MESH"

        self.assertFalse(CADDIM_PT_MeshSelection.poll(object_context))
        self.assertTrue(CADDIM_PT_MeshSelection.poll(edit_context))

        layout = LayoutRecorder()
        panel = SimpleNamespace(layout=layout)
        CADDIM_PT_MeshSelection.draw(panel, edit_context)
        self.assertEqual(layout.operators, [
            "dimensions.dimension_selected_edge",
            "dimensions.angle_selected_edges",
            "dimensions.area_selected_faces",
            "dimensions.rebind_area_from_selection",
        ])
        self.assertEqual(CADDIM_PT_MeshSelection.bl_parent_id, CADDIM_PT_MainPanel.bl_idname)
        self.assertLess(CADDIM_PT_MeshSelection.bl_order, 1)


class HandleManipulationStateTests(unittest.TestCase):
    def test_constraint_numeric_confirm_and_cancel_match_the_creation_contract(self):
        state = HandleManipulationState()
        self.assertEqual(state.set_axis("X"), "AXIS_SET")
        self.assertEqual(state.axis, "X")
        self.assertEqual(state.set_numeric_text("50mm", valid=True), "NUMERIC_UPDATED")
        self.assertEqual(state.confirm(), "COMMITTED")
        self.assertEqual(state.escape(), "NUMERIC_CLEARED")
        self.assertEqual(state.escape(), "CANCELLED")
        self.assertTrue(state.cancelled)

    def test_invalid_numeric_input_cannot_commit(self):
        state = HandleManipulationState("Z")
        state.set_numeric_text("not-a-distance", valid=False)
        self.assertEqual(state.confirm(), "NUMERIC_INVALID")
        self.assertFalse(state.cancelled)
        self.assertEqual(state.cancel(), "CANCELLED")


class CreateDimensionModalTests(unittest.TestCase):
    """The operator as a thin adapter over the contract, with a scripted viewport."""

    def setUp(self):
        self.operator = make_operator_harness(
            CADDIM_OT_CreateDimension,
            _state_machine=PointPlacementState(),
            hover_snap=None,
            hover_mouse=None,
            start_snap=None,
            end_snap=None,
            offset_distance=0.25,
            offset_plane_normal=None,
            continuous_placement=False,
            inference_axis="ALIGNED",
            inference_session=InferenceSession(),
            chain=False,
            chain_line=None,
        )
        self.reports = self.operator.reports
        self.context = make_context(scene=bpy.context.scene)
        self.context.view_layer = bpy.context.view_layer

    def _dimension_object_count(self):
        collection = get_or_create_dimension_collection(self.context)
        return len(collection.objects)

    def _drive(self, events, snaps=()):
        provider = ScriptedSnapProvider(snaps)
        with patch(
            "dimensions.operators.create_dimension.find_nearest_snap_point",
            provider,
        ):
            results = [self.operator.modal(self.context, event) for event in events]
        return results, provider

    def _pick_two_points(self, start=(0.0, 0.0, 0.0), end=(2.0, 0.0, 0.0)):
        """Click, move, click — the event order a real pick-pick sequence produces."""
        click = make_event("LEFTMOUSE", "PRESS")
        move = make_event("MOUSEMOVE", "PRESS")
        return self._drive(
            [click, move, click],
            [make_snap(start), make_snap(end)],
        )

    def test_operator_state_mirrors_the_machine(self):
        self.assertEqual(self.operator.state, PICK_START)
        self.operator._state_machine.accept_point()
        self.assertEqual(self.operator.state, PICK_END)

    def test_typed_text_and_validity_are_owned_by_the_machine(self):
        self.operator.distance_text = "2m"
        self.assertEqual(self.operator._state_machine.numeric_text, "2m")
        self.operator.distance_input_valid = False
        self.assertFalse(self.operator._state_machine.numeric_valid)

    def test_axis_is_owned_by_the_machine(self):
        self.operator.dimension_type = "Z"
        self.assertEqual(self.operator._state_machine.axis, "Z")

    def test_axis_can_be_selected_before_the_first_point_and_preview_explains_how(self):
        with patch("dimensions.operators.create_dimension.set_preview_state") as set_preview:
            result = self.operator.modal(self.context, make_event("Y", "PRESS"))

        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertEqual(self.operator.dimension_type, "Y")
        preview = set_preview.call_args.args[0]
        self.assertEqual(preview["axis"], "Y")
        self.assertTrue(preview["axis_selectable"])

    def test_interaction_status_is_a_compact_corner_badge(self):
        with patch("dimensions.drawing._draw_text_left") as draw_text:
            _draw_interaction_status({
                "axis": "X",
                "axis_selectable": True,
                "continuous_placement": True,
                "hover_label": "Vertex",
                "hover_screen": (600.0, 400.0),
            })

        text, position, _color, text_size = draw_text.call_args.args
        self.assertEqual(text, "DIM · X")
        self.assertEqual(tuple(position), (24.0, 44.0))
        self.assertEqual(text_size, 12)
        self.assertNotIn("Esc", text)
        self.assertNotIn("Right", text)
        self.assertNotIn("Vertex", text)

    def test_interaction_status_only_adds_input_while_typing(self):
        with patch("dimensions.drawing._draw_text_left") as draw_text:
            _draw_interaction_status({
                "tool_label": "GUIDE",
                "axis": "ALIGNED",
                "distance_text": "2m",
            })

        self.assertEqual(draw_text.call_args.args[0], "GUIDE · Auto · 2m")

    def test_modal_snap_key_cycles_targets_without_cancelling(self):
        settings = self.context.scene.dimensions_settings
        self.addCleanup(setattr, settings, "use_snap_target_override", False)
        settings.use_snap_target_override = True
        for identifier in (
            "vertex", "edge", "midpoint", "face_center", "face_point", "guide",
            "measurement_endpoint", "measurement_midpoint", "measurement_segment",
        ):
            setattr(settings, f"snap_{identifier}", True)
        result = self.operator.modal(self.context, make_event("S", "PRESS"))
        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertTrue(settings.snap_vertex)
        self.assertFalse(settings.snap_edge)

    def test_modal_inference_lock_persists_until_the_same_action_releases_it(self):
        self.operator.inference_session.references = [{
            "label": "Edge",
            "reference_line": ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        }]
        self.assertEqual(self.operator.modal(self.context, make_event("L", "PRESS")), {"RUNNING_MODAL"})
        self.assertTrue(self.operator.inference_session.locked)
        self.assertEqual(self.operator.modal(self.context, make_event("L", "PRESS")), {"RUNNING_MODAL"})
        self.assertFalse(self.operator.inference_session.locked)

    def test_repeating_an_axis_enters_local_axis_mode(self):
        self.assertEqual(self.operator.modal(self.context, make_event("X", "PRESS")), {"RUNNING_MODAL"})
        self.assertEqual(self.operator.inference_axis, "X")
        self.assertEqual(self.operator.modal(self.context, make_event("X", "PRESS")), {"RUNNING_MODAL"})
        self.assertEqual(self.operator.inference_axis, "LOCAL_X")
        self.assertEqual(self.operator.dimension_type, "ALIGNED")

    def test_invalid_interaction_input_stays_visible(self):
        with patch("dimensions.drawing._draw_text_left") as draw_text:
            _draw_interaction_status({
                "tool_label": "MEASURE",
                "axis": "Z",
                "distance_text": "bad",
                "distance_input_valid": False,
            })

        self.assertEqual(draw_text.call_args.args[0], "MEASURE · Z · ! bad")
        self.assertEqual(draw_text.call_args.args[2], (1.0, 0.22, 0.12, 1.0))

    def test_two_clicks_advance_to_the_placement_stage(self):
        self._pick_two_points()
        self.assertEqual(self.operator.state, PLACE)
        self.assertIsNotNone(self.operator.start_snap)
        self.assertIsNotNone(self.operator.end_snap)

    def test_a_click_that_hits_nothing_does_not_advance_the_stage(self):
        provider = EmptySnapProvider()
        with patch(
            "dimensions.operators.create_dimension.find_nearest_snap_point",
            provider,
        ):
            result = self.operator.modal(self.context, make_event("LEFTMOUSE", "PRESS"))
        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertEqual(self.operator.state, PICK_START)
        self.assertGreater(provider.query_count, 0)

    def test_click_at_changed_coordinates_requeries_instead_of_committing_stale_hover(self):
        self.operator.hover_snap = make_snap((1.0, 0.0, 0.0))
        self.operator.hover_mouse = Vector((10.0, 10.0))
        fresh = make_snap((5.0, 0.0, 0.0))
        with patch("dimensions.operators.create_dimension.find_nearest_snap_point", return_value=fresh) as query:
            result = self.operator.modal(
                self.context,
                make_event("LEFTMOUSE", "PRESS", mouse_region_x=50, mouse_region_y=10),
            )
        self.assertEqual(result, {"RUNNING_MODAL"})
        query.assert_called_once()
        self.assertEqual(self.operator.start_snap["world_co"], Vector((5.0, 0.0, 0.0)))

    def test_a_coincident_second_point_is_refused_with_a_warning(self):
        self._pick_two_points((1.0, 1.0, 1.0), (1.0, 1.0, 1.0))
        self.assertEqual(self.operator.state, PICK_END)
        self.assertTrue(any("different" in message.lower() for _severity, message in self.reports))

    def test_escape_at_the_first_stage_cancels_and_creates_nothing(self):
        before = self._dimension_object_count()
        result = self.operator.modal(self.context, make_event("ESC", "PRESS"))
        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(self._dimension_object_count(), before)

    def test_escape_steps_back_through_every_stage_leaving_nothing_behind(self):
        before = self._dimension_object_count()
        self._pick_two_points((0.0, 0.0, 0.0), (3.0, 0.0, 0.0))
        self.assertEqual(self.operator.state, PLACE)

        escape = make_event("ESC", "PRESS")
        self.operator.modal(self.context, escape)
        self.assertEqual(self.operator.state, PICK_END)
        self.assertIsNone(self.operator.end_snap)

        self.operator.modal(self.context, escape)
        self.assertEqual(self.operator.state, PICK_START)
        self.assertIsNone(self.operator.start_snap)

        result = self.operator.modal(self.context, escape)
        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(self._dimension_object_count(), before)

    def test_right_click_cancels_from_the_placement_stage_without_creating_objects(self):
        before = self._dimension_object_count()
        self._pick_two_points((0.0, 0.0, 0.0), (1.0, 2.0, 0.0))
        result = self.operator.modal(self.context, make_event("RIGHTMOUSE", "PRESS"))
        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(self._dimension_object_count(), before)

    def test_invalid_typed_distance_is_refused_without_committing(self):
        before = self._dimension_object_count()
        self._pick_two_points((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))

        self.operator._state_machine.set_numeric_text("zz", valid=False)
        self.reports.clear()
        result = self.operator.modal(self.context, make_event("LEFTMOUSE", "PRESS"))
        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertEqual(self.operator.state, PLACE)
        self.assertEqual(self._dimension_object_count(), before)
        self.assertTrue(any(severity == {"WARNING"} for severity, _message in self.reports))

    def test_a_committed_dimension_is_created_once(self):
        before = self._dimension_object_count()
        self._pick_two_points((0.0, 0.0, 0.0), (4.0, 0.0, 0.0))
        self.assertTrue(self.operator._create_dimension(self.context))
        self.assertEqual(self._dimension_object_count(), before + 1)

    def test_continuous_commit_restarts_with_session_axis_and_offset(self):
        self.operator.continuous_placement = True
        self.operator.dimension_type = "Z"
        remember_session_context(self.operator, self.context)
        self._pick_two_points((0.0, 0.0, 0.0), (0.0, 0.0, 4.0))
        self.assertTrue(self.operator._create_dimension(self.context))
        with patch("dimensions.operators.create_dimension.push_undo_step") as undo_step:
            result = self.operator._after_commit(self.context)
        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertEqual(self.operator.state, PICK_START)
        self.assertEqual(self.operator.dimension_type, "Z")
        self.assertEqual(self.operator.offset_distance, 0.25)
        self.assertIsNone(self.operator.start_snap)
        self.assertIsNone(self.operator.end_snap)
        undo_step.assert_called_once_with("Create Dimension")

    def test_a_locked_axis_gives_a_typed_distance_its_direction_without_moving(self):
        self.operator.dimension_type = "X"
        self.operator.inference_axis = "X"
        events = [make_event("LEFTMOUSE", "PRESS"), *typing_events("2"), make_event("RET", "PRESS")]
        self._drive(events, [make_snap((1.0, 1.0, 0.0), snap_type="VERTEX", label="Vertex")])
        self.assertEqual(self.operator.state, PLACE)
        self.assertEqual(tuple(self.operator.end_snap["world_co"]), (3.0, 1.0, 0.0))
        self.assertFalse(self.reports)

    def test_a_typed_distance_without_a_direction_says_how_to_give_one(self):
        events = [make_event("LEFTMOUSE", "PRESS"), *typing_events("2"), make_event("RET", "PRESS")]
        self._drive(events, [make_snap((1.0, 1.0, 0.0))])
        self.assertEqual(self.operator.state, PICK_END)
        messages_reported = [message for _severity, message in self.reports]
        self.assertTrue(any("direction" in message for message in messages_reported), messages_reported)
        self.assertFalse(any("valid distance" in message for message in messages_reported))

    def test_unit_letters_continue_a_typed_distance_instead_of_running_shortcuts(self):
        from dimensions.snap_targets import enabled_snap_targets

        before = enabled_snap_targets(self.context)
        self._drive(
            [make_event("LEFTMOUSE", "PRESS"), make_event("MOUSEMOVE", "PRESS"), *key_events("3 meters")],
            [make_snap((0.0, 0.0, 0.0)), make_snap((1.0, 0.0, 0.0))],
        )
        self.assertEqual(self.operator.distance_text, "3 meters")
        self.assertEqual(enabled_snap_targets(self.context), before)
        self.assertFalse(self.operator.inference_session.locked)

    def test_trackpad_ndof_and_numpad_view_keys_reach_blender(self):
        for event_type in NAVIGATION_EVENT_TYPES:
            with self.subTest(event=event_type):
                self.assertEqual(self.operator.modal(self.context, make_event(event_type, "NOTHING")), {"PASS_THROUGH"})

    def test_middle_mouse_navigates_at_every_stage(self):
        for stage in (PICK_START, PICK_END, PLACE):
            self.operator._state_machine.stage = stage
            with self.subTest(stage=stage):
                self.assertEqual(self.operator.modal(self.context, make_event("MIDDLEMOUSE", "PRESS")), {"PASS_THROUGH"})

    def test_a_numpad_digit_types_a_distance_once_typing_is_allowed(self):
        self._pick_two_points()
        self.operator._state_machine.step_back()
        result = self.operator.modal(self.context, make_event("NUMPAD_7", "PRESS", ascii_character="7"))
        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertEqual(self.operator.distance_text, "7")


class ChainDimensionModalTests(unittest.TestCase):
    """Chain is Create Dimension continuing each new dimension from the last end point."""

    def setUp(self):
        self.before_objects = set(bpy.data.objects)
        self.context = make_context(scene=bpy.context.scene)
        self.context.view_layer = bpy.context.view_layer
        self.operator = make_operator_harness(
            CADDIM_OT_CreateDimension,
            chain=True,
            _state_machine=PointPlacementState(),
            hover_snap=None,
            hover_mouse=None,
            start_snap=None,
            end_snap=None,
            offset_distance=0.25,
            offset_plane_normal=None,
            continuous_placement=True,
            inference_axis="ALIGNED",
            inference_session=InferenceSession(),
            chain_line=None,
        )
        remember_session_context(self.operator, self.context)

    def tearDown(self):
        for obj in list(bpy.data.objects):
            if obj not in self.before_objects:
                bpy.data.objects.remove(obj, do_unlink=True)

    def _created(self):
        return [
            obj for obj in bpy.data.objects
            if obj not in self.before_objects and obj.dimension_props.enabled
        ]

    def _drive(self, events, snaps):
        provider = ScriptedSnapProvider(snaps)
        with (
            patch("dimensions.operators.create_dimension.find_nearest_snap_point", provider),
            patch("dimensions.operators.create_dimension.push_undo_step") as undo_step,
        ):
            results = [self.operator.modal(self.context, event) for event in events]
        return results, undo_step

    def test_chain_creates_ordinary_linear_dimensions_end_to_end(self):
        click = make_event("LEFTMOUSE", "PRESS")
        move = make_event("MOUSEMOVE", "PRESS")
        # Start, end, place the first dimension line, then each click adds the next member.
        results, undo_step = self._drive(
            [click, move, click, click, move, click, move, click],
            [make_snap((0, 0, 0)), make_snap((1, 0, 0)), make_snap((3, 0, 0)), make_snap((3.5, 0, 0))],
        )
        self.assertTrue(all(result == {"RUNNING_MODAL"} for result in results))
        created = self._created()
        self.assertEqual(len(created), 3)
        self.assertTrue(all(obj.dimension_props.annotation_kind == "LINEAR" for obj in created))
        self.assertEqual(undo_step.call_count, 3)
        by_start = sorted(created, key=lambda obj: obj.dimension_props.start.world_co[0])
        for previous, following in zip(by_start, by_start[1:]):
            self.assertEqual(
                tuple(previous.dimension_props.end.world_co),
                tuple(following.dimension_props.start.world_co),
            )
        lines = []
        for obj in by_start:
            props = obj.dimension_props
            geometry = get_dimension_world_geometry(
                props.dimension_type, Vector(props.start.world_co), Vector(props.end.world_co),
                Vector(props.offset_plane_normal), props.offset_distance,
            )
            lines.append(geometry["line_start_world"])
        self.assertTrue(all(abs(line.y - lines[0].y) < 1e-6 for line in lines))
        self.assertEqual(self.operator.state, PICK_END)
        self.assertEqual(self.operator.modal(self.context, make_event("ESC", "PRESS")), {"CANCELLED"})
        self.assertEqual(len(self._created()), 3)

    def test_axis_locked_chain_accepts_off_axis_points_by_projecting_them(self):
        self.operator.dimension_type = "X"
        self.operator.inference_axis = "X"
        click = make_event("LEFTMOUSE", "PRESS")
        move = make_event("MOUSEMOVE", "PRESS")
        self._drive(
            [click, move, click, click, move, click],
            [make_snap((0, 0, 0)), make_snap((2, 1, 0)), make_snap((5, -3, 0))],
        )
        created = sorted(self._created(), key=lambda obj: obj.dimension_props.start.world_co[0])
        self.assertEqual(len(created), 2)
        self.assertEqual(tuple(created[1].dimension_props.end.world_co), (5.0, 0.0, 0.0))
        self.assertEqual(created[1].dimension_props.dimension_type, "X")

    def test_step_back_ends_the_run_and_returns_to_a_fresh_first_point(self):
        click = make_event("LEFTMOUSE", "PRESS")
        move = make_event("MOUSEMOVE", "PRESS")
        self._drive([click, move, click, click], [make_snap((0, 0, 0)), make_snap((1, 0, 0))])
        self.assertEqual(self.operator.state, PICK_END)
        self.operator.modal(self.context, make_event("BACK_SPACE", "PRESS"))
        self.assertEqual(self.operator.state, PICK_START)
        self.assertIsNone(self.operator.chain_line)

    def test_chain_and_dimension_have_distinct_tooltips(self):
        chain = CADDIM_OT_CreateDimension.description(None, SimpleNamespace(chain=True))
        plain = CADDIM_OT_CreateDimension.description(None, SimpleNamespace(chain=False))
        self.assertIn("end to end", chain)
        self.assertNotEqual(chain, plain)


class ConstructionToolModalTests(unittest.TestCase):
    """Guide tools share Create Dimension's acquisition contract and create movable objects."""

    def setUp(self):
        self.before_objects = set(bpy.data.objects)
        self.context = make_context(scene=bpy.context.scene)
        self.context.view_layer = bpy.context.view_layer

    def tearDown(self):
        for obj in list(bpy.data.objects):
            if obj not in self.before_objects:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if isinstance(data, bpy.types.Mesh) and data.users == 0:
                    bpy.data.meshes.remove(data)
        for states in _states.values():
            states.clear()

    def _tool(self, operator_class, **attributes):
        operator = make_operator_harness(
            operator_class,
            axis="ALIGNED",
            inference_axis="ALIGNED",
            continuous_placement=False,
            picked=[],
            hover_snap=None,
            hover_mouse=None,
            distance_text="",
            distance_input_valid=True,
            inference_session=InferenceSession(),
            **attributes,
        )
        remember_session_context(operator, self.context)
        operator._begin(self.context)
        return operator

    def _drive(self, operator, events, snaps):
        provider = ScriptedSnapProvider(snaps)
        with (
            patch("dimensions.operators.construction_tools.find_nearest_snap_point", provider),
            patch("dimensions.operators.construction_tools.push_undo_step"),
        ):
            return [operator.modal(self.context, event) for event in events]

    def _created(self, kind):
        return [
            obj for obj in bpy.data.objects
            if obj not in self.before_objects and obj.guide_props.enabled and obj.guide_props.kind == kind
        ]

    def test_guide_line_uses_two_snapped_points_and_becomes_a_transform(self):
        operator = self._tool(DIMENSIONS_OT_CreateGuide)
        click = make_event("LEFTMOUSE", "PRESS")
        move = make_event("MOUSEMOVE", "PRESS")
        results = self._drive(operator, [click, move, click], [make_snap((1, 2, 0)), make_snap((1, 5, 0))])
        self.assertEqual(results[-1], {"FINISHED"})
        guides = self._created("GUIDE")
        self.assertEqual(len(guides), 1)
        bpy.context.view_layer.update()
        origin, direction = guide_line_world(guides[0])
        self.assertLess((origin - Vector((1, 2, 0))).length, 1e-6)
        self.assertLess((direction - Vector((0, 1, 0))).length, 1e-6)

    def test_guide_line_axis_lock_and_typed_distance_need_no_second_snap(self):
        operator = self._tool(DIMENSIONS_OT_CreateGuide)
        self._drive(operator, [make_event("Z", "PRESS"), make_event("LEFTMOUSE", "PRESS")], [make_snap((0, 0, 1))])
        operator.hover_snap = None
        for event in typing_events("2"):
            operator.modal(self.context, event)
        result = operator.modal(self.context, make_event("RET", "PRESS"))
        self.assertEqual(result, {"FINISHED"})
        bpy.context.view_layer.update()
        _origin, direction = guide_line_world(self._created("GUIDE")[0])
        self.assertLess((direction - Vector((0, 0, 1))).length, 1e-6)

    def test_guide_point_click_creates_a_movable_point(self):
        operator = self._tool(DIMENSIONS_OT_CreateGuidePoint, placement_mode="DIRECT")
        results = self._drive(operator, [make_event("LEFTMOUSE", "PRESS")], [make_snap((4, 5, 6))])
        self.assertEqual(results, [{"FINISHED"}])
        point = self._created("POINT")[0]
        self.assertEqual(guide_point_world(point), Vector((4, 5, 6)))
        point.location = (7, 8, 9)
        bpy.context.view_layer.update()
        from dimensions.scene_sync import sync_scene_objects

        sync_scene_objects(bpy.context.scene)
        self.assertEqual(guide_point_world(point), Vector((7, 8, 9)))

    def test_three_point_plane_preview_then_grid_through_the_points(self):
        operator = self._tool(DIMENSIONS_OT_CreateGuidePlane, definition="THREE_POINTS")
        click = make_event("LEFTMOUSE", "PRESS")
        move = make_event("MOUSEMOVE", "PRESS")
        snaps = [make_snap((0, 0, 2)), make_snap((3, 0, 2)), make_snap((0, 2, 2))]
        results = self._drive(operator, [click, move, click, move], snaps)
        self.assertTrue(get_state("GUIDE", self.context)["plane_preview_segments"])
        results += self._drive(operator, [click], snaps[2:])
        self.assertEqual(results[-1], {"FINISHED"})
        plane = self._created("PLANE")[0]
        self.assertEqual(plane.type, "MESH")
        origin, axis_u, _axis_v, normal = guide_plane_frame(plane)
        self.assertLess((origin - Vector((0, 0, 2))).length, 1e-6)
        self.assertLess((axis_u - Vector((1, 0, 0))).length, 1e-6)
        self.assertAlmostEqual(abs(normal.z), 1.0, places=6)

    def test_collinear_plane_points_are_refused(self):
        operator = self._tool(DIMENSIONS_OT_CreateGuidePlane, definition="THREE_POINTS")
        click = make_event("LEFTMOUSE", "PRESS")
        move = make_event("MOUSEMOVE", "PRESS")
        results = self._drive(
            operator, [click, move, click, move, click],
            [make_snap((0, 0, 0)), make_snap((1, 0, 0)), make_snap((2, 0, 0))],
        )
        self.assertEqual(results[-1], {"RUNNING_MODAL"})
        self.assertEqual(self._created("PLANE"), [])
        self.assertTrue(any(severity == {"WARNING"} for severity, _message in operator.reports))

    def test_offset_guide_from_a_guide_line_at_a_typed_distance(self):
        source = bpy.data.objects.new("Offset Source Guide", None)
        bpy.context.scene.collection.objects.link(source)
        source.guide_props.enabled = True
        source.guide_props.kind = "GUIDE"
        source.location = (0, 0, 0)
        bpy.context.view_layer.update()
        operator = self._tool(DIMENSIONS_OT_CreateOffsetGuide)
        guide_snap = make_snap((2, 0, 0), snap_type="GUIDE", label="Guide")
        guide_snap["guide_object"] = source
        guide_snap["reference_line"] = (Vector((0, 0, 0)), Vector((1, 0, 0)))
        self._drive(
            operator,
            [make_event("LEFTMOUSE", "PRESS"), make_event("MOUSEMOVE", "PRESS")],
            [guide_snap, make_snap((2, 3, 0))],
        )
        for event in typing_events("1.5"):
            operator.modal(self.context, event)
        result = operator.modal(self.context, make_event("RET", "PRESS"))
        self.assertEqual(result, {"FINISHED"})
        created = [obj for obj in self._created("GUIDE") if obj is not source]
        self.assertEqual(len(created), 1)
        bpy.context.view_layer.update()
        origin, direction = guide_line_world(created[0])
        self.assertLess((origin - Vector((0, 1.5, 0))).length, 1e-6)
        self.assertLess((direction - Vector((1, 0, 0))).length, 1e-6)

    def _offset_from_typed_text(self, events):
        source = bpy.data.objects.new("Offset Source Guide", None)
        bpy.context.scene.collection.objects.link(source)
        source.guide_props.enabled = True
        source.guide_props.kind = "GUIDE"
        bpy.context.view_layer.update()
        operator = self._tool(DIMENSIONS_OT_CreateOffsetGuide)
        guide_snap = make_snap((2, 0, 0), snap_type="GUIDE", label="Guide")
        guide_snap["guide_object"] = source
        guide_snap["reference_line"] = (Vector((0, 0, 0)), Vector((1, 0, 0)))
        self._drive(
            operator,
            [make_event("LEFTMOUSE", "PRESS"), make_event("MOUSEMOVE", "PRESS")],
            [guide_snap, make_snap((2, 3, 0))],
        )
        for event in events:
            operator.modal(self.context, event)
        typed = operator.distance_text
        self.assertEqual(operator.modal(self.context, make_event("RET", "PRESS")), {"FINISHED"})
        created = [obj for obj in self._created("GUIDE") if obj is not source]
        bpy.context.view_layer.update()
        return typed, guide_line_world(created[0])[0]

    def test_a_negative_offset_distance_goes_on_the_other_side_of_the_pointer(self):
        _typed, origin = self._offset_from_typed_text(typing_events("-1.5"))
        self.assertLess((origin - Vector((0, -1.5, 0))).length, 1e-6)

    def test_offset_distance_accepts_feet_typed_with_letters(self):
        typed, origin = self._offset_from_typed_text(key_events("2ft"))
        self.assertEqual(typed, "2ft")
        self.assertLess((origin - Vector((0, 0.6096, 0))).length, 1e-4)

    def test_offset_guide_refuses_a_point_that_is_not_a_line(self):
        operator = self._tool(DIMENSIONS_OT_CreateOffsetGuide)
        results = self._drive(operator, [make_event("LEFTMOUSE", "PRESS")], [make_snap((0, 0, 0))])
        self.assertEqual(results, [{"RUNNING_MODAL"}])
        self.assertEqual(operator.picked, [])

    def test_escape_exits_and_clears_only_this_viewport(self):
        operator = self._tool(DIMENSIONS_OT_CreateGuide)
        self._drive(operator, [make_event("MOUSEMOVE", "PRESS")], [make_snap((0, 0, 0))])
        self.assertIsNotNone(get_state("GUIDE", self.context))
        self.assertEqual(operator.modal(self.context, make_event("ESC", "PRESS")), {"CANCELLED"})
        self.assertIsNone(get_state("GUIDE", self.context))

    def test_trackpad_ndof_and_numpad_view_keys_reach_blender(self):
        operator = self._tool(DIMENSIONS_OT_CreateGuide)
        for event_type in NAVIGATION_EVENT_TYPES:
            with self.subTest(event=event_type):
                self.assertEqual(operator.modal(self.context, make_event(event_type, "NOTHING")), {"PASS_THROUGH"})


class CreateAngleModalTests(unittest.TestCase):
    def setUp(self):
        mesh = bpy.data.meshes.new("Dimensions Modal Angle Mesh")
        mesh.from_pydata(
            [(0, 0, 0), (2, 0, 0), (0, -1, 0), (0, 1, 0)],
            [(0, 1), (2, 3)],
            [],
        )
        self.source = bpy.data.objects.new("Dimensions Modal Angle Source", mesh)
        bpy.context.scene.collection.objects.link(self.source)
        self.before_names = set(bpy.data.objects)
        self.context = make_context(scene=bpy.context.scene)
        self.context.view_layer = bpy.context.view_layer
        self.operator = make_operator_harness(
            DIMENSIONS_OT_CreateAngle,
            target_name="",
            continuous_placement=False,
            angle_mode="MINOR",
            state="PICK_EDGE_A",
            edge_a_snap=None,
            edge_b_snap=None,
            hover_snap=None,
            radius=0.25,
        )

    def tearDown(self):
        for obj in list(bpy.data.objects):
            if obj not in self.before_names and obj != self.source:
                bpy.data.objects.remove(obj, do_unlink=True)
        mesh = self.source.data
        bpy.data.objects.remove(self.source, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    def _edge_snap(self, index, vertices):
        points = tuple(self.source.matrix_world @ self.source.data.vertices[item].co for item in vertices)
        return {
            "type": "EDGE",
            "label": "Edge",
            "object": self.source,
            "edge_index": index,
            "edge_vertices": vertices,
            "world_points": points,
            "world_co": (points[0] + points[1]) * 0.5,
            "screen_co": Vector((0.0, 0.0)),
        }

    def test_two_edge_workflow_reaches_radius_and_commits(self):
        self.operator.hover_snap = self._edge_snap(0, (0, 1))
        self.assertEqual(
            self.operator.modal(self.context, make_event("LEFTMOUSE", "PRESS")),
            {"RUNNING_MODAL"},
        )
        self.assertEqual(self.operator.state, "PICK_EDGE_B")
        self.operator.hover_snap = self._edge_snap(1, (2, 3))
        self.assertEqual(
            self.operator.modal(self.context, make_event("LEFTMOUSE", "PRESS")),
            {"RUNNING_MODAL"},
        )
        self.assertEqual(self.operator.state, "PICK_RADIUS")
        self.assertEqual(
            self.operator.modal(self.context, make_event("RET", "PRESS")),
            {"FINISHED"},
        )
        annotation = bpy.context.view_layer.objects.active
        self.assertEqual(annotation.dimension_props.annotation_kind, "ANGLE")
        self.assertEqual(annotation.dimension_props.angle_a_start.target_object, self.source)
        self.assertEqual(annotation.dimension_props.angle_b_start.target_object, self.source)

    def test_backspace_steps_back_one_edge_and_the_prompt_names_the_next_step(self):
        self.operator.hover_snap = self._edge_snap(0, (0, 1))
        self.operator.modal(self.context, make_event("LEFTMOUSE", "PRESS"))
        self.assertEqual(self.operator._prompt(), "Click the second edge")
        self.assertEqual(self.operator.modal(self.context, make_event("BACK_SPACE", "PRESS")), {"RUNNING_MODAL"})
        self.assertEqual(self.operator.state, "PICK_EDGE_A")
        self.assertIsNone(self.operator.edge_a_snap)
        self.assertEqual(self.operator._prompt(), "Click the first edge")

    def test_trackpad_ndof_and_numpad_view_keys_reach_blender(self):
        for event_type in NAVIGATION_EVENT_TYPES:
            with self.subTest(event=event_type):
                self.assertEqual(self.operator.modal(self.context, make_event(event_type, "NOTHING")), {"PASS_THROUGH"})


class CreateAreaModalTests(unittest.TestCase):
    def setUp(self):
        mesh = bpy.data.meshes.new("Dimensions Modal Area Mesh")
        mesh.from_pydata(
            [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)],
            [],
            [(0, 1, 2, 3)],
        )
        self.source = bpy.data.objects.new("Dimensions Modal Area Source", mesh)
        bpy.context.scene.collection.objects.link(self.source)
        self.before_names = set(bpy.data.objects)
        self.context = make_context(scene=bpy.context.scene)
        self.context.view_layer = bpy.context.view_layer
        self.operator = make_operator_harness(
            DIMENSIONS_OT_CreateArea,
            target_name="",
            source_object=None,
            face_indices=[],
            hover_snap=None,
            label_snap=None,
            area_result=None,
            placement_axis="ALIGNED",
            continuous_placement=False,
            offset_distance=0.25,
            distance_text="",
            distance_input_valid=True,
            typed_distance=None,
            state="PICK_FACE",
        )

    def tearDown(self):
        for obj in list(bpy.data.objects):
            if obj not in self.before_names and obj != self.source:
                bpy.data.objects.remove(obj, do_unlink=True)
        mesh = self.source.data
        bpy.data.objects.remove(self.source, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    def test_face_axis_and_typed_distance_commit_one_constrained_area(self):
        self.operator.hover_snap = {
            "type": "FACE",
            "label": "Face",
            "object": self.source,
            "face_index": 0,
            "world_co": Vector((0.0, 0.0, 0.0)),
            "screen_co": Vector((0.0, 0.0)),
        }
        self.assertEqual(
            self.operator.modal(self.context, make_event("LEFTMOUSE", "PRESS")),
            {"RUNNING_MODAL"},
        )
        self.assertEqual(self.operator.state, "PLACE_LABEL")
        self.assertEqual(
            self.operator.modal(self.context, make_event("X", "PRESS")),
            {"RUNNING_MODAL"},
        )
        self.operator.hover_snap = {
            "type": "WORLD",
            "label": "Point",
            "world_co": Vector((3.0, 4.0, 0.0)),
            "screen_co": Vector((0.0, 0.0)),
        }
        self.assertEqual(
            self.operator.modal(
                self.context,
                make_event("TEXTINPUT", "PRESS", ascii_character="2"),
            ),
            {"RUNNING_MODAL"},
        )
        self.assertTrue(self.operator.distance_input_valid)
        self.assertEqual(tuple(self.operator.label_snap["world_co"]), (2.0, 0.0, 0.0))
        self.assertEqual(
            self.operator.modal(self.context, make_event("LEFTMOUSE", "PRESS")),
            {"FINISHED"},
        )
        annotation = bpy.context.view_layer.objects.active
        self.assertEqual(annotation.dimension_props.annotation_kind, "AREA")
        self.assertEqual(annotation.dimension_props.dimension_type, "X")
        self.assertAlmostEqual(annotation.dimension_props.area_value, 4.0)

    def _face_snap(self, obj=None, **extra):
        return {
            "type": "FACE",
            "label": "Face",
            "object": self.source if obj is None else obj,
            "face_index": 0,
            "world_co": Vector((0.0, 0.0, 0.0)),
            "screen_co": Vector((0.0, 0.0)),
            **extra,
        }

    def test_step_back_forgets_the_picked_faces(self):
        self.operator.hover_snap = self._face_snap()
        self.operator.modal(self.context, make_event("LEFTMOUSE", "PRESS"))
        self.assertEqual(self.operator.state, "PLACE_LABEL")
        self.assertEqual(self.operator.modal(self.context, make_event("BACK_SPACE", "PRESS")), {"RUNNING_MODAL"})
        self.assertEqual(self.operator.state, "PICK_FACE")
        self.assertEqual(self.operator.face_indices, [])
        self.assertIsNone(self.operator.source_object)
        self.assertEqual(self.operator._prompt(), "Click a face; Shift-click adds more")

    def test_a_construction_grid_is_never_an_area_source(self):
        from dimensions.collections import create_guide_plane_object

        grid = create_guide_plane_object(
            self.context, (Vector(), Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))), 1.0, 0.5,
        )
        self.operator.hover_snap = self._face_snap(grid, guide_plane=True)
        with patch("dimensions.operators.create_area.raycast_from_mouse", return_value=None):
            result = self.operator.modal(self.context, make_event("LEFTMOUSE", "PRESS"))
        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertEqual(self.operator.state, "PICK_FACE")
        self.assertIsNone(self.operator.source_object)
        self.assertTrue(self.operator.reports)

    def test_trackpad_ndof_and_numpad_view_keys_reach_blender(self):
        for event_type in NAVIGATION_EVENT_TYPES:
            with self.subTest(event=event_type):
                self.assertEqual(self.operator.modal(self.context, make_event(event_type, "NOTHING")), {"PASS_THROUGH"})


class TransientMeasureModalTests(unittest.TestCase):
    def setUp(self):
        self.context = make_context(scene=bpy.context.scene)
        self.context.view_layer = bpy.context.view_layer
        self.context.window_manager = SimpleNamespace(clipboard="")
        self.operator = make_operator_harness(
            CADDIM_OT_Measure,
            persistent_mode=False,
            state="PICK_START",
            axis="ALIGNED",
            continuous_placement=True,
            start_world=None,
            start_snap=None,
            end_world=None,
            hover_snap=None,
            distance_text="",
            distance_input_valid=True,
            inference_session=InferenceSession(),
            completed_start_world=None,
            completed_end_world=None,
        )
        self.reports = self.operator.reports
        remember_session_context(self.operator, self.context)
        self.before_names = {obj.name for obj in get_or_create_guide_collection(self.context).objects}

    def tearDown(self):
        collection = get_or_create_guide_collection(self.context)
        for obj in list(collection.objects):
            if obj.name not in self.before_names:
                bpy.data.objects.remove(obj, do_unlink=True)
        clear_state("MEASURE", self.context)

    def _drive_segment(self, start=(0, 0, 0), end=(3, 4, 0)):
        provider = ScriptedSnapProvider([make_snap(start), make_snap(end)])
        with patch("dimensions.operators.measure.find_nearest_snap_point", provider):
            self.operator.modal(self.context, make_event("LEFTMOUSE", "PRESS"))
            self.operator.modal(self.context, make_event("MOUSEMOVE", "PRESS"))
            return self.operator.modal(self.context, make_event("LEFTMOUSE", "PRESS"))

    def _measurement_count(self):
        return sum(
            1 for obj in get_or_create_guide_collection(self.context).objects
            if hasattr(obj, "guide_props")
            and obj.guide_props.enabled
            and getattr(obj.guide_props, "kind", "GUIDE") == "MEASUREMENT"
        )

    def test_two_points_create_nothing_and_chain_from_the_second_point(self):
        before = self._measurement_count()
        before_objects = len(get_or_create_guide_collection(self.context).objects)
        self.assertEqual(self._drive_segment(), {"RUNNING_MODAL"})
        self.assertEqual(self._measurement_count(), before)
        self.assertEqual(len(get_or_create_guide_collection(self.context).objects), before_objects)
        self.assertEqual(tuple(self.operator.completed_start_world), (0.0, 0.0, 0.0))
        self.assertEqual(tuple(self.operator.completed_end_world), (3.0, 4.0, 0.0))
        self.assertEqual(tuple(self.operator.start_world), (3.0, 4.0, 0.0))
        self.assertEqual(self.operator.state, "PICK_END")

    def test_save_creates_exactly_one_persistent_measurement(self):
        before = self._measurement_count()
        self._drive_segment()
        result = self.operator.modal(self.context, make_event("P", "PRESS"))
        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertEqual(self._measurement_count(), before + 1)

    def test_copy_uses_the_current_formatted_total_and_components(self):
        self._drive_segment((1, 5, 2), (4, 1, 14))
        event = make_event("C", "PRESS")
        event.ctrl = True
        result = self.operator.modal(self.context, event)
        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertIn("Distance", self.context.window_manager.clipboard)
        self.assertIn("ΔX", self.context.window_manager.clipboard)
        self.assertIn("ΔY", self.context.window_manager.clipboard)
        self.assertIn("ΔZ", self.context.window_manager.clipboard)

    def test_copy_binding_does_not_intercept_typed_centimetres(self):
        self.operator.state = "PICK_END"
        self.operator.start_world = make_snap((0, 0, 0))["world_co"]
        self.operator.hover_snap = None
        self.operator.distance_text = "2"
        event = make_event("C", "PRESS", ascii_character="c")
        self.assertEqual(self.operator.modal(self.context, event), {"RUNNING_MODAL"})
        self.assertEqual(self.operator.distance_text, "2c")
        self.assertEqual(self.context.window_manager.clipboard, "")

    def test_cancel_clears_only_the_invoking_viewport_state(self):
        other = make_context(scene=bpy.context.scene)
        set_state("MEASURE", {"marker": "current"}, self.context)
        set_state("MEASURE", {"marker": "other"}, other)
        result = self.operator.modal(self.context, make_event("RIGHTMOUSE", "PRESS"))
        self.assertEqual(result, {"CANCELLED"})
        self.assertIsNone(get_state("MEASURE", self.context))
        self.assertEqual(get_state("MEASURE", other)["marker"], "other")
        clear_state("MEASURE", other)


def main():
    dimensions.register()
    try:
        loader = unittest.defaultTestLoader
        suite = unittest.TestSuite(
            loader.loadTestsFromTestCase(case)
            for case in (
                PointPlacementStateTests,
                ModalCleanupTests,
                HandleManipulationStateTests,
                InteractionContextTests,
                CreateDimensionModalTests,
                ChainDimensionModalTests,
                ConstructionToolModalTests,
                CreateAngleModalTests,
                CreateAreaModalTests,
                TransientMeasureModalTests,
            )
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        dimensions.unregister()

    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
