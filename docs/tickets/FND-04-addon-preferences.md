# FND-04 — Add-on preferences

**Milestone:** M1 Foundation
**Effort:** M
**Depends on:** —
**Version impact:** Patch.

## Problem

The add-on registers no `AddonPreferences`. Every tuning value is a module constant in `dimensions/constants.py`:

```
DEFAULT_SNAP_PIXEL_THRESHOLD = 28.0
DEFAULT_SELECTION_PIXEL_THRESHOLD = 16.0
DEFAULT_TEXT_SIZE = 14
DEFAULT_ARROW_SIZE = 10.0
DEFAULT_LINE_WIDTH = 2.0
DEFAULT_HOVER_MARKER_SIZE = 8.0
DEFAULT_PRECISION = 3
DEFAULT_OFFSET_DISTANCE = 0.25
DEFAULT_EMPTY_DISPLAY_SIZE = 0.05
```

Snap and selection thresholds in particular are wrong for a meaningful share of users: they are pixel values, so they behave differently on a 4K laptop panel than on a 1080p monitor, and users working on dense models want them tighter while users on tablets want them looser. There is no way to change any of it without editing source.

There is also nowhere to put a preference that logically belongs to the user rather than the scene. Scene settings live in `CADDIM_PG_SceneSettings` and travel with the `.blend`, which is right for units and display but wrong for "how big I like my hit targets."

## Why it blocks 1.0

A precision tool that cannot be tuned to the user's display and working style is not finished. `FND-05` needs a home for keymap configuration UI, and `UX-05` needs a home for snap target toggles.

## Approach

Add `dimensions/preferences.py` with a `DIMENSIONS_AddonPreferences(bpy.types.AddonPreferences)` class, `bl_idname` matching the package name.

**Split the responsibility clearly, and document the rule:**

- **Add-on preferences** — per-user, per-machine, do not travel with the file: interaction thresholds, default sizes and widths, whether continuous placement is on by default, snap target defaults, keymap configuration.
- **Scene settings** — travel with the file because they describe the document: units, precision, global style, visibility.

Where a value exists in both — text size, line width, precision — preferences supply the **default for new scenes and new annotations**, and the scene or annotation value wins once set. Do not silently retro-apply a preference change to existing annotations.

Add a helper, `get_preferences(context)`, that returns the preferences block or a defaults object if the add-on is not found, so nothing crashes when preferences are unavailable. Replace direct `constants.py` reads at call sites with it. Keep the constants as the single source of default values so there is one place to change them.

Organize the preferences UI into labeled sections — Interaction, Display, Defaults, Keymap, Snapping — rather than one flat column.

## Acceptance criteria

- [ ] `AddonPreferences` registers and unregisters cleanly, and survives disable/re-enable with values intact.
- [ ] Snap pixel threshold, selection pixel threshold, hover marker size, line width, text size, arrow size, default precision, default offset distance, and empty display size are all user-editable.
- [ ] Every listed value takes effect without restarting Blender; viewports redraw on change.
- [ ] `constants.py` remains the single definition of default values; preferences initialize from it.
- [ ] `get_preferences(context)` never raises, including when called during registration or from a background process.
- [ ] Scene and per-annotation values continue to win over preference defaults; changing a preference does not alter existing annotations.
- [ ] Preferences UI is grouped into labeled sections.
- [ ] A "Reset to defaults" operator restores every preference.
- [ ] `DESIGN.md` records the preference-versus-scene-setting rule.
- [ ] README mentions where preferences live.

## Code map

- `dimensions/preferences.py` — new.
- `dimensions/constants.py` — stays as default definitions.
- `dimensions/__init__.py` — register the preferences class.
- `dimensions/snapping.py`, `dimensions/projected_snap.py` — threshold reads.
- `dimensions/drawing.py` — size, width, and marker reads.
- `dimensions/properties.py` — `CADDIM_PG_SceneSettings`, for the defaults relationship.
- `dimensions/ui.py` — where scene settings are drawn; add a link to preferences.

## Verification

- A test that sets a preference and asserts the consuming code path reads the new value.
- A test that `get_preferences()` returns usable defaults when the add-on module is not registered under its expected name.
- A test that a preference change does not mutate existing annotation properties.
- Register/unregister/re-register cycle with preference values preserved.

## Out of scope

- Keymap editing UI — `FND-05` adds it to the Keymap section this ticket creates.
- Snap target enable/disable toggles — `UX-05`.
- Named annotation styles — `OUT-03`. Preferences hold scalar defaults, not style presets.

## Invariants

- **No global preference mutation.** Add-on preferences are the add-on's own; nothing here writes to Blender's settings.
