# Dimensions

Dimensions is an experimental Blender 4.2+ extension for persistent, CAD-style measurements linked to base-mesh vertices. A dimension is stored as an Empty, can span two mesh objects, and follows its referenced geometry as objects or vertices move.

Version `0.1.1` contains a usable, Blender-tested core prototype. It remains experimental and should be validated on production models before broad deployment.

## Features

- Create dimensions by picking visible mesh vertices, construction guides, or free-space points in Object Mode and placing an offset.
- Measure true point-to-point distance and extend the annotation along an automatically chosen or explicit global X, Y, or Z direction.
- Draw extension lines, arrowheads, and formatted values in the 3D Viewport.
- Link anchors across one or two mesh objects and reattach either endpoint later.
- Rename, hide, recolor, delete, and adjust dimensions with Blender controls and the Dimensions sidebar.
- Select a drawn dimension by clicking its lines or label; Shift-click toggles selection.
- Format values with Blender units; automatic or explicit millimeters, centimeters, and meters; decimal inches; fractional inches; or feet and inches.
- Place labels inline in a line break, above the line, or outside the end arrow.
- Add optional per-dimension text above or below the measured value.
- Optionally show Length / Width / Thickness and evaluated volume for selected mesh objects in a viewport HUD.
- Create persistent finite construction measurements against mesh vertices, guides, other measurements, or free-space points.
- Create persistent construction guides in their own hideable collection and snap/select against them in the viewport.
- Draw chained mesh line segments in Edit Mode with the same point snapping workflow.

## Install

The extension payload is the contents of [`dimensions`](dimensions/). Its manifest must be at the root of the ZIP, not inside an additional directory.

From PowerShell at the repository root:

```powershell
Compress-Archive -Path dimensions\* -DestinationPath dimensions-0.1.1.zip -Force
```

In Blender 4.2 or later, open **Edit > Preferences > Add-ons**, choose **Install from Disk**, select the ZIP, and enable **Dimensions**. Open the 3D Viewport sidebar with `N` and select the **Dimensions** tab.

For distribution, build and validate the archive with Blender's extension commands instead of relying only on `Compress-Archive`.

## Use

1. Enter Object Mode and choose **Create Dimension** from the Dimensions sidebar.
2. Hover a target and click the orange-highlighted start point. Accepted targets remain blue while the next stage is active.
3. Point toward the end, optionally type a scene-unit length, and click or press `Enter`.
4. Move the pointer to set the offset, or type its distance. Press `X`, `Y`, or `Z` to constrain the extension direction to that global axis, or `A` to return to automatic axis selection.
5. Click or press `Enter` to finish. Right-click cancels the whole uncommitted dimension; `Esc` clears typed input first and then steps back through the picks.
6. Select the dimension Empty, or click the drawn annotation, to edit it in the sidebar.

Alternatively, select **Add Dimension**, **Measure**, or **Add Construction Guide** from the left 3D Viewport toolbar, then click in the viewport to begin the same workflow. **Draw Mesh Line** appears in the left toolbar while editing a mesh.

### Quick measure and construction guides

Use **Measure** to create a finite construction segment. Click a start point, point in the desired direction, and click again to commit. Press `A` for the direct aligned direction or `X`, `Y`, or `Z` for a global-axis direction. While choosing the endpoint, type a scene-unit distance such as `5"`, `125mm`, or `2ft`, then press `Enter` or click to commit. Measurements are fixed world-space construction objects, are saved in the blend file, display their value, and expose their start, midpoint, end, and finite line to Dimensions tools. Their exact start and end also participate in Blender's native **Vertex** transform snapping, including the `G`, then `B` snap-base workflow. `Backspace` edits typed input or resets the current pick; `Esc` resets and then exits.

Use **Add Construction Guide** for an infinite persistent reference. Pick a start, point in the desired direction, and optionally type a scene-unit distance before clicking or pressing `Enter`. Press `A` for a guide aligned between the points, or `X`, `Y`, or `Z` for a global-axis guide through the first point. The typed length establishes a precise direction endpoint; the resulting guide remains infinite. Guides and finite measurements are lightweight Empty objects in the `Construction Guides` collection. The sidebar controls shared visibility, color, and line width, with separate clear actions so clearing guides does not remove measurements.

Use **Draw Mesh Line** in Edit Mode as a combined surface-knife and pencil tool. Click a start point, then click or press `Enter` to commit each subsequent segment and continue the chain. Press `X`, `Y`, or `Z` before typing to constrain the next segment to a global axis. Type a scene-unit distance such as `5"` or `125mm` to set the next length along the pointed direction. `Esc` first clears active numeric input; with no numeric input, `Esc` or right-click ends the chain and preserves accepted segments. Vertex hits bind directly and edge hits split the edge. Edit Mode targets are restricted to the active mesh, and projected active-mesh edges remain available at silhouettes where a face ray can miss by a fraction of a pixel. Interior path points remain clean loose path vertices while the cut is incomplete, avoiding the radial fan created by face-poke topology. When the path reaches a second boundary point on the same face, the complete path becomes one knife-like face split with its interior turns preserved, including paths drawn over mildly non-planar n-gons. Closing a simple coplanar loop on a face creates an independent inner face and only two required bridge edges in the surrounding surface; the loop may share one vertex with an existing cut or the face boundary. Closing a loop in free space creates a standalone face suitable for extrusion. If a requested cut cannot be finalized, the accepted path remains intact as edges instead of deleting or partially replacing existing topology.

