# UX-03 — Inference: parallel, perpendicular, extension, intersection, local axis

**Milestone:** M2 Fluency
**Effort:** L
**Depends on:** FND-08
**Version impact:** Patch, unless it changes documented constraint keys — coordinate with `FND-05`.

## Problem

Snapping acquires points that **already exist**: vertices, edges, midpoints, face centers, guide and measurement points. Constraints are limited to aligned and the three global axes.

What is missing is inference — deriving points and directions that are implied by existing geometry but not present in it:

- **Parallel and perpendicular** to an edge, a face normal, or a previously acquired direction.
- **Extension** — a point along the continuation of an edge past its endpoint.
- **Intersection** — where two edges, an edge and a guide, or two guides would meet if extended.
- **Local axis** — the active object's own X/Y/Z rather than the world's, which is what a user wants when the object is rotated.
- **Face plane and active plane** — constraining a point to lie on a plane rather than a line.

Without these, dimensioning a rotated object is awkward, and constructing a point "20 mm past the end of that edge, perpendicular to this face" — an ordinary CAD operation — is not expressible.

This is the core of the P1 roadmap item and the technical heart of the "dimensionally built construction" goal.

## Why it matters for 1.0

Inference plus construction geometry (`CON-*`) is what separates a measuring tool from a tool you can build with. It is not in the 1.0 gate as a hard requirement, but the gate's premise — that this is useful for dimensionally built construction — is thin without it.

## Approach

This is large. Consider splitting into per-inference-type PRs after the framework lands.

**A candidate model.** Extend the existing snap candidate structure so an inference result is a candidate like any other, carrying its type, the geometry it derives from, and a priority. `_best_snap_candidate()` already scores candidates — inference should feed that, not bypass it.

**Priority matters more than breadth.** The failure mode of inference systems is offering too much: the cursor flickers between competing inferences and the user cannot land the point they want. Rank explicitly — existing geometry beats derived geometry; a closer candidate beats a farther one; a candidate derived from recently-referenced geometry beats an unrelated one.

**Reference acquisition.** Parallel and perpendicular need a reference direction. Two mechanisms, both worth having: implicit (the last edge or face hovered becomes the reference for a short window) and explicit (a key that locks the currently hovered element as the reference). Explicit locking is what makes it reliable; implicit is what makes it feel fast.

**Explicit lock.** The roadmap already calls for this. Once an inference is active, a key locks it so moving the mouse cannot lose it. This is what makes inference trustworthy rather than fiddly.

**Visual language.** Each inference type needs a distinct, immediately readable indicator — a dashed extension line, a perpendicular tick, an intersection cross — plus text naming what is inferred. The existing convention is orange for active and blue for accepted; inference indicators must fit it rather than inventing a third scheme.

**Local axis.** Smaller and independently useful. Add local X/Y/Z alongside the global constraints, using the active object's matrix. Decide how the user selects between global and local — a modifier on the axis key, or pressing the same axis key twice, which is Blender's own convention in the transform tools and therefore the better choice.

## Acceptance criteria

- [ ] Inference candidates flow through the existing snap candidate scoring, not a parallel path.
- [ ] Parallel, perpendicular, extension, intersection, local-axis, and face-plane inference are all available during point acquisition.
- [ ] A reference direction can be acquired both implicitly (recent hover) and explicitly (lock key).
- [ ] An explicit lock key holds the active inference through mouse movement until released.
- [ ] Each inference type has a distinct visual indicator plus naming text, consistent with the existing orange/blue convention.
- [ ] Priority is documented and deterministic — the same cursor position over the same geometry always yields the same candidate.
- [ ] Existing geometry always outranks derived geometry at comparable distance.
- [ ] Local axis constraint works on rotated objects and is documented as distinct from global.
- [ ] Inference does not regress the snap performance budgets from `FND-08`; measure and record.
- [ ] Inference can be disabled by type in preferences, for users who find it noisy.
- [ ] `DESIGN.md` interaction contract documents inference, priority, and the lock.
- [ ] README limitations no longer claim inference is unimplemented.

## Code map

- `dimensions/snapping.py` — candidate model, `_best_snap_candidate()` scoring.
- `dimensions/inference.py` — new; derivation of parallel, perpendicular, extension, intersection candidates.
- `dimensions/interaction.py` — constraint state, lock key, axis handling for local axes.
- `dimensions/drawing.py` — `_snap_highlight_geometry()`, `_draw_snap_highlight()`, indicator drawing.
- `dimensions/projected_snap.py` — if inference candidates need caching.
- `dimensions/preferences.py` — per-type enable toggles.

## Verification

- Unit tests per inference type against known geometry, including the degenerate cases: parallel edges that never intersect, coincident edges, perpendicular where the reference is itself perpendicular to the view.
- Priority tests: construct geometry where several inferences compete and assert the documented winner.
- A determinism test: same cursor, same geometry, same result across repeated queries.
- Performance comparison against the `FND-08` baseline on the reference scenes.

## Out of scope

- Construction geometry that persists — `CON-01` through `CON-04`. Inference is transient; guides are saved.
- Constraint solving or parametric relationships. Inference derives a point at acquisition time; it does not create a maintained relationship.
- Snapping to inferred geometry of *other* annotations.

## Invariants

- **Preview before commit.** An inferred point must be visibly identified as inferred, and which geometry it derives from must be shown, before the user commits.
- **Non-destructive annotation.** Inference reads topology and never modifies it.
