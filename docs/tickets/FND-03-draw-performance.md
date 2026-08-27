# FND-03 — Make draw cost scale with annotations, not scene size

**Milestone:** M1 Foundation
**Status:** ✅ Complete — delivered in 0.3.0.
**Effort:** M
**Depends on:** —
**Version impact:** Patch.

## Problem

`draw_dimensions()` in `dimensions/drawing.py` runs on every redraw of every 3D viewport and:

1. Iterates **`context.scene.objects`** — every object in the scene — calling `is_dimension_object()` on each. A scene with 20,000 objects and 3 dimensions pays for 20,000 checks per viewport per frame.
2. Calls `build_dimension_geometry_for_object()` per annotation per frame, recomputing world geometry from anchors even when nothing moved.
3. Issues a separate `batch_for_shader()` per annotation, and several per annotation for arrows, extension lines, and markers. Batch creation allocates and uploads to the GPU every frame.
4. Does `blf` text layout per annotation per frame in `_build_text_layout()`.

For a tool whose roadmap includes chain and baseline dimensions — which produce dozens of annotations on a single part — and whose stated purpose is documentation, this is the wrong shape.

## Why it blocks 1.0

`OUT-01` needs stable, correct world geometry it can convert to Grease Pencil, which is easier against a cached geometry layer than against a per-frame recompute. `DIM-01` multiplies annotation counts. Fixing the loop after either lands means rewriting more code.

## Approach

**Iterate the collection, not the scene.** `collections.py` already owns the scene's `Dimensions` and `Construction Guides` collections. Draw from `collection.all_objects`. Keep `is_dimension_object()` as a correctness check, not as the primary filter.

**Cache geometry, invalidate deliberately.** Add a per-viewport geometry cache keyed by annotation, holding the built world geometry and the inputs it was derived from. Invalidate from the existing `scene_sync.py` depsgraph handler, which already knows when sources move, and on view changes for anything screen-space dependent. `viewport_state.py` already provides per-viewport isolation — extend that rather than introducing a parallel mechanism.

**Batch by color and primitive.** Accumulate line segments across all annotations sharing a color into one vertex list and issue one `LINES` batch. Selected and unselected are two colors, so the common case collapses to roughly two batches plus text. Keep per-annotation batching available behind the cache for annotations that genuinely differ.

**Cache text layout.** `_build_text_layout()` results depend on the string, font size, and precision. Cache on those inputs.

**Measure first and last.** Add a reference scene generator and record before/after numbers in the PR. Without numbers this ticket cannot be judged.

## Acceptance criteria

- [ ] Draw time is independent of the count of non-annotation objects in the scene. Demonstrate with a scene of 10,000 cubes and 10 dimensions versus 10 cubes and 10 dimensions.
- [ ] Geometry is not rebuilt for annotations whose sources and view did not change since the last draw.
- [ ] Annotations sharing a color and primitive type are drawn in one batch.
- [ ] Text layout is not recomputed per frame for unchanged labels.
- [ ] Documented budget met on the reference scene: **500 visible dimensions at 30 fps or better** on the maintainer's hardware, with hardware and numbers recorded in `DESIGN.md`.
- [ ] Cache invalidation is correct — moving a source object, editing its mesh, changing style, toggling visibility, and orbiting all update the overlay immediately.
- [ ] Multiple viewports show correct independent results; no cache bleed between viewports or scenes.
- [ ] `DESIGN.md` known-risk 1 is updated with real measurements.

## Code map

- `dimensions/drawing.py` — `draw_dimensions()` at the top of the loop, `build_dimension_geometry_for_object()`, `_draw_dimension_geometry()`, `_draw_area_geometry()`, `_draw_angle_geometry()`, `_build_text_layout()`, `_draw_persistent_measurements()`, `draw_world_guides()`.
- `dimensions/collections.py` — `get_or_create_dimension_collection()`, `get_or_create_guide_collection()`.
- `dimensions/viewport_state.py` — per-viewport state to extend.
- `dimensions/scene_sync.py` — the depsgraph handler that drives invalidation.

## Verification

- A test that counts `build_dimension_geometry_for_object()` calls across two draws with no intervening change, asserting the second draw rebuilds nothing.
- A test asserting the draw path does not touch objects outside the Dimensions collections.
- Cache-correctness tests for each invalidation trigger listed above.
- A benchmark script under `tests/` that builds the reference scene and reports timings. It need not gate CI, but must be repeatable by hand.

## Out of scope

- Changing what is drawn or how it looks. This is purely a cost and correctness-of-caching change; the rendered result must be pixel-identical.
- Snap acquisition performance — `FND-08`.
- Level-of-detail or distance culling. Consider only if the budget cannot be met without it, and file separately.

## Invariants

- **Stable presentation.** Caching must never show a stale value. If invalidation is uncertain, rebuild.
- **Truthful state.** A cached geometry must never outlive a source that entered a repair state.
