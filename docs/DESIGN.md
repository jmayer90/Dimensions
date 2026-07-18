# Design and Roadmap

## Product definition

Dimensions is a focused, non-destructive precision-annotation companion for Blender. Its shared point-acquisition language supports three workflows:

1. persistent linear, angular, and area annotations;
2. saved finite measurements; and
3. construction guides.

The extension may inspect Edit Mode topology to acquire anchors or calculate values, but it does not create, cut, merge, or otherwise modify mesh geometry. Geometry-authoring tools belong in a separate project with their own interaction model, test budget, release cadence, and topology guarantees.

## Design invariants

- **Non-destructive annotation.** Dimension, measurement, and guide workflows never modify mesh topology.
- **No global preference mutation.** Registration does not alter Auto Merge, snapping, keymaps, or unrelated Blender settings.
- **One interaction contract.** Point, constrain, type, confirm, step back, and cancel behave predictably across tools.
- **Preview before commit.** The active target, constraint, value, and invalid state are visible before an annotation is saved.
- **Stable presentation.** Annotations remain readable during unrelated mode or topology changes. Missing vertex identity uses the stored fallback position.
- **Truthful state.** Live, captured, and invalid measurements are visibly distinct; a stale cached value is never presented as a current live result.
- **Source/presentation separation.** Measurement bindings determine values while label, leader, arc, and extension properties determine placement.
- **Editable placement objects.** An annotation Empty's transform is a user-facing placement offset from source-derived canonical geometry; synchronization preserves that offset when sources move.
- **Scene ownership.** Dimensions and construction objects belong to scene-owned collections and do not leak across scenes.
- **Blender-native data first.** Persistent objects remain inspectable, selectable, undoable, and saveable through normal Blender data.

## Current architecture

| Area | Responsibility |
| --- | --- |
| `anchors.py` | Assign persistent mesh point IDs and resolve vertex, object-local, and world anchors. |
| `area_binding.py` | Assign persistent face IDs, bind Area source sets, and calculate live world-space area. |
| `snapping.py`, `projected_snap.py` | Acquire and score targets; cache and depth-filter projected vertices. |
| `interaction.py` | Shared modal keys, numeric editing, and axis helpers. |
| `operators/` | Own annotation, measurement, guide, selection, and styling workflows. |
| `dimension_geometry.py` | Calculate world-space dimension geometry without viewport or operator state. |
| `drawing.py`, `viewport_state.py` | Draw overlays, hit-test annotations, and isolate transient state per viewport. |
| `scene_sync.py` | Synchronize annotation locations, repair proxies, migrate anchors, and invalidate caches. |
| `collections.py` | Enforce scene-owned collections and manage native measurement snap proxies. |
| `properties.py`, `ui.py` | Persist settings and expose scene and local editing. |
| `units.py`, `volume.py` | Parse and format units and calculate evaluated closed-mesh volume. |

Annotations are Empty objects with presentation properties and an annotation kind. Linear annotations use two measurement anchors. Live Areas store persistent face IDs in `dimensions_area_face_id`, source metadata, a cached value, and explicit Live/Captured/Needs Repair state. Two-edge Angles store four persistent endpoint anchors and derive a shared or virtual center. Vertex anchors store integer IDs in the mesh's `dimensions_anchor_id` point attribute. Angle arcs are generated in world space before viewport projection. A canonical source frame plus user presentation offset keeps annotation transforms editable. Guides and measurements are Empty objects in a separate collection.

## Interaction contract

