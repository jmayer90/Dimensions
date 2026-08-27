# CON-01 — Guide points

**Milestone:** M3 Construction
**Status:** ⬜ Planned.
**Effort:** M
**Depends on:** —
**Version impact:** Patch. Additive.

## Problem

Construction geometry currently comes in two forms: infinite guide lines and finite saved measurements. There is no way to save a **point**.

A point is the most basic construction primitive and the most frequently needed one. "Mark the centre of this face," "mark 300 mm along this edge," "mark where these two guides cross" — all of these are single points that other work then references. Today the only way to persist one is to create a measurement or guide you do not want, purely so its endpoint exists as a snap target.

This is a P1 roadmap item, and it gates the rest of M3: offset guides need an origin point, guide planes need three points or a point and a normal, and spacing needs a start point.

## Why it matters for 1.0

Not in the 1.0 gate, but M3 as a whole is what backs the claim that the tool supports dimensionally built construction rather than only annotation. Points are its foundation.

## Approach

**Follow the existing pattern exactly.** Guides and measurements are Empty objects in the scene-owned `Construction Guides` collection with a property group and a snap proxy. A guide point should be the same kind of thing — an Empty with `guide_props` extended, or a new `CADDIM_PG_GuidePoint`, living in the same collection. Do not invent a new persistence mechanism.

**Anchored or free.** A guide point should support the same anchor model as dimension endpoints: bound to a vertex, bound to a surface point on an object, or a fixed world position. An anchored point moves with its source, which is what makes it useful for construction rather than just a marker. Reuse `anchors.py` directly.

**Creation paths, in rough priority:**

- Place at a snapped position — the basic case, using the standard acquisition path.
- Place at a typed distance along an edge or from an existing point, with axis constraint. This is the one that makes it a construction tool rather than a marker tool.
- Place at the midpoint or centroid of the current selection.
- Place at an inferred intersection, once `UX-03` provides one.

**A snap target like any other.** Guide points must be snappable by every tool, and must appear in the snap target toggles from `UX-05` as their own type. `collections.py` already builds native snap proxies for measurements — reuse that mechanism.

**Visually distinct and unobtrusive.** A small screen-space marker distinct from snap indicators and from measurement endpoints. Constant pixel size, not world size.

## Acceptance criteria

- [ ] A guide point is a persistent object in the scene-owned `Construction Guides` collection.
- [ ] Guide points support vertex, surface, and world anchors via the existing `anchors.py` model.
- [ ] An anchored guide point follows its source through object transforms and mesh edits.
- [ ] Guide points can be created at a snapped position, at a typed distance along an edge or from an existing point, and at the midpoint or centroid of a selection.
- [ ] Guide points are snap targets for every acquisition tool and appear as their own type in the `UX-05` toggles.
- [ ] Guide points have a distinct, constant-pixel-size viewport marker.
- [ ] Guide points can be selected, named, hidden, and deleted individually, and appear in the `UX-02` manager.
- [ ] **Clear All Guides** handles guide points, or a separate clear action exists — decide and document.
- [ ] Guide points survive save/reload and undo/redo per the `FND-07` matrix.
- [ ] Creating one is a single undo step.
- [ ] Schema changes go through the `FND-02` migration framework.
- [ ] README and `DESIGN.md` document the new construction primitive.

## Code map

- `dimensions/properties.py` — `CADDIM_PG_Guide` to extend, or a new point property group.
- `dimensions/collections.py` — `create_guide_object()`, `ensure_measurement_snap_proxy()` as the proxy pattern to follow.
- `dimensions/anchors.py` — reuse for anchoring.
- `dimensions/operators/create_guide.py` — creation operators.
- `dimensions/snapping.py` — guide points as snap candidates.
- `dimensions/drawing.py` — marker drawing, hit testing via `find_guide_hit()`.
- `dimensions/scene_sync.py` — position sync for anchored points.

## Verification

- Tests that an anchored guide point follows its source through object transform and mesh edit.
- Tests for each creation path, including typed-distance-along-edge with axis constraint.
- A test that guide points are returned as snap candidates and respect the `UX-05` toggle.
- Save/reload and undo/redo tests per the `FND-07` matrix.

## Out of scope

- Offset and parallel guides — `CON-02`.
- Guide planes — `CON-03`.
- Arrays or patterns of points — `CON-04`.
- Converting guide points into mesh vertices. That is geometry authoring and is excluded from this project.

## Invariants

- **Non-destructive annotation.** Guide points never become mesh geometry and never modify topology.
- **Scene ownership.** They belong to the scene-owned `Construction Guides` collection and must not leak across scenes.
- **Blender-native data first.** Normal objects, normal selection, normal undo.
