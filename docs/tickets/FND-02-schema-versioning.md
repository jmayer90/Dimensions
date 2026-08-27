# FND-02 — Saved-data schema versioning and migration

**Milestone:** M1 Foundation
**Status:** ✅ Complete — delivered in 0.3.0; schema v2 followed in 0.4.0.
**Effort:** L
**Depends on:** —
**Version impact:** Patch to add the framework. Any later schema change that loses data is minor trigger 1.

## Problem

Annotations persist as Blender objects carrying `CADDIM_PG_Dimension`, `CADDIM_PG_Guide`, `CADDIM_PG_Anchor`, and `CADDIM_PG_AreaFaceBinding` property groups, plus mesh attributes `dimensions_anchor_id` and `dimensions_area_face_id`. None of it carries a version stamp.

The only migration that exists is `migrate_anchor_identity()`, which back-fills persistent IDs for anchors created before IDs existed. It is called opportunistically from `scene_sync.py` and infers what to do from whether fields are populated — it cannot distinguish "old file" from "new file with an unset field."

Consequences today:

- Renaming a property silently drops user data. Blender loads the file, the property is absent, the default applies, and the annotation is quietly wrong rather than visibly broken.
- Changing the meaning of a field — units, sign convention, what an enum value denotes — corrupts existing files with no way to detect it.
- There is no way to warn a user that a file was made by a newer version than they are running.

This costs almost nothing to add now and becomes progressively harder with every release that ships without it. `OUT-03` (named styles) and `UX-02` (bulk operations) both want to reshape stored data, and neither is safe to attempt first.

## Why it blocks 1.0

The 1.0 promise is that files keep working. That promise cannot be made retroactively — it requires a version stamp present in the files 1.0 users will later be upgrading from.

## Approach

**Stamp.** Add an integer `schema_version` to `CADDIM_PG_SceneSettings`, written on every scene that owns Dimensions data. Use a module-level `CURRENT_SCHEMA_VERSION` constant in `constants.py`. Start at `1`, describing today's shape.

Prefer a single scene-level stamp over a per-object one: it is one place to read and write, and migrations run per scene anyway. Note the trade-off in `DESIGN.md` — objects appended from another file arrive without a stamp, which `FND-07` must handle by treating unstamped-but-populated data as the version current at append time.

**Dispatcher.** Add `dimensions/migrations.py`:

- `migrate_scene(scene)` reads the stamp and applies each step in order from the file's version to `CURRENT_SCHEMA_VERSION`.
- Steps are registered functions `migrate_v1_to_v2(scene)` etc., each idempotent and each covering all four property groups plus mesh attributes.
- Runs from a `@persistent` `load_post` handler and on demand from the append/link path.
- A file stamped **newer** than `CURRENT_SCHEMA_VERSION` is never modified. Report a clear warning once and leave the data alone.

**Retrofit.** Treat unstamped scenes that contain Dimensions objects as version `0` and write a `migrate_v0_to_v1` that performs what `migrate_anchor_identity()` does today, then stamps them. Keep `migrate_anchor_identity()` working during the transition; remove the opportunistic calls from `scene_sync.py` once migration owns the job, so per-depsgraph-update work stops doing schema repair.

**Document.** Add a table to `DESIGN.md`: schema version, the release that introduced it, and what changed. Every future schema change adds a row and a migration step in the same PR.

## Acceptance criteria

- [ ] `CURRENT_SCHEMA_VERSION` exists in `constants.py` and `schema_version` is stored on scene settings.
- [ ] A scene containing Dimensions data is stamped on save or on first migration, whichever comes first.
- [ ] `load_post` migrates any scene whose stamp is below current, and does nothing to a scene already at current.
- [ ] Migrations are idempotent: running the dispatcher twice produces identical data.
- [ ] A scene stamped above `CURRENT_SCHEMA_VERSION` is left unmodified and reports one clear warning naming the add-on version needed.
- [ ] Unstamped scenes containing Dimensions objects migrate through `v0 → v1` and end up stamped.
- [ ] A scene with no Dimensions data is not stamped and not modified.
- [ ] `scene_sync.py` no longer performs schema repair on depsgraph updates.
- [ ] `DESIGN.md` documents the schema table and the rule that schema changes ship with a migration step.
- [ ] `CONTRIBUTING.md` versioning section is updated to reference the migration requirement.

## Code map

- `dimensions/migrations.py` — new.
- `dimensions/constants.py` — `CURRENT_SCHEMA_VERSION`.
- `dimensions/properties.py` — `CADDIM_PG_SceneSettings`, and the property groups being versioned.
- `dimensions/anchors.py` — `migrate_anchor_identity()` moves behind the dispatcher.
- `dimensions/scene_sync.py` — remove opportunistic migration calls; register the `load_post` handler alongside the existing `@persistent` handlers.
- `dimensions/__init__.py` — component registration.

## Verification

- Unit tests for the dispatcher: version below current migrates, at current is a no-op, above current warns and does not modify.
- Idempotence test: migrate twice, compare a full property dump.
- A `v0 → v1` test that builds a scene with anchors stripped of persistent IDs and asserts they resolve correctly afterward.
- **Fixture files.** Create `tests/fixtures/` with a `.blend` saved by each released version that had annotations, starting with 0.2.3. Add a test that opens each and asserts annotations resolve. This directory grows by one file per schema change and is the backbone of the 1.0 gate.

## Out of scope

- Any actual schema change. This ticket adds the framework and describes today's shape as version 1.
- Cross-version property renames. They become possible after this, and each is its own ticket.

## Invariants

- **Truthful state.** A migration that cannot fully recover data must leave the annotation in a visible repair state, never a plausible-looking wrong value.
- **Blender-native data first.** Migration reads and writes normal Blender data and stays undoable.
