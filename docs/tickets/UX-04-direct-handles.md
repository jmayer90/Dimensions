# UX-04 — Direct viewport handles for placement, radius, and offset

**Milestone:** M2 Fluency
**Status:** ✅ Complete in 0.4.3.
**Effort:** M
**Depends on:** FND-01
**Version impact:** Patch.

## Problem

Adjusting an existing annotation means editing numbers in the sidebar or re-running a dedicated operator:

- Angle radius is a `FloatProperty` slider.
- Area label position requires invoking **Move Label**.
- Linear offset distance is a sidebar number, though the annotation Empty can be dragged with Blender's transform tools.

The result is inconsistent: some placement is direct manipulation, some is a number field, some is a modal operator. A user who drags an area label expects the same to work for an angle radius, and it does not.

This is a P0 roadmap item — "direct viewport handles for Angle radius and Area label placement."

## Why it matters for 1.0

Placement is iterative. Nobody gets a label position right the first time, and the current loop — select, find the property, drag a slider, look, repeat — is slow enough that users leave labels badly placed.

## Approach

**Draw handles for the selected annotation only.** Showing handles for everything would make a dimensioned scene unreadable. The existing `_draw_selected_object_overlay()` in `drawing.py` is the natural place.

**Handle set by annotation kind:**

- **Linear** — offset distance handle on the dimension line; extension line endpoints if `DIM-04` adds gap and overshoot control.
- **Angle** — arc radius handle on the arc.
- **Area** — label position handle, matching what **Move Label** does today.
- **All** — label position, once labels can be offset from their default placement.

**Reuse the modal contract, do not invent a drag.** A handle drag should behave like the corresponding creation stage: axis constraints with `A`/`X`/`Y`/`Z`, typed numeric entry, `Esc` to cancel, click or `Enter` to confirm. This is the point of having one interaction contract, and it means dragging a radius handle and typing `50mm` works exactly as it does during creation.

**Consequence:** the existing **Move Label** and radius editing operators become the same code path the handle uses, rather than parallel implementations. Keep the operators — they are useful for keyboard-driven work and for users who cannot see the handle — but have them share the underlying logic.

**Hit testing** extends the mechanism `FND-01` establishes. Handles take priority over annotation-body selection when both are under the cursor.

## Acceptance criteria

- [x] Handles are drawn only for selected annotations.
- [x] Angle radius, area label position, and linear offset each have a draggable handle.
- [x] Dragging a handle supports axis constraints, typed numeric entry, `Esc` cancel, and click or `Enter` confirm, identical to the creation stages.
- [x] Handle drags are a single undo step, and cancelling restores the prior value exactly.
- [x] Handles are visually distinct from snap indicators and from the annotation geometry.
- [x] Handle hit testing takes priority over annotation selection at the same cursor position.
- [x] Existing **Move Label** and radius property editing continue to work and share the handle's implementation rather than duplicating it.
- [x] Handles scale sensibly with zoom — a constant pixel size, not world size.
- [x] Handles do not appear for annotations from a linked library (see `FND-07`).
- [x] `DESIGN.md` interaction contract covers handle manipulation.

## Code map

- `dimensions/drawing.py` — `_draw_selected_object_overlay()`, `find_dimension_hit()`, and new handle drawing and hit testing.
- `dimensions/operators/create_area.py` — `DIMENSIONS_OT_MoveAreaLabel` and `_constrained_label_world()` to share.
- `dimensions/operators/create_angle.py` — radius handling.
- `dimensions/interaction.py` — the shared constraint and numeric-entry contract.
- `dimensions/properties.py` — `angle_radius`, `presentation_offset`, `area_label_direction`, `offset_distance`.
- `dimensions/viewport_state.py` — transient drag state, per viewport.

## Verification

- State-machine tests (via `FND-06`) for a handle drag: constrain, type, confirm, and cancel.
- A test that cancelling a drag restores the exact prior value.
- A test that handle hit testing wins over body selection at an overlapping position.
- A test that a handle drag and the equivalent operator produce identical results.

## Out of scope

- Rotation and scale handles for annotation placement. `DESIGN.md` P0 calls for deliberate rotation and scale semantics for the canonical-frame model; that decision precedes handles for it and is its own ticket.
- Handles for editing anchors — that is rebinding, covered by `UX-07`.
- Gizmo API adoption. UX-04 deliberately uses custom overlay handles so its hit priority and modal behavior share the established selection and per-viewport interaction paths; the decision is recorded in `DESIGN.md`.

## Invariants

- **Source/presentation separation.** Handles adjust presentation only. Dragging a label must never alter which geometry an annotation is bound to.
- **Editable placement objects.** Handle manipulation writes the user placement offset, keeping the canonical source frame intact.
