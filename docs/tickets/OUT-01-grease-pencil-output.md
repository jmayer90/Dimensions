# OUT-01 — Render path via generated Grease Pencil

**Milestone:** M4 Output
**Effort:** L
**Depends on:** FND-03
**Version impact:** **Minor trigger 3 (new product surface)** — lands in `0.4.0`.
**Delivery order:** After the focused UX-01 and UX-08 work; does not wait for M3 construction tickets.

## Problem

Dimensions do not appear in renders. They are `SpaceView3D` draw handlers — GPU overlays that exist only in the interactive viewport. Render, OpenGL viewport render, Freestyle, and every export format see nothing.

This is listed as `DESIGN.md` known risk 4 and as a README limitation, and it is the single largest gap between what the tool is and what it is for. Someone dimensioning a part in order to produce a drawing cannot produce the drawing. They can screenshot the viewport.

Renderable dimensions were independently requested by two of the first five public reviewers. That is unusually strong signal for a new project and moves this ticket ahead of construction expansion. The scope does not grow: the first pass remains an explicit, non-destructive output generation step.

Everything needed is already computed: `dimension_geometry.py` calculates world-space geometry independent of viewport state, and `drawing.py` builds arrows, extension lines, arcs, and text layout. The geometry exists; it just never becomes anything renderable.

## Why it matters for 1.0

Listed in the 1.0 gate under capability. It is also the trigger that moves the minor version, because it changes what the product is.

## Approach

**Grease Pencil, not curves or meshes.** Grease Pencil is Blender's native 2D-in-3D annotation data, renders through EEVEE and Cycles, exports to SVG and PDF through Blender's own exporters, supports per-stroke materials and line weight, and is editable afterwards. Curves would need per-object materials and bevel setup for line weight; meshes are worse. Note the decision and its reasoning in `DESIGN.md`.

**Generate, do not convert.** The overlay stays the live, editable representation. Generation produces a separate Grease Pencil object in a scene-owned collection — a `Dimensions Output` collection alongside the existing two. Users keep working with live annotations and regenerate output when they need it. Do not replace annotations with Grease Pencil.

**Regeneration must be predictable.** Regenerating replaces prior generated output for the same annotations rather than accumulating duplicates. Tag generated objects so this is unambiguous. A user who has hand-edited generated output must be warned before it is replaced, or their edits must be preserved — decide which, and make it explicit rather than silently destroying work.

**Screen-space is the hard part.** Text size, arrow size, and line width are currently *pixel* values. Grease Pencil strokes live in world space. Something must resolve this, and it is the central design decision of the ticket:

- Generate relative to a specific camera and view, resolving pixel sizes at that camera's framing. Correct for producing a drawing; wrong if the camera moves.
- Generate in world space with a user-specified world scale for text and arrows. Simpler and view-independent, but sizes must be set by hand.

Recommend supporting both, defaulting to camera-relative since producing a drawing from a known view is the primary use. Record the decision in `DESIGN.md`.

**Text.** Grease Pencil has no text primitive — text must become strokes. Options: Blender's font-to-curve-to-stroke path, or a stroke font. This is a substantial sub-problem; scope it explicitly before starting, and treat "generated text is legible and correctly positioned at the target output resolution" as a hard acceptance criterion rather than an afterthought.

**Scope the first pass.** Linear dimensions only, then angle, then area. A working linear path is worth more than three half-working ones.

## Acceptance criteria

- [ ] An operator generates Grease Pencil output from selected annotations, or from all visible annotations.
- [ ] Generated output lands in a scene-owned `Dimensions Output` collection and is tagged as generated.
- [ ] Output renders in both EEVEE and Cycles.
- [ ] Linear dimensions generate correctly: dimension line, extension lines, arrows, and text.
- [ ] Angle and area annotations generate correctly, or have follow-up tickets referencing this one.
- [ ] Generated geometry matches the viewport overlay's positions within a documented tolerance.
- [ ] Text is legible and correctly positioned at the target output resolution.
- [ ] Both camera-relative and world-scale sizing modes work, with the default documented.
- [ ] Regeneration replaces prior output for the same annotations without duplicating.
- [ ] Hand-edited generated output is either preserved or the user is warned before replacement — documented either way.
- [ ] Per-annotation colors and styles carry through to Grease Pencil materials.
- [ ] Generation of 100 annotations completes in a time recorded in the CHANGELOG.
- [ ] `DESIGN.md` known risk 4 is resolved; README limitations no longer say dimensions cannot render.
- [ ] The CHANGELOG entry states that this triggers the minor version bump and why.

## Code map

- `dimensions/output/` — new package.
- `dimensions/dimension_geometry.py` — `get_dimension_world_geometry()`, `get_angle_world_geometry()`; the world-space source of truth to build on.
- `dimensions/drawing.py` — `_build_arrow_segments()`, `_build_text_layout()`, `_project_dimension_geometry()`; extract shared geometry construction rather than duplicating it.
- `dimensions/collections.py` — the output collection.
- `dimensions/constants.py` — pixel-size constants needing world-space resolution.
- `dimensions/ui.py` — the generate action.

## Verification

- Tests that generated stroke positions match computed world geometry within tolerance.
- A test that regeneration does not duplicate.
- A test that generated output is confined to the output collection and correctly tagged.
- Render tests: render a small scene headless in EEVEE and Cycles and assert non-empty output where dimensions should appear.
- Visual comparison of viewport overlay against a render from the same camera, recorded in the PR.

## Out of scope

- SVG and PDF export — `OUT-02`, which builds on this.
- Live-updating generated output. Generation is explicit and manual; a live link is a much larger commitment.
- Freestyle integration.
- Generating from measurements and guides. Consider once annotations work.

## Invariants

- **Non-destructive annotation.** Generation creates new objects and never modifies annotations or mesh geometry.
- **Source/presentation separation.** Generated output is a presentation artifact, never a source of truth. Deleting it must not affect any annotation.
- **Scene ownership.** Output belongs to a scene-owned collection.
