# Interaction Toolkit Plan

This plan covers the shared, non-destructive interaction layer for dimensions, measurements, and construction guides.

## Scope

The toolkit acquires points and constraints for annotation workflows. It may inspect Object or Edit Mode geometry, but it never changes mesh topology. Geometry creation and cutting belong in a separate project.

## Shared point model

- `VERTEX`: object plus persistent `dimensions_anchor_id`, migration index, and fallback local coordinate.
- `OBJECT_POINT`: object plus local coordinate for edge and face snaps that follow object transforms.
- `WORLD_POINT`: a world coordinate for free-space or inferred points without a durable object binding.

## Interaction contract

- Hover supplies a continuously previewed target.
- Orange identifies the current target and blue identifies accepted points.
- `A` chooses aligned behavior; `X`, `Y`, and `Z` choose global axes.
- Middle-mouse drag chooses a projected global axis after the first point; otherwise it remains viewport navigation.
- Typed scene-unit distance may precede or follow the axis choice, and `Enter` confirms the current stage.
- `Backspace` edits numeric text. `Esc` clears numeric input before stepping back or exiting. Right-click cancels the active one-shot workflow.

## Current capabilities

- Vertex, edge, midpoint, face-center, face-point, guide, and measurement snapping.
- Perspective-correct edge projection and depth-aware projected-vertex filtering.
- Continuous free-space preview for Dimension, Measure, and Guide.
- Typed scene-unit input and global-axis constraints.
- Persistent measurement endpoints exposed to Blender's native snapping through internal proxy geometry.
- Object and Mesh Edit Mode acquisition for dimensions and measurements without mesh mutation.

## Next work

1. Add object-origin and explicit intersection targets.
2. Add local-axis, parallel, perpendicular, extension, and active-plane inference.
3. Add target filters and visible lock state.
4. Add guide offsets, guide points, guide planes, angular guides, and repeated spacing.
5. Add temporary hover measurements with delta X/Y/Z and a save action.
6. Measure dense-scene acquisition cost and establish repeatable performance budgets.

## Architecture direction

- `snapping.py`: collect and score candidates.
- `projected_snap.py`: maintain projected candidate caches and visibility checks.
- `interaction.py`: own numeric input, axes, and shared modal conventions.
- A future `inference.py`: derive local, parallel, perpendicular, extension, intersection, and plane constraints.
- Modal annotation operators: consume toolkit results and own only workflow-specific state.

This boundary keeps Dimensions focused: improving acquisition or inference benefits every annotation workflow without introducing destructive modeling behavior or topology-specific tests.
