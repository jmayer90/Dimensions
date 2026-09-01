# Dimensions

A Blender extension for precise viewport dimensions, measurements, and construction guides — without creating or cutting mesh geometry.

Dimensions gives you persistent, editable annotations that stay attached to your model as it changes. It's aimed at people who need to communicate sizes and angles from a Blender scene: product and furniture design, architectural massing, fabrication drawings, and anyone who has wished Blender's measure tool remembered anything.

**Status:** early and actively developed. `0.5.0` is released and the `0.6.0` drawing-sheet candidate is implemented and validated. The core point-acquisition contract is stable; deliberate contract changes are versioned explicitly. The property schema is not yet frozen, but scenes carry a schema version and are migrated on load, so annotations saved with an older version are upgraded rather than recreated. Requires **Blender 5.1 or newer**.

## Features

- **Linear dimensions** between vertices, surface points, guides, measurements, or free world points, in Object or Mesh Edit Mode.
- **Chain and baseline dimension sets** with shared alignment, automatic baseline stacking, member insertion/deletion, and member-local repair.
- **Radial, diameter, and arc-length dimensions** fitted to selected mesh vertices, edge loops, or face sets, with fitted/across-flats/across-corners measurement and truthful fit-quality warnings.
- **Angle dimensions** from any two non-parallel edges — connected, intersecting only when extended, or skew in 3D — with minor, supplement, and reflex solutions.
- **Area dimensions** with a live face-set binding and an explicit label placement you control.
- **Transient tape measurement** with total and signed ΔX/ΔY/ΔZ, chaining, clipboard copy, and explicit promotion to a saved finite measurement.
- **Saved measurements, construction guides, guide points, and bounded guide planes** that other tools can snap to.
- **Snapping** to vertices, edges, midpoints, face centers, face points, guides, guide points, guide planes, and measurement endpoints, midpoints, and segments.
- **Drafting inference** for parallel, perpendicular, extension, intersection, active-face planes, and rotated-object local axes, with a lockable reference and per-type preferences.
- **Typed input** in scene units — `125mm`, `2ft`, `5"` — with `A`, `X`, `Y`, and `Z` axis constraints.
- **Continuous placement** for dimensions, angles, areas, measurements, and guides, with a session axis that persists while the tool remains active.
- **Presentation control** — reusable named styles, independent filled/open/tick/dot/none endpoints, extension gaps and overshoot, primary plus secondary units, aligned or horizontal labels, Above/Broken/Outside placement, automatic tight-space leaders, prefixes, suffixes, tolerances, and per-annotation overrides.
- **Renderable linear, angle, area, radial, diameter, and arc-length dimensions** generated as Grease Pencil strokes for EEVEE or Cycles, using camera-relative pixels or explicit world-space sizing.
- **Scale-correct SVG and PDF drawings** framed by an orthographic camera, with A4, A3, or US Letter paper, portrait/landscape orientation, and explicit 1:N scale.
- **Single-sheet drawing layout** with an optional physical border and fixed title block for drawing title, number, revision, author, date, and scale.
- **A viewport HUD** showing selected-mesh dimensions and evaluated volume.

Annotations are ordinary Blender objects in dedicated `Dimensions` and `Construction Guides` collections, so they select, undo, save, and link like anything else in your scene.

## Install

Download the latest `dimensions-<version>.zip` from the [Releases](../../releases) page. In Blender, choose **Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk**, select the ZIP, and enable **Dimensions**.

Installing does not change Blender's global snapping, keymaps, or Auto Merge settings.

To build the archive yourself instead, see [CONTRIBUTING.md](CONTRIBUTING.md). Windows uses PowerShell; Linux and macOS can use the included POSIX build and validation scripts.

## Getting started

Open the 3D Viewport sidebar with `N` and choose the **Dimensions** tab.

