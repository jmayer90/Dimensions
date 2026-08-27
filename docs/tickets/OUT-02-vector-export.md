# OUT-02 — SVG and PDF vector export

**Milestone:** M4 Output
**Status:** ⬜ Planned — sequenced after generated output and reusable styles stabilize.
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

## Acceptance criteria

- [ ] Blender's built-in Grease Pencil SVG and PDF exporters are evaluated against these criteria, with findings recorded in the PR and a chosen path justified.
- [ ] SVG export produces a valid file that opens correctly in at least two independent viewers.
- [ ] PDF export produces a valid file.
- [ ] The user specifies a drawing scale, and measuring the exported output at that scale yields the correct real dimension within a documented tolerance.
- [ ] Paper size and orientation are selectable.
- [ ] Export is framed from a camera.
- [ ] Line weights map to sensible stroke widths, and per-annotation colors are preserved.
- [ ] Text is legible; whether it is real text or outlines is documented.
- [ ] Export of 100 annotations completes in a time recorded in the CHANGELOG.
- [ ] README documents the export workflow, including the scale relationship.
- [ ] `DESIGN.md` P2 export item is updated with what shipped.

## Code map

- `dimensions/output/` — the package from `OUT-01`.
- `dimensions/output/export.py` — new.
- `dimensions/units.py` — scale computation, reusing existing unit handling rather than reimplementing it.
- `dimensions/ui.py` — export operator and its options.

## Verification

- A test that exported SVG parses as valid XML and contains the expected element count.
- A **scale correctness test**: export a known 100 mm dimension at 1:10 and assert the SVG path spans 10 mm in document units. This is the criterion that matters most and must be automated.
- Tests for several scales and paper sizes.
- Manual verification in independent viewers, recorded in the PR.

## Out of scope

- Title blocks, borders, and sheet layout. Adjacent and valuable; file separately.
- DXF export. Frequently requested for CAD interchange and a reasonable follow-up, but a different format family with its own entity model.
- Multi-sheet documents.
- A custom SVG writer for real text, unless evaluation shows it is required — in which case file it as its own ticket rather than expanding this one.

## Invariants

- **Source/presentation separation.** Export reads generated output and annotations; it never modifies them.
- **Truthful state.** An annotation in a repair state must not export as though it were valid. Either refuse to export it or mark it visibly in the output.
