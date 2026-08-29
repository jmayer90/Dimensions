# OUT-05 — Single-sheet drawing frame and title block

**Milestone:** M4 Output
**Status:** ✅ Complete in 0.6.0.
**Effort:** M
**Depends on:** OUT-02, OUT-03
**Version impact:** Minor trigger 3. A composed drawing sheet is a new product surface beyond annotation-only vector export.

## Problem

Scale-correct SVG and PDF export produces annotation linework on a physical page,
but not a drawing sheet. There is no border, controlled margin, drawing identity,
revision, authorship, or visible scale. Every exported page therefore needs manual
layout work before it can serve as a minimal issueable drawing.

OUT-02 deliberately excluded borders, title blocks, and sheet layout while naming
them as its adjacent follow-up. Its camera projection, physical millimetre mapping,
SVG/PDF serializers, and vector stroke font now provide the complete foundation for
a bounded first sheet surface.

## Why it matters for 0.6

This changes the answer to "what is this tool" from exporting scale-correct
annotation strokes to producing a composed, identified drawing sheet. That is the
new-product-surface trigger in `VERSIONING.md`. The saved settings remain additive
and preserve existing annotation and export behavior through migration.

## Approach

Keep the first surface deliberately small and deterministic:

- one physical page using OUT-02's A4, A3, or Letter size and orientation;
- an optional rectangular border inset by a configurable physical margin;
- an optional fixed lower-right title block with configurable physical width and
  height;
- stored drawing title, drawing number, revision, author, and date fields;
- an automatically rendered `1:N` scale field from the export setting;
- page-space vector strokes composed after camera projection, so camera or model
  changes never alter the border or title block's physical dimensions.

Use the bundled stroke font for portable SVG/PDF parity. Sheet settings are
scene-owned and travel with the `.blend`; they do not alter annotations, styles,
camera framing, or mesh geometry.

## Acceptance criteria

- [x] A scene can enable or disable its drawing border and title block independently.
- [x] Border margin and title-block width/height are stored and interpreted in physical millimetres.
- [x] The title block displays drawing title, drawing number, revision, author, date, and the current `1:N` scale.
- [x] A4, A3, and Letter portrait/landscape output preserve exact configured physical dimensions.
- [x] Changing the camera, model scale, or drawing scale never scales or shifts page-space sheet geometry.
- [x] Impossible margins or title-block dimensions fail with an actionable warning rather than emitting malformed output.
- [x] SVG and PDF contain equivalent sheet geometry and remain valid single-page documents.
- [x] Annotation projection, clipping, truthful repair-state omission, colors, and physical line/text sizes remain unchanged.
- [x] Sheet composition is deterministic and adds no scene-size-dependent work; 100-annotation export remains within its documented interactive budget.
- [x] Settings advance the saved schema, include an idempotent migration, and are covered from the immutable 0.5.0/schema-v14 fixture.
- [x] Save/reload preserves custom sheet settings without leaking between scenes.
- [x] README, `DESIGN.md`, `VERSIONING.md`, the changelog, and the ticket index document the 0.6 surface and limits.

## Code map

- `dimensions/sheet_layout.py` — validate and build physical page-space border, grid, metadata, and stroke-font labels.
- `dimensions/vector_export.py` — compose page-space sheet strokes with projected annotation strokes for both serializers.
- `dimensions/operators/export_vector.py` — pass scene metadata and report invalid layouts.
- `dimensions/properties.py`, `dimensions/ui.py` — scene-owned sheet settings and the Drawing Sheet panel.
- `dimensions/migrations.py`, `dimensions/constants.py` — additive schema v15 defaults.
- `tests/sheet_layout_smoke.py`, `tests/vector_export_smoke.py`, `tests/blender_lifecycle.py` — geometry, serializer, operator, migration, and persistence evidence.

## Verification

- Exact page-space border and title-block coordinates for every supported page/orientation.
- Physical invariance under camera-frame, scene-unit-scale, and drawing-scale changes.
- Empty, punctuation-heavy, and long metadata remain deterministic and inside the title block.
- SVG XML and PDF page/media validation include sheet geometry.
- A released schema-v14 file migrates once to v15 and is unchanged by a second pass.
- Save/reload and two-scene tests preserve independent metadata.
- Timed export of 100 labeled annotations with the sheet enabled.

Blender 5.1.2 release validation passes the seven-case physical sheet-layout suite,
the nine-case SVG/PDF export suite, 33 lifecycle cases including schema-v14 migration
and custom-setting reload, and every existing smoke/output suite. Exporting 100
labeled annotations with border and title block takes 0.092 seconds. The validated
extension archive is retained as `builds/dimensions-0.6.0.zip`.

## Out of scope

- Multi-sheet registries or multi-page PDF output.
- Arbitrary title-block templates, logos, raster images, or external template files.
- DXF export or selectable/editable text.
- Coordinate tables, hole schedules, bills of materials, or GD&T frames.
- Per-camera annotation restyling or automatic camera creation.
- Any mesh geometry creation or modification.

## Invariants

- **Non-destructive annotation.** A sheet is output presentation only and never modifies model geometry or annotation bindings.
- **Source/presentation separation.** Camera projection determines annotation placement; sheet furniture remains page-space presentation.
- **Truthful state.** Invalid annotations remain omitted exactly as in OUT-02; a border or title block cannot make stale values authoritative.
- **Scene ownership.** Sheet settings belong to one scene and never leak across scenes.