- Hover supplies a target and direction; orange is active and blue is accepted.
- `A` selects aligned behavior; `X`, `Y`, and `Z` select global axes.
- Middle-mouse drag chooses a projected global axis after a start point exists; before that, middle mouse remains viewport navigation.
- Typed scene-unit distance can precede or follow an axis choice. `Enter` confirms the current valid stage.
- `Esc` clears numeric input first, then steps back or exits. Right-click cancels a one-shot tool.
- Dimension and measurement point acquisition works in Object and Mesh Edit Mode without modifying the mesh.
- The main Dimension command is selection-first in Edit Mode: exactly one selected edge commits a length immediately; other selections enter interactive point acquisition.
- Edit selection can create a length from one edge, an angle from any two non-parallel edges, or an area leader from one or more faces.
- Area creation has its own source and placement stages: Edit Mode consumes selected faces, while Object Mode acquires base-mesh faces before the user places the leader label.
- Angle and Area use dedicated Remake actions; linear anchor eyedroppers are not reused for their multi-source workflows.
- Angle binds two edges directly. Connected edges use their shared vertex; disconnected edges derive a virtual placement point from their supporting lines and expose smaller, supplementary, and reflex solutions explicitly.

## Known risks

1. **Snap cache rebuild cost.** Geometry, transform, and view changes rebuild the projected snap cache. Dense-scene budgets still need foreground measurement.
2. **Duplicated anchor IDs.** Blender topology duplication may copy a point ID. Resolution chooses the candidate closest to the stored fallback coordinate.
3. **Face identity after topology duplication.** Live Areas use persistent face IDs. Missing, structurally changed, or duplicated identities intentionally enter Needs Repair instead of guessing; modifier-evaluated face correspondence is not yet defined.
4. **Viewport-only output.** Dimensions do not yet participate in render, drawing, or export workflows.
5. **Proxy lifecycle.** Native measurement snap proxies pass background save/reload repair checks; foreground, append/link, and undo/redo behavior still need release QA.

## Prioritized roadmap

### P0 — Trustworthy acquisition

- Add an optional explicit rebind or convert-to-world action for users who need to override fallback anchor resolution.
- Extend the implemented Live/Captured/Needs Repair model with a guided repair picker and source highlighting.
- Add direct viewport handles for the implemented world-space Angle radius and Area label placement.
- Define evaluated-modifier semantics for the implemented base-mesh live Area bindings.
- Extend the implemented canonical-frame and placement-offset model with deliberate rotation and scale semantics.
- Add foreground modal coverage for the implemented constrained Area and two-edge Angle workflows.
- Add repeatable dense-scene performance budgets and foreground modal-event tests.
- Complete foreground lifecycle QA for measurement proxies and annotations.

### P1 — Precision inference and management

- Add local-axis, parallel, perpendicular, extension, intersection, and active-plane inference with an explicit lock.
- Add a scene annotation manager for search, rename, select, hide, isolate, repair, and bulk style operations.
- Add temporary hover measurement with delta X/Y/Z and an explicit action to save it.
- Add offset guides, guide points, guide planes, angular guides, and repeated spacing.

### P2 — Documentation-grade dimensions

- Extend implemented true/global-axis projected length with local-axis and view-plane modes.
- Add chain, baseline, radial, diameter, arc-length, coordinate, and elevation dimensions.
- Add extension gaps and overshoot, arrow variants, label alignment, tolerance, prefix or suffix, and dual-unit display.
- Provide a render or export path through generated curves and text, Grease Pencil, SVG, or PDF.

## Explicitly excluded scope

Mesh-line drawing, face cutting, rectangles, Push/Pull, general Offset, Move/Copy arrays, Circle/Arc, and eraser-style mesh editing are geometry-authoring tools. They are not part of Dimensions. Any future implementation should start in a separate project rather than re-enter this extension incrementally.

The detailed design sequence and acceptance criteria for the annotation overhaul are maintained in [Dimension and Measurement Tools Improvement Plan](DIMENSION_TOOLS_PLAN.md).

## Release gate

### Version policy

The manifest remains on the `0.2.x` release line until the project owner expressly approves a change to the minor component (the `2`). The patch component is the routine adjustment counter and may be incremented for each adjustment.

A release candidate should pass:

- Python compilation and the focused Blender background smoke suite;
- Blender extension manifest validation and build;
- clean-profile register, unregister, install, disable, and re-enable;
- save/reload and undo/redo for every persistent object type;
- foreground viewport checks for selection, visibility, native measurement snapping, unit display, and broken anchors;
- tests on the declared Blender 5.1 target; and
- snap performance checks on representative dense scenes.
