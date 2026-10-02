# Dimensions 0.7.1

These notes cover what has changed since 0.4.1, the previous version on Blender Extensions: new tools for dimensioning, measuring, and construction, and fixes for several 0.4.1 bugs. Dimensions still never edits your mesh.

## Highlights

- **Chain** places a run of dimensions end to end.
- **Measure** is now a tape measure that shows the total distance plus ΔX, ΔY, and ΔZ.
- **Construction** tools add guide lines, offset guides, guide points, and snappable grid planes.
- **Drafting inference** finds parallel, perpendicular, and extension points, and each kind of snap target can be turned on or off.
- The **Annotation Manager** finds, filters, isolates, and repairs annotations.
- **SVG and PDF export** at true scale, with an optional title block.

## New tools and workflows

- **Chain:** place the first dimension, then each click adds the next one, starting where the last ended. Lock X, Y, or Z first to keep the run straight. Each dimension in the run is a separate object.
- **Measure:** each click continues from the last point. `P` saves the current segment, and `Ctrl+C` copies the reading.
- **Axis locks:** press an axis key twice to use the active object's local axis. With an axis locked, you can type a distance right after the first click.
- **Handles:** the selected annotation shows a purple handle for its offset, radius, or label. With **Dimensions Selection** active, click the handle, move, and click again.
- While a tool runs, the corner badge shows the next step and the status bar lists the keys.

## Construction guides

- **Guide Line**, **Offset Guide**, **Guide Point**, **Plane: 3 Points**, and **Plane: Face** work in Object and Edit Mode.
- Guides are ordinary objects. Move and rotate them with `G` and `R`, and dimensions snapped to them follow.
- Guide planes are wireframe grids that both Dimensions and Blender's own snapping can snap to.

## Snapping and drafting inference

- **Snap Targets** turns each kind of snap target on or off. Press `S` to cycle through them while a tool runs.
- Hover an edge or face to infer parallel, perpendicular, extension, and intersection points. `L` locks the reference.
- Outline edges snap in Object Mode even with the cursor just off the surface. Edit Mode snapping works across every object you are editing at once.

## Editing, repair, and the Annotation Manager

- **Annotation Manager:** search, filter, select, frame, rename, hide, delete, or **Isolate**.
- When a source disappears, the annotation is marked **Fallback** or **Needs Repair** instead of silently keeping its last stored position. **Guided Repair** helps you reattach it.
- **Selected** says what each end is attached to, with a **Repick** button.

## Output and styles

- **Grease Pencil:** **Camera Relative** sizing is now correct at every aspect ratio; in 0.4.1, landscape orthographic output could be up to 1.8 times too large. Generated strokes appear from the first frame of the scene.
- **SVG and PDF:** export at a 1:N scale from an orthographic camera. Turn on **Drawing Sheet** for a border and title block.
- **Named Annotation Styles**, filled arrows, dots, extension gaps, and dual units.
- Labels support all printable ASCII characters plus ×, Ø, µ, ≤, ≥, and ∠.

## Interaction and keys

- The new keys `S`, `L`, `P`, and `Ctrl+C` can be rebound in the add-on preferences.
- Trackpad, 3D mouse, `Home`, and the numpad view keys work while a tool runs.

## Performance and reliability

- The first snap in a very dense scene no longer stalls while Dimensions reads the mesh.
- Hovering dense meshes stays responsive, and Grease Pencil generation stays fast in large scenes.
- **Area** from an Edit Mode face selection now works.
- You can dimension newly extruded vertices without leaving Edit Mode.
- Annotations hold up better through undo, duplication, append, and linking.

## Changes to know about

- **Measure no longer saves automatically.** Press `P` to save a segment, or bind **Measure (Persistent)** in the add-on's keymap preferences to save on every click.
- **The middle mouse button always navigates.** To lock an axis, press `X`, `Y`, or `Z`.
- **Guides from 0.4.1 become fixed lines** and no longer follow their vertices.
- **Annotation rotation and scale are locked.** Move annotations with `G`.
- **Existing annotations keep their look** through per-annotation overrides. Prefix, suffix, and tolerance now live in **Selected**. **Clear Overrides and Inherit** returns an annotation to the shared styles.
- **Snap Radius** is now set in **Snap Targets**. A scene's own radius is used only when **Scene Override** is on.
- Renamed: **Selected Dimension (Local)** → **Selected**, **Grease Pencil Output** → **Output**, **Add Construction Guide** → **Guide Line**.
- `Backspace`, `Esc`, and right-click are fixed keys. Their keymap entries never worked and were removed, along with five preferences that had no effect.

## Upgrading

Requires Blender 5.1 or newer, the same as 0.4.1. Files from any earlier version open and convert automatically. If you may need to open a file in 0.4.1 again, keep a copy of it.
