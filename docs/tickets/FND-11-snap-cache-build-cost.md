# FND-11 — Bring the projected snap cache build within budget

**Milestone:** M2 Fluency (carried from M1)
**Effort:** M
**Depends on:** FND-08
**Version impact:** Patch.

## Problem

`FND-08` set a budget of **under 100 ms to build the 1M-vertex source cache** and
measured the result. The query path came in far under budget, but the build did not:

| Reference scene | Build | Reproject | Query |
| --- | --- | --- | --- |
| 10k vertices, 1 object | 35 ms | 21 ms | 0.013 ms |
| 100k vertices, 1 object | 380 ms | 306 ms | 0.013 ms |
| 100k vertices, 50 objects | 380 ms | 314 ms | 0.013 ms |
| 1M vertices, 10 objects | **4,886 ms** | **3,729 ms** | 0.013 ms |

Measured on AMD Ryzen 5 7520U, 14 GB RAM, Ubuntu 26.04, Blender 5.2.0 LTS, via
`tests/snap_benchmark.py`.

## What prevents meeting the budget today

`_build_sources()` in `dimensions/projected_snap.py` allocates one Python dictionary
per vertex and `_project_sources()` calls `location_3d_to_region_2d` once per vertex.
At a million vertices that is a million dictionaries and a million individual
projection calls, and no amount of caching around the outside changes the constant.

The cache design is right — a pure view change already reprojects without rescanning
mesh data, which is why `FND-08`'s other criteria pass. The remaining cost is the
per-vertex Python object overhead itself.

## Approach

Replace the per-vertex dictionaries with parallel arrays:

- Read coordinates in bulk with `mesh.vertices.foreach_get("co", buffer)` instead of
  iterating `obj.data.vertices`.
- Transform and project with a single matrix multiply over the whole buffer rather than
  one `location_3d_to_region_2d` call per vertex.
- Keep the spatial grid, but store indices into the arrays instead of dictionaries, and
  materialise a snap dictionary only for the handful of candidates a query actually
  returns.

## Acceptance criteria

- [ ] Build of the 1M-vertex reference scene is under 100 ms, or the budget is revised
      with a documented rationale and the README limitation restated to match.
- [ ] Reprojection after a pure view change is under 50 ms on the same scene.
- [ ] Query time does not regress from the current 0.013 ms.
- [ ] Snapping results are unchanged at every density — the existing occlusion and
      priority tests still pass, and vertex, edge, and face targets resolve identically.
- [ ] `tests/snap_benchmark.py` numbers are re-recorded in `DESIGN.md`.

## Code map

- `dimensions/projected_snap.py` — `_build_sources()`, `_project_sources()`,
  `nearest_visible_projected_vertex()`, `_get_cache()`.
- `tests/snap_benchmark.py` — the reference scenes and measurement harness.

## Verification

Re-run `tests/snap_benchmark.py` before and after and record both. The smoke suite's
snapping tests are the correctness gate; they must pass unchanged.

## Out of scope

- Changing which targets are offered or how they are scored — that is `UX-05` and
  `UX-03`.
- Level-of-detail or vertex decimation. Consider only if array projection alone cannot
  meet the budget, and file separately.

## Invariants

- **Truthful state.** A faster cache must never offer a snap that is occluded, and must
  never miss a target the slower path would have found.