The current snap layer recognizes visible mesh hits, nearby projected base-mesh vertices, perspective-correct edge projections, edge midpoints, face centers, face points, infinite guides, measurement starts/midpoints/ends, finite measurement lines, and free-space cursor points. During all four creation workflows, the current hovered vertex, edge, face, guide, or measurement is highlighted orange and accepted targets are highlighted blue; the viewport status shows the target, active axis, typed value, and invalid input in red. Logical candidates take precedence over raw face hits within the configurable **Snap Radius**, which defaults to 28 pixels. Edit Mode reads every active BMesh vertex and edge for corner, boundary, and path-closure capture, so newly created loose or surface topology is immediately available to the next segment. Intersection inference, parallel/perpendicular constraints, local axes, guide planes, and depth-filtered snap caching are planned follow-ups. See the living [Measure and Construction Guides plan](docs/MEASURE_GUIDES_PLAN.md) and [Interaction Toolkit Plan](docs/INTERACTION_TOOLKIT_PLAN.md).

Numeric input follows one shared contract. Point in a direction, type a value with optional scene units, and press `Enter` to accept the current stage. `A`, `X`, `Y`, or `Z` can change the applicable alignment/axis before or after the number, matching Blender's transform-style ordering; other letters remain available for unit suffixes. `Backspace` edits the value and, once empty, returns to the previous pick where the tool supports staged picking. `Esc` clears typed input before stepping back or exiting. Right-click cancels one-shot Dimension, Measure, and Guide creation; in the chained Mesh Line tool it ends the session while retaining already accepted geometry.

The measurement line and value always remain aligned to the two selected anchors. **Extension Axis** controls how the annotation moves away from that edge:

- **Auto:** choose the usable global axis closest to the natural placement direction from the current view.
- **X / Y / Z:** extend toward the selected global axis while keeping the dimension line parallel to the measured edge.

Changing **Extension Axis** after creation preserves the numeric offset. If the selected axis is parallel to the measured edge and cannot move the annotation away from it, the extension falls back to the automatically selected usable axis instead of hiding the dimension.

Use the global **Text Placement** setting to apply **Inline (Gap)**, **Above Line**, or **Outside End** to every dimension in the scene. Inline labels automatically move outside when the projected line is too short to contain the text and arrowheads cleanly.

Each anchor's picker displays the current vertex index, **Object Point**, or **World Point**. Edge and face snaps become object-local points, so they follow object transforms; vertex snaps continue to follow the referenced base vertex. Click the picker to enter viewport reattachment mode, then click a replacement vertex, edge, midpoint, face, guide, or free-space point.

The sidebar uses independently collapsible sections. **Global Dimension Settings** controls units, numeric precision, text placement, logical snap radius, and whether drawn dimensions can be selected in the viewport. **Selected Mesh Size HUD** controls the optional corner readout, including evaluated volume, its viewport corner, and horizontal/vertical edge padding. Volume uses the evaluated viewport mesh, so visible modifiers and object scale are included. One closed manifold shell shows a normal value, multiple disconnected closed shells show an approximate (`~`) sum, and open or non-manifold meshes show `N/A`. **Selected Dimension (Local)** appears only for a selected dimension and changes that annotation alone. New dimensions use cyan-blue, with a lighter blue selected state; existing saved colors are preserved.

Each dimension has a local **Offset Angle**. Zero degrees follows the selected extension axis; positive or negative angles rotate the annotation plane around the measured edge, tilting it forward or backward without changing its value or offset distance.

The dimension Empty follows the world-space midpoint of its rendered dimension line as anchors, referenced geometry, extension axis, offset, or offset angle change. This keeps the selectable scene object near its annotation without modifying scene data from the viewport draw callback.

**Global Dimension Style** defines the color, selected color, line width, text size, and arrow size copied into new dimensions. **Set All Dimensions** copies those values to every existing dimension in the scene. Each selected dimension can customize the same values locally, and **Reset to Global** copies the current global style back to that dimension. Style values are copied rather than linked, so later global edits do not overwrite intentional local changes until one of those actions is used.

**Copy to Global** performs the reverse operation: it copies the selected dimension's local style into the global defaults for future dimensions. It does not modify other existing dimensions unless **Set All Dimensions** is subsequently used.

Use **Custom Text** in the selected dimension panel for an optional note. The note can sit above or below the measured value and participates in inline gaps, outside placement, readability spacing, and viewport hit-testing as one label block.

