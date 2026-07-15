# Measure and Construction Guides - Working Plan

This document tracks two persistent but deliberately distinct construction workflows:

- **Measure** creates a fixed, finite measured segment that is saved and can be snapped to.
- **Construction Guide** creates a reusable infinite reference line that is saved with the blend file.

## First-pass scope

### Persistent Measure

- [x] Object Mode toolbar tool.
- [x] Snap the start and end to visible mesh vertices, edge projections, edge midpoints, face centers, face points, construction guides, or free-space points.
- [x] Live line and formatted distance while choosing the end.
- [x] `A` for aligned distance and `X`, `Y`, or `Z` for a global-axis projection.
- [x] Point in a direction and type a scene-unit distance before committing.
- [x] Store the committed result as a lightweight Empty with fixed world-space endpoints.
- [x] Draw a finite line and formatted value after the tool exits and after save/reload.
- [x] Use the finite segment plus its exact start, midpoint, and end as logical snap targets.
- [x] Expose the exact start and end through an internal two-vertex mesh so Blender-native transform snapping (`G`, then `B`) can target measurements.
- [x] Keep creation undoable and provide a separate Clear Measurements action.

### Construction Guides

- [x] Object Mode toolbar tool.
- [x] Create a persistent guide from two point snaps.
- [x] `A` creates an aligned guide; `X`, `Y`, or `Z` creates a guide through the first point on that global axis.
- [x] Draw guides as effectively infinite world-space line geometry so they remain stable as the camera moves.
- [x] Store guides as lightweight Empty objects in a dedicated `Construction Guides` collection.
- [x] Follow linked vertices as source objects move or their vertex positions change.
- [x] Respect object, collection, and view-layer visibility.
- [x] Global guide visibility, color, line width, and a clear-all action in the sidebar.
- [x] Exclude hidden guides consistently from drawing, hit-testing, and snap candidate collection.
- [x] Project the mouse ray onto the mathematical infinite guide instead of interpolating a finite screen-space proxy.

## Interaction model

1. Select **Measure** or **Add Construction Guide** from the Object Mode toolbar.
2. Click a highlighted vertex for the start.
3. Move to a second vertex; press `A`, `X`, `Y`, or `Z` at any time to change the constraint.
4. Optionally type a distance such as `5"`, `125mm`, or `2ft`.
5. Click or press `Enter` to finish.

Both tools finish after committing one construction object. Run the tool again to create another.

## Deliberate first-pass limitations

- Snapping uses the add-on's current visible mesh hit, base-vertex picker, edge projection, midpoint, face center, face point, construction guide projection, and free-space point picker; intersection and richer inference locking are future work.
- Logical vertices and construction points use a configurable screen-space capture radius (28 pixels by default) and take precedence over a raw face hit while inside that radius.
- Axis constraints are global. Local object axes and arbitrary inferred directions are future work.
- Guides are infinite construction lines, not guide planes.
- Guides can be hidden or cleared as a group, selected directly in the viewport, and managed as scene objects in the Outliner. Per-guide styling is future work.
- Typed distances are implemented for Measure and Draw Mesh Line. Guide offsets, arrays, and typed guide length/origin offsets are future work.

## Next stages

1. Add SketchUp-like intersection inference, guide-plane inference, and richer axis color feedback.
2. Add a construction-object history/list with convert-to-dimension and finite/infinite conversion actions.
3. Add parallel/perpendicular guide constraints, guide planes, repeated spacing, and selective erase.
4. Add hover feedback and a dedicated guide management list.
5. Add automated Blender integration coverage for modal lifecycle, save/reload, collection visibility, and topology changes.

## Acceptance checks

- Measure creates one finite construction object with two fixed world anchors and survives save/reload.
- Measure value uses the scene-aware Dimensions unit and precision settings.
- Axis switching updates both preview geometry and value without restarting the operation.
- Guides survive save/reload and follow their linked anchor vertices.
- Hiding the guide object or `Construction Guides` collection hides its overlay.
- Guides remain visually attached to their infinite world-space line as the camera moves.
- Guides can be selected and used as snap/measurement references in the viewport.
- Hidden guides and guides disabled by the global Show Guides control cannot be selected or used as snap targets.
- Measurement starts and ends can be acquired by Blender's native Vertex transform snapper, including after loading measurements created by an earlier extension version.
- Clear Guides and Clear Measurements are separate undoable actions and affect no dimension or mesh objects.
