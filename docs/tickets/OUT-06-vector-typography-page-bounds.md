# OUT-06 — Vector typography and printable-area correctness

**Milestone:** M6 1.0 gate
**Status:** ⬜ Planned — accepted after FND-12.
**Effort:** M
**Depends on:** FND-12, OUT-05
**Version impact:** Patch.

## Problem

The drawing-sheet and vector-font paths have five confirmed correctness gaps:

- the minimum 60 mm title block can be accepted even though its fixed Date cell
  cannot hold the supported ten-character ISO date at the configured text height;
- annotation projection is centered on the full physical page, so linework can
  overlap enabled margins, borders, and the lower-right title block;
- fifteen printable ASCII characters and common drafting symbols (`×`, `Ø`, `µ`,
  `≤`, `≥`, and `∠`) fall back to a boxed-X glyph;
- centered and right-aligned text include the final inter-character gap in their
  measured width, shifting the rendered strokes from the requested anchor; and
- the expected invalid-layout path reports a raw exception string instead of the
  shared actionable message catalog.

Simply increasing one minimum width is not sufficient: metadata and configuration
remain variable. The layout must prove that each field fits, and export must define
one explicit printable annotation rectangle.

## Approach

- Derive title-block minimums from its grid, labels, supported default metadata, and
  text metrics. Keep rejecting overflowing user metadata rather than silently
  shrinking drafting text.
- Define the printable annotation rectangle as the page inside enabled margins and
  outside enabled sheet furniture. Fit Scale and `build_vector_document()` must use
  the same rectangle and must either place the complete camera frame within it or
  refuse export.
- Complete printable ASCII coverage and add native aliases or strokes for the named
  technical symbols. Preserve the existing single-line, dependency-free font.
- Measure glyph ink/advance consistently: inter-character spacing belongs between
  characters, never after the final character, for metrics and all alignments.
- Route expected vector/layout failures through `dimensions/messages.py` with
  warning severity and a corrective action.

## Acceptance criteria

- [ ] Every title-block size accepted by validation fits all fixed labels plus the
  documented default metadata, including an ISO `YYYY-MM-DD` date.
- [ ] User metadata that cannot fit is refused before writing a file and identifies
  the field and corrective action; text is not silently scaled below the configured
  drafting height.
- [ ] With margins or a title block enabled, every annotation stroke lies inside the
  explicit printable annotation rectangle and never crosses sheet furniture.
- [ ] Fit Scale and export use the identical bounds calculation, so a successful fit
  cannot be rejected by the subsequent export.
- [ ] All printable ASCII characters render native glyphs; `×`, `Ø`/`⌀`, `µ`, `≤`,
  `≥`, and `∠` have intentional drafting glyphs or documented equivalent aliases.
- [ ] Left, center, and right alignment share exact metrics, with no trailing-gap
  offset for single- or multi-character lines.
- [ ] Expected layout/export refusals use the shared message catalog and remain
  warnings; unexpected I/O failures remain errors.
- [ ] SVG and PDF remain geometrically equivalent and the 100-annotation export
  benchmark remains within the documented budget.

## Code map

- `dimensions/sheet_layout.py` — field fit and printable bounds.
- `dimensions/vector_export.py` — camera-frame placement and clipping.
- `dimensions/operators/export_vector.py` — shared bounds and reports.
- `dimensions/stroke_font.py` — glyph coverage and exact alignment metrics.
- `dimensions/messages.py` — actionable export warnings.
- `tests/sheet_layout_smoke.py`, `tests/stroke_font_smoke.py`,
  `tests/vector_export_smoke.py` — layout, typography, and serializer evidence.

## Verification

- Exercise minimum/default/custom title blocks with the longest fixed labels, ISO
  date, maximum supported scale text, and deliberately overflowing metadata.
- Export each page/orientation with border only, title block only, both, and neither;
  assert annotation bounds do not intersect furniture.
- Compare measured bounds with rendered stroke bounds for one- and multi-character
  left/center/right strings, including every printable ASCII and technical glyph.
- Assert warning reports use catalog messages and retain the underlying actionable
  detail without exposing an uncategorized raw exception.
- Run `scripts/validate.ps1` and the documented 100-annotation export benchmark.

## Out of scope

- Arbitrary title-block templates, automatic word wrapping, font substitution, or
  selectable text.
- Multi-page documents, DXF, model linework, or per-camera styling.
- Shrinking text below the configured physical height to force metadata to fit.

## Invariants

- **Source/presentation separation.** Sheet furniture changes page composition, not
  model geometry, camera projection, or annotation bindings.
- **Physical output.** Margins, text, and line widths remain deterministic millimetre
  values in SVG and PDF.
- **Truthful refusal.** Export either fits the declared printable area or explains
  why it cannot; it never emits a knowingly overlapping sheet.
