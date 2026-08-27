# Changelog

All notable user-visible changes are recorded here. Versions before 0.2.0 were rapid pre-release iteration and are summarized rather than listed individually.

## 0.4.0 — August 27, 2026

- Added explicit Grease Pencil generation for selected or all visible linear dimensions. Generated output contains dimension and extension lines, open arrows or architectural ticks, vector-stroke labels, prefixes, suffixes, tolerances, custom text, and per-annotation color. Labels preserve Inline, Above, and Outside placement plus custom-text ordering.
- Added Camera Relative sizing, which resolves line, label, and endpoint sizes from render pixels at each annotation's midpoint depth, plus view-independent World Scale sizing with separate scene-unit controls. Camera Relative is the default and requires an active camera.
- Generated artifacts live in an exclusive scene-owned `Dimensions Output` collection, remain separate from live annotations, and regenerate predictably through a scene-owned source registry. Name collisions do not repurpose user collections, duplicated annotations receive independent identities, and generation does not write metadata to annotation objects. Regeneration is intentionally disposable and replaces hand edits to matching generated objects; the Output panel warns before use.
- Verified non-empty generated strokes in both EEVEE and Cycles on Blender 5.2. Repeated local runs generated 100 labeled linear annotations in under 0.4 seconds.
- This is a minor release because renderable output is a new product surface under version-policy trigger 3. Angle and area generation remain follow-up work.
- Added the schema v1 to v2 migration for the new output settings and scene-owned source registry; existing `.blend` files keep their saved values, receive defaults only when a field is absent, and discard incomplete registry bindings.
- Reorganized roadmap documentation around explicit Complete, Partial, Next, Planned, and Blocked states, with a milestone rollup, delivery sequence, and matching status headers on every work ticket.

## 0.3.2 — August 26, 2026

- Added an **Architectural Tick** endpoint style for linear dimensions, configurable globally for new annotations and as a local per-annotation override. Existing and new files continue to use open arrows by default.

## 0.3.1 — August 26, 2026

- Added continuous placement, on by default, to linear dimension, angle, area, measurement, and construction-guide tools. Each committed annotation is its own undo step; `Esc` or right-click exits the session, and changing mode or active object ends it without leaving preview state behind.
- Added a configurable default Auto/X/Y/Z session axis. The axis can be chosen before the first point, persists across repeated placements, and can be changed between annotations without leaving the tool.
- Clarified that Text Size and Arrow Size are fixed viewport-pixel sizes and added regression coverage across view projection, source and parent transforms, annotation transforms, and selected/unselected drawing.
- Expanded the Blender background suites to 61 smoke and 28 modal-interaction tests.

## 0.3.0 — August 15, 2026

- Added POSIX build and validation scripts for Linux and macOS, alongside the existing PowerShell workflow.
- Added scene-level schema versioning and load-time migration for legacy persistent vertex anchors.
- Replaced the always-running viewport selection modal with the explicit **Dimensions Selection** toolbar tool.
- Added per-user add-on preferences for interaction target sizes and defaults for new annotation presentation.
- Changed the default annotation color for dimensions and measurements to opaque white, which reads more clearly against Blender's default theme than the previous blue; the selected color is now an amber highlight so selection stays distinguishable. Existing annotations keep their stored colors.
- Added removable, customizable add-on keymap entries for Dimensions creation tools.
- Cleared transient viewport and snap caches after undo and redo, and made linked annotations read-only in the local editor.
- Made annotation and guide drawing iterate their scene-owned collections instead of every object in the scene.
- Cached projected dimension geometry per viewport/view and invalidate it on source, style, undo, and redo changes.
- Registered the shared axis and confirm modal actions so compatible Dimensions tools honor customized modal bindings.
- Centralized all operator status messages, using actionable warnings for recoverable input and reserving errors for unexpected failures.
- Added pure point-placement state coverage for the shared cancel and step-back interaction contract, plus named lifecycle tests for persistent measurement proxies.
- Added opt-in dense-scene snap profiling and a deterministic reference-scene generator; pure view changes now reuse world-space snap sources instead of rebuilding them.
- Fixed the add-on failing to enable at all: registration read `bpy.data.scenes` while Blender still restricts it, so enabling Dimensions raised `AttributeError` and rolled the whole registration back. Scenes already open when the add-on is enabled are now migrated on the next event loop tick.
- Fixed add-on preferences never taking effect once installed as an extension. Preferences were looked up under `bl_ext` rather than the full package name, so every configured value silently fell back to its default.
- Fixed picking the same point twice for a linear dimension refusing the stage without saying why; it now reports that a different end point is required.
- Batched annotation drawing by color and line width, so the usual selected/unselected split costs about two GPU batches regardless of annotation count. Label layout and font metrics are cached instead of recomputed every frame.
- Bounded the annotation geometry cache to one entry per viewport. Orbiting previously added a cache entry per annotation per frame and never released them.
- Made modal keys genuinely rebindable: the `Dimensions Modal` action map is read through the user key configuration on every event, and the preferences Keymap section now shows editable key rows instead of read-only properties.
- Measured and documented draw and snapping performance in `docs/DESIGN.md`. Overlay draw cost is now independent of scene size (0.310 ms/frame with 10,000 non-annotation objects versus 0.312 ms/frame with 10), and the 500-dimension budget is met at 58 fps worst case. Snap queries run at 0.013 ms against an 8 ms budget; the 1M-vertex cache build misses its budget and is tracked as `FND-11`.
- Expanded the test suites from 47 to 93 tests: 59 in `blender_smoke.py` (draw caching and batching, keymap registration and collision, and extension-packaging regressions), 25 in the new `blender_modal.py` (pick-pick-place, axis locks before and after each point, typed distance around an axis choice, invalid input, escape and step-back from every stage, and cancellation leaving no objects behind), and 9 in `blender_lifecycle.py` (now including migration of a released-file fixture).

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
