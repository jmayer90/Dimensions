# Dimensions

Dimensions is an experimental Blender 4.2+ extension for persistent, CAD-style measurements linked to base-mesh vertices. A dimension is stored as an Empty, can span two mesh objects, and follows its referenced geometry as objects or vertices move.

Version `0.1.0` contains a usable core prototype. It still needs Blender runtime testing, automated tests, and release packaging before it should be considered production-ready.

## Features

- Create dimensions by picking two visible mesh vertices in Object Mode and placing an offset.
- Measure true point-to-point distance and extend the annotation along an automatically chosen or explicit global X, Y, or Z direction.
- Draw extension lines, arrowheads, and formatted values in the 3D Viewport.
- Link anchors across one or two mesh objects and reattach either endpoint later.
- Rename, hide, recolor, delete, and adjust dimensions with Blender controls and the Dimensions sidebar.
- Select a drawn dimension by clicking its lines or label; Shift-click toggles selection.
- Format values with Blender units; automatic or explicit millimeters, centimeters, and meters; decimal inches; fractional inches; or feet and inches.
- Place labels inline in a line break, above the line, or outside the end arrow.
- Add optional per-dimension text above or below the measured value.
- Optionally show Length / Width / Thickness for selected mesh objects in a viewport HUD.
- Make transient two-point measurements without creating or saving scene objects.
- Create persistent infinite construction guides in their own hideable collection.

## Install

The extension payload is the contents of [`dimensions`](dimensions/). Its manifest must be at the root of the ZIP, not inside an additional directory.

From PowerShell at the repository root:

```powershell
Compress-Archive -Path dimensions\* -DestinationPath dimensions-0.1.0.zip -Force
```

In Blender 4.2 or later, open **Edit > Preferences > Add-ons**, choose **Install from Disk**, select the ZIP, and enable **Dimensions**. Open the 3D Viewport sidebar with `N` and select the **Dimensions** tab.

For distribution, build and validate the archive with Blender's extension commands instead of relying only on `Compress-Archive`.

## Use

1. Enter Object Mode and choose **Create Dimension** from the Dimensions sidebar.
2. Hover near a visible vertex and click the highlighted start vertex.
3. Pick the end vertex on the same mesh or another mesh.
4. Move the pointer to set the offset. Press `X`, `Y`, or `Z` to constrain the extension direction to that global axis, or `A` to return to automatic axis selection.
5. Click to finish. Right-click or `Esc` cancels.
6. Select the dimension Empty, or click the drawn annotation, to edit it in the sidebar.

Alternatively, select **Add Dimension** from the Object Mode toolbar directly below Blender's Add Cube tool, then click in the viewport to begin the same workflow.

### Quick measure and construction guides

Use **Measure** for a temporary answer. Click a start vertex, move to another vertex, and click to keep the result visible while the tool remains active. Click again to replace it with a new measurement. Press `A` for the direct aligned distance or `X`, `Y`, or `Z` to measure the projected difference on that global axis. `Backspace`/`Delete` clears the result; `Esc` clears and then exits. Transient measurements create no object and are not saved.

Use **Add Construction Guide** for a persistent reference. Pick two vertices and press `A` for a guide aligned between them, or `X`, `Y`, or `Z` for an infinite global-axis guide through the first vertex. Guides are lightweight Empty objects in the `Construction Guides` collection and follow their linked anchors. The sidebar controls global guide visibility, color, line width, and **Clear All Guides**.

The current first pass snaps to visible mesh hits and base-mesh vertices, with a fallback for modifier/evaluated-geometry hits. Edge, midpoint, face, and intersection inference; free-space cursor points; typed distances; parallel offsets; guide planes; and direct line selection are planned follow-ups. See the living [Measure and Construction Guides plan](docs/MEASURE_GUIDES_PLAN.md) and [Interaction Toolkit Plan](docs/INTERACTION_TOOLKIT_PLAN.md).

The measurement line and value always remain aligned to the two selected anchors. **Extension Axis** controls how the annotation moves away from that edge:

- **Auto:** choose the usable global axis closest to the natural placement direction from the current view.
- **X / Y / Z:** extend toward the selected global axis while keeping the dimension line parallel to the measured edge.

Changing **Extension Axis** after creation preserves the numeric offset. If the selected axis is parallel to the measured edge and cannot move the annotation away from it, the extension falls back to the automatically selected usable axis instead of hiding the dimension.

Use the global **Text Placement** setting to apply **Inline (Gap)**, **Above Line**, or **Outside End** to every dimension in the scene. Inline labels automatically move outside when the projected line is too short to contain the text and arrowheads cleanly.

