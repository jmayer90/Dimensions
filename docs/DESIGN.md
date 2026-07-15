# Design and Roadmap

## Product definition

Dimensions is a focused precision-modeling companion for Blender. Its core is one point-acquisition language shared by four workflows:

1. persistent dimensions;
2. saved measurements;
3. construction guides; and
4. explicit Edit Mode mesh-line creation.

The add-on should improve precision without quietly changing Blender-wide behavior. Annotation and construction tools are non-destructive. Mesh changes occur only inside the explicit Edit Mode line tool and must preserve accepted geometry when a requested topology finalization is unsupported.

## Design invariants

- **No global preference mutation.** Registration must not enable Auto Merge, alter snapping, install keymaps, or change other Blender tool settings without a separate user action.
- **One interaction contract.** Point, constrain, type, confirm, step back, and cancel should behave predictably across tools.
- **Preview before commit.** The active target, constraint, value, and invalid state must be visible before data changes.
- **Trust is explicit.** Valid references render normally; detached references warn visibly; missing references never produce a plausible but invented value.
- **Scene ownership.** Dimensions and construction objects belong to scene-owned collections and must not leak into another scene merely because a collection has a familiar name.
- **Failure preserves work.** Unsupported mesh cuts remain as the accepted edge path instead of partially replacing or deleting topology.
- **Blender-native data first.** Persistent objects remain inspectable, selectable, undoable, and saveable through normal Blender data.

## Current architecture

| Area | Responsibility |
| --- | --- |
| `anchors.py` | Serialize and resolve vertex, object-local, and world anchors. |
| `snapping.py` | Acquire and score mesh, guide, measurement, and free-space targets. |
| `interaction.py` | Shared modal keys, numeric editing, and axis helpers. |
| `operators/` | Own workflow stages and commit annotations or mesh topology. |
| `drawing.py` | Build dimension geometry, draw overlays, hit-test annotations, and synchronize proxy object locations. |
| `collections.py` | Enforce scene-owned collections and manage native measurement snap proxies. |
| `properties.py`, `ui.py` | Persist settings and expose scene/local editing. |
| `units.py`, `volume.py` | Parse and format units and calculate evaluated closed-mesh volume. |

Dimensions are Empty objects with two anchors and presentation properties. Guides and measurements are Empty objects in a separate collection. Measurements also own an internal two-vertex child mesh so Blender's native vertex snapper can acquire their endpoints.

## Interaction contract

- Hover supplies a target and direction; orange is active and blue is accepted.
- `A` selects aligned behavior; `X`, `Y`, and `Z` select global axes.
- Middle-mouse drag chooses a projected global axis after a start point exists; before that, middle mouse remains viewport navigation.
- Typed scene-unit distance can precede or follow an axis choice. `Enter` confirms the current valid stage.
- `Esc` clears numeric input first, then steps back or exits. Right-click cancels one-shot tools; it finishes an accepted mesh-line chain.
- Draw Mesh Line operates only on the active Edit Mode mesh. Vertex hits bind, edge hits split, supported face paths finalize as topology, and unsupported finalization leaves path edges intact.

## Known risks

1. **Snap correctness and performance.** Object Mode fallback projects every visible base vertex on each mouse move and is not depth-filtered. This is both the largest scaling cost and the main source of plausible occluded snaps.
2. **Anchor identity.** A base vertex index is not a persistent identity. Topology edits can detach an anchor or make the same index refer to different geometry without a warning.
3. **Mesh transaction scope.** A complete Draw Mesh Line session is one Blender undo transaction. Geometry validation is strong for covered cases but is not yet a general multi-face transaction planner.
4. **Viewport-only output.** Dimensions are useful while modeling but cannot yet participate in render, drawing, or export workflows.
5. **Proxy lifecycle.** Native measurement snap proxies need foreground, save/reload, append/link, undo/redo, and multi-version compatibility QA.

## Prioritized roadmap

### P0 — Trustworthy acquisition

- Build a per-viewport, depth-aware projected snap cache with 2D spatial queries and target filters.
- Add persistent anchor identity and binding confidence, plus locate, reconnect, and convert-to-world actions.
- Separate destructive mesh validation from commit and add rollback/custom-data tests for unsupported paths.
- Add repeatable performance budgets and foreground modal-event tests.

### P1 — Precision inference and management

- Add local-axis, parallel, perpendicular, extension, intersection, and active-plane inference with an explicit lock.
- Add a scene annotation manager for search, rename, select, hide, isolate, repair, and bulk style operations.
- Add temporary hover measurement with delta X/Y/Z and an explicit action to save it.
- Add offset guides, guide points, guide planes, angular guides, and repeated spacing.
- Make mesh-line undo granularity deliberate and user-visible, ideally one transaction per committed segment.

### P2 — Documentation-grade dimensions

- Separate true/aligned length from projected horizontal, vertical, and axis-distance modes.
- Add chain/baseline, angular, radial, diameter, and area dimensions.
- Add extension gaps/overshoot, arrow variants, label alignment, tolerance, prefix/suffix, and dual-unit display.
- Provide a render/export path through generated curves/text, Grease Pencil, SVG, or PDF.

### Deferred scope

Rectangle, Push/Pull, general Offset, Move/Copy arrays, Protractor/Rotate, Circle/Arc, and Eraser-style mesh editing are broader modeling tools. They should be considered only after the four current workflows meet the P0 trust and performance bar. Of those, Rectangle on Plane is the best fit because it can reuse the same snapping, plane, constraint, and typed-input infrastructure without requiring a large new selection or topology system.

## Release gate

A release candidate should pass:

- Python compilation and the Blender background smoke suite;
- Blender extension manifest validation and build;
- clean-profile register/unregister and install/disable/re-enable;
- save/reload and undo/redo for every persistent object type;
- foreground viewport checks for selection, visibility, native measurement snapping, unit display, and broken anchors;
- tests on Blender 4.2 and the newest supported Blender version; and
- snap performance checks on representative dense scenes.
