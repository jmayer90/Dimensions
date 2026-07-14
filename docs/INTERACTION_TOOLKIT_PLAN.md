# Interaction Toolkit Plan

This plan captures the next design direction for Dimensions tools: measurement, dimensions, construction guides, snapping, and future geometry drawing should share one interaction toolkit instead of each modal operator inventing its own behavior.

## Current problems

- After picking the first point, the active tool only updates cleanly when the cursor hovers another valid vertex. The preview feels disconnected because it disappears or stalls over empty space.
- Persistent dimensions can only store object/vertex anchors. That is useful for linked CAD-style annotations, but too narrow for sketching, measuring, and guide workflows.
- Snap behavior is currently vertex-centered. It needs a broader inference model without copying every behavior from a general-purpose snap add-on.
- Typed direction-and-distance workflows are missing, which blocks SketchUp-like deliberate construction.

## Target interaction model

Every point-picking tool should work with a common `ToolPoint` concept:

- `VERTEX`: object plus base vertex index, with fallback local coordinate.
- `OBJECT_POINT`: object plus local coordinate, used for face centers, edge midpoints, curve points, and arbitrary object-surface hits.
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

1. Endpoint and vertex snaps.
2. Edge midpoint snaps.
3. Face center and object-origin snaps.
4. Axis and parallel inference from the active start point.
5. Typed distance along the active inferred direction.
6. Intersection and guide-plane inference.

## Snap Line-style workflows

These workflows should be added only after the shared point acquisition layer exists.

### Measure, Dimension, and Guide preview

This is the first user-visible improvement. After the first point, the tool should always draw to a candidate end point:

- A snap target when the cursor is near a vertex, edge midpoint, face center, origin, intersection, or guide.
- A projected point on the active construction plane when no snap target is nearby.
- A projected point along the locked axis, parallel direction, perpendicular direction, or typed-distance vector when inference is active.

The result is a smooth preview that never disappears just because the cursor leaves a valid vertex.

### Guide line tool

The guide tool should become the non-destructive version of Snap Line:

1. Pick or infer a start point.
2. Move the mouse to preview an infinite guide, finite guide, or construction segment.
3. Press axis/inference keys to lock global, local, parallel, or perpendicular directions.
4. Type a distance to place the endpoint precisely.
5. Click to commit the guide without creating mesh geometry.

This gives the precision workflow before adding mesh-edit side effects.

### Geometry line tool

Geometry creation should be a separate explicit tool, not hidden inside Measure or Dimension.

1. User selects a target mesh or enters edit mode.
2. User picks a start `ToolPoint`.
3. User previews a segment using the same snap, inference, and typed-distance system.
4. User commits a new edge/vertex segment.
5. If the endpoint lands on existing geometry, the tool can auto-merge to a vertex or split/bind to an edge based on a clear option.
6. The committed endpoint becomes the next start point for chained lines and closed shapes.

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

The next implementation slice should not create new mesh geometry yet. It should first make existing Dimension, Measure, and Guide tools preview smoothly over empty space and persist either snapped vertex anchors or world-coordinate anchors.

## Rollout plan

1. Extract `ToolPoint` and snap-candidate scoring without changing visible behavior.
2. Add free-space construction-plane projection and continuous previews to Measure, Dimension, and Guide.
3. Add midpoint, face-center, origin, and edge/guide inference targets.
4. Add axis, parallel, perpendicular, and typed-distance locks for non-destructive tools.
5. Upgrade construction guides to support finite segments, offsets, and chained guide creation.
6. Add a separate Geometry Line tool with explicit target mesh selection and undo-safe mesh edits.
7. Add auto-merge/split options after the Geometry Line tool is reliable.