Choose a creation tool first, then use the compact, full-width **Direction** selector beneath the tool buttons to select Auto, X, Y, or Z before placing points. The **Snap Targets** row independently enables vertices, edges, midpoints, face centers, face points, guides, guide points, guide planes, and measurement endpoints, midpoints, and segments. By default it edits your persistent add-on preferences; enable **Scene Override** to store a document-specific set in the `.blend` file. Continuous placement is on by default.

**Construction Planes** creates a bounded saved plane from three selected vertices, one point plus a normal, a selected base-mesh face, or an offset from another plane. The grid extent changes presentation only. Use a selected guide plane, selected face, current view, or World XY/YZ/ZX as the one active construction plane; **Clear** restores normal view-derived placement and world axes in one action. While active, free points land on the plane, `X`/`Y` use its two in-plane axes, `Z` uses its normal, typed distances follow those directions, and the plane is highlighted amber. Lost or degenerate sources show a red Needs Repair grid. Guide planes remain viewport-only construction data and never create, section, or modify mesh geometry.

To select an existing annotation directly in the viewport, activate **Dimensions Selection** from the 3D View toolbar in Object Mode. Clicks that do not hit a Dimensions object continue to Blender's normal selection tool.

The active selected editable dimension shows one purple presentation handle: a diamond on a linear dimension line adjusts offset, a circle on an angle arc adjusts radius, and a square at an area or circular leader end moves its label. Click the handle, move the pointer, optionally press `A`, `X`, `Y`, or `Z` or type a scene-unit distance, then click or press `Enter` to confirm. `Esc` clears typed input first and otherwise cancels without changing the annotation. Handles stay a constant screen size, take priority over the annotation body, and never appear on linked or library-override data.

Annotation Empty transforms are deliberately translation-only. Moving an annotation object records a world-space presentation offset that continues to follow its source geometry. Rotation and Scale channels are locked for normal Blender transforms and never rotate, resize, or alter a measurement; legacy or scripted non-identity values are retained but ignored by the overlay, Grease Pencil, SVG, and PDF paths. Use annotation properties and presentation handles for radius, line offset, label placement, orientation, and sizing. Parent motion is treated only through the annotation's resulting world-space translation.

The **Annotation Manager** lists every dimension, measurement, guide, and guide point with its current value and Live, Fallback, Captured, or Needs Repair state. Search by name; combine kind and state filters; or capture the active mesh with **References Active** to find dependent annotations. Clicking a row name selects it. Row actions rename, show or hide, frame, delete, and open guided repair. Bulk actions operate on either the filtered rows or Blender's current selection and can show, hide, isolate, delete, assign the active named style, or reset to global style. **Exit Isolate** restores the exact visibility state from before isolation.

**A linear dimension:**

1. Click **Create Dimension** in Object or Mesh Edit Mode.
2. Click a highlighted start point, then move toward the next point.
3. Optionally press `A`, `X`, `Y`, or `Z` — press the same axis twice for the active object's local axis — or drag middle mouse after the first point.
4. Optionally type a distance and press `Enter`. Clicking also commits a valid stage.

After a commit, the tool starts another placement while retaining its session axis and placement offset. A small lower-corner badge shows the active tool and direction, plus typed distance only while you are entering one. Press `A`, `X`, `Y`, or `Z` at the fresh stage to change direction for the next annotation. Press `Esc` or right-click to exit the session. Changing mode or the active object also ends it cleanly.

**Chain and Baseline** create one persistent dimension set rather than a stack of unrelated objects. Pick the datum, then each subsequent point; every accepted member is its own undo step. The session supports the same snap-target cycle, inference lock, active construction plane, initial A/X/Y/Z constraint, typed distance, step-back, and clean exit contract as ordinary dimensions. The first member fixes the shared direction and placement plane. Later Chain points must advance along that axis, while Baseline points must remain on it; reverse or off-axis picks stay highlighted with an actionable warning and are not committed. Chain members join end to end, while Baseline members reuse the datum and add automatically spaced rows derived from label size without compressing a larger configured pitch. Select the set to change its shared offset or spacing, expand its manager/Selected Dimension member list, reattach one member endpoint, insert a point into a chain, or delete or reorder a member. Short chain labels alternate outside their segment when inline placement would collide. Legacy zero-projection, reverse, or off-axis members remain visible as Needs Repair without spoke-like shared-axis projection and are withheld from output; valid sets generate through Grease Pencil, SVG, and PDF.

