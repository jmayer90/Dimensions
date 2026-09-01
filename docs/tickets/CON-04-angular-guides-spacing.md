# CON-04 — Angular guides and repeated spacing

**Milestone:** M3 Construction
**Status:** ✅ Complete in 0.5.0; anchored Spacing acquisition and repair hardened in the 0.6.0 candidate.
**Effort:** M
**Depends on:** CON-02
**Version impact:** Patch. Additive.

## Problem

Two gaps in the construction toolkit, both listed in the P1 roadmap.

**Angular guides.** A guide at a typed angle from an existing edge or guide, about a point. Roof pitches, chamfer angles, radial layouts, anything on a bevel. Currently expressible only by placing points you have computed yourself.

**Repeated spacing.** A series of parallel guides at a regular interval — stud spacing, shelf pitch, mullion layout, grid lines. `CON-02` creates one offset guide; laying out fifteen at 400 mm means fifteen operations, and adjusting the spacing afterwards means redoing all of them.

Both are ordinary drafting operations. Their absence is what makes the guide system feel like a marker tool rather than a layout system.

## Why it matters for 1.0

Not a 1.0 gate item. But regular spacing is the operation that most often turns a modelling session into a layout session, and it is where the tool's construction claim is most visibly tested.

## Approach

### Angular guides

Extend `CON-02`'s derived-guide model. An angular guide stores a source direction, a pivot point, and an angle, resolving position from them so the source can move.

- Typed angle entry through the existing numeric path, accepting degrees and, where the scene is set to radians, radians. `units.py` handles linear units; angle parsing likely needs adding — check before assuming.
- Live preview with the angle shown before commit, and a key to flip direction.
- Support angle from an edge, from another guide, and from a plane's in-plane reference once `CON-03` lands.

### Repeated spacing

The design decision is whether a spaced set is **one object or many**.

Recommend **one object holding a definition**: origin, direction, interval, and count. Reasons: adjusting interval or count is then one edit rather than a rebuild; the scene stays clean; and it matches how the rest of the project separates definition from presentation. Each generated line still needs to be an individual snap target, which the drawing and snapping layers can produce from the definition without materialising objects.

Verify early that `snapping.py`'s candidate generation can emit candidates for generated lines without an object per line. If it cannot, that is a prerequisite change and should be sized before starting.

Support both count-driven ("fifteen guides at 400 mm") and extent-driven ("guides at 400 mm until 6 m"), since users think in both. Offer a "distribute evenly between these two" mode, which is common and awkward to express with either of the first two.

Provide an explicit "bake to individual guides" action for when a user wants to adjust one line independently.

## Acceptance criteria

**Angular guides**

- [x] A guide can be created at a typed angle from an edge or another guide, about a chosen pivot point.
- [x] Angle entry accepts degrees, and radians when the scene unit rotation is radians.
- [x] Live preview shows the resulting guide and the angle before commit; `F` flips direction.
- [x] Angular guides store their source relationship and update when the source moves.
- [x] A lost source produces a visible repair state.

**Repeated spacing**

- [x] A spaced set is created from an origin, direction, interval, and count or extent.
- [x] "Distribute evenly between two references" is supported through the source origin and anchored end reference.
- [x] Interval and count are editable after creation, updating the whole set.
- [x] Every generated line is an individual snap target.
- [x] A "bake to individual guides" action produces separate guide objects at the same positions.
- [x] A spaced set displays as one manager entry (`UX-02`), not as N entries.
- [x] Creation and each subsequent edit are single undo steps.

**Both**

- [x] Schema changes go through the `FND-02` migration framework.
- [x] Spaced sets with a large count do not regress the `FND-03` draw budget or the `FND-08` snap budget; measure with 200 generated lines.
- [x] README and `DESIGN.md` document both features.

## Code map

- `dimensions/properties.py` — angular guide and spaced-set property groups.
- `dimensions/operators/create_guide.py` — creation operators.
- `dimensions/snapping.py` — candidates for generated lines without one object per line.
- `dimensions/drawing.py` — spaced-set rendering and angle preview.
- `dimensions/units.py` — angle parsing, if not already present.
- `dimensions/scene_sync.py` — resolving derived angular guides.
- `dimensions/ui.py` — editing interval and count on a selected set.

## Verification

- Angular guide tests at known angles, including 0°, 90°, 180°, and negative angles.
- Angle parsing tests for degrees and radians, including malformed input.
- Spacing tests for count-driven, extent-driven, and distribute-evenly modes.
- A test that editing interval or count updates every generated line.
- A test that bake produces guides at positions identical to the generated ones.
- A test that every generated line is returned as a snap candidate.
- Performance measurement with 200 generated lines against the `FND-03` and `FND-08` budgets.

On Blender 5.1.2, the deterministic 200-line benchmark measures 0.125 ms for
production draw preparation and 2.287 ms for a public guide-snap query, below
the respective 33.333 ms and 8 ms budgets. The benchmark is part of both release
validation scripts.

The 0.6.0 hardening pass turns Spacing creation into an anchored modal workflow:
all modes acquire an origin and Distribute acquires a second endpoint through the
shared snap/inference/active-plane path. Both anchors persist their source type,
can be repaired independently, and are covered for source motion, loss, repair,
click-without-mousemove, and pure query resolution on Blender 5.2.

## Out of scope

- Radial and polar arrays of guides. Same family, worth doing, separate ticket once linear spacing is proven.
- Arrays of guide points rather than lines. Natural follow-up.
- Arraying mesh geometry, which is geometry authoring and excluded.

## Invariants

- **Non-destructive annotation.** Nothing here creates or modifies mesh.
- **Truthful state.** A spaced set whose origin or direction source is lost must be visibly broken.
- **Scene ownership.** Generated lines belong to the scene-owned `Construction Guides` collection.
