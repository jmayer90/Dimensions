# FND-07 — Lifecycle hardening: undo, append, link, multi-scene

**Milestone:** M1 Foundation
**Status:** ✅ Complete — the lifecycle matrix remains verified; query-time RNA writes and linked tool mutations were hardened in the 0.6.0 candidate.
**Effort:** M
**Depends on:** FND-02
**Version impact:** Patch.

## Problem

`DESIGN.md` previously listed proxy lifecycle as known risk 5: background save/reload passed, but foreground, append/link, and undo/redo behavior still needed release QA. Blender 5.2 background coverage now exercises the persistent-data matrix, and a foreground two-window check verifies scene isolation.

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

- [x] The full object-type × operation matrix is documented in `DESIGN.md` with the expected result for every cell.
- [x] Every cell either behaves as documented or has a filed follow-up ticket referenced from the matrix.
- [x] Undo and redo restore annotations, anchors, mesh attributes, and proxies consistently, with caches cleared.
- [x] No cache keyed on an object pointer or index survives an undo.
- [x] Annotations from a linked library are never written to; the UI presents them as read-only.
- [x] Deleting a source object leaves affected annotations in a visible repair state, never a silently wrong value.
- [x] Duplicating an annotation produces documented, deliberate behavior.
- [x] Two scenes with annotations in two windows each show and sync correctly with no cross-scene leakage.
- [x] `DESIGN.md` known risk 5 is replaced with results.

## Code map

- `dimensions/scene_sync.py` — `@persistent` handlers, `sync_scene_objects()`; add undo/redo handlers, guard linked data.
- `dimensions/collections.py` — scene ownership, `ensure_measurement_snap_proxy()`.
- `dimensions/viewport_state.py` — `prune_stale_states()`.
- `dimensions/projected_snap.py` — cache invalidation.
- `dimensions/anchors.py` — resolution when a target object is gone.
- `dimensions/ui.py` — read-only presentation for linked annotations.
- `tests/blender_lifecycle.py` — the natural home for the matrix.

## Verification

- Blender 5.2 background: `tests/blender_lifecycle.py` passes 18 tests, including real undo/redo and undo past creation; restoration of annotation objects, persistent mesh IDs, and native measurement proxies; invalidation of projected-snap, volume, drawing, and viewport caches; source/annotation deletion; duplicate semantics; append/link through a temporary library; an actual library override; linked-area drawing without RNA writes; and scheduled synchronization across two populated scenes.
- Appended current-version objects entering an unstamped destination cause that scene to receive the current schema stamp on first sync. Linked and overridden annotation objects are skipped by synchronization and exposed as read-only in the UI and editing operators.
- Blender 5.2 foreground: `bpy.ops.wm.window_new_main()` created a second main window for a temporary second scene. Each temporary scene contained one world-anchored dimension with a distinct value (2.0 and 3.0). Each window context resolved its assigned scene; the Annotation Manager registry and scene-owned `Dimensions` collection contained only that scene's object; the other scene's object was absent; and geometry evaluation returned the expected value in both contexts. Cleanup closed the temporary window, restored the original `Scene`, and removed all temporary data.
- This foreground check is recorded evidence rather than an automated test: Blender background mode cannot exercise multiple application windows reliably.
- Run: `/app/blender/blender --background --factory-startup --python tests/blender_lifecycle.py`.

The 0.6.0 hardening pass separates pure plane/derived/set queries from the guarded
scene-sync write phase, removes manager selection writes from panel redraw, and
adds read-only refusal to guide detach/repair, datum promotion, and Area capture.
Blender 5.2 passes the expanded 33-test lifecycle/linked-data suite.

## Out of scope

- Guided repair UI — delivered in `UX-07`; this ticket remains responsible for reaching the repair state correctly.
- New annotation types.

## Invariants

- **Scene ownership.** Annotations belong to scene-owned collections and must not leak across scenes.
- **Truthful state.** Any lifecycle operation that breaks a binding must surface it, not hide it behind a stale value.
