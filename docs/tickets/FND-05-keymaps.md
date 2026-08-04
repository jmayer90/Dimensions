# FND-05 — Registered, customizable keymaps

**Milestone:** M1 Foundation
**Effort:** M
**Depends on:** FND-01, FND-04
**Version impact:** Patch, unless default bindings change a documented contract key.

## Problem

The add-on registers no keymap items at all. Every command is reachable only by clicking a button in the sidebar. The modal keys — `A`, `X`, `Y`, `Z`, `Esc`, `Enter`, right-click, middle-drag — are hard-coded inside the modal handlers in `interaction.py` and each operator's `modal()`.

Two distinct problems:

1. **No invocation shortcuts.** Starting a dimension requires reaching for the N-panel every time. For a tool used repeatedly during modeling, that is the dominant cost of using it. This is the same underlying complaint as `UX-01`.
2. **Un-rebindable modal keys.** The hard-coded modal keys cannot be changed. `X` is a reasonable axis constraint but collides with muscle memory for delete. Non-QWERTY layouts and users with Blender's Industry Compatible keymap have no recourse.

Custom keymaps are already listed as unimplemented in the README limitations.

## Why it blocks 1.0

Listed in the 1.0 gate under user control. Blender users expect every operator to be bindable; an add-on that cannot be is treated as unfinished.

## Approach

**Invocation keymaps.** Add `dimensions/keymaps.py` registering items in the `3D View` keymap for the main creation operators. Follow the add-on convention: keep a module-level list of `(keymap, keymap_item)` pairs and remove exactly those on unregister.

Choose defaults that do not collide with Blender's own bindings. Prefer leaving invocation **unbound by default** and shipping the entries as disabled-but-present, so they appear in Preferences ▸ Keymap ▸ Add-ons for the user to assign. Colliding by default is worse than requiring one setup step. Record the reasoning in `DESIGN.md`.

**Modal keymaps.** Convert the hard-coded modal keys to a registered `ModalKeyMap`, which is Blender's supported mechanism for exactly this. Define named modal events — `CONSTRAIN_ALIGNED`, `CONSTRAIN_X`, `CONSTRAIN_Y`, `CONSTRAIN_Z`, `CONFIRM`, `CANCEL`, `STEP_BACK`, `AXIS_GESTURE` — and dispatch on `event.type` when the modal map is active. This makes them appear in the keymap editor automatically.

`interaction.py` currently owns `axis_from_event()`, `is_confirm_event()`, and related helpers. They become the translation layer between modal event names and behavior, rather than reading raw key types.

**Preferences integration.** Add a Keymap section to the preferences panel (created in `FND-04`) that draws the add-on's keymap items inline, so users find them without hunting through Blender's keymap tree.

## Acceptance criteria

- [ ] Keymap items register on enable and are removed exactly on disable, with no leaked or duplicated entries across repeated enable/disable cycles.
- [ ] Add-on keymap items appear under Preferences ▸ Keymap ▸ Add-ons ▸ Dimensions.
- [ ] Default bindings collide with no default Blender binding — verify against the Blender and Industry Compatible presets, and document the check.
- [ ] Modal keys are driven by a registered modal keymap, not hard-coded `event.type` comparisons in operator bodies.
- [ ] Rebinding a modal key in the keymap editor changes behavior in the tool without restarting Blender.
- [ ] Existing documented defaults — `A`, `X`, `Y`, `Z`, `Esc`, `Enter`, right-click cancel — continue to work unchanged out of the box.
- [ ] The preferences Keymap section lists the add-on's items and allows editing in place.
- [ ] README key table and `DESIGN.md` interaction contract note that keys are rebindable.

## Code map

- `dimensions/keymaps.py` — new.
- `dimensions/interaction.py` — `axis_from_event()`, `is_confirm_event()`, `nearest_axis_from_screen_vectors()`, `update_distance_text()`.
- `dimensions/operators/create_dimension.py`, `create_angle.py`, `create_area.py`, `create_guide.py`, `measure.py` — `modal()` dispatch.
- `dimensions/preferences.py` — Keymap section.
- `dimensions/__init__.py` — component registration and rollback ordering.

## Verification

- A test that enable/disable/enable leaves exactly the expected keymap item count.
- A test that unregister removes the add-on's items and leaves Blender's own untouched.
- A test driving a modal handler with a synthesized remapped event, asserting the remapped key produces the mapped behavior. Depends on the harness from `FND-06`.

## Out of scope

- Continuous placement behavior — `UX-01`, though the two together are what make the tool fast.
- A `WorkSpaceTool` keymap, which `FND-01` establishes; this ticket adds items to it or to the 3D View map depending on that decision.

## Invariants

- **No global preference mutation.** Add keymap entries under the add-on's own registration and remove them on unregister. Never modify or delete Blender's built-in items.
- **One interaction contract.** Whatever the bindings, point/constrain/type/confirm/step-back/cancel must behave identically across every tool.
