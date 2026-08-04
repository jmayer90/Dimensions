# Changelog

All notable user-visible changes are recorded here. Versions before 0.2.0 were rapid pre-release iteration and are summarized rather than listed individually.

## 0.2.3 — July 30, 2026

- Fixed installation on Blender 5.2 by removing the `blender_version_max = "5.2.0"` compatibility ceiling.
- Added Blender 5.2.0 to CI alongside the existing Blender 5.1.2 coverage.
- Added a regression check that the running Blender version falls inside the manifest's declared compatibility range.

## 0.2.2 — July 17, 2026

- Added marketplace metadata for the `3D View` category and identified Cynic Wild as the maintainer.
- Moved package exclusions into the manifest's `[build]` section.
- Made the release build self-validating, with checks for required documentation, licensing, and excluded Python cache files.
- Made validation use Blender's bundled Python interpreter instead of requiring a separate Python installation on `PATH`.
- Made CI retain the validated submission archive as a downloadable artifact.

## 0.2.1 — July 15, 2026

**Angle dimensions** were rebuilt around two persistent edge sources instead of a vertex and two rays:

- Added connected, intersecting-disconnected, and skew 3D edge handling with shared or virtual arc centers.
- Added Minor, Supplement, and Reflex angle solutions.
- Added independent Replace Edge A and Replace Edge B actions, plus a Remake Angle action replacing the previous linear anchor-eyedropper editor.

**Area dimensions** gained a dedicated tool and explicit label placement:

- Added Create Area Dimension in Object and Mesh Edit Mode, with single-face and Shift-click multi-face acquisition in Object Mode.
- Added explicit label placement during creation instead of committing an automatic position, plus Move Label and Remake Area actions.
- Added Apply Faces to Selected Area for selection-based replacement, alongside the existing Select Source Faces.
- Made live area evaluation read bound geometry during drawing, so the value and leader origin update as geometry changes.
- Added `A`, `X`, `Y`, and `Z` constraints and typed scene-unit distances to area creation and Move Label, and kept the constrained direction and distance stable as sources change.

**Placement** became a persistent, user-facing control:

- Made annotation Empty translation a presentation control instead of overwriting it during scene synchronization.
- Preserved linear and area placement offsets when source geometry or owning-object transforms change.

## 0.2.0 — July 15, 2026

- Replaced captured-only area notes with live base-mesh face-set bindings using persistent face IDs and automatic world-space recalculation.
- Added explicit Live, Captured, and Needs Repair states. Legacy areas migrate to Captured; missing or ambiguous live sources stay visibly repairable.
- Added source-face selection, rebind-from-selection, and capture-value actions for area annotations.
- Replaced the screen-space angle approximation with a projected world-space arc, and added editable radius plus minor/reflex display.
- Added an interactive three-point angle tool for Object and Mesh Edit Mode, exposing start, vertex, and end anchor editing.
- Added true and global X/Y/Z projected linear distance modes.
- Added per-annotation value prefixes, suffixes, symmetric tolerance, and independent upper/lower deviations.

## 0.1.x — July 2026

Pre-release iteration. The significant outcomes carried into 0.2.0:

- **Scope was settled.** An in-progress mesh-cutting experiment (Smart Knife / Draw Mesh Line) was removed from the add-on, fixing the product on annotation only: dimensions, measurements, construction guides, and shared snapping. Geometry authoring was ruled out as a separate project.
- **Persistent anchors.** Vertex anchors moved to persistent mesh point IDs with legacy migration, so dimensions survive topology edits and fall back to a stored position when their point disappears.
- **Snapping performance.** Repeated all-vertex projection was replaced with a per-viewport spatial cache and ray-based occlusion rejection.
- **Viewport isolation.** Modal preview state was scoped to its owning viewport, so separate windows and editors no longer overwrite one another.
- **No global preference mutation.** The add-on stopped changing Blender's scene-wide Auto Merge and split settings during registration.
- **Edit Mode support.** Interactive dimension and measurement tools became available in Mesh Edit Mode, including selection-driven lengths, angles, and area leaders.
- **Release engineering.** Transactional registration rollback, focused modules for geometry, scene sync, projected snapping, and viewport state, repeatable build and validation scripts, Blender CI, and GPL license text in release archives.
