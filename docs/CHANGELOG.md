# Changelog

## 0.2.3 — July 30, 2026

- Fixed installation on Blender 5.2 by removing the exclusive `blender_version_max = "5.2.0"` compatibility ceiling.
- Added Blender 5.2.0 to CI while retaining Blender 5.1.2 coverage.
- Added a smoke regression that verifies the running Blender version is inside the extension manifest's declared compatibility range.

## 0.2.2 — July 17, 2026

- Added marketplace metadata for the official `3D View` category, identified Cynic Wild as the maintainer, and intentionally omitted a manifest website.
- Restricted declared compatibility to the tested Blender 5.1.x release line.
- Moved package exclusions into the manifest's documented `[build]` section.
- Made the release build self-validating and added checks for required documentation, licensing, and excluded Python cache files.
- Made validation use Blender's bundled Python interpreter instead of requiring a separate Python installation on `PATH`.
- Added a Blender Extensions publishing checklist and made CI retain the validated submission archive as a downloadable artifact.

## 0.2.1 — July 15, 2026

- Documented the next placement revision: user-editable annotation transforms, axis/distance Area placement, and persistent two-edge Angle sources with connected, intersecting, and skew-edge behavior.
- Replaced Angle's misleading linear anchor-eyedropper editor with a dedicated Remake Angle action that reruns the complete vertex, ray, ray, and radius workflow.
- Added a dedicated Create Area Dimension tool in Object and Mesh Edit Mode.
- Added explicit Area label placement during creation instead of committing an automatic label position.
- Added Move Label and Remake Area actions without changing or exposing raw measurement anchors.
- Kept Select Source Faces and added an Apply Faces to Selected Area step for selection-based replacement.
- Added single-face and Shift-click multi-face acquisition in Object Mode; Edit Mode uses the current selected faces.
- Made live Area overlay evaluation read bound geometry during drawing so the value and leader origin update while geometry changes.
- Added Object Mode Area-binding regression coverage and increased the Blender smoke suite to 32 tests.
- Made annotation Empty translation a persistent presentation control instead of overwriting it during scene synchronization.
- Preserved Linear and Area placement offsets when source geometry or owning-object transforms change.
- Added `A`, `X`, `Y`, and `Z` constraints plus typed scene-unit distances to Area creation and Move Label.
- Kept constrained Area label direction and distance stable as live source geometry changes.
- Replaced vertex-plus-two-rays Angle acquisition with two persistent edge sources.
- Added connected, intersecting-disconnected, and skew 3D edge handling with shared or virtual arc centers.
- Added Minor, Supplement, and Reflex angle solutions.
- Added independent Replace Edge A and Replace Edge B actions while retaining Remake Angle.
- Expanded the Blender smoke suite to 36 tests covering dynamic two-edge angles, disconnected/skew geometry, Area constraints, and transform-offset preservation.


## 0.2.0 — July 15, 2026

- Replaced captured-only Area notes with live base-mesh face-set bindings using persistent face IDs and automatic world-space recalculation.
- Added explicit Live, Captured, and Needs Repair states; legacy Areas migrate to Captured, while missing or ambiguous live sources remain visibly repairable.
- Added source-face selection, rebind-from-selection, and capture-value actions for Area annotations.
- Replaced Angle's screen-space approximation with a projected world-space arc and added editable radius plus minor/reflex display.
- Added an interactive three-point Angle tool for Object and Mesh Edit Mode and exposed start, vertex, and end anchor editing.
- Added true and global X/Y/Z projected linear distance modes.
- Added per-annotation value prefixes, suffixes, symmetric plus/minus tolerance, and independent upper/lower deviations.
- Expanded Blender smoke coverage for live Area updates and invalidation, world-space minor/reflex Angle geometry, and projected distances.

## 0.1.9 — July 15, 2026

- Documented the Area and Angle redesign: live face-set bindings, explicit captured/repair states, world-space angle arcs, editable placement, interactive creation, and a phased expansion of the measurement toolset.
- Extracted the in-progress Smart Knife work out of the live `Dimensions` add-on into a separate root-level folder for future add-on development.
- Removed the live Smart Knife registration and returned the product/docs scope to dimensions, measurements, construction guides, and shared snapping only.
- Removed left-toolbar custom tool registration so commands remain available only from the right-side Dimensions panel.

## 0.1.8 — July 15, 2026

