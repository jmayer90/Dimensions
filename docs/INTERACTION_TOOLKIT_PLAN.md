# Interaction Toolkit Plan

This plan captures the next design direction for Dimensions tools: measurement, dimensions, construction guides, snapping, and future geometry drawing should share one interaction toolkit instead of each modal operator inventing its own behavior.

## Current problems

- The first implementation now keeps Measure, Dimension, and Guide previews alive over free space and adds visible-face vertex, edge, midpoint, face-center, face-point, and guide snapping. The inference model still needs intersections, parallel/perpendicular locks, and guide planes.
- Persistent dimensions and guides can store vertex anchors, object-local edge/face points, or world-coordinate anchors. Stable vertex identity and deformation-following barycentric surface anchors are still future work.
- Snap behavior now covers the basic point classes, but it still needs a broader inference model without copying every behavior from a general-purpose snap add-on.
- Typed scene-unit distance and staged `Enter`/`Backspace`/`Esc` handling now exist across Dimension, Measure, Guide, and Mesh Line. The shared layer is intentionally small; the four operators still duplicate parts of their session state machines.

## QuickSnap-inspired target model

[QuickSnap](https://github.com/JulienHeijmans/quicksnap) provides a useful reference for typed snap targets, pixel-radius lookup, nearby-object processing, depth-aware candidate scoring, target highlighting, and explicit target-mode switching. Dimensions should adopt those interaction principles without coupling snapping to object translation.

Dimensions extends that model in several ways:

- Construction guides are first-class snap targets rather than mesh-like display geometry.
- Every candidate carries target identity and durable binding metadata separately from its world and screen coordinates.
- Hidden objects, collections, guides, and disabled guide overlays are excluded consistently from drawing, selection, and snapping.
- Edge projection uses perspective-correct interpolation so the committed world point matches the screen marker.
- Edit Mode candidates come from the live BMesh, allowing a committed segment to become the next segment's valid snap topology immediately.
- Edit Mode fallback candidates stay on the active mesh and include projected boundary edges, preventing silhouette ray misses from binding a mesh path to geometry behind the edited object.
- Vertices, corners, and measurement start/mid/end points own the full configurable capture radius instead of losing to a raw face or line projection that happens to be closer to the pointer.
- Hovered mesh targets expose all visible base edges and vertices as a lightweight, depth-tested black edit-like overlay, while the exact target keeps a restrained colored emphasis and a hovered vertex emphasizes every incident edge. This supplies object and neighborhood context without overwhelming the model.
- Persistent measurement endpoints also have a non-selectable two-vertex proxy for Blender-native transform snapping; the midpoint and finite segment remain Dimensions-level targets.
- Candidate scoring should remain extensible to intersections, inferred axes, guide planes, and user-selectable target filters.

The current implementation still collects only the visible ray-hit face plus visible guides instead of maintaining a scene-wide screen-space cache. A future performance pass should add an incrementally refreshed spatial index, borrowing QuickSnap's nearby-object/batched-processing idea while retaining Dimensions-specific guide and inference targets.

## Target interaction model

Every point-picking tool should work with a common `ToolPoint` concept:

- `VERTEX`: object plus base vertex index, with fallback local coordinate.
- `OBJECT_POINT`: object plus local coordinate, used for edge and face snaps so an anchor follows object transforms. It does not yet follow later surface deformation.
- `WORLD_POINT`: world coordinate only, used when the cursor is over empty space or when a typed/inferred point has no durable object link.

During modal creation, tools should always have a preview end point. If no snap target is under the mouse, the end point should come from a stable construction plane, view plane, selected axis, guide plane, or inferred direction. Snapped points should override the free-space point when the cursor is close enough.

## Snapping and inference

Useful ideas from QuickSnap include snap target modes for vertices/curve points, edge midpoints, face centers, origins, target-type hotkeys, two-click workflows, target highlighting, and prioritizing closer candidates. Dimensions should adopt the concepts that serve measuring and construction, but keep the implementation focused on point acquisition rather than object translation.

Useful ideas from Snap Utilities Line include direction locking, typed distance entry, and creating geometry from a start point plus a deliberate direction and length. Dimensions should use that interaction style for guides, dimensions, and eventual geometry creation.

Additional Snap Line-style concepts to adapt:

- Interactive line drawing: click or drag from a start point, preview the active segment continuously, and commit a segment on click.
- Closed and irregular shapes: after one segment is committed, the end point becomes the next start point until the user exits or closes the loop.
- Parallel and perpendicular constraints: infer directions from hovered or selected edges, then allow explicit lock-in for parallel/perpendicular drawing.
- Intelligent binding: when a committed line terminates on an existing vertex or edge, optionally weld or split geometry cleanly instead of leaving near-duplicate points.
- Mesh edit awareness: geometry creation should run only when the target mesh/edit context is explicit; measurement and guide tools should remain non-destructive by default.

The practical first target is:

1. Done: endpoint and vertex snaps.
2. Done: edge projection and edge midpoint snaps.
3. Done: face point and face center snaps.
4. Next: object-origin snaps.
5. Next: axis and parallel inference from the active start point.
6. Done: typed distance and `Enter` confirmation are implemented for Measure, Draw Mesh Line, Dimension, and Guide.
7. Next: intersection and guide-plane inference.

## Snap Line-style workflows

These workflows build on the shared point acquisition layer.

### Measure, Dimension, and Guide preview

This is the first user-visible improvement. After the first point, the tool should always draw to a candidate end point:

- A snap target when the cursor is near a vertex, edge midpoint, face center, origin, intersection, or guide.
- A projected point on the active construction plane when no snap target is nearby.
- A projected point along the locked axis, parallel direction, perpendicular direction, or typed-distance vector when inference is active.

The result is a smooth preview that never disappears just because the cursor leaves a valid vertex.

### Guide line tool

The guide tool should become the non-destructive version of Snap Line:

1. Pick or infer a start point.
2. Move the mouse to preview an infinite guide or construction line.
3. Press axis/inference keys to lock global, local, parallel, or perpendicular directions.
4. Type a distance to place the endpoint precisely.
5. Click to commit the guide without creating mesh geometry.

This gives the precision workflow before adding mesh-edit side effects.

### Geometry line tool

Geometry creation remains a separate explicit tool, not hidden inside Measure or Dimension.

1. User selects a target mesh or enters edit mode.
2. User picks a start `ToolPoint`.
3. User previews a segment using the same snap, inference, and typed-distance system.
4. User commits a new edge/vertex segment; an unfinished path with an interior endpoint remains clean loose geometry instead of forcing a face-poke fan.
5. When both path ends reach one face boundary, the deferred path is replaced with a knife-like face split that preserves all intermediate turns. Edge endpoints split their target edges first.
6. The committed endpoint becomes the next start point for chained lines. Closing a simple coplanar surface loop rebuilds the surrounding ring with two required bridge edges and an independent inner face; closing away from a surface creates a standalone face.

This keeps CAD-like creation available without making annotation tools unexpectedly destructive.

## Constraint model

Constraints should be explicit state in the shared toolkit:

- `FREE`: use snap target or construction-plane projection.
- `GLOBAL_AXIS`: X, Y, or Z.
- `LOCAL_AXIS`: selected object or active element local axis.
- `PARALLEL`: direction copied from a hovered, selected, or recent edge.
- `PERPENDICULAR`: perpendicular to a hovered, selected, or recent edge on the active plane.
- `TYPED_DISTANCE`: distance applied along the current inferred or locked direction.

The UI should show the active constraint through color and a small viewport label, but the internal state should be independent of drawing so tests can exercise it.

## Auto-merge and binding policy

Auto-merge needs conservative defaults:

- Measurement, dimensions, and construction guides never modify mesh geometry.
- Geometry Line can auto-merge only when its option is enabled and a target mesh/edit context is explicit.
- Vertex hits merge directly to that vertex.
- Edge hits either split the edge and bind to the inserted vertex, or create a loose endpoint, depending on the selected mode.
- Face hits create a point projected onto the face only when the tool is in geometry mode and the mesh operation is valid.
- Every merge/split operation must be a normal Blender undo step.

## Data model impact

Dimensions should support mixed anchors. A dimension can connect any two `ToolPoint` values. Vertex-linked dimensions keep their current durable behavior. World-coordinate dimensions remain valid even when no object was chosen, but they will not follow mesh edits. Object-local points can follow object transforms without depending on a vertex index.

Construction guides should use the same point model, with guide direction stored separately as aligned, global axis, inferred axis, or explicit vector.

## Implementation notes

Keep this as a toolkit layer, probably separate from the drawing code:

- `snapping.py`: collect candidates and score them.
- `inference.py`: derive free-space points, axes, planes, projected points, and typed distances.
- `tool_points.py`: serialize and resolve durable point references.
- `constraints.py`: own active locks for global axes, local axes, parallel, perpendicular, and typed distance.
- `geometry_ops.py`: create vertices/edges and perform explicit merge/split operations for the future Geometry Line tool.
- Modal operators: consume toolkit results and focus on workflow state.

The current implementation makes Dimension, Measure, and Guide tools preview over empty space; supports typed distances in all four priority tools; highlights hovered targets in orange and accepted targets in blue; snaps to vertices, edges, midpoints, faces, infinite guides, and finite measurements; exposes measurement endpoints to Blender-native transform snapping; keeps Edit Mode fallback snaps on the active mesh; and selects construction objects in the viewport. Invalid numeric input is shown in red near the cursor.

## Rollout plan

1. Done: add vertex/world point anchors, guide snap projections, and free-space construction-plane projection.
2. Done: add continuous previews to Measure, Dimension, and Guide.
3. Done: add a separate Edit Mode Geometry Line tool with explicit active mesh editing, connected chains, vertex/edge binding, common-face splitting, and undo-safe mesh edits.
4. Done: add midpoint, face-center, and richer edge/guide inference targets.
5. Partly done: typed distance and consistent confirmation/cancel staging are shared across all four priority tools. Parallel, perpendicular, and local-axis locks remain.
6. Next: upgrade construction guides to support offsets, chained guide creation, and guide planes.
7. Done for the single-face path: deferred boundary-to-boundary strokes cut without radial support fans, including on caps created by extrusion, and simple closed coplanar paths create independent faces. A loop may share one existing vertex or reuse one contiguous chain of existing face/cut edges; an existing edge no longer prematurely resets the active path. Global-axis constraints on an angled edit face are projected into the face plane and revalidated so they cannot masquerade as surface points while actually sitting off the mesh. Finalization keeps the loose path intact when validation or face creation fails. Next: genuine multi-face path routing, configurable edge split/bind behavior, and robust handling for multiple boundary chains, self-intersecting, or non-manifold loops.

## Current shared input contract

- Hover establishes direction and snap identity; orange marks the current target and blue marks accepted targets.
- `A`, `X`, `Y`, or `Z` chooses aligned/global-axis behavior before or after numeric entry, matching Blender transform ordering.
- During an active directional stage, middle-mouse press/drag displays all three global axes and release locks the axis closest to the mouse direction. Before a start point is accepted, middle mouse passes through for viewport orbit.
- Typing a scene-unit value changes the current distance; `Enter` accepts the current stage. Mesh Line commits that segment and continues the chain.
- `Backspace` edits numeric text and steps back only after the text is empty.
- `Esc` clears numeric text first, then steps back or exits. Right-click cancels one-shot tools; for Mesh Line it finishes the session and keeps accepted segments.
- Wheel navigation always passes through to Blender; middle mouse passes through before an active directional stage and becomes the axis gesture during that stage.

This is the baseline Blender-friendly contract. Future Shift/arrow-key inference locks should extend it without changing these meanings.
