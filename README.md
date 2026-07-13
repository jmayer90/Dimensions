# Dimensions

Blender 4.2+ extension scaffold for persistent, vertex-linked dimensions that can attach to base-mesh vertices across different objects.

## Current Scope

This repo starts with the reduced MVP:

- Persistent dimension data stored on one Empty per dimension.
- A dedicated `Dimensions` collection.
- Object Mode only.
- `Aligned`, `X`, `Y`, and `Z` display modes.
- Sidebar-based management first.
- A first-pass viewport click-selection mode for drawn dimensions.

The corner-overlay idea from `itzg/blender-woodworking-addon` will be treated as a separate HUD-style subsystem later, not as the primary dimension system.

## Repo Layout

```text
dimensions/
├── blender_manifest.toml
├── __init__.py
├── anchors.py
├── collections.py
├── constants.py
├── drawing.py
├── properties.py
├── snapping.py
├── ui.py
├── units.py
└── operators/
    ├── __init__.py
    ├── click_select.py
    ├── create_dimension.py
    └── reattach_anchor.py
```

## First Milestone

The current scaffold includes:

- Installable Blender extension package structure.
- Sidebar panel in the 3D Viewport.
- Dimension creation from Object Mode vertex picks.
- Axis-aware dimension display with `Aligned`, `X`, `Y`, and `Z` modes.
- Reattach operators for both anchors.
- A selected-object overlay for `Length / Width / Thickness`.
- Initial viewport click-selection mode for drawn dimensions.

## Installing During Development

This repository keeps the Blender extension inside the `dimensions` folder. For Blender installation, package the contents of that folder as the extension payload.
