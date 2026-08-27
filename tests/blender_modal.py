"""Headless coverage for modal interaction state, driven without a live viewport.

Run with ``blender --background --factory-startup --python tests/blender_modal.py``.

These tests exercise the interaction contract that the changelog keeps revisiting:
stage transitions, axis locks, typed distances, step-back, and cancellation. They use
``tests/support`` rather than a real 3D view, so a regression here is reported by the
suite instead of by a user.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import dimensions
from dimensions.collections import get_or_create_dimension_collection
from dimensions.drawing import _draw_interaction_status
from dimensions.interaction import remember_session_context, session_axis, session_context_changed
from dimensions.modal_state import PointPlacementState
from dimensions.operators.create_dimension import CADDIM_OT_CreateDimension
from dimensions.ui import CADDIM_PT_MainPanel

from support import (
    EmptySnapProvider,
    ScriptedSnapProvider,
    make_context,
    make_event,
    make_operator_harness,
    make_snap,
)


PICK_START = PointPlacementState.PICK_START
PICK_END = PointPlacementState.PICK_END
PLACE = PointPlacementState.PLACE


class LayoutRecorder:
    """Small stand-in for the sidebar layout used by the UI contract test."""

    def __init__(self):
        self.labels = []
        self.properties = []
        self.operators = []
        self.enabled = True

    def box(self):
        return self

    def column(self):
        return self

    def row(self):
        return self

    def label(self, *, text, **_kwargs):
        self.labels.append(text)

    def prop(self, target, name, **kwargs):
        self.properties.append((target, name, kwargs))

    def operator(self, identifier, **_kwargs):
        self.operators.append(identifier)
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

    def test_sidebar_exposes_direction_before_a_placement_session_starts(self):
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

        self.assertIn("Next Placement Direction", layout.labels)
        self.assertIn(
            (preferences, "default_axis_mode", {"text": "Direction", "expand": True}),
            layout.properties,
        )


class CreateDimensionModalTests(unittest.TestCase):
    """The operator as a thin adapter over the contract, with a scripted viewport."""

    def setUp(self):
        self.operator = make_operator_harness(
            CADDIM_OT_CreateDimension,
            _state_machine=PointPlacementState(),
            hover_snap=None,
            start_snap=None,
            end_snap=None,
            offset_distance=0.25,
            offset_plane_normal=None,
            axis_gesture_active=False,
            continuous_placement=False,
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

    def test_selectable_axis_status_identifies_the_pre_pick_keys(self):
        with patch("dimensions.drawing._draw_text_left") as draw_text:
            _draw_interaction_status({"axis": "X", "axis_selectable": True})

        self.assertIn("Direction: X (press A/X/Y/Z)", draw_text.call_args.args[0])

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


def main():
    dimensions.register()
    try:
        loader = unittest.defaultTestLoader
        suite = unittest.TestSuite(
            loader.loadTestsFromTestCase(case)
            for case in (PointPlacementStateTests, InteractionContextTests, CreateDimensionModalTests)
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        dimensions.unregister()

    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
