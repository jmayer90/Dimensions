# Dimensions

A Blender extension for precise viewport dimensions, measurements, and construction guides — without cutting or editing your model's geometry.

Dimensions gives you persistent, editable annotations that stay attached to your model as it changes. It's aimed at people who need to communicate sizes and angles from a Blender scene: product and furniture design, architectural massing, fabrication drawings, and anyone who has wished Blender's measure tool remembered anything.

**Status:** early and actively developed. `0.7.0` is a deliberate simplification: fewer tools, each one predictable. The property schema is not yet frozen, but scenes carry a schema version and are migrated on load. See [Upgrading from 0.6](#upgrading-from-06) for what changes in older files. Requires **Blender 5.1 or newer**.

## Features

- **Linear dimensions** between vertices, edges, faces, guides, measurements, or free points, in Object or Mesh Edit Mode.
- **Chain** — a run of ordinary linear dimensions placed end to end on one dimension line. Each one is an independent dimension you can edit or delete.
- **Angle dimensions** from any two non-parallel edges, with minor, supplement, and reflex solutions.
- **Area dimensions** with a live face binding and a label you place.
- **Measure** — a transient tape measure with total and ΔX/ΔY/ΔZ, chaining, clipboard copy, and an explicit save.
- **Construction guides** — guide lines, offset guides, guide points, and snappable guide-plane grids. They are ordinary objects: select them and move, rotate, or scale them with Blender's own tools.
- **Snapping** to vertices, edges, midpoints, face centers, face points, guides, guide points, grids, and measurement points, with drafting inference (parallel, perpendicular, extension, intersection, face plane, local axis).
- **Typed input** in scene units — `125mm`, `2ft`, `5"` — with `A`, `X`, `Y`, and `Z` axis locks.
- **Presentation control** — named styles, endpoint marks, extension gaps and overshoot, dual units, label placement, prefixes, suffixes, tolerances, and per-annotation overrides.
- **Annotation Manager** to search, filter, select, frame, rename, hide, isolate, restyle, delete, and repair annotations and guides.
- **Renderable output** as Grease Pencil strokes for EEVEE or Cycles, plus **scale-correct SVG and PDF** drawings with an optional border and title block.
- **A viewport HUD** showing selected-mesh dimensions and evaluated volume.

Annotations are ordinary Blender objects in dedicated `Dimensions` and `Construction Guides` collections, so they select, undo, save, and link like anything else in your scene.

## Install

Download the latest `dimensions-<version>.zip` from the [Releases](../../releases) page. In Blender, choose **Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk**, select the ZIP, and enable **Dimensions**.

Installing does not change Blender's global snapping, keymaps, or Auto Merge settings.

To build the archive yourself instead, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Getting started

Open the 3D Viewport sidebar with `N` and choose the **Dimensions** tab. From top to bottom:

- **Dimensions** — Dimension, Chain, Angle, Area, and Measure, followed by the **Direction** row (Auto, X, Y, Z) that every tool starts with.
- **Construction** — Guide Line, Offset Guide, Guide Point, Guide Point at Selection, Plane: 3 Points, and Plane: Face, plus guide display settings and Clear buttons.
- **Annotation Manager**, **Selected** (settings for the active annotation or guide), and **Output**.
- **Snap Targets**, global settings, and named styles, collapsed by default.

Every button has a tooltip. While a tool runs, a small badge in the lower-left corner names the tool and the next step, and Blender's status bar lists the keys.

To select an annotation by clicking it, use **Dimensions Selection** in the 3D View toolbar. Guide points, lines, and planes are ordinary objects, so the normal select tool works on them too.

### A linear dimension

1. Click **Dimension** in Object or Mesh Edit Mode.
2. Click a start point, then an end point.
3. Move the mouse to place the dimension line, and click.

Press `A`, `X`, `Y`, or `Z` before the first point or while placing the line to lock the direction; press the same axis twice for the active object's local axis. Type a distance after the first point to set an exact length — with an axis locked you can type right away; otherwise point toward the end first. Units are welcome: `125mm`, `2ft`, `3 meters`. After each dimension the tool starts the next one with the same direction. `Backspace` steps back; `Esc` or right-click exits.

In Mesh Edit Mode with exactly one edge selected, **Dimension** dimensions that edge immediately.

### Chain

**Chain** places ordinary linear dimensions end to end. Click the first point, the second point, and place the dimension line; from then on, every click adds the next dimension, starting where the previous one ended and sharing its dimension line. Choose a direction first to dimension along X, Y, or Z — points off that axis are projected onto it, so the run stays straight. `Backspace` starts a new run; `Esc` or right-click ends it. Each dimension in the run is a separate object with its own undo step.

### Measure

**Measure** is a tape measure. Click two points to see the distance plus signed ΔX, ΔY, and ΔZ; each new click continues from the last point. Nothing is saved unless you press `P`, which saves the current segment as a measurement other tools can snap to. `Ctrl+C` copies the reading. `Esc` or right-click exits.

### Construction guides

Construction objects live in the `Construction Guides` collection, are never rendered, and are never part of generated output. Every construction tool uses the same snapping, axis locks, and typed distances as **Dimension**, and keeps placing until you press `Esc`.

- **Guide Line** — click a point on the line, then a second point for its direction (or press `X`, `Y`, or `Z` and type a length). The line runs through the object's origin along its local X axis, so moving or rotating the object moves the line.
- **Offset Guide** — click an edge, guide line, or measurement, then click where the parallel line should pass or type its distance. A typed distance goes on the side of the pointer; type a negative distance for the other side.
- **Guide Point** — click to place points; **At Selection** places one at the center of the selected objects or mesh vertices. Move a point with `G` like any object.
- **Plane: 3 Points** — click three points to place a grid through them. In Mesh Edit Mode with exactly three vertices selected, the grid is placed immediately.
- **Plane: Face** — places a grid lying on a face and extending past it. In Mesh Edit Mode the selected face is used; otherwise click a face.

A guide plane is a real wireframe grid mesh, so you can click it to select it; move, rotate, and scale it; and snap to it with Blender's own snapping as well as with Dimensions tools. Its grid intersections, lines, midpoints, and surface are all snap targets. Grids never block snapping to the model behind them. Select a plane to change its **Half Size** and **Grid Spacing** in the **Selected** panel; dimensions snapped to a grid survive a spacing change.

Dimensions snapped to a guide point, guide line, or grid follow it when you move or rotate it. **Clear Guides** and the manager's **Delete** leave those dimensions where they are as fixed points; deleting a guide with Blender's own Delete marks them **Needs Repair**, like any deleted source.

### Area and angle

**An area dimension** works in both modes. In Edit Mode, select faces and choose **Area** (or **Area from Selected Faces**), then click to place the label. In Object Mode, click a face — Shift-click to add more, `Enter` to continue — then place the label. `Backspace` starts the face picking over. Live areas follow their faces; **Capture** freezes the current value. Faces must come from a local mesh: construction grids and linked meshes cannot be Area sources.

**An angle dimension** picks Edge A, then Edge B, then the arc radius. Connected edges use their shared vertex; disconnected or skew edges use their extended lines. A selected angle can switch solution or replace either edge.

### Editing and repair

The active selected dimension shows one purple handle: a diamond adjusts a linear dimension's offset, a circle adjusts an angle's radius, and a square moves an area label. Click the handle, move, optionally press an axis key or type a distance, and click to confirm. `Esc` cancels.

Moving an annotation object records a presentation offset that keeps following the source geometry. Rotation and scale are locked for annotations; use the handles and properties instead.

When a source vertex or face disappears, the annotation keeps its last value but is labeled **Fallback** or **Needs Repair**. The manager's **Show Sources** button selects what it was attached to, and the **Guided Repair** panel frames the last known position and lets you accept the nearest match on the same source, pick a new source, or convert a lost point to a fixed world point.

### Annotation Manager

The manager lists every dimension, measurement, and guide. Type in the search box to filter by name; click the filter button beside it to show or hide types (Linear, Angle, Area, Measure, Line, Point, Plane) and states (Live, Captured, Fallback, Needs Repair), or to show only annotations measuring the active object. Click a row to select it; its value and actions appear below the list.

**Apply To** chooses what the buttons below change: **Selected** (the default) uses the annotations selected in the viewport, or the highlighted row if nothing is selected; **All Listed** uses every row the search and filters show. **Isolate** shows only those annotations and hides every other annotation and guide — your model stays visible. **Exit Isolate** restores everything as it was.

### Output

**Renderable output:** open **Output**, choose Selected or Visible annotations, choose Camera Relative or World Scale sizing, and click **Generate Grease Pencil Output**. Generated objects go in the scene-owned `Dimensions Output` collection and are replaced on regeneration, so hand edits to them are disposable. Fallback and Needs Repair annotations are skipped.

**Scale-correct vector export:** set an active orthographic camera framing the region to export. Choose A4, A3, or US Letter, portrait or landscape, and a scale denominator — `10` means 1:10. Set physical line weight, text height, and endpoint size in millimetres, optionally enable the **Drawing Sheet** border and title block, then **Export SVG** or **Export PDF**. **Fit Scale to Camera** chooses a scale that fits the printable area.

### Keys

| Key | Action |
| --- | --- |
| `A` `X` `Y` `Z` | Lock to aligned or a world axis; press an axis twice for the active object's local axis |
| `S` | Cycle all snap targets, then each target individually |
| `L` | Lock or release the current inference reference |
| `P` | Save the current Measure segment |
| `Ctrl+C` | Copy the current Measure reading |
| Type + `Enter` | Use a typed distance in scene units, or with a unit such as `2ft` or `125mm` |
| `Backspace` | Step back one point (in Chain, start a new run) |
| `Esc` | Exit the tool; with continuous placement off, first clear typed input or step back |
| Right-click | Exit the tool |

Orbit, pan, and zoom keep working while a tool runs — with the mouse, a trackpad, a 3D mouse, `Home`, or the numpad view keys. Once you start typing a distance, letters belong to its unit, so `S` and `L` act only before you type.

Every key except `Backspace`, `Esc`, and right-click is rebindable in the add-on preferences, and changes take effect immediately. Creation shortcuts ship unbound, so nothing Dimensions installs can shadow a binding you already use.

While a tool runs, hovering an edge, guide, or face records an inference reference. Parallel, perpendicular, extension, intersection, face-plane, and local-axis candidates appear as orange glyphs, and the badge names the current one. Press `L` to freeze the reference. Real geometry under the cursor always wins over inference unless the reference is locked. Each inference type can be turned off in the preferences.

### Placement and styles

Text Size and Arrow Size are fixed viewport-pixel sizes; zoom and object transforms never change them. **Global Dimension Settings** sets units, precision, and text placement (Inline, Above Line, Outside Start, Outside End).

Linear dimensions can use Open Arrow, Filled Arrow, Architectural Tick, Dot, or None at each end, with extension gaps and overshoot. Named styles under **Named Annotation Styles** store color, sizes, precision, endpoint marks, extension treatment, primary and secondary units, label layout, prefix, suffix, and tolerance. Select annotations and click **Assign Style to Selection**. Each property resolves as local override → named style → scene default, and **Clear Overrides and Inherit** restores full inheritance.

## Upgrading from 0.6

Opening a file saved by 0.6 or earlier converts it automatically:

- **Chain and Baseline sets** become separate linear dimensions with the same anchors, offsets, and style. Baseline rows keep their stacking.
- **Offset, centerline, angular, and spaced guides** become fixed guide lines at their last position. A spaced set keeps its first line.
- **Guide lines and guide points** become movable objects at their current position. They no longer follow the vertex they were placed on.
- **Guide planes** become snappable grid meshes on their last resolved plane.
- **Named datums** become ordinary guide points.
- **Radial, diameter, arc-length, coordinate, and elevation annotations are removed**, because 0.7 has no equivalent. Their names are printed to Blender's system console when the file opens. Keep a copy of the file if you still need them.
- The **active construction plane** setting is cleared. X, Y, and Z always mean world axes.
- Objects **appended** from a 0.6 file into a 0.7 scene are converted the same way.

Linked and library-override objects from a 0.6 library cannot be converted, because Dimensions never writes linked data. They keep their 0.6 state — sets and radial annotations hidden, guide lines along X, planes as plain empties — until you open the library file in 0.7 and save it. Objects appended from files older than 0.4.2 into an existing 0.7 scene receive only the 0.7 conversion, not the earlier upgrades; open and save the old file in 0.7 first.

## Known limitations

- Grease Pencil generation and vector export cover linear, angle, and area annotations in Live or Captured state. Measurements and construction guides are viewport and construction data only.
- Camera-relative output resolves sizes at each dimension's midpoint, so dimensions spanning very different camera depths can vary under perspective.
- Generated output is a snapshot. Regeneration replaces matching generated objects and their hand edits. The stroke font maps lowercase custom text to uppercase and shows a boxed fallback glyph for unsupported characters.
- Guide lines and guide points are fixed where you place them; they do not follow later edits to the mesh they were snapped to. Dimensions snapped to a guide follow the guide, not the mesh behind it.
- A distance typed with **X**, **Y**, or **Z** locked, or a point projected onto a locked axis, becomes a fixed point in space rather than following the vertex under the pointer.
- A scene saved by a newer version of Dimensions is left untouched; update the add-on before adding annotations to it.
- Guide planes are real meshes, so Blender's own face snapping lands on them while they are visible. Hide a grid or turn off its **Guide Plane** snap target when you want to snap past it. A grid lying exactly on a model face can occasionally hide that face's edges from Dimensions snapping, depending on which surface Blender reports first.
- Vertex anchors use persistent mesh point IDs. Removed or duplicated IDs keep the last value but are marked **Fallback** and offer guided repair; surface anchors follow object transforms but not later deformation.
- Deleting an object used by an annotation keeps its last value and marks it **Needs Repair**. Linked and library-override annotations are read-only.
- Live Areas bind base-mesh faces from one object. Evaluated modifiers are used only when bound face IDs propagate uniquely with unchanged topology; otherwise the base value is shown as a non-authoritative **Fallback** and is not exported.
- Projected snapping and overlay drawing are measured on dense scenes; see [`docs/DESIGN.md`](docs/DESIGN.md#measured-performance).
- Named styles are stored per scene; there is no cross-file style library.
- SVG/PDF export is a single camera-framed page and needs an orthographic camera. Labels are vector strokes rather than selectable text.

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for how to build, test, and what the project is and isn't trying to be.

- [docs/DESIGN.md](docs/DESIGN.md) — architecture, design invariants, known risks, and the roadmap.
- [docs/tickets/](docs/tickets/) — the milestone and status dashboard plus structured work tickets.
- [docs/VERSIONING.md](docs/VERSIONING.md) — what moves the version number, and what 1.0 will mean.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
