# UX-10 — Focused 0.7 toolset

**Milestone:** M2 Fluency
**Status:** ✅ Complete in 0.7.0.
**Effort:** L
**Depends on:** UX-01, UX-02, CON-01
**Version impact:** Minor, triggers 1 and 2: saved data is converted or removed, and documented tools and the active-plane axis contract are withdrawn.

## Problem

User testing of the 0.6.0 build found that much of the toolset was broken, hard to understand, or both:

- **Broken or unclear tools.** Measure and Create Guide did nothing when clicked. Chain refused to work with an X, Y, or Z direction and broke as soon as a point left its axis. Plane from Face produced a perpendicular plane and then crashed on a stale BMesh face. Area from Selected Faces crashed on every redraw.
- **Hard to use or to understand.** Guide points and planes could not be moved. Grid planes could not be selected or snapped to. The manager's filters were hidden behind Blender's list-filter triangle. Isolate appeared to do nothing, and many buttons showed "Undocumented" on hover.
- **Too much surface.** Baseline, datums, coordinate and elevation dimensions, radial/diameter/arc fitting, angular and spaced guides, and the active construction plane each added concepts that testing could not explain.

The direction from testing was explicit: fewer tools, each one predictable.

## Decisions

- **Keep, and make them work:** linear dimension, Chain, angle, area, Measure, guide line, offset guide, guide point, guide plane (3 points and face), the Annotation Manager, styles, repair, and output.
- **Chain** is a mode of Create Dimension that places ordinary linear dimensions end to end on a shared dimension line. There is no set object.
- **Remove:** Baseline, datums, coordinate, elevation, radial, diameter, arc length, centerline, angular guides, spacing, live derived guides, the guide-plane Offset and Cursor + Normal definitions, and the active construction plane.
- **Construction objects are ordinary movable objects:**
  - a guide point is its object origin;
  - a guide line runs along its object's local X axis;
  - a guide plane is a wireframe grid mesh, so Blender's own selection, transform, and snapping work on it.
- **Grids never block model snapping.** Snaps onto a grid bind as object points, so they follow the grid and survive a spacing change.
- **Isolate** shows only the chosen annotations and keeps the model visible. **Apply To** defaults to the viewport selection.
- **Release review decisions:** middle mouse always navigates (the middle-drag axis gesture is removed; `X`/`Y`/`Z` lock axes); Offset Guide has no flip key (a typed distance goes on the pointer's side, a negative one on the other side, so `2ft` types normally); and dimensions snapped to guide points and lines follow them, as they follow grids. Deleting guides through Dimensions keeps dependent dimensions as fixed points.

## Acceptance criteria

- [x] Measure, Guide Line, Guide Point, Offset Guide, and both plane tools start a modal session when clicked, show snap targets on hover, and create their result.
- [x] Every registered operator resolves to its Python class and has a tooltip; no registered operator subclasses another.
- [x] Chain creates independent linear dimensions whose start is the previous end and whose dimension lines are collinear, with Auto or a locked axis.
- [x] Guide points, guide lines, and guide planes keep a `G`/`R` move through scene synchronization and save/reload.
- [x] Plane: Face lies on the face and extends past it, from an Edit Mode selection or a click, without a `ReferenceError`.
- [x] Guide planes can be selected, are excluded from render and output, snap with Dimensions tools, and never hide model geometry from snapping.
- [x] Area from Selected Faces creates a live Area in Edit Mode without a `ReferenceError`.
- [x] Annotation Manager filters are visible above the list; Isolate hides every other annotation and guide and keeps the model visible; Exit Isolate restores it.
- [x] Schema v16 converts the released 0.6.0 fixture: sets become linear dimensions, derived guides become fixed lines, planes become grids, removed kinds are deleted, and a second migration changes nothing.

## Verification

- `tests/blender_smoke.py` — `DimensionsConstructionTests` (grid geometry, transforms, see-through ray casts, coplanar faces, grid anchors), plus operator-registration and interface-icon checks in `DimensionsPackagingTests`.
- `tests/blender_modal.py` — `ChainDimensionModalTests` and `ConstructionToolModalTests`.
- `tests/blender_lifecycle.py` — moved grid, point, and line save/reload, and `test_schema_v15_fixture_converts_removed_0_6_features` against `tests/fixtures/schema-v15-0.6.0.blend`.
- `tests/foreground_workflows.py` — 36 checks driven by real window events in foreground Blender 5.1.2 and 5.2, including the release-review fixes: typed axis distances, Angle, Object Mode Area, Clear Guides, guide-point following, typed units, middle-mouse navigation, and dense-mesh hover cost.

## Code map

- `dimensions/construction.py` — point, line, measurement, and plane geometry, plus the grid mesh.
- `dimensions/operators/construction_tools.py` — shared point acquisition and the four construction tools.
- `dimensions/operators/create_dimension.py` — the Chain mode.
- `dimensions/snapping.py` — see-through grid ray casts, coplanar grid hits, and outline-edge sampling.
- `dimensions/migrations.py` — `migrate_v15_to_v16`, which reads removed fields through `bl_system_properties_get()`.
- `dimensions/ui.py` and `dimensions/operators/annotation_manager.py` — sidebar layout, visible filters, and Isolate.

## Out of scope

- Guide lines and points that follow the vertex they were placed on. They are fixed, movable objects by design.
- Bringing back any removed tool. A future radial or diameter tool needs its own ticket, with a usability study first.
