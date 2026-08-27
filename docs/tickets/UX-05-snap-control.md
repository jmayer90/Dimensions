# UX-05 — User control over which snap targets are active

**Milestone:** M2 Fluency
**Status:** ⬜ Planned.
**Effort:** S
**Depends on:** FND-04
**Version impact:** Patch.

## Problem

Snapping always considers every target type: vertices, edges, midpoints, face centers, face points, guides, and measurement endpoints, midpoints, and segments. There is no way to turn any of them off.

On dense geometry this makes precise acquisition frustrating. Trying to hit a midpoint next to a cluster of vertices means fighting the vertex snap. Trying to place a point on a face surface means fighting every edge crossing it. The scoring in `_best_snap_candidate()` is reasonable, but no scoring function substitutes for the user saying "I want midpoints right now."

Blender's own snapping has exactly this control, so users arrive expecting it and are surprised by its absence.

`UX-03` makes this sharper: inference adds more candidate types, and without filtering the noise compounds.

## Why it matters for 1.0

Small, cheap, and directly addresses the most common precision-tool complaint. It also derisks `UX-03` by giving users a way to quiet inference they do not want.

## Approach

**Store the enabled set in preferences** (per-user working style, `FND-04`) with a scene-level override for documents that need particular behavior. Follow the same defaults relationship the preferences ticket establishes.

**Expose it in two places, both necessary:**

- A compact row of toggle icons in the Dimensions sidebar panel, mirroring how Blender presents its own snap targets in the header. This is where users set it up.
- A modal key to cycle or toggle target types during acquisition, because the need usually becomes apparent mid-operation. Coordinate with `FND-05` so this is rebindable.

**Filter at candidate generation, not at scoring.** Skipping disabled types before generating candidates is both faster and simpler than generating then discarding, and it means disabling types measurably improves performance on dense scenes.

**Show the active set.** The viewport status text should indicate which target types are live, otherwise a user who left vertices off will be confused later.

## Acceptance criteria

- [ ] Each snap target type — vertex, edge, midpoint, face center, face point, guide, measurement endpoint, measurement midpoint, measurement segment — can be independently enabled or disabled.
- [ ] The setting lives in preferences with a scene override, following the `FND-04` defaults rule.
- [ ] A toggle row appears in the Dimensions sidebar panel.
- [ ] A modal key adjusts active targets during acquisition without cancelling the operation.
- [ ] Disabled types are skipped before candidate generation, and disabling types measurably reduces snap query time on the `FND-08` reference scenes.
- [ ] Viewport status text shows the active target set.
- [ ] Disabling every target type still allows free world-point placement rather than making the tool unusable.
- [ ] Settings persist across sessions and survive add-on disable and re-enable.
- [ ] README documents the control.

## Code map

- `dimensions/snapping.py` — candidate generation entry points, `_best_snap_candidate()`.
- `dimensions/projected_snap.py` — vertex candidate generation.
- `dimensions/preferences.py` — the enabled set.
- `dimensions/properties.py` — `CADDIM_PG_SceneSettings` override.
- `dimensions/ui.py` — the toggle row.
- `dimensions/interaction.py` — modal key handling.
- `dimensions/drawing.py` — `_draw_interaction_status()`.

## Verification

- A test per target type asserting that disabling it removes exactly those candidates and leaves others intact.
- A test that disabling all types still permits world-point placement.
- A performance check confirming disabled types are not generated, not merely filtered.

## Out of scope

- Changing the scoring function for enabled types.
- Per-annotation-type snap profiles (for example, "areas only snap to faces"). Possibly useful later; not now.

## Invariants

- **One interaction contract.** The modal toggle must work identically across all acquisition tools.
