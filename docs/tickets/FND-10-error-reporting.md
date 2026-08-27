# FND-10 — Consistent, actionable error reporting

**Milestone:** M1 Foundation
**Status:** ✅ Complete — delivered in 0.3.0.
**Effort:** S
**Depends on:** —
**Version impact:** Patch.

## Problem

There are 63 `self.report()` calls across the operators, written at different times with no shared convention. Reviewing them surfaces several inconsistencies:

- **Severity is applied unevenly.** `{"ERROR"}` is used for conditions the user can immediately correct, such as "A dimension needs two different points," which is closer to a `{"WARNING"}`. `{"ERROR"}` in Blender implies the operation failed abnormally, and it is the level that gets reported as a bug.
- **Messages describe internal state rather than the fix.** "Could not determine a dimension offset plane" tells the user what the code failed to compute, not what to do differently.
- **Failure modes are silent in places.** `_create_dimension()` returns `False` on several paths; some report, and the modal then returns `RUNNING_MODAL`, leaving the user in a stage with no feedback about why nothing happened.
- **No message catalog.** The same condition can be phrased differently in two operators, and there is no way to audit coverage.

Blender's report system is the only channel for feedback during a modal operation, so its quality is disproportionately important.

## Why it blocks 1.0

Not architecturally blocking, but it is one of the cheapest available improvements to how finished the tool feels, and every later ticket adds new failure paths that will follow whatever convention exists.

## Approach

**Set the convention, and write it in `CONTRIBUTING.md`:**

- `{"INFO"}` — a thing succeeded and the user should know what was created. "Created angle dimension from selected edges."
- `{"WARNING"}` — the operation could not proceed but the user can fix it by doing something different. Message must name the corrective action.
- `{"ERROR"}` — a genuine failure, an unexpected state, or a condition the user cannot resolve. Should be rare enough that seeing one is worth investigating.

**Message style:** state what is needed, not what failed. "Select two non-parallel edges" rather than "Could not derive angle from selection." Name the object or count involved where it helps. No trailing periods on short messages, matching Blender's own convention.

**Audit all 63 call sites** against the convention. Expect most `{"ERROR"}` uses in creation operators to become `{"WARNING"}`.

**Close the silent paths.** Every path that abandons or refuses a stage must report exactly once. Guard against reporting the same condition repeatedly on every mouse-move in a modal — report on transition into the condition, not on every event.

**Centralize.** Add a small module of message constants so wording is defined once and can be audited. This also positions the project for translation later, though `bpy.app.translations` is out of scope here.

## Acceptance criteria

- [ ] The severity convention is documented in `CONTRIBUTING.md`.
- [ ] All 63 existing call sites are audited and conform.
- [ ] `{"ERROR"}` is used only for genuine failures; user-correctable conditions are `{"WARNING"}`.
- [ ] Every message names a corrective action where one exists.
- [ ] No modal path abandons or refuses a stage without reporting.
- [ ] No message repeats on every mouse-move; conditions report on entry.
- [ ] Messages are defined in one module rather than inline at call sites.
- [ ] Success messages consistently name what was created.

## Code map

- All files under `dimensions/operators/` — every `self.report()` call.
- `dimensions/messages.py` — new, message constants.
- `CONTRIBUTING.md` — the convention.

## Verification

- A test that greps the source for `report(` and asserts every call uses a constant from the messages module rather than an inline string. Crude, but it keeps the convention from eroding.
- Tests for the previously silent refusal paths, asserting a report is emitted.

## Out of scope

- Translation via `bpy.app.translations`. Centralizing messages makes it possible later; doing it now is a much larger commitment including maintaining translation catalogs.
- Redesigning how errors surface in the viewport, such as inline HUD messages rather than the status bar.

## Invariants

- **Truthful state.** A report must never claim success for a partial result, and never stay silent about an annotation entering a repair state.