**Measure** is a transient tape-measure tool. Pick two points to see the total distance plus signed ΔX, ΔY, and ΔZ in scene units; the second point immediately becomes the start of the next segment. This creates no Blender object. Press `P` to save the current segment as a persistent measurement (including its normal snap proxy), or `Ctrl+C` to copy the displayed total and components. `Esc` or right-click exits and removes the viewport overlay. The former save-on-confirm workflow remains available through Blender Search as **Measure (Persistent)** and as an unbound add-on keymap entry.

**Guide Point** saves one construction location with a distinct fixed-pixel square-and-cross marker. Use **Point** for one-click snapped/free placement, **Offset** to pick a reference and then use inference, an axis, or typed distance, and **Selection** for the midpoint/centroid of selected objects or selected mesh vertices. Vertex and surface points follow their source through supported edits; world points remain fixed. Guide points have their own snap toggle, appear in the Annotation Manager, and are included by **Clear Guides**.

**Datum** promotes the active guide point, or creates one at the cursor/selected mesh vertex, into a named oriented coordinate frame. Multiple datums can coexist. Start **Coordinate** or **Elevation** with an active datum; if several exist and none is active, choose one explicitly. In Object Mode, click any shared snap/free target to acquire the annotated point, including inference and the active construction plane. In Mesh Edit Mode, select exactly one vertex. Each annotation stores that exact datum and point binding. Coordinates show X, Y, XY, or XYZ in datum axes with configurable signs and free/row/column alignment. Elevations use world X/Y/Z or datum Z, can be absolute or relative to another elevation, and have independent fixed-decimal/sign/prefix/suffix formatting. Lost point or datum sources enter Needs Repair, and Live annotations generate through Grease Pencil, SVG, and PDF.

**Offset Guide** derives a persistent infinite guide from a mesh edge, another guide, or a face plane. Pick the source, move across it to choose the live side/distance preview, optionally press `F` to flip sides, type the same scene-unit expressions accepted elsewhere, and confirm. **Centerline** picks two parallel edge/guide lines or face planes and places the guide midway between them. Derived guides keep their relationship through source transforms and supported topology identity changes; chained offsets resolve in dependency order, while cycles are refused. A lost source turns the guide into a red dashed Needs Repair fallback instead of silently freezing it. Use its manager repair action to pick a replacement, or **Detach Selected** while live to preserve the resolved line as a fixed guide.

**Angular Guide** rotates a selected edge/guide or a guide plane's in-plane reference about the 3D cursor. Type degrees (or radians when configured), watch the line and angle preview update, press `F` to flip the signed solution, and click or press `Enter` to commit. **Spacing** stores one repeated-line definition rather than creating N manager entries: choose interval + count, interval + extent, or distribute a count evenly between two acquired references. After choosing the source direction, click the anchored origin; Distribute then asks for an anchored end. These picks use shared snap targets, inference, and the active construction plane, and both can be repaired independently. Every resolved line participates in snapping and redraw; editing interval, count, or extent updates the set in one step. **Bake to Individual Guides** materializes equivalent fixed construction guides when one line needs independent editing.

In Mesh Edit Mode, **Create Dimension** is selection-first: with exactly one edge selected it commits a length immediately, and any other selection falls through to interactive picking. The contextual, collapsible **From Mesh Selection** panel also provides explicit selected-edge angle and length actions plus selected-face area actions.

