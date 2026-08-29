# UX-09 — Annotation transform semantics

**Milestone:** M2 Fluency
**Status:** ✅ Complete — delivered in the 0.4.3 work and verified for the 0.6.0 candidate.
**Effort:** S
**Depends on:** UX-04, UX-08
**Version impact:** Patch.

## Problem

The roadmap deferred a deliberate decision about how an annotation Empty's rotation
and scale interact with its canonical source frame and presentation offset. Leaving
those transforms meaningful by accident would let the live overlay, generated output,
and vector export disagree about geometry, label orientation, or size.

## Decision

Annotation objects are translation-only presentation locators. Their world translation
records the delta from canonical geometry as `presentation_offset`. Ordinary rotation
and scale editing is locked, and non-identity values introduced by scripts or legacy
files are retained but ignored. Drafting orientation and size remain explicit
annotation/style properties and direct-handle operations.

## Acceptance criteria

- [x] Rotation and scale are locked for ordinary annotation transforms.
- [x] Existing non-identity values are retained rather than destructively normalized.
- [x] Live overlay geometry ignores annotation-object rotation and scale.
- [x] Grease Pencil, SVG, and PDF output use the same translation-only policy.
- [x] Parent transforms affect annotations only through the locator's world translation.
- [x] No schema change is introduced because canonical location plus presentation offset already represent the full supported state.
- [x] The UI and durable documentation explain the policy.
- [x] Regression tests cover policy enforcement, live synchronization, and generated output.

## Code map

- `dimensions/transform_policy.py` — locking and canonical world-location policy.
- `dimensions/scene_sync.py` — translation-to-presentation synchronization.
- `dimensions/drawing.py` — live overlay geometry.
- `dimensions/output_geometry.py` — generated and vector output geometry.
- `dimensions/ui.py` — selected-annotation explanation.

## Verification

`tests/blender_smoke.py` verifies locking, ignored scripted values, and parent-derived
world translation. `tests/output_geometry_smoke.py` verifies that rotation and scale do
not change generated geometry. The full Blender 5.1/5.2 validation matrix covers both
paths.

## Out of scope

- Rotation or scale handles.
- Using object scale as a replacement for explicit drafting size/style controls.
- Rewriting legacy transforms to identity.

## Invariants

- **Source/presentation separation.** Object transforms never change source bindings or measured values.
- **Stable presentation.** Live and exported representations resolve the same geometry.
- **No mesh authoring.** The policy never modifies mesh geometry.
