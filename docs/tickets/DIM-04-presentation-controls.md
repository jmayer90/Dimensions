# DIM-04 — Drafting presentation controls: ticks, arrows, units, and alignment

**Milestone:** M5 Documentation-grade
**Status:** ✅ Complete in 0.4.3 — architectural ticks shipped in 0.3.2, Outside Start in 0.4.1, and the remaining style-owned controls in 0.4.3.
**Effort:** M
**Depends on:** OUT-03
**Version impact:** Patch. Additive.

## Problem

Presentation control is thinner than documentation work requires. Prefixes, suffixes, tolerances, precision, color, line width, and text size exist. The conventions that make a drawing look drafted rather than diagrammed do not:

- **Extension line gap and overshoot.** Drafting standards leave a small gap between the feature and the start of the extension line, and extend it slightly past the dimension line. Extension lines currently touch the geometry, which reads as a diagram.
- **Arrow variants.** Only one arrow style. Real drawings use filled arrows, open arrows, slashes or ticks (standard in architectural drawing), and dots. Architectural drawings using engineering arrowheads look immediately wrong to their audience.
- **Dual units.** Showing `100 mm [3.94"]` in one label. Standard on anything crossing metric and imperial markets, and currently impossible.
- **Label alignment.** Whether text sits above the dimension line, breaks it, or aligns horizontally regardless of dimension direction. ISO and ANSI differ here, and both are in use.
- **Text placement for tight spaces.** When a dimension is too short for its label, the label must move outside with a leader. Currently it overlaps.

Listed in `DESIGN.md` P2.

Architectural tick marks were the directly requested part of this ticket and shipped as the first independently reviewable slice in 0.3.2, using the existing global and per-annotation style controls. The remaining variants can join reusable named styles from `OUT-03`; do not hold them behind dual units or tight-space layout.

Manual **Outside Start** placement shipped in 0.4.1 as the mirror of the existing Outside End option. It preserves existing persisted values and matches between the viewport and generated Grease Pencil output. Automatic tight-space detection and leader routing remain part of this ticket's unfinished scope.

## Why it matters for 1.0

Not a 1.0 gate item and the least architecturally significant ticket in the set. But it is the difference between output that reads as professional and output that reads as a Blender screenshot, and it is where `OUT-01` and `OUT-02`'s value is realized or lost.

## Approach

Largely additive property work plus drawing changes. The main risk is property sprawl — this ticket adds a dozen presentation properties to an already large `CADDIM_PG_Dimension`, which is why it depends on `OUT-03`. Add these as **style properties** so they are set once per style rather than per annotation.

**Extension gap and overshoot.** Two scalar properties. Pixel or world units — follow whatever `OUT-01` decided for sizing so viewport and generated output agree.

**Arrow variants.** An enum plus geometry generation per variant. `_build_arrow_segments()` currently builds one shape; generalize it. Support at minimum: filled triangle, open triangle, architectural tick/slash, dot, and none. Name the tick option in user-facing UI as **Architectural Tick**, even if its geometry helper uses "slash." Per-end control matters — leaders often have an arrow at one end only.

**Dual units.** A secondary unit system and format, plus a template controlling arrangement — `primary [secondary]`, `primary (secondary)`, or stacked. `units.py` handles formatting; the work is a second format pass and label layout. Precision for the secondary unit needs its own setting; converting 3 decimal places of millimeters to inches gives absurd precision.

**Label alignment.** An enum: aligned with the dimension line, always horizontal, or above versus broken-into the line. Affects text layout and dimension line generation, since a broken line is drawn in two segments.

**Tight-space handling.** Detect that the label does not fit between extension lines and move it outside with a leader. Needs a documented rule for which side, and must be consistent so a row of dimensions does not alternate arbitrarily.

The delivered rule is deliberately stable: automatic tight-space placement always uses the dimension's end side, with a leader from that endpoint toward the label. Manual Outside Start and Outside End remain available for deliberate exceptions.

## Acceptance criteria

- [x] Extension line gap and overshoot are configurable and render correctly in the viewport and through `OUT-01`.
- [x] Remaining arrow variants — filled triangle, open triangle, dot, and none — are available and independently settable per end. Architectural Tick is already available at both ends as a global or local style.
- [x] Dual unit display works with a configurable arrangement template.
- [x] Secondary unit precision is independently configurable.
- [x] Label alignment modes — aligned, horizontal, above, broken — all render correctly.
- [x] A label too large for its dimension moves outside with a leader, following a documented and consistent side rule.
- [x] All new properties are style properties per `OUT-03`, not per-annotation-only.
- [x] Existing annotations keep their current appearance after upgrade.
- [x] Every new property generates correctly through `OUT-01`.
- [x] Schema changes go through the `FND-02` migration framework.
- [x] Adding these does not regress the `FND-03` draw budget.
- [x] README and `DESIGN.md` document the presentation controls.

## Code map

- `dimensions/properties.py` — new presentation properties; add to the style group from `OUT-03`.
- `dimensions/drawing.py` — `_build_arrow_segments()`, `_build_text_layout()`, `_draw_dimension_geometry()`, `_project_dimension_geometry()`.
- `dimensions/dimension_geometry.py` — extension line geometry with gap and overshoot.
- `dimensions/units.py` — dual unit formatting.
- `dimensions/output/` — matching generation in `OUT-01`.
- `dimensions/ui.py` — presentation controls.

## Verification

- Geometry tests for gap and overshoot at several values including zero.
- Tests that each arrow variant produces the expected geometry, and that per-end settings are independent.
- Dual unit formatting tests across metric/imperial combinations, including secondary precision.
- Label alignment tests for each mode.
- Tight-space tests asserting the label moves outside and that the side rule is consistent across a row.
- A test that viewport rendering and `OUT-01` generation agree for every new property.

## Out of scope

- GD&T symbols, feature control frames, and datum indicators. A large, well-specified domain of its own; separate ticket or project.
- Leader-only annotations with arbitrary text. Useful and adjacent; separate ticket.
- Per-standard presets (ISO, ANSI, DIN, JIS) that set all of these at once. A natural follow-up once the individual controls exist, and a good use of `OUT-03` styles.

## Invariants

- **Stable presentation.** New controls must not change any annotation's value, only its appearance.
- **Source/presentation separation.** All of this is presentation; none of it touches bindings.
