# DIM-01 — Chain and baseline dimensions

**Milestone:** M5 Documentation-grade
**Status:** ⬜ Planned.
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

- [ ] A chain dimension set can be created by picking a datum then successive points, committing each segment as it is placed.
- [ ] A baseline dimension set can be created by picking a datum then successive points, each stacking one offset further out.
- [ ] Set members share direction and dimension line, and stay aligned when source geometry moves.
- [ ] Baseline offset spacing derives from text size by default and never overlaps labels at default settings; it is user-adjustable.
- [ ] Inserting a point mid-chain renumbers and reflows subsequent members.
- [ ] Deleting a member closes the chain correctly.
- [ ] Changing the shared offset moves every member.
- [ ] A set appears as one entry in the `UX-02` manager, expandable to members.
- [ ] Short segments do not produce overlapping labels, or the limitation is documented.
- [ ] Members use existing anchor types and enter repair states individually per `UX-07`.
- [ ] Each creation step is a single undo step.
- [ ] Sets generate correctly through `OUT-01` if it has landed.
- [ ] Schema changes go through the `FND-02` migration framework.
- [ ] README and `DESIGN.md` document both types.

## Code map

- `dimensions/properties.py` — set property group and member storage.
- `dimensions/operators/create_dimension.py` — creation flow to extend.
- `dimensions/dimension_geometry.py` — shared dimension line and stacked offset geometry.
- `dimensions/drawing.py` — set rendering and label collision handling.
- `dimensions/interaction.py` — continuous placement from `UX-01`.
- `dimensions/ui.py` — set editing.

## Verification

- Geometry tests asserting members share a dimension line and correct stacked offsets.
- Tests for insert, delete, and reorder, asserting the set stays coherent.
- A test that moving source geometry keeps members aligned.
- A test that a member entering a repair state does not break the rest of the set.
- Label collision tests at small segment lengths.

## Out of scope

- Radial, diameter, and arc-length — `DIM-02`.
- Coordinate and elevation dimensions — `DIM-03`, though ordinate dimensioning is closely related to baseline and the two should be checked for shared structure.
- Automatic dimension placement, where the tool chooses what to dimension. Much larger and separate.

## Invariants

- **Source/presentation separation.** Set membership and shared configuration are presentation; each member's anchors remain its own source binding.
- **Stable presentation.** A set must stay readable and aligned through unrelated topology and mode changes.
