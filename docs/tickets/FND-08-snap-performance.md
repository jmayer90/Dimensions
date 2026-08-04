# FND-08 — Snap performance budgets on dense scenes

**Milestone:** M1 Foundation
**Effort:** M
**Depends on:** —
**Version impact:** Patch.

## Problem

`DESIGN.md` known risk 1 states that snap cache rebuild cost after geometry, transform, and view changes "still needs foreground measurement," and the README warns rebuilds "can still be noticeable on very dense scenes." Neither statement is backed by a number, so there is no way to tell whether a change made it better or worse.

The architecture is sound — `projected_snap.py` maintains a per-viewport spatial cache with ray-based occlusion rejection, which replaced naive all-vertex projection. What is missing is measurement and a budget.

Concerns worth measuring:

- Full cache rebuild cost as a function of visible vertex count.
- Rebuild frequency: orbiting invalidates on view change, and modeling invalidates on every depsgraph update. During a drag, that may be every frame.
- Whether rebuilds happen on the main thread during modal interaction, which is where a stall is felt as input lag.
- `_is_visible()` raycast cost per candidate, and how it scales with candidate count.
- Edit Mode paths — `_nearest_projected_edit_mesh_element()`, `_raycast_edit_mesh()` — which have a different cost profile than Object Mode.

## Why it blocks 1.0

Snapping is the core interaction. If it stalls, the tool feels broken regardless of correctness. `UX-03` adds inference candidates on top of the existing acquisition, which will make an unmeasured baseline worse in ways nobody can attribute.

## Approach

**Define reference scenes.** Add a generator under `tests/` producing repeatable scenes at several densities — for example 100k, 1M, and 5M visible vertices — plus a high-object-count variant (10,000 objects of 100 vertices each), since object count and vertex count stress different paths.

**Instrument.** Add opt-in timing around cache build, cache query, and occlusion rejection, reporting to console when enabled. Gate it behind a preference or environment variable so it costs nothing when off.

**Measure and record.** Publish a table in `DESIGN.md`: scene, operation, time, hardware. This replaces known risk 1's prose.

**Set budgets and meet them.** Proposed, adjust once real numbers exist:

- Snap query during modal interaction: **under 8 ms**, so a hover stays inside a 120 fps frame.
- Full cache rebuild: **under 100 ms** on the 1M-vertex reference scene.
- No rebuild triggered by a view change that does not change which objects are visible.

**Optimize only where measurement points.** Likely candidates, in order of expected value: avoid full rebuilds when only the view rotated, budget rebuilds incrementally across frames rather than doing all work in one, cache occlusion results per candidate per view, and cull by visible bounds before projecting vertices.

## Acceptance criteria

- [ ] A reference scene generator exists and produces identical scenes run to run.
- [ ] Opt-in instrumentation reports cache build, query, and occlusion timings, and is inert when disabled.
- [ ] Measurements for every reference scene are recorded in `DESIGN.md` with hardware noted.
- [ ] Documented budgets are stated and met, or a specific follow-up ticket explains what prevents meeting them.
- [ ] A view change that does not change object visibility does not trigger a full rebuild.
- [ ] Snapping remains correct at every density — occlusion rejection does not degrade under optimization.
- [ ] Edit Mode and Object Mode paths are both measured.
- [ ] `DESIGN.md` known risk 1 is replaced with data; the README limitation is updated to say something specific.

## Code map

- `dimensions/projected_snap.py` — cache build, `_is_visible()`.
- `dimensions/snapping.py` — `_best_snap_candidate()`, `_nearest_projected_vertex()`, `_nearest_projected_edit_mesh_element()`, `_raycast_edit_mesh()`, `_edit_mesh_projected_vertex_priority()`.
- `dimensions/scene_sync.py` — what triggers invalidation.
- `dimensions/viewport_state.py` — per-viewport cache lifetime.
- `tests/` — generator and benchmark harness.

## Verification

- A repeatable benchmark script, run by hand, reporting a table.
- Correctness tests at high density asserting the same snap results as at low density for equivalent geometry.
- A test asserting no rebuild occurs on a pure view rotation with unchanged visibility.

## Out of scope

- Adding new snap target types — `UX-03`, `CON-01`.
- Draw performance — `FND-03`.
- Multithreaded cache building. Consider only if single-threaded work cannot meet budget; Blender's threading constraints make it a separate design problem.

## Invariants

- **Preview before commit.** Optimization must not delay or suppress the hover preview; a fast wrong preview is worse than a slightly slower correct one.
