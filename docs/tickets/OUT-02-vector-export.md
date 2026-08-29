# OUT-02 — SVG and PDF vector export

**Milestone:** M4 Output
**Status:** ✅ Complete — scale-correct SVG and PDF export delivered and verified on Blender 5.2.
**Effort:** L
**Depends on:** OUT-01
**Version impact:** Patch, once `OUT-01` has established the output surface.

## Problem

`OUT-01` makes dimensions render as pixels. Producing an actual drawing — something to send to a fabricator, drop into a document, or open in Illustrator or a CAD package — needs vector output at a known scale.

A raster render of a dimensioned part is not a drawing. It cannot be scaled without loss, text cannot be selected or searched, and it carries no scale relationship to real dimensions. The gap between "renders" and "produces a drawing" is exactly this ticket.

`DESIGN.md` P2 lists "a render or export path through generated curves and text, Grease Pencil, SVG, or PDF." `OUT-01` covers the first half; this is the second.

## Why it matters for 1.0

Not a 1.0 gate item — `OUT-01` satisfies the capability requirement. This is what makes the output genuinely useful for documentation work, and it is the natural next step once generation exists.

## Approach

**Use Blender's Grease Pencil exporters if they suffice.** Blender ships SVG and PDF export for Grease Pencil. Evaluate them first against the requirements below. If they meet the bar, this ticket is mostly a scale-and-framing wrapper plus documentation — a much smaller job than writing an exporter.

Expect gaps. Likely problems: text exported as stroke outlines rather than selectable text, no control over document scale, line weights not mapping to sensible stroke widths, and no page setup. Evaluate and record findings before choosing a path, since the answer determines whether this is an M or an L.

**Scale is the point.** A drawing at 1:50 means 1 mm on paper is 50 mm in the model. The export must let the user specify a scale and a paper size, and produce a document where measuring the drawing gives the right answer. This is what separates this from "save the render as SVG." Get it right and verify it by measuring exported output.

**Framing.** Export from a camera, or from a defined region of a construction plane (`CON-03`). Camera-based is simpler and should come first.

**Text.** If Blender's exporter outlines text, decide whether that is acceptable. For fabrication drawings it usually is; for documents people edit it usually is not. If real text is needed, a custom SVG writer may be required — which is a significant scope increase and should be its own ticket rather than absorbed here.

**A drawing frame is out of scope but adjacent.** Title blocks, borders, and sheet layout are what turn an export into a drawing sheet. Note as a follow-up; do not attempt here.

### Blender 5.2 exporter evaluation and chosen path

Both `bpy.ops.wm.grease_pencil_export_svg` and `bpy.ops.wm.grease_pencil_export_pdf` completed in an isolated foreground scene. The SVG operator wrote a `1000px × 1000px` viewport document and expanded a Grease Pencil stroke into a filled outline. The PDF was likewise viewport-derived. Their Blender 5.2 RNA exposes object/frame scope, sampling, fill, and uniform-width controls; SVG also exposes camera clipping. Neither operator exposes physical document units, paper size, orientation, or a drawing-scale relationship. Wrapping them could not satisfy the central acceptance criterion without format-specific post-processing, especially for PDF.

OUT-02 therefore reuses Dimensions' existing world-space output strokes and adds a small physical-page serializer. An orthographic camera supplies the frame. Scene units and the requested 1:N denominator convert model coordinates into paper millimetres; the camera frame is centered on the selected A4, A3, or US Letter page and export refuses to rescale it silently when it does not fit. SVG retains physical `mm` dimensions, RGB/opacity, and stroke weights. PDF writes the same RGB vector segments to a single physical page. Labels remain the bundled single-line stroke font, so they are portable outlines rather than selectable text.

## Acceptance criteria

- [x] Blender's built-in Grease Pencil SVG and PDF exporters are evaluated against these criteria, with findings recorded in the PR and a chosen path justified.
- [x] SVG export produces a valid file that opens correctly in at least two independent viewers.
- [x] PDF export produces a valid file.
- [x] The user specifies a drawing scale, and measuring the exported output at that scale yields the correct real dimension within a documented tolerance.
- [x] Paper size and orientation are selectable.
- [x] Export is framed from a camera.
- [x] Line weights map to sensible stroke widths, and per-annotation colors are preserved.
- [x] Text is legible; whether it is real text or outlines is documented.
- [x] Export of 100 annotations completes in a time recorded in the CHANGELOG.
- [x] README documents the export workflow, including the scale relationship.
- [x] `DESIGN.md` P2 export item is updated with what shipped.

## Code map

- `dimensions/vector_export.py` — camera projection, physical-page geometry, SVG serialization, and PDF serialization.
- `dimensions/operators/export_vector.py` — annotation resolution, valid-state filtering, and file operators.
- `dimensions/output_geometry.py` — shared world-space linework and stroke-font labels from generated output.
- `dimensions/properties.py`, `dimensions/ui.py` — persisted paper, orientation, scale, and physical presentation controls.

## Verification

- `tests/vector_export_smoke.py` parses SVG XML, checks element counts, validates PDF structure and page size, covers A4/A3/Letter orientations, skips Fallback and Needs Repair annotations, and exercises both file operators.
- The automated scale test exports a 100 mm segment at 1:10 and measures exactly 10 mm in SVG document coordinates within 0.00001 mm.
- Blender 5.2 exported 100 labeled linear annotations to SVG in **0.090 s**.
- Independent validation: `xmllint` parsed the SVG; headless Chrome rendered it correctly; Blender's independent SVG importer reopened all three validation strokes. `pdfinfo` identified one landscape A4 page at 841.89 × 595.276 points; Poppler rendered it; and Ghostscript accepted the PDF without errors.

## Out of scope

- Title blocks, borders, and sheet layout. Adjacent and valuable; file separately.
- DXF export. Frequently requested for CAD interchange and a reasonable follow-up, but a different format family with its own entity model.
- Multi-sheet documents.
- Selectable/editable text. Labels ship as portable vector strokes; a separate real-text exporter would be a different editing contract.

## Invariants

- **Source/presentation separation.** Export reads generated output and annotations; it never modifies them.
- **Truthful state.** An annotation in a repair state must not export as though it were valid. Either refuse to export it or mark it visibly in the output.
