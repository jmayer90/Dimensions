# FND-13 — Lifecycle, modal cleanup, and Blender API hardening

**Milestone:** M6 1.0 gate
**Status:** ⬜ Planned — accepted after FND-12.
**Effort:** M
**Depends on:** FND-12, FND-07
**Version impact:** Patch.

## Problem

Eight confirmed state-management defects remain across migrations, dimension sets,
the Annotation Manager, and modal overlays:

- a scene with an older nonzero schema or custom styles but no annotation objects is
  treated as empty; first-object stamping can skip every migration;
- migration loops do not consistently skip linked/read-only objects before an
  anchor migration attempts to create mesh attributes;
- moving a Chain member reorders shared anchors into a backward segment and can put
  the set into `NEEDS_REPAIR`;
- isolate restore ignores records whose objects are excluded from the active view
  layer, losing their saved property visibility;
- deleting the final dimension-set member removes its object without synchronizing
  the Annotation Manager registry;
- preview cleanup derives its viewport key from the current global context, so an
  operator cancelled over another editor can leave a ghost overlay in the original
  3D View;
- modal operators do not all implement Blender's external `cancel()` cleanup path;
  the audit specifically reaches guide-point, guide-plane, anchor-reattach, and area
  repair workflows, with multiple modal classes in those files; and
- Grease Pencil output writes the deprecated `show_stroke` property. The reported
  `world.use_nodes` write is not present in the current tree, so it requires no code
  change unless a failing compatibility test locates another call site.

These paths violate the project's existing lifecycle, truthful-state, and
per-viewport ownership contracts even though the broad FND-07 matrix is complete.

## Approach

- Define “scene has Dimensions data” from persisted schema/settings/registries as
  well as objects. A first write must migrate an older scene before stamping current;
  it must never jump over intermediate idempotent migrations.
- Apply the shared read-only predicate before every migration mutation, including
  mesh identity creation, while still migrating local scene-owned settings.
- Refuse Chain reordering unless a monotonic, semantics-preserving operation is
  specified. Do not silently reorder anchors and manufacture invalid geometry.
- Separate property visibility restoration from active-view-layer `hide_set()`
  restoration so excluded objects keep their saved property value and records are
  cleared deterministically.
- Synchronize the manager after the final set object is removed.
- Capture the invoking viewport key on every preview-producing operator and pass it
  through all finish, cancel, context-change, and exception cleanup paths. Make
  cleanup idempotent.
- Audit every class with `modal()` for an explicit `cancel()` that invokes its shared
  cleanup, including cursor/status restoration where applicable.
- Remove deprecated API writes only when behavior is already the Blender 5.x default;
  protect the decision with declared Blender 5.1/5.2 tests and a Blender 6.0
  compatibility check when available.

## Acceptance criteria

- [ ] A released older-schema fixture containing custom styles/settings but no
  annotation objects migrates through every schema step exactly once before its
  first new annotation is stamped current.
- [ ] Migration never mutates linked or overridden objects or their mesh data and
  completes without `RuntimeError`; local scene-owned settings still migrate.
- [ ] Chain member reordering cannot create a reverse or off-axis segment. If the
  operation has no unambiguous semantic meaning, the UI refuses it actionably.
- [ ] Isolate/restore preserves property visibility for objects excluded from the
  active view layer and restores `hide_set()` where the view layer permits it.
- [ ] Deleting the last set member removes the manager row in the same undoable
  operation and leaves no dead pointer.
- [ ] Every preview is cleared from the exact invoking viewport on confirm, normal
  cancel, editor change, Blender external cancellation, file/window change, and
  operator exception.
- [ ] Every modal operator has an idempotent external `cancel()` path covered by a
  source-level audit and representative behavioral tests.
- [ ] Grease Pencil output creates equivalent visible strokes without deprecated
  `show_stroke`; no speculative `world.use_nodes` edit is made without evidence.
- [ ] Save/reload, undo/redo, append/link, and two-scene lifecycle coverage remain
  green on Blender 5.1 and 5.2.

## Code map

- `dimensions/migrations.py`, `dimensions/properties.py` — scene-data detection and
  read-only migration boundaries.
- `dimensions/dimension_sets.py`, `dimensions/operators/dimension_set.py` — reorder
  semantics and manager synchronization.
- `dimensions/operators/annotation_manager.py` — isolate records and excluded
  collections.
- `dimensions/drawing.py`, `dimensions/viewport_state.py`, and modal operators under
  `dimensions/operators/` — explicit viewport ownership and cleanup.
- `dimensions/grease_pencil_output.py` — deprecated property removal.
- `tests/blender_lifecycle.py`, `tests/blender_modal.py`,
  `tests/dimension_set_smoke.py`, `tests/output_smoke.py` — regression evidence.

## Verification

- Add a released-file-style no-object/old-settings fixture and assert sequential,
  idempotent migration plus preservation of custom values.
- Link an annotation source and run the migration/synchronization path while
  asserting the library data is unchanged.
- Exercise every exposed Chain move direction, excluded-collection isolate restore,
  and final-member deletion with manager state and undo assertions.
- Invoke previews in one 3D View, cancel from another editor or through each
  operator's `cancel()`, and assert only the invoking viewport state is removed.
- Generate and minimally render Grease Pencil output without the deprecated write;
  treat Blender 6.0 warnings as compatibility evidence, not a supported-version
  expansion.
- Run `scripts/validate.ps1`.

## Out of scope

- A new semantic model for arbitrary Chain member permutation. Refusal is acceptable
  unless a separate design proves reorder meaning and preserves the shared axis.
- Editing linked data, changing collection exclusion, or opening excluded collections
  as a side effect of visibility restore.
- Declaring Blender 6.0 support before the manifest and CI matrix do so.

## Invariants

- **Schema continuity.** Persisted data advances sequentially and idempotently; first
  use cannot skip migrations.
- **Read-only libraries.** Linked and overridden data is observed, never mutated.
- **Per-viewport state.** A tool owns and cleans the viewport where it was invoked,
  regardless of the current global context.
- **Truthful set geometry.** UI operations cannot silently turn a valid Chain into a
  backward or repair-state chain.
