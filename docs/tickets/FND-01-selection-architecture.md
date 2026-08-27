# FND-01 — Replace the always-on click-select modal

**Milestone:** M1 Foundation
**Status:** ✅ Complete — delivered in 0.3.0.
**Effort:** L
**Depends on:** —
**Version impact:** Minor trigger 2 (interaction-contract change) — lands in `0.3.0`.

## Problem

Annotations are viewport overlays, not pickable geometry, so clicking one has to be intercepted. Today that is done by keeping a modal operator permanently alive in every 3D viewport:

- `register_click_select()` starts an `app.timers` callback at a 1-second interval.
- `_ensure_click_select_running()` walks every window and every `VIEW_3D` area on every tick and invokes `dimensions.click_select_modal` in any viewport not already covered.
- That modal runs forever, inspecting every `LEFTMOUSE` press and returning `PASS_THROUGH` for everything it does not claim.
- Liveness is tracked in a class-level `_running_areas` set keyed by window and area pointers.

This is unsound in several ways:

- **It competes with other modal operators.** Modal handlers are a stack. A permanently-running modal in every viewport is a known source of hard-to-reproduce conflicts with other add-ons and with Blender's own modal tools.
- **Pointer-keyed liveness is fragile.** `as_pointer()` values are reused after areas are freed. Splitting, joining, or closing editors, and switching workspaces or window layouts, can leave stale keys or drop coverage.
- **It is invisible and unstoppable.** A user cannot see that it is running, and there is no way to disable it beyond the `enable_click_select` setting, which the modal checks but which does not stop the timer.
- **It burns a timer tick per second forever**, walking all windows and areas, whether or not any annotation exists in the scene.
- **It will not survive extension review.** This pattern is one of the most commonly rejected in Blender extension submissions.

`tools.py` contains no-op `register_tools()` / `unregister_tools()` stubs, which suggests a `WorkSpaceTool` was the original intent. The 0.1.9 changelog confirms toolbar tool registration was removed rather than finished.

## Why it blocks 1.0

Selection is the entry point to every editing workflow. `UX-04` (direct handles) needs a sound hit-testing and drag architecture to build on, and the 1.0 gate requires that this not be a background modal.

## Approach

Choose one of two designs and record the choice in `DESIGN.md`.

**Option A — `WorkSpaceTool` (preferred).** Register a Dimensions tool in the 3D View toolbar with its own keymap. Selection, and later direct handles, are active while the tool is active. This is idiomatic, discoverable, visible in the UI, and scopes input capture to a mode the user opted into.

Trade-off: annotations are only clickable while the tool is active. Mitigate by making the creation operators return to the tool rather than the previous one, and by keeping sidebar selection available always.

**Option B — registered keymap entry.** Add a keymap item in the `3D View` map bound to `LEFTMOUSE` with a `dimensions.click_select` operator whose `poll()` returns `False` unless annotations exist and the setting is on. Blender's keymap system handles the fallthrough ordering; a failing `poll` lets the click reach normal selection.

Trade-off: keymap conflicts become the user's problem, but they are visible and editable, which the current design is not.

Either way:

- Delete the timer, the self-restarting invoke loop, and `_running_areas`.
- Implement `register_tools()` / `unregister_tools()` for real, or delete `tools.py` if Option B is chosen.
- Keep the existing hit-testing logic in `find_dimension_hit()` and `find_guide_hit()` — it is fine. Only the delivery mechanism changes.
- Preserve current behavior: plain click selects and makes active, Shift-click toggles and manages the active object, a miss falls through to Blender's own selection.

## Acceptance criteria

- [ ] No `app.timers` callback is registered for selection.
- [ ] No modal operator runs outside an explicit user interaction.
- [ ] `_running_areas` and its pointer-keyed bookkeeping are gone.
- [ ] Clicking an annotation selects it and makes it active; Shift-click toggles selection and updates the active object exactly as it does today, including the "active object was deselected" fallback.
- [ ] A click that hits no annotation reaches Blender's normal object selection.
- [ ] Selection behaves correctly after splitting an area, joining areas, opening a second window, and switching workspaces.
- [ ] Disabling the add-on leaves no registered timers, keymaps, tools, or handlers. Re-enabling restores full function.
- [ ] The chosen design and its trade-off are recorded in `DESIGN.md` under the interaction contract.
- [ ] README and CHANGELOG describe the new selection behavior.

## Code map

- `dimensions/operators/click_select.py` — the whole file is in scope.
- `dimensions/tools.py` — stub to implement or delete.
- `dimensions/__init__.py` — `_COMPONENTS` registration order and rollback.
- `dimensions/drawing.py` — `find_dimension_hit()`, `find_guide_hit()`; reuse, do not rewrite.
- `dimensions/properties.py` — `CADDIM_PG_SceneSettings.enable_click_select`.
- `dimensions/viewport_state.py` — `prune_stale_states()` is currently called from the timer and needs a new home.

## Verification

- Register/unregister cycles in `tests/blender_lifecycle.py` assert that no timers, keymaps, or tools leak.
- A test asserting `bpy.app.timers.is_registered` is false for any selection callback after `register()`.
- Manual foreground checks for the area/window/workspace cases listed in the acceptance criteria — record results in the PR, since these cannot run headless.

## Out of scope

- Direct manipulation handles — `UX-04`.
- Changing what counts as a hit, or the hit threshold — `FND-04` moves the threshold into preferences.
- Box, circle, or lasso select for annotations.

## Invariants

- **No global preference mutation.** Registering a tool or keymap must not alter existing keymaps or Blender settings. Add entries; never modify or remove Blender's own.
- **Blender-native data first.** Selection must go through `select_set()` and the view layer's active object, not a private selection model.
