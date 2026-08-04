# CON-02 — Offset and parallel guides at a typed distance

**Milestone:** M3 Construction
**Effort:** M
**Depends on:** CON-01
**Version impact:** Patch. Additive.

## Problem

Guides are created by picking points. There is no way to say "a guide parallel to this edge, 400 mm away" — the single most common construction operation in any drafting workflow.

Laying out a facade with 600 mm mullion spacing, setting a 50 mm margin inside a panel edge, establishing a centreline between two faces: all of these are *derived* guides. Constructing them by picking points means computing the position yourself first, which defeats the purpose of a construction tool.

Combined with `CON-01`'s guide points, offset guides are what let a user build a dimensionally correct framework before modelling anything — the workflow the project is ultimately aiming at.

## Why it matters for 1.0

This is where construction guides stop being markers and start being a layout system. Not a 1.0 gate item, but the strongest single argument for the tool's construction claim.

## Approach

**Offset from a source, keeping the relationship.** The important design decision: does an offset guide remember its source, or is it baked at creation?

Recommend **remembering**. Store a reference to the source (an edge, a face, another guide) plus an offset vector or scalar distance, and resolve position the way anchors resolve today. Moving the source moves the offset guide. This is what makes it a construction system rather than a one-time calculation, and it reuses the source/presentation separation the project already has.

Provide "detach" to convert a derived guide into a fixed one, for cases where the relationship becomes unwanted, and handle a lost source with the same repair-state model as everything else (`UX-07`).

**Offset sources to support:**

- Parallel to an existing edge, at a distance and a side.
- Parallel to an existing guide, same.
- Offset from a face plane along its normal.
- Midway between two parallel edges, guides, or faces — the centreline case, worth special-casing because it is so common.

**Typed distance with direction control.** Reuse the existing numeric entry from `interaction.py`, so `400mm` and `2ft` work as they do everywhere else. The offset side needs to be pickable — mouse position choosing the side with a live preview is the natural interaction, with an explicit flip key.

**Preview before commit**, as everywhere else: show the resulting guide and its distance before the user confirms.

## Acceptance criteria

- [ ] A guide can be created parallel to an edge, to another guide, or offset from a face plane, at a typed distance.
- [ ] A centreline guide can be created midway between two parallel sources.
- [ ] Offset guides store their source relationship and update when the source moves.
- [ ] Offset side is chosen by mouse position with a live preview, and an explicit key flips it.
- [ ] Typed distance uses the standard numeric entry, accepting the same unit expressions as every other tool.
- [ ] A "detach" action converts a derived guide to a fixed one.
- [ ] A lost source puts the guide into a visible repair state, consistent with `UX-07`.
- [ ] Offset guides are snap targets like any other guide.
- [ ] Chained derivation works — an offset from an offset resolves correctly — and cycles are detected and refused rather than looping.
- [ ] Creation is a single undo step.
- [ ] Schema changes go through the `FND-02` migration framework.
- [ ] README and `DESIGN.md` document derived guides and the source relationship.

## Code map

- `dimensions/properties.py` — `CADDIM_PG_Guide`, source reference and offset storage.
- `dimensions/operators/create_guide.py` — `CADDIM_OT_CreateGuide` and new offset operators.
- `dimensions/anchors.py` — the source-resolution pattern to follow.
- `dimensions/scene_sync.py` — resolving derived guides when sources move; where cycle detection belongs.
- `dimensions/snapping.py` — `guide_line_world()`, `construction_segment_world()`.
- `dimensions/drawing.py` — preview and derived-guide display.
- `dimensions/interaction.py` — numeric entry, side flip key.

## Verification

- Tests for each offset source type against known geometry.
- A test that moving a source updates the derived guide.
- A test that chained derivation resolves in the correct order.
- A cycle-detection test asserting refusal rather than infinite recursion or a hang.
- A test that detach produces a fixed guide with the same position.
- A test that a deleted source produces a repair state, not a wrong position.

## Out of scope

- Guide planes — `CON-03`.
- Repeated spacing and arrays — `CON-04`.
- A general constraint solver. Derived guides resolve in dependency order from their sources; they do not solve mutual constraints.
- Offsetting mesh geometry, which is geometry authoring and excluded.

## Invariants

- **Non-destructive annotation.** No mesh is created or modified.
- **Truthful state.** A derived guide whose source is gone must be visibly broken, never silently frozen at its last position.
- **Source/presentation separation.** The source relationship determines position; user-facing display properties stay independent.
