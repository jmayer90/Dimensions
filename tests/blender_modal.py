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
from mathutils import Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import dimensions
from dimensions.collections import get_or_create_dimension_collection, get_or_create_guide_collection
from dimensions.drawing import _draw_interaction_status
from dimensions.interaction import remember_session_context, session_axis, session_context_changed
from dimensions.inference import InferenceSession
from dimensions.modal_state import HandleManipulationState, PointPlacementState
from dimensions.operators.create_dimension import CADDIM_OT_CreateDimension
from dimensions.operators.measure import CADDIM_OT_Measure
from dimensions.operators.angular_spacing import angular_preview_state
from dimensions.viewport_state import clear_state, get_state, set_state
from dimensions.ui import CADDIM_PT_MainPanel, CADDIM_PT_MeshSelection

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


class AngularGuideModalStateTests(unittest.TestCase):
    def setUp(self):
        self.source = {"kind": "LINE", "origin": Vector(), "direction": Vector((1.0, 0.0, 0.0))}

    def test_preview_contains_result_line_and_typed_angle_label(self):
        state = angular_preview_state(self.source, Vector((2.0, 3.0, 0.0)), 1.5707963267948966)
        self.assertEqual(tuple(state["start_world"]), (2.0, 3.0, 0.0))
        self.assertAlmostEqual(state["end_world"].x, 2.0, places=5)
        self.assertAlmostEqual(state["end_world"].y, 4.0, places=5)
        self.assertEqual(state["derived_label"], "90.000°")

    def test_flip_changes_signed_solution_without_changing_pivot(self):
        normal = angular_preview_state(self.source, Vector(), 0.5, False)
        flipped = angular_preview_state(self.source, Vector(), 0.5, True)
        self.assertEqual(normal["start_world"], flipped["start_world"])
        self.assertAlmostEqual(normal["end_world"].x, flipped["end_world"].x, places=5)
        self.assertAlmostEqual(normal["end_world"].y, -flipped["end_world"].y, places=5)
        self.assertTrue(flipped["flipped"])


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
        self.assertEqual(layout.events.count("COLUMN"), 2)
        self.assertLess(
            layout.events.index(("OPERATOR", "dimensions.create_dimension")),
            layout.events.index(("PROPERTY_ENUM", "default_axis_mode", "ALIGNED")),
        )

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
            "dimensions.create_area",
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
            start_snap=None,
            end_snap=None,
            offset_distance=0.25,
            offset_plane_normal=None,
            axis_gesture_active=False,
            continuous_placement=False,
            inference_axis="ALIGNED",
            inference_session=InferenceSession(),
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
            axis_gesture_active=False,
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
                AngularGuideModalStateTests,
                HandleManipulationStateTests,
                InteractionContextTests,
                CreateDimensionModalTests,
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
