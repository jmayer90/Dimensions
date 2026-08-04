# UX-07 — Guided repair for broken anchors and area bindings

**Milestone:** M2 Fluency
**Effort:** M
**Depends on:** UX-02
**Version impact:** Patch.

## Problem

The project already does the hard part: it detects when a binding breaks. Area annotations enter an explicit **Needs Repair** state when a bound face is missing or ambiguous, and `resolve_anchor()` falls back to a stored position when a vertex anchor's persistent ID disappears.

What is missing is the fix. A user faced with a broken annotation can:

- Run **Remake Area**, which discards the annotation's configuration and rebuilds from scratch.
- Use `CADDIM_OT_ReattachAnchor` for linear anchors — an eyedropper with no indication of what broke or where the anchor used to be.
- Delete it and start over.

None of these tell the user *what* broke, *where* it was, or offer the likely fix. On a scene with many annotations they will not even find the broken ones without `UX-02`.

There is a related honesty problem in the anchor path. `DESIGN.md` known risk 2 and the README both note that a removed or duplicated point ID resolves to the closest stored position **without showing a detached state**. So a linear dimension can silently display a plausible wrong number. The area path handles this correctly with an explicit state; the anchor path does not.

## Why it matters for 1.0

The **Truthful state** invariant says a stale value is never presented as current. The anchor fallback is a real exception to that, and it produces the worst failure available: a confidently wrong measurement in a document someone builds from.

## Approach

**Make anchor breakage visible first.** This is the more important half. Add a resolution-status concept to anchors mirroring the area model: resolved by ID, resolved by fallback position, or unresolvable. An anchor resolved by fallback is not an error — it is often correct — but it must be visible in the annotation's display and in the manager list, not silent.

Preserve current behavior for the value itself. Changing what the fallback *computes* is out of scope; this is about surfacing how it was reached. The `DESIGN.md` P0 item asking for an explicit rebind or convert-to-world action is part of the same picture.

**Then build the repair workflow.** For an annotation in a broken or fallback state:

- **Explain.** What broke, on which source object, and when it was last resolved cleanly.
- **Show.** Highlight the last known position in the viewport and frame the view on it. A user who can see where the anchor used to be can usually identify the replacement instantly.
- **Suggest.** Offer the most likely candidate — nearest vertex to the stored fallback position, or nearest face to a lost area face — with a preview and an accept action. This is where most repairs should end.
- **Pick.** Fall back to guided manual picking, reusing the standard acquisition path so snapping and constraints work normally.
- **Convert.** Offer "convert to world point" for anchors whose source is gone permanently, satisfying the `DESIGN.md` P0 item.
- **Bulk.** Repair-all for annotations broken by the same cause, which is the common case after a destructive edit.

**Entry points:** the manager list rows from `UX-02`, the sidebar for a selected annotation, and the annotation's viewport display.

## Acceptance criteria

- [ ] Anchors carry an explicit resolution status: by ID, by fallback, or unresolvable.
- [ ] Fallback-resolved and unresolvable anchors are visually distinct in the viewport and in the manager list.
- [ ] The computed value for a fallback-resolved anchor is unchanged from today — only its presentation changes.
- [ ] A repair workflow exists for linear anchors and area face bindings.
- [ ] Repair explains what broke and on which object.
- [ ] Repair highlights the last known position and can frame the view on it.
- [ ] Repair suggests a most-likely candidate with a preview and a one-action accept.
- [ ] Manual picking is available and uses the standard acquisition path.
- [ ] "Convert to world point" is available for anchors whose source is gone.
- [ ] Bulk repair handles multiple annotations broken by the same cause.
- [ ] Every repair is a single undo step and never silently changes an annotation that was not broken.
- [ ] `DESIGN.md` known risk 2 is updated; README limitations no longer say breakage is invisible.

## Code map

- `dimensions/anchors.py` — `resolve_anchor()`, `set_anchor()`, `migrate_anchor_identity()`; add resolution status.
- `dimensions/area_binding.py` — `evaluate_area_binding()`, existing state model to mirror.
- `dimensions/operators/reattach_anchor.py` — `CADDIM_OT_ReattachAnchor`, to grow into the repair workflow.
- `dimensions/properties.py` — status storage on `CADDIM_PG_Anchor`; coordinate with `FND-02` since this is a schema change.
- `dimensions/drawing.py` — repair-state display.
- `dimensions/ui.py` — sidebar entry point.

## Verification

- Tests for each resolution status: ID present, ID missing with usable fallback, ID duplicated, source object deleted.
- A test that fallback-resolved values are numerically identical to today's, guarding against a presentation change becoming a behavior change.
- Tests that suggested candidates are correct for known broken geometry.
- A test that repair is one undo step and touches no other annotation.
- A test that bulk repair fixes only annotations matching the cause.

## Out of scope

- Changing the fallback resolution algorithm. Surface it now; changing it is separate and would be a minor trigger.
- Automatic repair without user confirmation. The whole point is that guessing silently is the current problem.
- Repair for angle sources — same pattern, file as a follow-up once linear and area are proven.

## Invariants

- **Truthful state.** This ticket exists to close the largest remaining gap in this invariant.
- **Source/presentation separation.** Repair rebinds sources and must not disturb the user's placement offsets.
