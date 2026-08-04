# FND-06 — Make modal operators testable, then test them

**Milestone:** M1 Foundation
**Effort:** L
**Depends on:** —
**Version impact:** Patch.

## Problem

The modal operators *are* the product. Everything a user does — picking points, constraining to an axis, typing a distance, stepping back, cancelling — happens inside `modal()` methods. None of it is tested.

`tests/blender_smoke.py` has 37 tests and covers the pure layer well: anchor resolution, snapping math, area and angle binding, unit parsing, geometry. It reaches into operators only for isolated helpers such as `_constrained_label_world()`. `tests/blender_lifecycle.py` is a script with 9 bare `assert` statements and no test functions, covering proxy save/reload.

The gap is structural, not incidental. `CADDIM_OT_CreateDimension.modal()` interleaves four concerns:

- state machine transitions across `PICK_START`, `PICK_END`, `SET_OFFSET`
- raw event interpretation
- viewport and snapping queries needing a real region and `region_data`
- committing scene changes

Only the third genuinely needs a live viewport, but because they are interleaved, none of it can run headless.

The cost shows up as regressions in exactly the places the changelog keeps revisiting: axis constraints, numeric entry, step-back, and stage transitions.

## Why it blocks 1.0

`UX-01`, `FND-05`, `UX-03`, and `UX-04` all modify modal behavior. Without coverage each is a gamble, and the compounding risk is the single largest quality threat to a 1.0.

## Approach

**Extract the state machine.** For each modal operator, pull the transition logic into a pure class or function set that takes a described intent — `pick_point(snap)`, `set_axis("X")`, `type_digit("5")`, `confirm()`, `step_back()`, `cancel()` — and returns the next state plus an action. No `bpy.context`, no event objects, no scene mutation. The operator becomes a thin adapter: translate event to intent, call the machine, apply the resulting action.

Do this incrementally, one operator per PR, starting with `create_dimension.py` as the reference implementation.

**Fake the viewport.** Add `tests/support/` with a fake context supplying `region`, `region_data`, and a scripted snap provider, so the adapter layer can be exercised without a window. `blender_smoke.py` already builds `SimpleNamespace` stand-ins in places — generalize that into a reusable helper rather than repeating it.

**Restructure the lifecycle script.** Convert `blender_lifecycle.py` to real `unittest` test methods so failures name themselves and one failure does not hide the rest.

**Then write the tests.** The point of the refactor is the coverage that follows it.

## Acceptance criteria

- [ ] `create_dimension` state transitions are covered by tests that need no live viewport.
- [ ] Coverage exists for: full pick-pick-offset commit; axis constraint applied before and after the first point; typed distance before and after axis choice; invalid typed input rejected without advancing the stage; `Esc` clearing numeric input before stepping back; step-back from each stage; cancel at each stage leaving no objects behind.
- [ ] The same treatment is applied to `create_angle`, `create_area`, `create_guide`, and `measure`, or each has a follow-up ticket filed with a reference to this one.
- [ ] `tests/support/` provides a reusable fake context and scripted snap provider.
- [ ] `blender_lifecycle.py` uses `unittest` test methods, and every existing assertion survives as a named test.
- [ ] A cancelled operator provably leaves no objects, no collections, and no lingering preview state.
- [ ] Test count and what is covered are recorded in the CHANGELOG entry.
- [ ] `DESIGN.md` release gate is updated — "foreground modal coverage" moves from aspiration to a described mechanism.

## Code map

- `dimensions/operators/create_dimension.py` — reference case. `modal()`, `_accept_start()`, `_accept_end()`, `_apply_numeric_input()`, `_step_back()`, `_begin_offset_stage()`, `_create_dimension()`.
- `dimensions/interaction.py` — already close to pure; the natural home for shared intent handling.
- `dimensions/operators/` — remaining modal operators.
- `tests/support/` — new.
- `tests/blender_smoke.py`, `tests/blender_lifecycle.py`.

## Verification

The ticket is its own verification. The bar is that a contributor can change axis-constraint behavior and find out from the test suite, not from a user.

## Out of scope

- Changing modal behavior. This is a refactor plus tests; user-visible behavior must be identical. If a test reveals a genuine bug, file it separately and fix it in its own PR so the refactor stays reviewable.
- Synthetic event injection into a real Blender window. Valuable, much harder, and not required here — the extraction removes most of the need.

## Invariants

- **One interaction contract.** The extracted state machines should make the shared contract explicit and shared, not reimplement it per tool.