**An area dimension** works in both modes. In Edit Mode, select faces first, run the tool, then place the label. In Object Mode, click a face — Shift-click to add more, `Enter` to proceed — then place the label. A selected area also exposes **Remake Area**, **Select Source Faces**, and **Capture**. Live Areas bind base-mesh face IDs, then read viewport-evaluated modifier geometry only when Blender propagates every bound ID exactly once and preserves that face's vertex count. Topology-preserving deformation can therefore remain Live. If a modifier drops, duplicates, or structurally changes a bound identity, Dimensions keeps the base value visibly labeled **Fallback — Modifier Faces Unresolved** and withholds it from output instead of guessing correspondence. Disable the modifier to return Live automatically, or Capture if the displayed base value is the intended fixed result. Object Mode face picking remains base-mesh-only; bind before adding modifiers or select base faces in Edit Mode.

**An angle dimension** acquires Edge A, then Edge B, then the arc radius. Connected edges use their shared vertex; disconnected or skew edges derive a virtual center from their supporting lines. A selected angle can switch solution or replace either edge independently.

**Radial, Diameter, and Arc** consume at least three selected mesh points in Object or Mesh Edit Mode. Select vertices directly, an edge loop, or faces whose vertices describe the feature, then choose the circular tool. Dimensions projects the points onto a least-squares best-fit plane and fits one circle. **Fitted** reports the least-squares radius; **Inscribed** reports the selected polygon's across-flats radius; **Circumscribed** reports its across-corners radius. A closed selection produces a full circumference, while an open edge chain gives Arc its endpoint sweep. The default 2% relative RMS fit threshold marks non-circular input **Fallback** and appends the measured fit error instead of presenting the radius as authoritative; such annotations are withheld from generated/vector output and cannot be captured until repaired. Presentation follows an ANSI/ASME-style convention: radial leaders run center-to-arc, diameters cross the center, and arc length uses `⌒`; drag the square label handle or edit Leader Angle and Label Distance to place the leader.

When topology removes or duplicates an anchor identity, its value continues to use the same stored-position fallback but is labeled **Fallback — Confirm Source** instead of looking Live. Click its manager repair icon to select available sources and show the last known position in red plus the suggested nearest vertex or face in green. The **Guided Repair** panel explains the source, frames the old position, and lets you explicitly accept the suggestion, pick a replacement through normal acquisition, convert a permanently lost anchor to a world point, or repair annotations with the same cause. Linear, angle, and area repair preserves presentation offsets and is one undoable action; linked annotations remain read-only.

**Renderable output:** open **Output** in the Dimensions sidebar, choose Selected or Visible annotations, then use the **Grease Pencil** section and choose Camera Relative or World Scale sizing. Camera Relative uses the active camera and resolves pixel sizes at each annotation's depth; World Scale uses explicit scene-unit sizes. Click **Generate Grease Pencil Output** to create renderable linear, angle, area, chain/baseline, radial, diameter, arc-length, coordinate, and elevation strokes in the scene-owned `Dimensions Output` collection. Generated objects use 3D Location depth ordering with Grease Pencil lighting disabled, and generation enables the active view layer's Depth and Grease Pencil data passes. Output rechecks live source authority instead of trusting a cached state: Fallback, Needs Repair, deleted, and Visible-scope hidden sources cannot leave stale render artifacts, while Selected scope preserves valid output belonging to unselected annotations. Labels and presentation offsets follow the live annotations. Live annotations remain the source of truth. Generated objects are disposable: regenerating the same annotation replaces its prior output and any hand edits to that generated object.

**Scale-correct vector export:** set an active orthographic camera and frame the model region to export. In **Output**, choose Selected or Visible scope, A4/A3/US Letter paper, portrait or landscape, and a scale denominator. A value of `10` means 1:10: 100 mm in the model measures 10 mm in the exported SVG or PDF. Set physical line weight, text height, and endpoint size in millimetres. The optional **Drawing Sheet** section adds a border at a physical margin and a fixed lower-right title block containing the drawing title, number, revision, author, date, and current scale. These stay fixed in page millimetres when the camera, model units, or drawing scale changes. Click **Export SVG** or **Export PDF**. The camera frame is centered on the page at the requested scale; if it cannot fit, Dimensions asks for a larger page, a larger denominator, or a tighter camera frame instead of silently changing scale. Invalid sheet dimensions are likewise refused rather than clipped. Live and Captured annotations export with their resolved colors and presentation; Fallback and Needs Repair annotations are skipped.

