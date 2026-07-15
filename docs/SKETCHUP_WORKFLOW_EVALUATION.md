# SketchUp Workflow Evaluation and Roadmap

Date: 2026-07-14

## Executive assessment

Dimensions now contains credible first versions of all four priority workflows:

- persistent construction lines;
- persistent dimensions;
- a finite measurement/tape workflow; and
- a chained Edit Mode pencil/line tool.

This is a strong experimental core, not yet a production-safe SketchUp-style modeling layer. The add-on already solves more of the hard geometry problem than its `0.1.0` version suggests: shared logical snapping, free-space previews, typed scene-unit lengths, persistent annotations, vertex/edge binding, edge splitting, single-face knife-like paths, and closed-loop face creation are all present. The implementation follow-up passed all 35 Blender 5.1 smoke tests.

The largest remaining gap is not the absence of more tools. SketchUp's characteristic speed comes from a shared interaction language: inference points and lines, lockable directions and planes, a Measurements box that works consistently, predictable cancel/undo behavior, and immediate visual explanations of what will happen. Dimensions currently has useful pieces of that language, but each modal operator still implements a different subset.

The recommended product sequence is therefore:

1. Done for currently supported open/closed single-face cuts: make Pencil topology commits recoverable and preserve the loose path on failure.
2. Replace per-mouse-move full vertex scans with a depth-aware cached snap index.
3. Extend the new shared numeric/confirmation helpers into a complete inference and constraint toolkit.
4. Add stable vertex identity and stronger surface association on top of the new object-local anchors and broken-reference warnings.
5. Improve the four priority workflows before reconsidering broader tool expansion.

Scope decision: the seven higher-level modeling proposals in the original audit are not on the active roadmap. They are retained only as historical ideas and should not be implemented without a new product decision.

## Reference behavior

This evaluation uses the current official SketchUp workflow as a behavioral reference, not as a requirement to clone its UI exactly:

