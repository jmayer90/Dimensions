# UX-06 — Transient hover measurement with delta X/Y/Z

**Milestone:** M2 Fluency
**Status:** ⬜ Planned.
**Effort:** M
**Depends on:** —
**Version impact:** Patch.

## Problem

Every measurement is a commitment. `CADDIM_OT_Measure` creates a persistent measurement object in the `Construction Guides` collection. There is no way to answer "how far apart are these two points?" without creating something you then have to delete.

Most measuring during modeling is throwaway — checking a clearance, confirming a wall thickness, sanity-checking a proportion. Users want a number, not an object. Forced to choose between creating clutter and not measuring, they mostly stop measuring.

The scene already shows selected-mesh dimensions and volume in the HUD via `volume.py`, so the display surface exists. What is missing is a transient point-to-point query, and the component breakdown: total distance is often less useful than "12 mm in X, 0 in Y, 40 mm in Z."

This is a P1 roadmap item: "temporary hover measurement with delta X/Y/Z and an explicit action to save it."

## Why it matters for 1.0

It changes measuring from a decision into a reflex. Not in the 1.0 gate, but it is the feature most likely to make the add-on part of someone's daily workflow rather than something they open when producing a drawing.

## Approach

**A modal tool that creates nothing.** Reuse the existing acquisition path — same snapping, same highlighting, same axis constraints — but hold the result in transient viewport state rather than committing an object. `viewport_state.py` and `drawing.py`'s `_draw_transient_measure()` already handle transient measure display; this extends that rather than starting fresh.

**Show components, not just total.** Display total distance plus ΔX, ΔY, ΔZ, formatted through `units.py` so metric and imperial behave consistently. Include the angle from the horizontal plane if it is cheap — useful for checking slopes.

**Chaining.** After the second point, treat it as the start of the next measurement so a user can walk a series of distances without re-invoking. This is `UX-01`'s pattern applied here, and it is what makes the tool feel like a tape measure.

**An explicit save.** One key promotes the current transient measurement to a persistent measurement object, using the existing `create_measurement_object()` path. This is the bridge between throwaway and permanent, and it means the transient tool can be the *default* measure tool with permanence as the opt-in.

**Copy to clipboard.** A key that copies the current value as text. Small, and constantly wanted.

**Decide the relationship to `CADDIM_OT_Measure`.** Cleanest is for the transient tool to become the primary **Measure** command, with saving as an in-tool action, and the existing operator kept for direct invocation. Whatever is chosen, document it — two similarly named tools with different persistence is exactly the confusion to avoid.

## Acceptance criteria

- [ ] A measure mode acquires two points and displays the result without creating any object.
- [ ] Display shows total distance and ΔX, ΔY, ΔZ, formatted per scene units.
- [ ] Snapping, highlighting, and axis constraints behave identically to the persistent measure tool.
- [ ] After the second point, the tool chains from that point into the next measurement.
- [ ] An explicit key saves the current measurement as a persistent measurement object.
- [ ] A key copies the current value to the clipboard as text.
- [ ] Exiting leaves no objects and no lingering viewport state.
- [ ] The relationship to the existing **Measure** command is documented in README and `DESIGN.md`.
- [ ] Transient state does not leak between viewports.

## Code map

- `dimensions/operators/measure.py` — `CADDIM_OT_Measure`; either extend or add a sibling operator.
- `dimensions/viewport_state.py` — transient state, per viewport.
- `dimensions/drawing.py` — `_draw_transient_measure()`, `set_measure_state()`, `clear_measure_state()`.
- `dimensions/units.py` — formatting for components.
- `dimensions/collections.py` — `create_measurement_object()` for the save action.
- `dimensions/interaction.py` — chaining and key handling.

## Verification

- State-machine tests (`FND-06`) for acquire, chain, save, and exit.
- A test asserting no objects are created during a transient session, and exactly one on save.
- Delta component tests against known point pairs, including negative deltas and non-uniform scene unit scales.
- A test that exiting clears viewport state in all viewports.

## Out of scope

- Angle and area hover queries. Same idea, worth doing, separate tickets once this establishes the pattern.
- Measuring along a path of more than two points with a running total. A natural extension of chaining; file separately.
- HUD redesign — `volume.py`'s existing display stays as is.

## Invariants

- **Truthful state.** A transient measurement must be visually distinct from a saved one, so nobody mistakes a hover value for a committed annotation.
- **Non-destructive annotation.** No geometry is created or modified, including no proxy objects, until the user explicitly saves.
