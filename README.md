# CAD Dimensions

Blender 4.2+ extension scaffold for persistent, CAD-style dimensions that can attach to base-mesh vertices across different objects.

## Current Scope

This repo starts with the reduced MVP:

- Persistent dimension data stored on one Empty per dimension.
- A dedicated `CAD Dimensions` collection.
- Object Mode only.
- Aligned dimensions first.
- Sidebar-based management first.
- No in-viewport dimension picking in the initial release.

The corner-overlay idea from `itzg/blender-woodworking-addon` will be treated as a separate HUD-style subsystem later, not as the primary dimension system.

## Repo Layout

```text
cad_dimensions/
├── blender_manifest.toml
├── __init__.py
├── collections.py
├── constants.py
├── properties.py
├── ui.py
└── operators/
    ├── __init__.py
    └── add_test_dimension.py
```

## First Milestone

The current scaffold targets Stage 0 plus the beginning of Stage 1:

- Installable Blender extension package structure.
- Sidebar panel in the 3D Viewport.
- Test operator that creates a selectable Empty in the `CAD Dimensions` collection.
- Initial property groups for dimension and anchor data.

## Installing During Development

This repository keeps the Blender extension inside the `cad_dimensions` folder. For Blender installation, package the contents of that folder as the extension payload.