- [Precise Modeling with Measurements](https://help.sketchup.com/en/sketchup/measuring-angles-and-distances-model-precisely) describes Tape Measure, Protractor, guide lines/points, and the cross-tool Measurements box.
- [Measuring Distance](https://help.sketchup.com/en/measuring-distance) describes Tape Measure's measure, guide-line, and guide-point modes, hover measurements, and optional model rescaling.
- [Using Guides](https://help.sketchup.com/en/using-guides) describes offset guide creation, guide points, infinite guides, individual hide/erase, and clear-all behavior.
- [Introducing Drawing Basics and Concepts](https://help.sketchup.com/en/sketchup/introducing-drawing-basics-and-concepts) describes endpoint, midpoint, intersection, on-edge/on-face, axis, from-point, through-point, extension, parallel, perpendicular, and plane inference plus Shift/arrow-key locking.
- [Using the Measurements Box](https://help.sketchup.com/en/using-measurements-box) establishes consistent typed values and explicit unit suffixes across modeling tools.

## Capability scorecard

Scores describe readiness for the requested SketchUp-like workflow, not code effort or feature count.

| Capability | Current readiness | What is already strong | Main gap |
| --- | --- | --- | --- |
| Construction lines | 3/5 | Persistent infinite lines, aligned/global axes, linked vertex anchors, visibility, selection, clearing, snap projection | The workflow creates a line from two points instead of the common offset-from-edge guide; no guide points, angular guides, editable offsets, dashes, or chain/repeat workflow |
| Dimensions | 4/5 | Three-click placement, typed endpoint/offset values, target highlighting, true 3D value, object-local edge/face anchors, reattachment, styling, hit selection, and broken-reference warnings | Vertex identity remains index-based; no projected/angular/radial/baseline/chain dimensions or export/render path |
| Tape Measure | 2.5/5 | Continuous preview, logical snaps, typed units, global-axis constraints, persistent finite segment, label, custom and native endpoint snap targets | This is a saved construction segment, not yet a full Tape Measure: no hover-only readout, mode cycling, offset guide/guide point creation, optional ephemeral result, or resize-to-measure workflow |
| Pencil / Line | 3.5/5 | Chained segments, typed/Enter commit, global axes, live target highlighting, direct vertex binding, edge splitting, recoverable deferred one-face cuts, and closed loops sharing one existing vertex | One modal session has coarse undo semantics; no inference locks, multi-face cutting, or robust self-intersection/non-manifold handling |
| Shared inference | 3/5 | Common numeric editing/confirmation, target and lock highlights, vertices, edge projections, midpoints, face centers/points, guides, measurements, and free-space points | Full visible-vertex scans, no depth filtering, intersections, extensions, local axes, parallel/perpendicular inference, guide planes, or target filters |

## Priority findings

### P0 resolved for supported cases: Pencil failure preserves existing topology and the loose path

The implementation follow-up changed `dimensions/operators/create_line.py` so open-path cleanup happens only after `face_split` succeeds. Closed-loop replacement faces are now built before the source face is removed, with rollback of newly created faces/edges on construction failure. A forced-failure regression test asserts that the original counts and complete loose path remain unchanged.

- `_finalize_open_surface_path()` now leaves the accepted path untouched until the replacement split exists.
- `_cut_closed_loop_in_face()` now leaves the original surface face in place until all replacement geometry exists, and cleans up new partial geometry on failure.
- A closed loop may share one vertex with the surrounding face or an existing cut; this covers the reported triangle-apex/odd-loop case.

The current happy-path tests are valuable, but unsupported, degenerate, self-intersecting, boundary-touching, or numerically difficult input is exactly where a modeling tool must fail without damaging the mesh.

During the audit, the newly added `test_path_across_a_nonplanar_visible_face_splits_the_face` initially exposed a refusal to split a non-planar quad. The concurrently updated surface-tolerance calculation made that regression test pass in the final run. Keep the case as a permanent regression test: membership tolerance for non-planar n-gons can easily become either too strict (rejecting visible paths) or too broad (accepting points away from the surface), and silent refusal after temporary mesh edges have already been created is not sufficient feedback.

Remaining recommendation:

- Separate topology planning/validation from commit.
- Validate the path, target faces, coplanarity, self-intersection, edge reuse, and expected output on a copied BMesh or other temporary representation.
- Extend validation/rollback coverage to self-intersection, repeated points, custom-data preservation, multi-face paths, and non-manifold input.

### P1: Snapping is linear in every visible vertex on every mouse move

`dimensions/snapping.py::_nearest_projected_vertex()` iterates every vertex of every visible mesh in Object Mode, and every active BMesh vertex in Edit Mode. Every point-picking modal calls this during mouse movement. That gives useful capture of newly created topology, but it will eventually dominate interaction time on production models.

The same fallback is not depth filtered, so an occluded vertex sharing the same screen neighborhood can beat the visible surface. This is already documented as a limitation and should be treated as a correctness issue as well as a performance issue.

Recommendation:

- Maintain a per-viewport projected candidate cache keyed by object geometry revision, object transform, region size, and view matrix.
- Rebuild incrementally from changed objects and live Edit Mode topology.
- Query candidates with a 2D spatial index before doing exact scoring.
- Reject candidates behind the camera or materially behind the visible depth at the pointer, with a deliberate option to include occluded targets.
- Add target filters for vertex, midpoint, edge, face, origin, guide, and measurement classes.
- Establish budgets such as sub-8 ms hover updates around 250k visible vertices and usable interaction around one million visible vertices on reference hardware.

### P1 partially resolved: object-local surface anchors and visible broken-reference state

`dimensions/anchors.py::set_anchor_from_snap()` now stores mesh edge and face snaps as `OBJECT_POINT` anchors, so they follow object transforms. Detached vertex anchors render red and show a warning in the selected-dimension panel. Missing objects are reported in the panel even though their viewport geometry cannot be resolved. Vertex association still resolves by base-mesh index, so a topology edit can invalidate the index or, more dangerously, leave it valid while it names a different vertex.

Remaining recommendation:

- For surface points, store object-local position plus face/triangle identity and barycentric coordinates where possible.
- Introduce a persistent vertex identifier layer for geometry created or touched by the add-on, retaining index and local-coordinate fallbacks for migration.
- Track the mesh revision or binding confidence and show stale/detached/missing anchors in a warning color and management list.
- Provide Reconnect, Convert to World Point, and Locate Target actions.

### P1 baseline implemented: the four modal tools share numeric confirmation and target feedback

The operators now share numeric editing, axis parsing, confirmation detection, navigation pass-through, and distance constraints through `dimensions/interaction.py`:

- Dimension, Measure, Guide, and Pencil accept scene-unit values and `Enter` accepts the current stage.
- Pencil `Enter` commits the current segment and continues the chain; `Esc` clears typed input first, while `Esc`/right-click with no text ends the chain and keeps accepted geometry.
- Hovered targets are orange, locked targets are blue, and the cursor label shows snap type, axis, numeric text, and invalid input.
- `A/X/Y/Z` remain axis keys before or after numeric entry, matching Blender transform-style ordering; other letters remain available for unit suffixes.

Remaining recommendation:

Create reusable, testable components:

- `ToolPoint`: snap identity, world coordinate, durable binding, label, and confidence.
- `SnapCandidate` and `SnapQuery`: candidate class, priority, distance, visibility/depth, and filters.
- `ConstraintState`: free, global axis, local axis, inferred direction, parallel, perpendicular, plane, and typed distance.
- `NumericInput`: editing, parsing, units, validity, and a consistent Enter/Backspace/Escape contract.
- `ToolSession`: staged point picking, previous point, hover point, cancel/reset, commit, and status text.
- `GeometryTransaction`: validate, preview, commit, and rollback for destructive tools.

The baseline contract is documented and its shared helpers are covered by smoke tests. Point/session state and richer inference are still duplicated.

### P1: A complete Pencil chain is one undo transaction

The Pencil operator remains active while multiple edges are committed and returns `FINISHED` only when the session ends. With the normal Blender operator undo model, that makes the session one coarse undo step rather than one step per committed segment. Escape and right-click also finish rather than canceling only the active preview.

Recommendation:

- Keep uncommitted preview state non-destructive.
- Make each clicked/typed segment a discrete geometry transaction and undo boundary, or clearly document and expose a deliberate “finish chain as one action” mode.
- Use Escape first to cancel/reset the active segment or typed value, then a second Escape to leave the tool; right-click can finish the accepted chain if that is the chosen convention.
- Add an explicit close-loop action rather than relying only on positional tolerance.

### P2: Construction guides are useful, but their creation model is not yet SketchUp-like

The current guide is defined by two points, then made aligned or global-axis. The most common SketchUp construction workflow instead starts from an edge or guide and pulls out a parallel line at a typed perpendicular offset. SketchUp also distinguishes infinite guide lines from guide points and supports angular guides.

Additional current limitations:

- Guides render as solid world lines rather than dashed construction geometry.
- A fixed `10000.0` world-unit display extent is not scale independent.
- X/Y/Z guide resolution now depends only on its logical start anchor; the unused stored end no longer hides an axis guide.
- The Empty acts as a selection proxy; normal Blender transforms do not edit the stored anchors/direction in a user-facing way.
- There is no selective guide list, rename/edit-offset workflow, per-guide visibility control in the add-on UI, or Eraser-style deletion.

Recommendation:

- Add Offset Guide, Guide Point, and Angular Guide types.
- Store guide origin and direction/plane directly; store source geometry separately only when association is desired.
- Draw scale-independent dashed lines clipped to the viewport/frustum.
- Support click-drag repeat creation, typed offset, last-distance repeat, arrays/equal spacing, individual hide/delete, and a guide management list.

### P2: The Measure tool should be named and modeled deliberately

The current object is a persistent, fixed-world finite construction measurement. That is a useful feature, but it combines concepts that SketchUp keeps distinct: Tape Measure readout, non-geometric guides, and model rescaling.

Recommendation:

Turn the tool into a mode-driven Tape Measure while retaining “Saved Measure” as an explicit result type:

1. **Measure**: hover an edge for an immediate readout; click two points for a temporary result.
2. **Saved Measure**: pin the current result as the existing persistent finite segment.
3. **Offset Guide**: pull a parallel guide from an edge/guide and type the offset.
4. **Guide Point**: create a standalone inference point or endpoint offset.
5. **Resize to Measure**: opt-in, confirmation-gated scaling of the active object/selection; never infer permission to scale the whole scene.

Saved measures should offer Snapshot (fixed world) and Associative (linked endpoints) modes so users can choose whether a later geometry edit updates the result.

### P2: Native measurement snap proxies need lifecycle and compatibility coverage

The current work creates hidden child mesh proxies for measurement endpoints so Blender-native vertex snapping can see them, while the add-on's own snap layer also provides endpoints, midpoint, and segment snapping. The helper is wired into creation and synchronization, and orphan cleanup exists.

Recommendation:

- Verify native snapping behavior in foreground Blender rather than only checking proxy geometry in a background test.
- Confirm hidden/select-disabled proxy behavior across supported Blender versions, collection exclusion, duplication, scene linking, save/reload, undo/redo, direct Outliner deletion, add-on disable/re-enable, and file append/link.
- Keep proxies in an explicitly managed hidden collection or mark them clearly enough that cleanup is deterministic.
- Make native compatibility optional if proxy object count becomes expensive in large files.

## Per-tool product recommendations

### Construction lines

Keep the current two-point infinite line as **Guide Through Points**. Add **Offset Guide** as the default Tape Measure guide action, because it matches the fastest architectural workflow. Then add guide points, angular guides, local-axis/face-plane guides, editable offsets, and repeat spacing.

The UI should show the inferred source edge, perpendicular direction, numeric offset, and resulting guide before commit. A guide created from object geometry should optionally remain associative; a guide created in world space should remain stable regardless of object edits.

### Dimensions

The current aligned true-distance dimension is a solid core. Improve trust before breadth:

1. durable anchors and visible warning/reconnect behavior;
2. object-local face/edge anchors;
3. chain/baseline dimensions with equal-offset continuation;
4. horizontal/vertical/projected distance as distinct measurement modes;
5. angular, radial, diameter, and area dimensions;
6. extension-line gap/overshoot, arrow style, text alignment, and per-side controls;
7. export/render support, preferably through generated curves/text or a documented SVG/PDF/Grease Pencil path.

Do not overload “Extension Axis” to also mean measurement projection. Store measurement mode and presentation direction separately.

### Tape Measure

Make Tape Measure the front door to measuring and guides. The always-visible numeric readout should show:

- current length and delta X/Y/Z;
- active unit and typed text;
- snap/inference label;
- whether the result is temporary, saved, associative, or a guide;
- the active axis/plane lock.

Hover-only edge length and point coordinates are inexpensive, high-value additions once snap performance is fixed.

### Pencil / Line

After transaction safety and undo semantics, the next Pencil milestone should be inference quality, not more topology cases. Add axis/local-axis locks, parallel/perpendicular/extension inference, through-point inference, on-face plane locking, and explicit colored previews. Then address multi-face path routing and robust loop validation.

The tool should expose binding policy where it matters:

- vertex hit: weld to vertex;
- edge hit: split edge or create loose endpoint;
- face hit: on-face vertex/cut only when valid;
- other object hit: reference-only projection into the active edit mesh;
- free space: active construction plane, never an unexplained view-plane depth.

## Shared inference UX target

The viewport should explain every committed result before the click:

- distinct marker shapes for endpoint, midpoint, edge, face, guide, intersection, and world point;
- readable tooltips such as `Endpoint`, `Midpoint`, `On Face`, `Parallel`, or `From Point`;
- red/green/blue axis colors and a separate inferred-direction color;
- dashed inference lines from the start point and hovered reference;
- Shift to lock the current inference;
- arrow keys for axis/plane locks, while retaining X/Y/Z as an optional Blender-friendly mapping;
- a toggle for all linear inference, none, or parallel/perpendicular only;
- an on-screen Measurements field with consistent editing and invalid-input feedback.

This layer should be renderer-independent so inference and constraint tests can run without a live GPU context.

## Deferred modeling-tool ideas (not current scope)

The user explicitly chose not to add these items at this time and may never include them in this add-on. They remain here only as a record of the original evaluation, not as an implementation queue.

1. **Rectangle on Plane** — two corners, plane inference/lock, typed `width, depth`, automatic face creation, and predictable winding.
2. **Push/Pull** — face-normal extrusion with typed distance, inference to another face, copy/new-start modifier, and conservative manifold validation.
3. **Offset** — offset a selected face boundary or edge loop with typed distance and robust self-intersection handling.
4. **Move/Copy with Arrays** — inferred direction, typed displacement, copy modifier, and `xN`, `*N`, or `/N` distribution syntax.
5. **Protractor / Rotate** — angle measurement, angular guides, typed degrees/radians, plane locking, and copy arrays.
6. **Circle and Arc** — plane-aware creation, typed radius/segment count, center/quadrant/tangent inference.
7. **Eraser / Soften** — click or drag to delete guide/construction entities and optionally dissolve or soften mesh edges with explicit mode feedback.

No work on these ideas should begin without an explicit future scope decision.

## Test and release strategy

The current background Blender suite provides useful coverage of geometry helpers and happy paths. Add the following gates before calling the four priority workflows production ready.

Audit snapshot:

- Blender 5.1.2 manifest validation: passed.
- Blender 5.1.2 background smoke suite: 35 passed.
- Added regression coverage for a closed loop sharing an existing cut vertex, forced open-cut failure preservation, shared numeric input, target-highlight geometry, object-local anchors, and axis-guide anchor independence.
- The non-planar visible-face split regression briefly failed during the audit and passed after the current surface-tolerance update; retain both that test and the off-surface rejection test.

### Geometry safety

- Open/closed path failure leaves the complete input mesh unchanged.
- Self-intersecting, repeated-point, zero-area, non-coplanar, boundary-touching, and non-manifold cases fail predictably.
- Edge split and face cut preserve UVs, materials, normals, sharp/seam/crease attributes, and relevant custom data.
- Non-uniform object scale and very small/large coordinates do not break tolerance decisions.

### Modal behavior

- Event-sequence tests for click, move, typed input, Backspace, Enter, Escape, right-click, navigation pass-through, mode change, area closure, and add-on disable.
- One shared contract test applied to Dimension, Measure, Guide, and Pencil.
- Undo/redo assertions after every supported commit granularity.

### Persistence and references

- Save/reload dimensions, guides, measures, proxies, styles, and collection visibility.
- Object rename/delete, mesh edit/reorder, linked duplicates, modifiers, scene duplication, append/link, and library override behavior.
- Visible stale/broken status and successful reattachment.

### Snapping and performance

- Occluded versus visible candidates, behind-camera points, perspective edges, overlapping objects, collection exclusion, local view, clipping, and X-Ray.
- Candidate priority tests that include intersections and inference locks.
- Repeatable hover benchmarks at 10k, 100k, 250k, and one million visible vertices.

### Visual and compatibility QA

- Foreground scripted or manual viewport checks for marker, tooltip, line, label, selection, and native snap behavior.
- Registration/unregistration and tool availability in clean Blender 4.2 and the newest supported Blender version.
- Extension validate/build, clean-profile install, save/reopen, and packaged smoke test.

## Proposed milestones

### Milestone 1 — Trustworthy core (partly complete)

- Done for supported single-face operations: recoverable Pencil finalization and failure tests.
- Done as one documented chain transaction: segment confirmation and staged cancel behavior. Per-segment undo remains open.
- Depth-aware cached snapping with performance benchmarks.
- Partly done: broken-anchor visualization; management actions remain.

Exit criterion: invalid input cannot damage existing topology, large-scene hover remains interactive, and stale dimensions are never silently presented as trustworthy.

### Milestone 2 — One SketchUp-style interaction language (baseline in place)

- Shared ToolPoint, SnapCandidate, ConstraintState, NumericInput, ToolSession, and overlay feedback.
- Axis, local-axis, parallel, perpendicular, extension, through-point, intersection, and plane inference.
- Shift and arrow-key locking plus target filters.
- Done: typed values, `Enter` confirmation, staged cancel behavior, and hovered/locked target feedback in all four tools.

Exit criterion: a user who learns precision input and inference in one tool can predict all other tools.

### Milestone 3 — Tape and construction workflow

- Unified Tape Measure modes, hover readout, Saved Measure, Offset Guide, Guide Point, and Angular Guide.
- Associative/fixed result choice, guide editing/list, dashes, repeat spacing, and selective erasing.
- Optional confirmation-gated resize-to-measure for active selection/object.

Exit criterion: the common measure-and-lay-out-reference workflow requires no sidebar round trip.

### Milestone 4 — Documentation-grade dimensions

- Object-local/stable anchors, chain/baseline and projected dimensions.
- Angular/radial/diameter dimensions.
- Better extension/text styles and export/render path.

Exit criterion: dimension annotations remain trustworthy through normal modeling edits and can leave the viewport in a documented output workflow.

### Milestone 5 — SketchUp-style modeling expansion (parked)

- No planned implementation. Revisit only if the product scope changes after the four core workflows mature.

This milestone is not required for success of the current add-on.

## Definition of success for the original four needs

The original request is fully met when:

- **Construction lines** can be created through points or as typed offsets, include guide points/angular guides, are easy to hide/edit/delete, and participate in shared inference.
- **Dimensions** are associative or visibly stale, support the essential linear variants, remain editable, and have an output path beyond a transient viewport overlay.
- **Tape Measure** provides hover and two-point readout, temporary and saved results, guide modes, typed values, and safe optional rescaling.
- **Pencil** creates chained edges/faces with consistent inference and numeric input, has per-segment cancel/undo, and never damages existing topology when a requested cut is invalid.

The current add-on is meaningfully on the way to each of these. Work should remain centered on the four priority workflows; broader modeling tools are not presumed to belong in this add-on.