### Keys

| Key | Action |
| --- | --- |
| `A` `X` `Y` `Z` | Constrain to aligned or world axis; with an active construction plane, X/Y are in-plane and Z is its normal |
| Middle drag | Choose a projected world or active-plane axis (after the first point) |
| `S` | Cycle all snap targets, then each target individually |
| `L` | Lock or release the current inference reference |
| `F` | Flip the side of an offset-guide preview |
| `P` | Save the current transient measurement |
| `Ctrl+C` | Copy the current measurement and components |
| Type + `Enter` | Commit a scene-unit distance |
| `Esc` | Exit continuous placement; otherwise clear typed input, cancel a handle drag, step back, or exit |
| Right-click | Exit the active placement session |

Every key in this table is rebindable, and the modal keys take effect as soon as you change them — no restart. The lower-corner badge shows the active snap set; **Snap: Free** means all targets are disabled and free world-point placement remains available. Creation shortcuts ship unbound, as disabled entries in the Dimensions add-on Keymap preferences, so nothing Dimensions installs can shadow a binding you already use.

During Dimension, Measure, and Guide point placement, hovering an eligible edge, guide, or face records the most recent inference reference. Parallel, perpendicular, extension, intersection, local-axis, and active-plane candidates use distinct orange glyphs and a named badge; an accepted inferred point uses the existing blue locked color. Press `L` to freeze the current reference through mouse movement, then `L` again to release it. Native vertices, edges, faces, guides, and measurement points own the full configured snap radius; inference is considered after native geometry unless its reference is explicitly locked. Candidate ranking is distance-led with a small logical-target bias, so a far vertex no longer steals a nearer edge or face. The add-on preference supplies the default radius and targets, while **Scene Override** switches both to document-specific values. Preferences can disable each inference type. Edge-derived inference follows the Edge snap control, guide-derived inference follows Guide, and face-plane inference follows Face Center/Face Point.

### Placement

Linear and area annotations are placement objects. Move one with Blender's normal transform tools and you move its presentation — the source anchors stay attached, and the offset you set survives later changes to the source geometry or object transform.

Text Size and Arrow Size are fixed viewport-pixel sizes. View zoom, projection, source transforms, and the annotation Empty's scale do not enlarge the live overlay. Generated output has separate camera-pixel and world-space sizing controls.

Text Placement under **Global Dimension Settings** supports Inline, Above Line, Outside Start, and Outside End. Outside Start and Outside End place the full value/custom-text block beyond the corresponding endpoint in both the live overlay and generated output. Named styles refine Inline into **Above** or **Broken** and choose **Aligned** or always-horizontal label orientation. If a Broken label plus endpoint clearance cannot fit, Dimensions consistently moves it beyond the end side and draws a leader; rows never alternate sides unpredictably.

Linear dimensions independently set their start and end marks to **Open Arrow**, **Filled Arrow**, **Architectural Tick**, **Dot**, or **None**. Extension Gap leaves clear space at the source; Extension Overshoot continues the extension beyond the dimension line. Both are viewport pixels and are converted by the same endpoint sizing policy for Grease Pencil, SVG, and PDF output.

Named styles live in the scene under **Named Annotation Styles**. Create or duplicate a style, edit its color, sizes, precision, per-end marks, extension treatment, primary and optional secondary unit format, secondary precision, bracket/parenthesis/stacked arrangement, label orientation and line relation, prefix, suffix, and tolerance, then select annotations and click **Assign Style to Selection**. Assignment clears their local overrides so later style edits update them together. A selected annotation shows an override switch and the effective inherited value beside every style property: off means inherited; on means local. Resolution is independent for every property: local override → assigned named style → scene default. **Clear Overrides and Inherit** restores full inheritance. Deleting a style safely sends its users back to scene defaults. Rename and delete remain disabled when linked annotations use the style, because linked data cannot be rewritten safely.

