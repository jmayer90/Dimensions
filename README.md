# Dimensions

A Blender extension for precise viewport dimensions, measurements, and construction guides — without creating or cutting mesh geometry.

Dimensions gives you persistent, editable annotations that stay attached to your model as it changes. It's aimed at people who need to communicate sizes and angles from a Blender scene: product and furniture design, architectural massing, fabrication drawings, and anyone who has wished Blender's measure tool remembered anything.

**Status:** early and actively developed (`0.3.x`). The interaction model is settled; the property schema is not yet frozen, but scenes now carry a schema version and are migrated on load, so annotations saved with an older version are upgraded rather than recreated. Requires **Blender 5.1 or newer**.

## Features

- **Linear dimensions** between vertices, surface points, guides, measurements, or free world points, in Object or Mesh Edit Mode.
- **Angle dimensions** from any two non-parallel edges — connected, intersecting only when extended, or skew in 3D — with minor, supplement, and reflex solutions.
- **Area dimensions** with a live face-set binding and an explicit label placement you control.
- **Measurements and construction guides** — saved finite measurements and infinite guides that other tools can snap to.
- **Snapping** to vertices, edges, midpoints, face centers, face points, guides, and measurement endpoints, midpoints, and segments.
- **Typed input** in scene units — `125mm`, `2ft`, `5"` — with `A`, `X`, `Y`, and `Z` axis constraints.
- **Continuous placement** for dimensions, angles, areas, measurements, and guides, with a session axis that persists while the tool remains active.
- **Presentation control** — metric and imperial formatting, projected distances, architectural tick or arrow endpoints, value prefixes and suffixes, linear tolerances, and per-annotation style overrides.
- **A viewport HUD** showing selected-mesh dimensions and evaluated volume.

Annotations are ordinary Blender objects in dedicated `Dimensions` and `Construction Guides` collections, so they select, undo, save, and link like anything else in your scene.

## Install

Download the latest `dimensions-<version>.zip` from the [Releases](../../releases) page. In Blender, choose **Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk**, select the ZIP, and enable **Dimensions**.

Installing does not change Blender's global snapping, keymaps, or Auto Merge settings.

To build the archive yourself instead, see [CONTRIBUTING.md](CONTRIBUTING.md). Windows uses PowerShell; Linux and macOS can use the included POSIX build and validation scripts.

## Getting started

Open the 3D Viewport sidebar with `N` and choose the **Dimensions** tab.

Use **Edit ▸ Preferences ▸ Add-ons ▸ Dimensions** to tune snap and selection radii, choose the default Auto/X/Y/Z session axis, enable or disable continuous placement, and set defaults for new annotations. Continuous placement is on by default. Scene and per-annotation settings remain part of the `.blend` file.

To select an existing annotation directly in the viewport, activate **Dimensions Selection** from the 3D View toolbar in Object Mode. Clicks that do not hit a Dimensions object continue to Blender's normal selection tool.

**A linear dimension:**

1. Click **Create Dimension** in Object or Mesh Edit Mode.
2. Click a highlighted start point, then move toward the next point.
3. Optionally press `A`, `X`, `Y`, or `Z` — or drag middle mouse after the first point — to lock to a global axis.
4. Optionally type a distance and press `Enter`. Clicking also commits a valid stage.

After a commit, the tool starts another placement while retaining its session axis and placement offset. Press `A`, `X`, `Y`, or `Z` at the fresh stage to change direction for the next annotation. Press `Esc` or right-click to exit the session. Changing mode or the active object also ends it cleanly.

In Mesh Edit Mode, **Create Dimension** is selection-first: with exactly one edge selected it commits a length immediately, and any other selection falls through to interactive picking.

**An area dimension** works in both modes. In Edit Mode, select faces first, run the tool, then place the label. In Object Mode, click a face — Shift-click to add more, `Enter` to proceed — then place the label. A selected area also exposes **Remake Area**, **Select Source Faces**, and **Capture**.

**An angle dimension** acquires Edge A, then Edge B, then the arc radius. Connected edges use their shared vertex; disconnected or skew edges derive a virtual center from their supporting lines. A selected angle can switch solution or replace either edge independently.

### Keys

| Key | Action |
| --- | --- |
| `A` `X` `Y` `Z` | Constrain to aligned or global axis |
| Middle drag | Choose a projected global axis (after the first point) |
| Type + `Enter` | Commit a scene-unit distance |
| `Esc` | Exit continuous placement; otherwise clear typed input, step back, or exit |
| Right-click | Exit the active placement session |

Every key in this table is rebindable, and the modal keys take effect as soon as you change them — no restart. Creation shortcuts ship unbound, as disabled entries in the Dimensions add-on Keymap preferences, so nothing Dimensions installs can shadow a binding you already use.

### Placement

Linear and area annotations are placement objects. Move one with Blender's normal transform tools and you move its presentation — the source anchors stay attached, and the offset you set survives later changes to the source geometry or object transform.

Text Size and Arrow Size are fixed viewport-pixel sizes. View zoom, projection, source transforms, and the annotation Empty's scale do not enlarge the live overlay. Generated render output will use separate sizing rules when that output path is added.

Linear dimensions can use the default open arrows or **Architectural Tick** endpoints. Set the default under **Global Dimension Style**, or override it for the selected dimension under **Local Style**.

## Known limitations

- **Dimensions are viewport overlays and do not appear in renders.** A render or export path is planned but not built.
- Construction guides are Object Mode only. Dimensions and measurements work in both modes.
- Vertex anchors use persistent mesh point IDs. If topology removes an anchored point or duplicates its ID, the anchor resolves to the closest stored position rather than reporting a detached state. Surface anchors follow object transforms but not later deformation.
- Live areas bind base-mesh faces from a single object. Modifier-evaluated and multi-object areas are not supported; lost or ambiguous faces surface a visible **Needs Repair** state rather than guessing.
- **Snapping becomes slow to start on scenes above roughly 100,000 visible vertices.** The first snap query in a new view builds a source cache: about 0.4 s at 100k vertices, but around 4.9 s at 1 million. Once built, individual snaps are effectively instant (0.013 ms) and moving the view alone does not rebuild the cache. See [`docs/DESIGN.md`](docs/DESIGN.md#measured-performance) for the full measurements.
- Overlay drawing is measured at 500 visible dimensions and holds above 30 fps; draw cost does not depend on how many other objects the scene contains.
- There is no annotation manager, no local-axis or parallel/perpendicular inference, or guide planes yet.

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for how to build, test, and what the project is and isn't trying to be.

- [docs/DESIGN.md](docs/DESIGN.md) — architecture, design invariants, known risks, and the prioritized roadmap. Read this first for anything non-trivial.
- [docs/tickets/](docs/tickets/) — structured work tickets on the path to 1.0, each with acceptance criteria and a code map.
- [docs/VERSIONING.md](docs/VERSIONING.md) — what moves the version number, and what 1.0 will mean.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
