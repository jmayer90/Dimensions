"""A scripted stand-in for the snapping backend.

``find_nearest_snap_point`` normally raycasts the depsgraph and reads mesh data. Tests
replace it with a provider that hands back a predetermined sequence of snaps, so a
pick-pick-place sequence is fully determined by the script rather than by scene state.
"""

from mathutils import Vector


def make_snap(world_co, screen_co=(0.0, 0.0), snap_type="WORLD", label="Point", obj=None, vertex_index=-1):
    """Build a snap dictionary shaped like the one ``snapping.py`` returns."""
    snap = {
        "world_co": Vector(world_co),
        "screen_co": Vector(screen_co),
        "type": snap_type,
        "label": label,
        "object": obj,
        "vertex_index": vertex_index,
    }
    return snap


class ScriptedSnapProvider:
    """Return queued snaps in order, then repeat the last one.

    Repeating the final snap keeps mouse-move traffic from exhausting the script; tests
    care about the sequence of accepted points, not about how many times the tool
    re-queried the same hover position.
    """

    def __init__(self, snaps=()):
        self.snaps = [make_snap(snap) if not isinstance(snap, dict) else snap for snap in snaps]
        self.query_count = 0
        self._index = 0

    def __call__(self, context, mouse_x, mouse_y, **kwargs):
        self.query_count += 1
        if not self.snaps:
            return None
        snap = self.snaps[min(self._index, len(self.snaps) - 1)]
        self._index += 1
        return dict(snap, world_co=snap["world_co"].copy(), screen_co=snap["screen_co"].copy())

    def push(self, snap):
        self.snaps.append(snap if isinstance(snap, dict) else make_snap(snap))

    def reset(self):
        self._index = 0
        self.query_count = 0


class EmptySnapProvider:
    """Always misses, for exercising the "nothing under the cursor" paths."""

    def __init__(self):
        self.query_count = 0

    def __call__(self, context, mouse_x, mouse_y, **kwargs):
        self.query_count += 1
        return None
