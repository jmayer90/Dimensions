# Dimensions

Dimensions is an experimental Blender 4.2+ extension for precise viewport modeling and annotation. It provides persistent dimensions, saved measurements, construction guides, and an Edit Mode mesh-line tool with shared snapping, axis constraints, and scene-unit input.

## What it does

- Creates editable dimensions between vertices, object-local surface points, guides, measurements, or world points.
- Keeps vertex dimensions associated with base-mesh vertices and visibly warns when a reference detaches.
- Creates saved finite measurements and infinite construction guides.
- Draws chained Edit Mode mesh lines, including supported single-face cuts and simple closed faces.
- Snaps to vertices, edges, midpoints, face centers, face points, guides, and measurement endpoints/midpoints/segments.
- Accepts typed values such as `125mm`, `2ft`, or `5"`, with `A`, `X`, `Y`, and `Z` constraints.
- Formats metric and imperial values and can show selected-mesh dimensions and evaluated volume in a viewport HUD.

## Install

Build the extension archive from the repository root:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --command extension build --source-dir dimensions
```

In Blender, choose **Edit > Preferences > Add-ons > Install from Disk**, select the generated ZIP, and enable **Dimensions**. The add-on does not change Blender's global mesh-editing or Auto Merge settings.

## Use

Open the 3D Viewport sidebar with `N`, then choose the **Dimensions** tab. The same tools are also available in the left toolbar.

1. Choose **Create Dimension**, **Measure**, or **Add Construction Guide** in Object Mode, or **Draw Mesh Line** in Edit Mode.
2. Click a highlighted start point, then point toward the next point.
3. Optionally press `A`, `X`, `Y`, or `Z`, or drag middle mouse after the first point to choose a global axis.
4. Optionally type a scene-unit distance and press `Enter`; click also commits a valid stage.

`Esc` clears numeric input before stepping back or exiting. Right-click cancels one-shot annotation tools; for Draw Mesh Line it finishes the chain and preserves committed geometry.

Dimensions and guides are normal scene objects in dedicated `Dimensions` and `Construction Guides` collections. Select a dimension to edit its anchors, placement, text, visibility, and local style in the sidebar.

## Current limitations

- Dimension and guide creation is an Object Mode workflow; Draw Mesh Line is an Edit Mode workflow.
- Vertex anchors use base-mesh indices, so topology changes can detach or silently retarget them. Surface anchors follow object transforms but not later deformation.
- Object Mode projected-vertex fallback is not depth-filtered and can become slow on dense scenes.
- Dimensions are viewport overlays and do not appear in final renders.
- Draw Mesh Line supports deliberate single-face and simple coplanar-loop cases; it is not a volumetric bisect or general multi-face knife.
- A full annotation/guide manager, local-axis and parallel/perpendicular inference, guide planes, and custom keymaps are not yet implemented.

See [Design and Roadmap](docs/DESIGN.md) for architecture, invariants, known risks, and prioritized next work. Detailed interaction history remains in [Interaction Toolkit Plan](docs/INTERACTION_TOOLKIT_PLAN.md), [Measure and Construction Guides](docs/MEASURE_GUIDES_PLAN.md), and [SketchUp Workflow Evaluation](docs/SKETCHUP_WORKFLOW_EVALUATION.md).

## Development

Run the Blender smoke suite and manifest validation from the repository root:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --factory-startup --python tests\blender_smoke.py
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --factory-startup --command extension validate dimensions
```

The current suite covers registration, units, volume, collection isolation, anchor behavior, snapping, measurement proxies, and supported mesh-line topology. Foreground viewport behavior, package installation, save/reload, undo granularity, and large-scene performance still require release QA.
