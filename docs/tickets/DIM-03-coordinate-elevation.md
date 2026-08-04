# DIM-03 — Coordinate and elevation dimensions

**Milestone:** M5 Documentation-grade
**Effort:** M
**Depends on:** —
**Version impact:** Patch. Additive.

## Problem

Every dimension measures *between* two things. There is no way to annotate a single point's position relative to a datum.

Two standard forms are missing:

- **Coordinate (ordinate) dimensions** — a point labeled with its X and Y position from an origin, with a leader and no dimension line. Standard for plates with many holes, where a chain of linear dimensions would be unreadable and would accumulate tolerance.
- **Elevation dimensions** — a point labeled with its height above a datum, typically drawn as a level symbol. Standard in architectural sections and elevations: floor levels, sill heights, ceiling heights.

Listed in `DESIGN.md` P2. Elevation in particular is fundamental to architectural work, which the README names as a target audience.

## Why it matters for 1.0

Not a 1.0 gate item. Coordinate dimensions are the cleaner answer for densely featured parts, and elevations are near-mandatory for architectural output — together they cover a broad class of drawings that the current tool cannot produce at all.

## Approach

**A datum concept is the shared prerequisite.** Both types measure from an origin, so a datum must exist as a first-class thing: a named origin with a position and orientation, referenced by the annotations that use it, resolving like any other anchored source so moving the datum updates every dependent annotation.

Reuse `anchors.py` for datum position. A datum should be anchorable to geometry — "the datum is this corner" — not only a world coordinate.

Coordinate with `CON-01`: a guide point and a datum are similar objects. Decide whether a datum *is* a specially-flagged guide point or a separate type, and cross-reference whichever ticket lands first. A shared implementation is preferable if it does not force either into an awkward shape.

**Coordinate dimensions:**

- Bind one point; report its position relative to the datum along the datum's axes.
- Configurable components: X only, Y only, X and Y, or all three.
- Leader from the point to a label, with the label placed clear of the geometry. Standard practice aligns labels in a column or row for readability — support that alignment, because unaligned ordinate labels are the failure mode that makes them useless.
- Sign convention and whether negatives display explicitly must be configurable; conventions differ by discipline.

**Elevation dimensions:**

- Bind one point; report its height above the datum along a chosen up-axis, defaulting to world Z.
- Draw the conventional level symbol — a triangle or arrow with a horizontal line and the value.
- Support both absolute (from a project datum) and relative (from another elevation) modes; both appear on real drawings.
- Height formatting in architectural drawings often differs from linear dimension formatting — commonly `+3.250` with explicit sign and fixed decimals. Make it separately configurable.

## Acceptance criteria

- [ ] A datum is a first-class object with position and orientation, anchorable to geometry.
- [ ] Moving a datum updates every annotation referencing it.
- [ ] Multiple datums can coexist; each annotation names the one it uses.
- [ ] Coordinate dimensions bind one point and report position relative to a datum.
- [ ] Component selection — X, Y, X and Y, or XYZ — works.
- [ ] Coordinate labels can be aligned as a set for readability.
- [ ] Sign convention and negative display are configurable.
- [ ] Elevation dimensions bind one point and report height above a datum along a configurable up-axis.
- [ ] The conventional level symbol is drawn.
- [ ] Absolute and relative elevation modes both work.
- [ ] Elevation value formatting is configurable independently of linear formatting.
- [ ] Both types use existing anchors and enter repair states per `UX-07`.
- [ ] Both generate correctly through `OUT-01` if it has landed.
- [ ] Schema changes go through the `FND-02` migration framework.
- [ ] README and `DESIGN.md` document datums and both annotation types.

## Code map

- `dimensions/properties.py` — datum property group, coordinate and elevation properties, annotation kind enum.
- `dimensions/anchors.py` — datum anchoring.
- `dimensions/collections.py` — datum objects; coordinate with `CON-01`.
- `dimensions/dimension_geometry.py` — world-space geometry for both types.
- `dimensions/drawing.py` — leader, label alignment, level symbol.
- `dimensions/units.py` — elevation formatting with explicit sign and fixed decimals.
- `dimensions/operators/` — creation operators.

## Verification

- Coordinate tests against known points relative to datums at the world origin and at arbitrary positions and orientations.
- A test that moving a datum updates dependents.
- Tests for each component selection mode.
- Label alignment tests on a set of coordinate dimensions.
- Elevation tests for absolute and relative modes, including points below datum with correct sign.
- Formatting tests for the elevation convention, including zero and negative values.

## Out of scope

- Automatic datum detection.
- Coordinate tables or hole schedules, which pair naturally with these but belong after `OUT-02`.
- Grid line systems, common in architectural drawings and closer to `CON-04`.
- Multiple simultaneous datum systems on one annotation.

## Invariants

- **Truthful state.** A datum whose anchor is lost must put dependent annotations into a visible repair state — an elevation measured from a moved-but-unresolved datum is exactly the confidently-wrong output the project avoids.
- **Source/presentation separation.** The datum reference is a source binding; leader and label placement are presentation.
