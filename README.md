# Dimensions

Dimensions is an experimental Blender 5.1 extension focused on precise viewport dimensions and annotation. It provides persistent dimensions, saved measurements, construction guides, shared snapping, axis constraints, and scene-unit input without creating or cutting mesh geometry.

## What it does

- Creates editable dimensions between vertices, object-local surface points, guides, measurements, or world points in Object or Mesh Edit Mode.
- Creates a length from one selected edge, a live angle from any two non-parallel edges, and a live face-area leader with explicit label placement.
- Keeps vertex dimensions associated with base-mesh vertices and falls back to their last known position if topology removes the original point.
- Creates saved finite measurements and infinite construction guides.
- Snaps to vertices, edges, midpoints, face centers, face points, guides, and measurement endpoints/midpoints/segments.
- Accepts typed values such as `125mm`, `2ft`, or `5"`, with `A`, `X`, `Y`, and `Z` constraints.
- Formats metric and imperial values and can show selected-mesh dimensions and evaluated volume in a viewport HUD.
- Supports true and global-axis projected distances, angle radius/reflex controls, value prefixes/suffixes, and linear tolerances.

## Install

Build the extension archive from the repository root. The build script stages the extension and required GPL license text before invoking Blender:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_extension.ps1
```

In Blender, choose **Edit > Preferences > Add-ons > Install from Disk**, select the generated ZIP, and enable **Dimensions**. The add-on does not change Blender's global mesh-editing or Auto Merge settings.

## Use

Open the 3D Viewport sidebar with `N`, then choose the **Dimensions** tab.

1. Choose **Create Dimension**, **Create Angle Dimension**, or **Measure** in Object or Mesh Edit Mode. Construction guides remain an Object Mode tool; selection-based length, angle, and area actions are available in Mesh Edit Mode.
2. Click a highlighted start point, then point toward the next point.
3. Optionally press `A`, `X`, `Y`, or `Z`, or drag middle mouse after the first point to choose a global axis.
4. Optionally type a scene-unit distance and press `Enter`; click also commits a valid stage.

**Create Area Dimension** works in both modes. In Edit Mode, select faces first and run the tool, then place the label. In Object Mode, click a base-mesh face, then place the label; Shift-click builds a multi-face source and `Enter` proceeds to placement. During creation or **Move Label**, press `A`, `X`, `Y`, or `Z` and optionally type a scene-unit distance. A selected Area also exposes **Remake Area**, **Select Source Faces**, and **Capture**.

**Create Angle Dimension** acquires Edge A and Edge B, then places the arc radius. The edges may be connected, intersecting only when extended, or skew in 3D. Connected edges use their shared vertex; other edges derive a virtual center from their supporting lines. A selected Angle can switch between Minor, Supplement, and Reflex solutions or replace either source edge independently.

Linear and Area annotation Empties are placement objects. Moving one with Blender's normal transform controls moves its presentation while its source anchors remain attached. Later source geometry or object transforms preserve that user placement offset.

`Esc` clears numeric input before stepping back or exiting. Right-click cancels one-shot annotation tools.

Dimensions and guides are normal scene objects in dedicated `Dimensions` and `Construction Guides` collections. Select a dimension to edit its anchors, placement, text, visibility, and local style in the sidebar.

## Current limitations

- Construction guide creation remains an Object Mode workflow; dimensions and measurements work in Object and Mesh Edit Mode.
- Vertex anchors use persistent mesh point IDs. If topology removes an anchored point or duplicates its ID, resolution uses the closest stored position without showing a detached state. Surface anchors follow object transforms but not later deformation.
- Live Area annotations currently bind base-mesh faces from one mesh object. Modifier-evaluated and multi-object area aggregation are not yet supported; topology that removes or ambiguously duplicates a bound face produces a visible Needs Repair state.
- Object Mode projected-vertex snapping uses a per-viewport spatial cache and rejects occluded candidates with ray checks. Cache rebuilds after geometry, transform, or view changes can still be noticeable on very dense scenes.
- Dimensions are viewport overlays and do not appear in final renders.
- A full annotation/guide manager, local-axis and parallel/perpendicular inference, guide planes, and custom keymaps are not yet implemented.

See [Design and Roadmap](docs/DESIGN.md) for architecture, invariants, known risks, and prioritized next work. The [Dimension and Measurement Tools Improvement Plan](docs/DIMENSION_TOOLS_PLAN.md) defines the Area and Angle redesign plus the path toward a fuller documentation toolset. Detailed interaction planning remains in [Interaction Toolkit Plan](docs/INTERACTION_TOOLKIT_PLAN.md) and [Measure and Construction Guides](docs/MEASURE_GUIDES_PLAN.md).

## Development

Run the complete local release check from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate.ps1
```

The reduced suite covers registration, units, volume, collection isolation, persistent anchor identity, constrained live Areas, persistent connected/disconnected/skew edge angles, source-preserving annotation transforms, projected distances, cached and depth-aware snapping, viewport state isolation, and measurement proxy save/reload repair. Foreground modal behavior, append/link workflows, undo/redo, package installation through the UI, and large-scene performance still require release QA. The declared and tested compatibility target is the latest Blender 5.1 release; older Blender versions are not supported.

The same validation runs in GitHub Actions against Blender 5.1.2. Update the workflow's pinned patch release when adopting a newer Blender 5.1 build.