The visible **Unit Style** choices follow Blender's Scene Unit System: metric scenes show adaptive metric, millimeters, centimeters, meters, and Blender-native formatting; imperial scenes show feet/inches, decimal inches, fractional inches, and Blender-native formatting. Separate metric and imperial selections are preserved when switching systems. All conversions respect Blender's scene **Unit Scale** (`scale_length`).

## Data and limitations

Each dimension is an Empty in a scene-owned `Dimensions` collection. Infinite guides and finite measurement segments use a separate scene-owned `Construction Guides` collection. Each measurement keeps an internal, non-selectable two-vertex child mesh at its exact endpoints so Blender's native transform snapper can acquire them; existing saved measurements receive this proxy automatically. A second Blender scene receives its own annotation collections rather than sharing objects with another scene. Dimension and guide custom properties store anchors as linked base-mesh vertices, object-local surface points, or fixed world coordinates, plus placement data and display settings. Measurements intentionally use fixed world anchors. Screen-space rendering keeps text and arrowheads a stable pixel size while zooming.

Current limitations:

- Dimension creation and reattachment are Object Mode workflows; mesh line drawing is an Edit Mode workflow.
- Snapping considers the visible ray-cast face, projected vertices within the configured capture radius, edge projections, edge midpoints, face centers, face hits, infinite guide projections, measurement endpoints/midpoints/segments, and free-space points. Draw Mesh Line confines its fallback candidates to the active Edit Mode mesh; projected-vertex fallback in Object Mode is not yet depth-filtered, so dense meshes can offer an occluded vertex that shares the same screen neighborhood. A cached depth-aware index is planned.
- Anchors use base-mesh vertex indices, not modifier output or persistent vertex IDs. Topology changes can detach an anchor or make an index identify a different vertex.
- Dimensions are viewport overlays and do not appear in final renders.
- Dimension overlays follow Blender viewport visibility, including an individual Empty's hide state and hidden or excluded parent collections/view layers.
- A detached vertex uses its fallback coordinate and renders in red with a warning in the selected-dimension panel. A missing target object prevents the viewport annotation from drawing, but the panel still reports the missing reference.
- There is no dimension list, bulk visibility controls, preferences panel, or custom keymap yet.
- Construction guides currently support infinite aligned/global-axis lines and group controls, while measurements support fixed finite segments. Neither supports guide planes, offsets, or per-object styling.
- Draw Mesh Line performs a surface-topology cut, not a volumetric bisect through the entire solid. An open path becomes a face split when both ends reach the boundary of one face; an unfinished interior-ended path remains loose instead of forcing invalid polygon topology. Closed surface-face creation assumes a simple coplanar loop and now supports a single shared boundary/cut vertex. Self-intersecting, non-coplanar, multi-face, highly non-manifold, or more extensively boundary-sharing loops remain ordinary path edges.
- The selected-object HUD sorts bounding-box extents largest-to-smallest; Length, Width, and Thickness are not fixed local-axis labels.
- HUD volume is only reported for closed manifold evaluated meshes. A `~` value sums disconnected shells and may over-count overlapping or nested shells; self-intersecting geometry can also remain ambiguous.

## Development

The extension uses Blender's bundled `bpy`, `blf`, `gpu`, `mathutils`, and `bpy_extras` modules. Meaningful integration tests must therefore run in Blender's Python environment.

Run the Blender smoke suite from the repository root:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --factory-startup --python tests\blender_smoke.py
```

The executable path may differ by installed Blender version. Before a release:

1. Compile all Python files and run `tests/blender_smoke.py`, plus focused tests for unit formatting and geometry helpers.
2. Build and validate the extension with the supported Blender version.
3. Test registration, unregistration, saving, and reopening in a clean Blender profile.
4. Create dimensions within one object and across two objects; then move, rotate, scale, and edit referenced geometry.
5. Verify Auto/X/Y/Z extension switching, keyboard constraints, offset editing, guide snapping/selection, mesh line creation, reattachment, click selection, unit formats, and broken references.
6. Add CI for Blender integration coverage and release validation.

The next useful product work is a cached, depth-aware, target-filterable snap index; parallel/perpendicular and local-axis inference; stable vertex identities; a dimension/construction-object management list; and performance testing on larger scenes. The separate Rectangle, Push/Pull, Offset, Move/Copy, Protractor, Circle/Arc, and Eraser proposals are intentionally deferred; the current product direction is to make the four core workflows trustworthy before deciding whether any broader tool expansion belongs in this add-on.

## Source layout

```text
|-- dimensions/
|   |-- blender_manifest.toml
|   |-- anchors.py, collections.py, properties.py
|   |-- drawing.py, snapping.py, tools.py, units.py, ui.py
|   `-- operators/
|       |-- create_dimension.py, create_guide.py, create_line.py, measure.py
|       |-- reattach_anchor.py
|       |-- style.py
|       `-- click_select.py
`-- tests/
    `-- blender_smoke.py
```