## Known limitations

- Grease Pencil generation supports every persistent annotation kind in valid Live or Captured state, including chain/baseline, coordinate, and elevation annotations. Measurements and construction guides remain viewport/construction data.
- Camera-relative output resolves presentation size at each dimension's midpoint. Coplanar dimensions target one output pixel of the live camera layout; dimensions that span substantially different camera depths can vary under perspective.
- Generated output is an explicit snapshot, not a live link. Regeneration replaces matching generated objects and their hand edits. The compact stroke font maps lowercase custom text to uppercase and shows a visible fallback glyph for unsupported characters.
- Generated output inherits style color, endpoint variant, precision, units, prefix, suffix, and tolerance. Its physical line, label, and endpoint sizes continue to use the separate Camera Relative or World Scale output controls, so sheets remain consistently scaled regardless of viewport pixel sizes.
- Infinite construction guides and interactive guide-point placement are Object Mode workflows; guide points and guide-plane sources can also consume Mesh Edit selections. Dimensions and measurements work in both modes.
- Vertex anchors use persistent mesh point IDs. Removed or duplicated IDs retain the prior numeric fallback but are visibly marked **Fallback** and offer explicit guided rebind; surface anchors follow object transforms but not later deformation.
- Deleting an object used by a linear, angle, area, or circular annotation preserves stored fallback data and marks the annotation **Needs Repair** instead of presenting a stale value as live. Guided repair can pick a replacement or convert a lost point source to a fixed world point. Linked and library-override annotations are shown read-only and are never rewritten by synchronization, drawing, or repair.
- Live Areas bind base-mesh faces from one object. Evaluated viewport modifiers are supported only when persistent bound face IDs propagate uniquely with unchanged per-face topology. Ambiguous evaluated identity is a non-authoritative base-value **Fallback**, while lost or ambiguous base identity is **Needs Repair**; neither is exported.
- Circular fitting reads base-mesh vertices only; Curve/NURBS sources and evaluated modifier geometry are not supported. Face sets that describe multiple concentric boundaries should be reduced to one boundary loop, or the fit-quality warning will reject them as non-circular.
- Projected snapping retains exact source coordinates and scales with visible vertex count. On the current Windows validation host, the measured cold-cache build is 6.732 ms for 100,000 vertices across 50 objects and 50.128 ms at 1 million; steady queries remain effectively instant. See [`docs/DESIGN.md`](docs/DESIGN.md#measured-performance) for the full measurements.
- Overlay drawing is measured at 500 visible dimensions and holds above 30 fps; draw cost does not depend on how many other objects the scene contains.
- Guide planes use base-mesh anchors and persistent face IDs; modifier-evaluated face correspondence is not inferred. Active face planes are captured working frames, while a saved face-defined guide plane maintains the persistent relationship.
- Derived face guides bind one base-mesh face by persistent ID. Missing or ambiguous face identity enters Needs Repair; modifier-evaluated face correspondence is not inferred.
- Chain joints and Baseline datums are synchronized by every supported edit and repair workflow, but their current saved representation duplicates the shared logical anchor across adjacent members. Direct external RNA edits can bypass that synchronization; normalizing the storage itself requires a future schema migration.
- Named styles are stored in each scene; there is no cross-file style library.
- SVG/PDF export is a single camera-framed page and requires an orthographic camera for one truthful scale across the drawing. Labels are portable vector strokes rather than selectable text. The optional fixed border/title block is single-sheet only; DXF, multi-sheet documents, and arbitrary title-block templates are not included.

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for how to build, test, and what the project is and isn't trying to be.

- [docs/DESIGN.md](docs/DESIGN.md) — architecture, design invariants, known risks, and the prioritized roadmap. Read this first for anything non-trivial.
- [docs/tickets/](docs/tickets/) — the canonical milestone/status dashboard plus structured work tickets with acceptance criteria and code maps.
- [docs/VERSIONING.md](docs/VERSIONING.md) — what moves the version number, and what 1.0 will mean.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
