# FND-12 — Critical stability and bounded geometry hardening

**Milestone:** M6 1.0 gate
**Status:** ⏭ Next — accepted from the September 2026 external audit.
**Effort:** M
**Depends on:** —
**Version impact:** Patch.

## Problem

An external static audit identified eight reachable failure modes in anchor resolution,
Edit Mode repair, construction geometry, and vector preparation. Inspection of the
current implementation confirms the unsafe paths:

- object-mode anchor resolution trusts any mesh attribute named
  `dimensions_anchor_id`; a non-`INT` or non-`POINT` collision can raise while drawing
  or index the wrong mesh domain;
- guided Edit Mode repair reads BMesh vertex and face indices without first updating
  them, so newly created elements can be proposed with index `-1`;
- Extent repeated spacing derives an unbounded line count from extent / interval and
  can allocate millions of lines during mouse movement;
- guide-plane snapping accepts an infinite-line intersection behind the ray origin;
- `plane_frame()` retries only one fallback axis, which is still parallel for a
  Y-normal/Y-preferred-axis plane;
- fit-to-page scale rounds the required denominator to nearest hundredth, which can
  round down and immediately fail the export validation it is meant to satisfy;
- the stroke font preserves carriage returns, rendering pasted CRLF text with the
  fallback error glyph; and
- SVG serialization assumes every stroke color has four channels even though the
  output contract accepts RGB colors elsewhere.

These are crash, freeze, or command-refusal defects. They block the 1.0 requirement
that there be no known data-loss or crash defects.

## Approach

Harden the boundaries rather than patching individual examples:

- treat the reserved anchor attribute as usable only when its type and domain match
  the persistent-ID contract; otherwise resolve truthfully through the stored
  fallback without indexing attribute data;
- update BMesh lookup tables and indices immediately before repair candidates are
  ranked and returned;
- define one documented maximum generated-line budget for repeated spacing, enforce
  it in the shared definition path, and keep the persisted user inputs unchanged;
- require plane intersections to lie on the forward ray and make plane-frame axis
  selection try deterministic non-parallel basis axes;
- round fitted denominators upward at the stored precision and verify the computed
  value through the same page-fit predicate used by export;
- normalize CRLF and lone CR before both text measurement and stroke generation; and
- normalize and validate RGB/RGBA once when page strokes are constructed so SVG and
  PDF consume the same four-channel representation.

## Acceptance criteria

- [ ] A colliding anchor attribute with the wrong data type or domain never raises,
  never indexes a non-point domain as vertices, and leaves the anchor in a truthful
  fallback/repair state.
- [ ] Edit Mode vertex and area repair candidates created by extrude, subdivide, or
  knife always carry current non-negative BMesh indices and can be accepted.
- [ ] Every repeated-spacing mode has a finite documented line budget; Extent mode
  cannot allocate above it, and normal-size definitions are unchanged.
- [ ] A saved guide plane behind the view ray is not offered as a snap candidate.
- [ ] `plane_frame()` returns a valid orthonormal frame for axis-aligned normals even
  when the preferred axis is parallel to the normal.
- [ ] Fit Scale always chooses a denominator that passes export for the selected
  page, orientation, margins, and orthographic camera frame.
- [ ] LF, CRLF, and CR versions of the same text have identical metrics and strokes,
  with no carriage-return fallback glyph.
- [ ] Valid RGB and RGBA strokes serialize identically apart from default alpha;
  other channel counts fail early with an actionable validation error.
- [ ] The full validation suite passes on the declared Blender 5.1 and 5.2 targets.

## Code map

- `dimensions/anchors.py` — reserved attribute validation during resolution.
- `dimensions/repair.py` — live BMesh candidate indices.
- `dimensions/derived_guides.py` — repeated-spacing budget.
- `dimensions/snapping.py`, `dimensions/guide_planes.py` — forward ray and stable
  plane frames.
- `dimensions/operators/export_vector.py` — upward fit-scale rounding.
- `dimensions/stroke_font.py`, `dimensions/vector_export.py` — newline and color
  normalization.
- `tests/blender_smoke.py`, `tests/stroke_font_smoke.py`,
  `tests/vector_export_smoke.py` — regression coverage.

## Verification

- Synthetic wrong-domain and wrong-type reserved attributes resolve without an
  exception and without claiming `BY_ID`.
- A live Edit Mode mesh creates new vertices/faces without a manual mode switch;
  suggested repairs have valid indices and bind successfully.
- Extreme spacing inputs return no more than the shared budget and complete within
  the existing interactive benchmark envelope.
- Forward and backward plane-ray fixtures distinguish candidates by signed ray
  distance; X-, Y-, and Z-normal frames remain orthonormal.
- A camera/page case whose exact denominator has a third decimal below five passes
  after Fit Scale; newline and RGB/RGBA serializer fixtures remain deterministic.
- Run `scripts/validate.ps1`.

## Out of scope

- Changing the stored spacing definition to materialized guide objects.
- Adding new snap kinds, mesh geometry, fonts, page sizes, or export formats.
- Automatically renaming or deleting user-authored mesh attributes that collide
  with the reserved anchor name.

## Invariants

- **Non-destructive annotation.** Validation and repair never modify mesh geometry.
- **Truthful state.** Invalid identity data must fall back visibly, never masquerade
  as a live binding.
- **Bounded interaction.** User-entered values cannot produce unbounded per-event
  allocation.