- Promoted validated open paths across multiple connected faces instead of requiring the complete stroke to belong to one face.
- Converted geometric crossings with prior surface edges into shared vertices even when the user did not click the intersection.
- Validated multi-face cuts on a BMesh copy before commit so invalid paths add no intermediate crossing splits or partially divided faces and preserve the accepted wire geometry.
- Added regressions for automatic divider crossings, linked-face validity, and non-destructive rejection of floating multi-face paths.
- Documented Blender's face-loop validity rules and the validate-then-commit multi-face cut design needed for lines that cross earlier subdivisions.
- Fixed repeated cuts when stale loose vertices from an earlier failed attempt occupy the same coordinates as a valid face-boundary vertex.
- Start-point binding now checks and splits the real surface edge before considering coincident loose topology.
- Coordinate lookup now prefers vertices owned by faces over wire or isolated vertices.
- Extended the triangle-surrounding regression with deliberately duplicated loose endpoint vertices.

## 0.1.7 — July 15, 2026

- Fixed the 0.1.6 surface-projection regression that could bind an inference point on a silhouette or shared edge to an adjacent side face.
- The actual cursor now chooses the working face, while the measurement or guide marker is projected onto that specific face for precise alignment.
- Added regressions for sequential paths that reuse the outer boundary and for face-aware external-inference projection.

## 0.1.6 — July 15, 2026

- Made the main Create Dimension command immediately create a linear dimension from one selected Edit Mode edge; without exactly one selected edge it continues into interactive point picking.
- Changed Draw Mesh Line inference from measurements, guides, and other external targets to project onto the visible active edit surface, preserving the snap alignment without creating off-surface loose geometry.
- Added an explicit warning when a session ends with a path that cannot bound a face.
- Added regression coverage for external measurement-to-surface projection and the selection-first main Dimension command.
- Added a prioritized MeasureIt_ARCH feature evaluation covering live areas, dimension styles, bounds/arc dimensions, annotations, view controls, vector output, line groups, and later documentation workflows.

## 0.1.5 — July 15, 2026

- Fixed Draw Mesh Line paths whose endpoints visually land on earlier cut edges but are reported by Blender's raycast as face hits.
- Geometrically exact surface-edge hits now split and bind to the existing edge instead of creating overlapping loose vertices and lines.
- Added a screenshot-shaped regression that first cuts a triangular face and then creates a surrounding face between the midpoints of the triangle's side edges.

## 0.1.4 — July 15, 2026

- Removed detached and ambiguous anchor warnings; missing or duplicated vertex identity now resolves silently from the stored fallback position.
- Enabled interactive dimension and measurement tools in Mesh Edit Mode as well as Object Mode.
- Added selection-driven length dimensions from one edge, angle dimensions from two connected edges, and combined-area leader annotations from selected faces.
- Kept area formatting consistent with scene units and object transforms; area annotations store the measured value at creation time.
- Hardened Draw Mesh Line junction behavior and added a regression for a new face cut terminating in the middle of an earlier cut.
- Extended scene synchronization, hit testing, local styling, tool registration, and smoke coverage for the new annotation types.

## 0.1.3 — July 15, 2026

- Added persistent mesh point IDs for vertex anchors, including legacy migration and explicit ambiguous-binding warnings.
- Replaced repeated all-vertex projection with a per-viewport spatial cache and ray-based occlusion rejection.
- Scoped modal preview state to its owning viewport so separate windows and editors cannot overwrite one another.
- Preserved face, loop, vertex, UV, and other BMesh custom data when closed surface cuts reconstruct topology, and deferred source-face removal until validation succeeds.
- Added transactional add-on registration rollback and extracted dimension geometry, scene synchronization, projected snapping, viewport state, and mesh-attribute handling into focused modules.
- Added save/reload proxy lifecycle checks and regressions for persistent anchors, occlusion, viewport isolation, and UV preservation.
- Narrowed declared compatibility to the tested Blender 5.1 release.
- Added repeatable build and validation scripts plus Blender 5.1 CI; release archives now include the GPL license text.

## 0.1.2 — July 15, 2026

- Stopped changing Blender's scene-wide Auto Merge and split settings during add-on registration.
- Excluded hidden Edit Mode geometry and internal native-snap proxy meshes from add-on snap targets.
- Made annotation visibility, color, and unit-format changes redraw every open 3D View consistently.
- Kept viewport active-object state consistent when Shift-click deselects an annotation.
- Removed unused workflow state, constants, and helpers; clarified the manifest description.
- Reworked the README and added a consolidated design, risk, release, and precision-modeling roadmap.
