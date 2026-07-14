# Measure and Construction Guides — Working Plan

This document tracks the implementation of two deliberately separate workflows:

- **Measure** answers a quick question and does not alter the scene.
- **Construction Guide** creates reusable reference geometry that is saved with the blend file.

## First-pass scope

### Transient Measure

- [x] Object Mode toolbar tool.
- [x] Snap the start and end to visible mesh vertices.
- [x] Live line and formatted distance while choosing the end.
- [x] `A` for aligned distance and `X`, `Y`, or `Z` for a global-axis projection.
- [x] Keep the last result visible while the tool is active.
- [x] Click again to begin a replacement measurement.
- [x] `Backspace` or `Delete` clears; `Esc` clears, then exits.
- [x] Store no object, undo step, or saved scene data.

### Construction Guides

- [x] Object Mode toolbar tool.
- [x] Create a persistent guide from two vertex snaps.
- [x] `A` creates an aligned guide; `X`, `Y`, or `Z` creates a guide through the first point on that global axis.
- [x] Draw guides across the viewport as infinite screen-space lines.
- [x] Store guides as lightweight Empty objects in a dedicated `Construction Guides` collection.
- [x] Follow linked vertices as source objects move or their vertex positions change.
- [x] Respect object, collection, and view-layer visibility.
- [x] Global guide visibility, color, line width, and a clear-all action in the sidebar.

## Interaction model

1. Select **Measure** or **Add Construction Guide** from the Object Mode toolbar.
2. Click a highlighted vertex for the start.
3. Move to a second vertex; press `A`, `X`, `Y`, or `Z` at any time to change the constraint.
4. Click the second vertex to finish.

Measure remains active for repeated questions. A completed construction guide ends its placement operation; another click with the guide tool starts another guide.

## Deliberate first-pass limitations

- Snapping uses the add-on's current visible-face vertex picker; edge, midpoint, face, intersection, and inference locking are future work.
- Axis constraints are global. Local object axes and arbitrary inferred directions are future work.
- Guides are infinite lines, not guide planes or finite segments.
- Guides can be hidden or cleared as a group, and can be managed as scene objects in the Outliner. Direct line click-selection and per-guide styling are future work.
- Numeric distance entry, guide offsets, arrays, and copy-to-guide conversion are future work.

## Next stages

1. Add SketchUp-like inference targets: endpoints, midpoints, edges, faces, intersections, and axis color feedback.
2. Add typed distances and a measurement history/list with explicit pin-to-dimension and convert-to-guide actions.
3. Add parallel offset guides, guide planes, repeated spacing, and selective erase.
4. Add viewport guide hit-testing, hover feedback, and a dedicated guide management list.
5. Add automated Blender integration coverage for modal lifecycle, save/reload, collection visibility, and topology changes.

## Acceptance checks

- Measure creates no Blender object and nothing remains after leaving/reloading the file.
- Measure value uses the scene-aware Dimensions unit and precision settings.
- Axis switching updates both preview geometry and value without restarting the operation.
- Guides survive save/reload and follow their linked anchor vertices.
- Hiding the guide object or `Construction Guides` collection hides its overlay.
- Clear All Construction Guides is undoable and affects no dimension or mesh objects.
