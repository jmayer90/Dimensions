# UX-08 — Verify and enforce stable screen-space label sizing

**Milestone:** M2 Fluency
**Status:** ✅ Complete — verified, documented, and regression-tested in 0.3.1.
**Effort:** S
**Depends on:** —
**Version impact:** Patch if a bug is found; documentation and regression coverage otherwise.

## Problem

An early user asked for a way to lock dimension numbers so they do not grow. The overlay already passes `text_size` and `arrow_size` directly to Blender's pixel-space drawing APIs, so zooming the viewport or scaling source geometry should not change their apparent size. The request therefore points to one of three things: an untested path violates the intended behavior, annotation/source transforms produce surprising results, or the sizing control is not clear enough for users to recognize the existing behavior.

Do not add a second viewport sizing mode until the current behavior has been reproduced and measured. Stable pixel sizing is the correct default for an interactive overlay and is now part of `DESIGN.md`'s stable-presentation invariant.

## Why it matters for 1.0

This is a small trust issue with high visibility. A numeric label that changes apparent size while navigating the model feels unstable even when its measured value remains correct. The investigation is deliberately scheduled beside continuous placement rather than hidden inside later drafting-output work.

## Approach

**Reproduce first.** Exercise perspective and orthographic zoom, camera view, viewport UI scaling, source-object scale, parent scale, annotation Empty scale, and file reload. Record which operation, if any, changes the pixel bounds of text or arrowheads.

**Keep viewport and output semantics separate.** Viewport overlays use configured pixel sizes. `OUT-01` may resolve those sizes relative to a camera or use explicit world sizing for generated output, but that choice must not feed back into the live overlay.

**Fix the narrow cause.** If a path scales labels, remove that transform from presentation-size resolution. If no violation can be reproduced, add the regression coverage and clarify the Text Size control and screen-space behavior in the README; do not invent a no-op "lock" toggle.

## Acceptance criteria

- [ ] Text and arrowhead pixel bounds are measured before and after perspective zoom, orthographic zoom, and switching projection; they remain within a documented tolerance.
- [ ] Scaling, rotating, parenting, or moving a source object does not change viewport text or arrowhead pixel size.
- [ ] Scaling or rotating the annotation Empty does not accidentally scale viewport text; any future deliberate rotation/scale semantics remain a separate design decision.
- [ ] Save/reload preserves the configured text and arrow sizes.
- [ ] The selected and unselected draw paths behave identically.
- [ ] Generated-output sizing choices from `OUT-01` do not change live-overlay sizing.
- [ ] README documents that Text Size is a fixed viewport size, or the CHANGELOG and README describe the corrected behavior if a bug is fixed.
- [ ] No mesh geometry is modified.

## Code map

- `dimensions/drawing.py` — screen geometry construction, `_draw_text*()`, `_build_arrow_segments()`, and draw caches.
- `dimensions/properties.py` — per-annotation and scene `text_size` and `arrow_size` properties.
- `dimensions/dimension_geometry.py` — confirm world geometry does not carry presentation scale into screen geometry.
- `tests/blender_smoke.py` — geometry/cache regression coverage.

## Verification

- Pure layout tests comparing text and arrowhead pixel bounds across projected world geometries at several depths and zoom levels.
- A Blender background test covering source and annotation transforms plus save/reload of configured sizes.
- Foreground QA in perspective, orthographic, and camera views at normal and high-DPI UI scales, recorded in the PR.

## Out of scope

- User-selectable world-space viewport text. Generated render output has separate camera-relative and world-scale modes in `OUT-01`.
- Label alignment, tight-space leaders, and arrow variants — `DIM-04`.
- Defining annotation Empty rotation and scale as user-facing placement controls. That broader canonical-frame decision remains in `DESIGN.md` P0.

## Invariants

- **Stable presentation.** View navigation and unrelated source transforms do not change label readability.
- **Source/presentation separation.** Source geometry determines the measured value and anchor positions, never text pixel size.
