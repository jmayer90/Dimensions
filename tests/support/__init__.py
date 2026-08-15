"""Reusable headless stand-ins for the pieces of Blender that modal operators need.

Modal tools normally require a live 3D viewport: a region to project into, a
``region_data`` carrying the view matrices, and a snapping backend that reads the
depsgraph. The helpers here supply all three from plain Python so the adapter layer
and the state machines underneath it can be driven in a background Blender session.
"""

from .fake_context import (
    FakeArea,
    FakeContext,
    FakeEvent,
    FakeRegion,
    FakeRegionData,
    FakeWindow,
    make_context,
    make_event,
    typing_events,
    world_point,
)
from .operator_harness import make_operator_harness
from .snap_provider import EmptySnapProvider, ScriptedSnapProvider, make_snap

__all__ = (
    "EmptySnapProvider",
    "FakeArea",
    "FakeContext",
    "FakeEvent",
    "FakeRegion",
    "FakeRegionData",
    "FakeWindow",
    "ScriptedSnapProvider",
    "make_context",
    "make_event",
    "make_operator_harness",
    "make_snap",
    "typing_events",
    "world_point",
)