Each anchor's **Vertex Index** control displays its current index as a picker button. Click the index to enter viewport reattachment mode, then click the replacement vertex; direct numeric index editing is intentionally disabled.

The sidebar uses independently collapsible sections. **Global Dimension Settings** controls units, numeric precision, text placement, and whether drawn dimensions can be selected in the viewport. **Selected Mesh Size HUD** controls the optional corner readout, including its viewport corner and horizontal/vertical edge padding. **Selected Dimension (Local)** appears only for a selected dimension and changes that annotation alone. New dimensions use cyan-blue, with a lighter blue selected state; existing saved colors are preserved.

Each dimension has a local **Offset Angle**. Zero degrees follows the selected extension axis; positive or negative angles rotate the annotation plane around the measured edge, tilting it forward or backward without changing its value or offset distance.

The dimension Empty follows the world-space midpoint of its rendered dimension line as anchors, referenced geometry, extension axis, offset, or offset angle change. This keeps the selectable scene object near its annotation without modifying scene data from the viewport draw callback.

**Global Dimension Style** defines the color, selected color, line width, text size, and arrow size copied into new dimensions. **Set All Dimensions** copies those values to every existing dimension in the scene. Each selected dimension can customize the same values locally, and **Reset to Global** copies the current global style back to that dimension. Style values are copied rather than linked, so later global edits do not overwrite intentional local changes until one of those actions is used.

**Copy to Global** performs the reverse operation: it copies the selected dimension's local style into the global defaults for future dimensions. It does not modify other existing dimensions unless **Set All Dimensions** is subsequently used.

Use **Custom Text** in the selected dimension panel for an optional note. The note can sit above or below the measured value and participates in inline gaps, outside placement, readability spacing, and viewport hit-testing as one label block.

The visible **Unit Style** choices follow Blender's Scene Unit System: metric scenes show adaptive metric, millimeters, centimeters, meters, and Blender-native formatting; imperial scenes show feet/inches, decimal inches, fractional inches, and Blender-native formatting. Separate metric and imperial selections are preserved when switching systems. All conversions respect Blender's scene **Unit Scale** (`scale_length`).

## Data and limitations

Each dimension is an Empty in the scene-level `Dimensions` collection. Its custom properties store two object pointers, base-mesh vertex indices, fallback local coordinates, extension-axis placement data, and display settings. Screen-space rendering keeps text and arrowheads a stable pixel size while zooming.

Current limitations:

- Creation and reattachment are Object Mode workflows; edit-mode picking is not supported.
- Snapping considers vertices on the visible ray-cast face within a pixel threshold. It does not pick occluded or arbitrary nearby vertices.
- Anchors use base-mesh vertex indices, not modifier output or persistent vertex IDs. Topology changes can detach an anchor or make an index identify a different vertex.
- Dimensions are viewport overlays and do not appear in final renders.
- Dimension overlays follow Blender viewport visibility, including an individual Empty's hide state and hidden or excluded parent collections/view layers.
- A missing target object prevents that dimension from drawing. A detached vertex uses its fallback coordinate, without a special viewport warning style.
- There is no dimension list, bulk visibility controls, preferences panel, or custom keymap yet.
- Construction guides currently support infinite aligned/global-axis lines and group controls, but not guide planes, offsets, or direct overlay selection.
- The selected-object HUD sorts bounding-box extents largest-to-smallest; Length, Width, and Thickness are not fixed local-axis labels.

## Development

The extension uses Blender's bundled `bpy`, `blf`, `gpu`, `mathutils`, and `bpy_extras` modules. Meaningful integration tests must therefore run in Blender's Python environment.

Before a release:

1. Compile all Python files and run focused tests for unit formatting and geometry helpers.
2. Build and validate the extension with the supported Blender version.
3. Test registration, unregistration, saving, and reopening in a clean Blender profile.
4. Create dimensions within one object and across two objects; then move, rotate, scale, and edit referenced geometry.
5. Verify Auto/X/Y/Z extension switching, keyboard constraints, offset editing, reattachment, click selection, unit formats, and broken references.
6. Add CI for Blender integration coverage and release validation.

The next useful product work is a dimension-management list with bulk visibility actions, clearer broken-anchor warnings, and performance testing of the draw and click-selection loops in larger scenes.

## Source layout

```text
dimensions/
|-- blender_manifest.toml
|-- anchors.py, collections.py, properties.py
|-- drawing.py, snapping.py, tools.py, units.py, ui.py
`-- operators/
    |-- create_dimension.py, create_guide.py, measure.py
    |-- reattach_anchor.py
    |-- style.py
    `-- click_select.py
```
