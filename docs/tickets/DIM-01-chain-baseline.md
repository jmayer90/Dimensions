# DIM-01 — Chain and baseline dimensions

**Milestone:** M5 Documentation-grade
**Status:** ✅ Complete — persistent sets delivered; creation, repair, collision, and output paths hardened in the 0.6.0 candidate.
**Effort:** M
**Depends on:** UX-01
**Version impact:** Patch. Additive.

## Problem

Every dimension is independent. Annotating a row of holes means placing each dimension separately, then manually aligning them so they read as a set — and any change to the model breaks the alignment.

Drafting has two standard answers, and neither exists here:

- **Chain (continuous) dimensions** — a run of dimensions end to end, each starting where the last ended, sharing one dimension line. Used for sequential features along an edge.
- **Baseline (ordinate) dimensions** — several dimensions from one common origin, stacked at increasing offsets. Used where cumulative tolerance matters, since each measurement references the datum rather than its neighbor.

Both are listed in `DESIGN.md` P2. Their absence is the clearest gap against documentation-grade output, and the alignment problem makes the current workaround genuinely bad rather than merely tedious.

## Why it matters for 1.0

Not a 1.0 gate item. But these are what most distinguishes a dimensioning tool from a measuring tool, and `UX-01` makes them natural to build.

## Approach

**Model the set, not just the members.** A chain or baseline is a relationship: members share a dimension line direction, a common origin (baseline) or sequential linkage (chain), and a spacing rule for stacked offsets. Store the set as an object holding the shared configuration plus its member anchors, rather than as N independent dimensions that happen to line up.

This is the same definition-versus-instance decision as `CON-04`'s spaced guides. Answer it the same way for consistency, and cross-reference whichever ticket lands first.

**Creation extends continuous placement.** `UX-01` establishes repeating without re-invoking. Chain creation is that plus "the next dimension starts where the last ended." Baseline is that plus "the next dimension starts at the datum and stacks one row further out." Both should feel like the same tool in a different mode, not separate tools.

- Chain: pick datum, pick each subsequent point; each segment commits as you go.
- Baseline: pick datum, pick each measured point; each new dimension offsets one step further from the last.

**Automatic offset stacking.** For baseline, offset spacing must be automatic and consistent, derived from text size so labels never collide. Make it adjustable but correct by default — a baseline set whose labels overlap is worse than no feature.

**Editing the set.** Inserting a point mid-chain must renumber and reflow the rest. Deleting a member must close the chain. Changing the shared offset must move every member. These are the operations that make it a set rather than a snapshot, and they are where a naive implementation falls apart.

**Label collision.** Chain dimensions with short segments produce overlapping text. Standard drafting practice moves the label outside with a leader. Detect the collision and handle it, or document the limitation explicitly — do not ship silently overlapping labels.

## Acceptance criteria

- [x] A chain dimension set can be created by picking a datum then successive points, committing each segment as it is placed.
- [x] A baseline dimension set can be created by picking a datum then successive points, each stacking one offset further out.
- [x] Set members share direction and dimension line, and stay aligned when source geometry moves.
- [x] Baseline offset spacing derives from text size by default and never overlaps labels at default settings; it is user-adjustable.
- [x] Inserting a point mid-chain renumbers and reflows subsequent members.
- [x] Deleting a member closes the chain correctly.
- [x] Changing the shared offset moves every member.
- [x] A set appears as one entry in the `UX-02` manager, expandable to members.
- [x] Short segments do not produce overlapping labels, or the limitation is documented.
- [x] Members use existing anchor types and enter repair states individually per `UX-07`.
- [x] Each creation step is a single undo step.
- [x] Sets generate correctly through `OUT-01` if it has landed.
- [x] Schema changes go through the `FND-02` migration framework.
- [x] README and `DESIGN.md` document both types.

## Code map

- `dimensions/properties.py` — set kind, ordered member anchors, shared offset, spacing, and active member storage.
- `dimensions/operators/dimension_set.py` — continuous creation plus insert/delete editing.
- `dimensions/dimension_sets.py` — shared direction, stacked baseline geometry, reflow, and member-local state.
- `dimensions/drawing.py`, `dimensions/output_geometry.py` — overlay collision handling and Grease Pencil/vector strokes.
- `dimensions/annotation_manager.py`, `dimensions/repair.py`, `dimensions/ui.py` — one-row expandable management and member-local repair/editing.

## Verification

- Geometry tests asserting members share a dimension line and correct stacked offsets.
- Tests for insert, delete, and reorder, asserting the set stays coherent.
- A test that moving source geometry keeps members aligned.
- A test that a member entering a repair state does not break the rest of the set.
- Label collision tests at small segment lengths.

`tests/dimension_set_smoke.py` verifies the persistent one-object model, shared
chain alignment, automatic and explicit baseline spacing, insert/delete reflow,
source motion, member-local repair state, one-row manager representation,
per-member undo dispatch, and OUT-01 stroke generation. `tests/blender_lifecycle.py`
opens the released schema-v2 fixture through the sequential v6 → v7 → v8 path
and performs a real save/reload of a populated chain set.

The 0.6.0 hardening pass adds stable-direction and invalid-projection geometry
coverage, shared-anchor repair propagation, reorder/hit/collision regressions, and
adapter tests for continued creation, inference, active planes, axis/typed input,
step-back, Edit Mode, and insert cleanup. Foreground follow-up makes the first
member's axis/plane authoritative for preview and commit, restores the native
snap aperture ahead of unlocked inference, refuses duplicate/reverse/off-axis
members before persistence, and renders incompatible saved members as bounded
Needs Repair geometry instead of shared-axis spokes.

## Out of scope

- Radial, diameter, and arc-length — `DIM-02`.
- Coordinate and elevation dimensions — `DIM-03`, though ordinate dimensioning is closely related to baseline and the two should be checked for shared structure.
- Automatic dimension placement, where the tool chooses what to dimension. Much larger and separate.

## Invariants

- **Source/presentation separation.** Set membership and shared configuration are presentation; each member's anchors remain its own source binding.
- **Stable presentation.** A set must stay readable and aligned through unrelated topology and mode changes.
