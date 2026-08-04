# FND-07 — Lifecycle hardening: undo, append, link, multi-scene

**Milestone:** M1 Foundation
**Effort:** M
**Depends on:** FND-02
**Version impact:** Patch.

## Problem

`DESIGN.md` lists proxy lifecycle as known risk 5: background save/reload passes, but "foreground, append/link, and undo/redo behavior still need release QA." That QA has not happened, and the paths involved are where Blender add-ons most often lose user data.

Specific exposures:

- **Undo/redo.** Blender's undo restores whole datablocks. Annotation objects, their property groups, the mesh attributes `dimensions_anchor_id` and `dimensions_area_face_id`, and the native measurement snap proxies must all come back consistent. Caches in `viewport_state.py` and the projected snap cache in `projected_snap.py` hold references and derived data across an undo that replaces the objects underneath them.
- **Append and link.** Appending an annotation from another file brings the object and its properties but not necessarily its source object, its collection membership, or a schema stamp. Linked annotations are read-only, and `scene_sync.py` writes to annotations during depsgraph updates — writing to linked data raises.
- **Multiple scenes.** `collections.py` enforces scene-owned collections, but the depsgraph handler and the draw path both reach through `bpy.context`, whose scene depends on which window is active. Two scenes each with annotations, in two windows, is untested.
- **Object deletion.** Deleting a source object leaves annotations whose anchors resolve to nothing. Deleting one half of a linear dimension's anchors, or an area's source object, should produce a visible repair state — the current behavior is unverified.
- **Library overrides.** Not considered at all.

## Why it blocks 1.0

The 1.0 gate requires every persistent object type to survive save/reload, undo/redo, append, and link. These are also the failures users cannot work around and will not forgive.

## Approach

Treat this as an audit with fixes, not a feature. Work through a matrix of **object type × operation** and fix what fails:

Object types: linear dimension, angle dimension, area dimension, measurement, measurement snap proxy, construction guide.

Operations: save/reload, undo, redo, undo past creation, duplicate (`Alt+D` and `Shift+D`), delete source object, delete annotation, append from another file, link from another file, move between scenes, copy to a second scene, library override.

For each cell, define the correct behavior before testing it. Some cells should legitimately produce a repair state rather than working — write that down as the expected result so it is not mistaken for a bug.

Specific work likely needed:

- **Cache invalidation on undo.** Register a `@persistent` `undo_post` / `redo_post` handler that clears the projected snap cache and per-viewport state. Pointer-keyed caches must not survive an undo.
- **Guard writes to linked data.** `scene_sync.py` must skip annotations whose `library` is not `None`, and the UI must show them as read-only rather than offering edit actions that fail.
- **Explicit scene resolution.** Audit the depsgraph handler and draw path for `bpy.context` reads that should be explicit scene or depsgraph parameters.
- **Duplication semantics.** Decide and document what duplicating an annotation means — most likely a copy anchored to the same sources, which then needs the anchor IDs handled deliberately rather than by accident.
- **Append without a stamp.** Coordinate with `FND-02`: appended objects arrive unstamped, and the migration path must handle "unstamped but populated" without corrupting current-version data.

## Acceptance criteria

- [ ] The full object-type × operation matrix is documented in `DESIGN.md` with the expected result for every cell.
- [ ] Every cell either behaves as documented or has a filed follow-up ticket referenced from the matrix.
- [ ] Undo and redo restore annotations, anchors, mesh attributes, and proxies consistently, with caches cleared.
- [ ] No cache keyed on an object pointer or index survives an undo.
- [ ] Annotations from a linked library are never written to; the UI presents them as read-only.
- [ ] Deleting a source object leaves affected annotations in a visible repair state, never a silently wrong value.
- [ ] Duplicating an annotation produces documented, deliberate behavior.
- [ ] Two scenes with annotations in two windows each show and sync correctly with no cross-scene leakage.
- [ ] `DESIGN.md` known risk 5 is replaced with results.

## Code map

- `dimensions/scene_sync.py` — `@persistent` handlers, `sync_scene_objects()`; add undo/redo handlers, guard linked data.
- `dimensions/collections.py` — scene ownership, `ensure_measurement_snap_proxy()`.
- `dimensions/viewport_state.py` — `prune_stale_states()`.
- `dimensions/projected_snap.py` — cache invalidation.
- `dimensions/anchors.py` — resolution when a target object is gone.
- `dimensions/ui.py` — read-only presentation for linked annotations.
- `tests/blender_lifecycle.py` — the natural home for the matrix.

## Verification

- One test per matrix cell that can run headless, in `blender_lifecycle.py` restructured per `FND-06`.
- Undo/redo tests that assert cache state, not just object existence.
- An append test using a fixture `.blend` from `tests/fixtures/` (created in `FND-02`).
- Foreground checks for the two-window, two-scene cases, with results recorded in the PR.

## Out of scope

- Guided repair UI — `UX-07`. This ticket ensures the repair *state* is reached correctly; presenting a fix is separate.
- New annotation types.

## Invariants

- **Scene ownership.** Annotations belong to scene-owned collections and must not leak across scenes.
- **Truthful state.** Any lifecycle operation that breaks a binding must surface it, not hide it behind a stale value.
