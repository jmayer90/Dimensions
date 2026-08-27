# OUT-04 — Extend generated output to angle and area annotations

**Milestone:** M4 Output
**Status:** ✅ Complete — delivered in 0.4.1.
**Effort:** M
**Depends on:** OUT-01
**Version impact:** Patch on the `0.4.x` line.

## Problem

Version 0.4.0 establishes selected/visible Grease Pencil generation, scene ownership, regeneration keys, vector labels, camera/world sizing, and verified EEVEE/Cycles rendering for linear dimensions. Angle and area annotations still exist only in the live overlay.

## Approach

Add angle and area adapters that emit the same `GreasePencilOutputSpec` consumed by the existing backend. Reuse `get_angle_world_geometry()` and `evaluate_area_binding()` rather than reconstructing source geometry. Resolve labels through the bundled stroke font and the same sizing policy. Keep regeneration keys, collection ownership, material behavior, and disposable-output warning identical to linear output.

## Acceptance criteria

- [ ] Minor, supplement, and reflex angle arcs, rays, and labels generate at their live world positions.
- [ ] Live, captured, and valid area leaders and labels generate; Needs Repair areas are skipped with an actionable warning.
- [ ] Camera Relative and World Scale sizing behave identically across linear, angle, and area output.
- [ ] Selected and Visible scope includes eligible angle and area annotations.
- [ ] Regeneration replaces only the matching generated artifact.
- [ ] Per-annotation color and current presentation offset carry through.
- [ ] EEVEE and Cycles render tests cover all three annotation kinds.
- [ ] No mesh geometry is modified.

## Verification

- Add focused world-geometry tests for angle arcs and area leaders.
- Extend the output operator suite with mixed annotation kinds, invalid sources, and regeneration.
- Render a deterministic mixed scene in EEVEE and Cycles and assert non-empty output.

## Out of scope

- Measurements and construction guides.
- Live-updating output; generation remains explicit.
- SVG/PDF export, which remains `OUT-02`.

## Invariants

- **Non-destructive annotation.** Generated artifacts never replace or modify live sources.
- **Source/presentation separation.** Output is disposable presentation data.
- **Scene ownership.** Every generated object remains in the owning scene's output collection.
