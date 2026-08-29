# DIM-02 — Radial, diameter, and arc-length dimensions

**Milestone:** M5 Documentation-grade
**Status:** ✅ Complete.
**Effort:** M
**Depends on:** —
**Version impact:** Patch. Additive.

## Problem

There is no way to dimension a curved feature. Linear, angle, and area cover straight and planar cases; holes, fillets, rounded corners, and cylindrical features have no representation.

Every mechanical or architectural drawing needs these. A plate with four mounting holes needs `⌀8` on the holes, not four pairs of linear dimensions across them. A rounded corner needs `R12`. A curved wall needs an arc length.

Listed in `DESIGN.md` P2.

## Why it matters for 1.0

Not a 1.0 gate item. But "cannot dimension a hole" is a hard stop for mechanical work, and it is the most common single reason a user would find the tool unusable for their part.

## Approach

**Circle fitting is the core problem.** Blender meshes have no arcs — a hole is an N-sided polygon approximating a circle. Dimensioning it means fitting a circle to selected geometry and reporting the fit, which brings real questions the ticket must answer explicitly:

- **What is selected?** An edge loop around a hole, a set of faces forming a fillet, or a set of vertices.
- **How is the fit computed?** Least-squares circle fit to the vertices, projected onto a best-fit plane. Standard and robust.
- **Inscribed, circumscribed, or fitted?** An 8-sided approximation of a 10 mm hole has a different across-flats and across-corners measurement, and the "right" answer depends on what the user means. Expose the choice; default to fitted, which is what the modeller intended.
- **How is fit quality reported?** A loop that is not circular produces a meaningless radius. Report fit error and enter a visible warning state past a threshold — this is the **Truthful state** invariant applied directly, and it is the part most likely to be skipped.

**Three annotation types sharing the fit:**

- **Radial** — leader from the center to the arc, labeled `R<value>`.
- **Diameter** — line through the center to both sides, or a leader, labeled `⌀<value>`.
- **Arc length** — length along the fitted arc between two points, labeled with an arc symbol.

Share one binding and fit implementation across all three; they differ in presentation and in what they report.

**Binding follows the area model.** `area_binding.py` binds face sets with persistent IDs and Live/Captured/Needs Repair states. A radial dimension binds an edge loop or face set the same way and recomputes on change. Reuse that model rather than inventing a third.

**Placement conventions matter.** Drafting has established conventions — inside versus outside placement depending on available space, leader angle, whether the leader points at the center or the arc. Getting these approximately right is what makes output look drafted. Follow ISO or ANSI; pick one, document it, and note the other as a possible future preference.

## Acceptance criteria

- [x] Radial, diameter, and arc-length dimensions can be created from a selected edge loop, face set, or vertex set.
- [x] A least-squares circle fit computes center, radius, and plane from the selection.
- [x] Inscribed, circumscribed, and fitted measurement modes are available; fitted is the default.
- [x] Fit error is computed, and a selection that is not acceptably circular enters a visible warning state rather than reporting a plausible wrong radius.
- [x] Bindings use persistent IDs with Live/Captured/Needs Repair states, consistent with `area_binding.py`.
- [x] Values update live as bound geometry changes.
- [x] Labels use `R`, `⌀`, and arc-length conventions, and respect prefix, suffix, and tolerance properties.
- [x] Placement follows a documented drafting convention, with leader direction user-adjustable.
- [x] Label placement is user-controllable, consistent with area label placement.
- [x] Full circumference is available for closed circular sources, distinct from open-arc length.
- [x] Works in Object and Mesh Edit Mode, consistent with the other tools.
- [x] Generates correctly through `OUT-01` if it has landed.
- [x] Schema changes go through the `FND-02` migration framework.
- [x] README and `DESIGN.md` document the mesh types, fit method, and fit-quality warning.

## Code map

- `dimensions/circle_binding.py` — fitting and binding, modeled on `area_binding.py`.
- `dimensions/area_binding.py` — the binding pattern to follow.
- `dimensions/properties.py` — annotation kind enum and new properties.
- `dimensions/operators/` — creation operators.
- `dimensions/dimension_geometry.py` — world-space geometry for the three types.
- `dimensions/drawing.py` — rendering and label conventions.
- `dimensions/units.py` — `R` and `⌀` prefixing in formatted values.

## Verification

- Fit tests against known circles at several segment counts (8, 16, 32, 64), asserting radius converges to the true value.
- Fit tests on deliberately non-circular loops asserting the warning state is entered.
- Tests for inscribed, circumscribed, and fitted modes on a known polygon, asserting the three differ correctly.
- Tests on circles at arbitrary orientations, not just axis-aligned.
- Arc-length tests against known arcs including a full circle and a very short arc.
- Live-update tests as bound geometry changes.

## Out of scope

- Dimensioning true curve or NURBS objects. Different data, worth a follow-up.
- Spherical or toroidal dimensions.
- Automatic hole detection and dimensioning.
- Hole tables or callout schedules. Valuable for real drawings; separate ticket after `OUT-02`.

## Invariants

- **Truthful state.** A poor circle fit must never present a confident radius. This is the ticket's central risk.
- **Non-destructive annotation.** Fitting reads geometry and never modifies it.
