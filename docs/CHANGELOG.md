# Changelog

All notable user-visible changes are recorded here. Versions before 0.2.0 were rapid pre-release iteration and are summarized rather than listed individually.

## 0.6.0 — Unreleased

- Added an optional single-sheet drawing layout to scale-correct SVG and PDF export. A physical-mm border and fixed lower-right vector title block carry drawing title, number, revision, author, date, and the current 1:N scale without changing camera projection or annotation styling. Border and title block can be enabled independently; invalid margins, undersized blocks, and overflowing metadata are refused before a file is written. The default block accommodates the full supported `1:100000` scale denominator and common metadata without shrinking physical text. Scene-owned schema v15 settings preserve the furniture-free 0.5 behavior by default and migrate from an immutable released 0.5.0/schema-v14 fixture. Blender 5.1.2 exported 100 labeled annotations plus sheet furniture in 0.092 seconds.

- This is a minor release because producing an identified drawing sheet is a new product surface under versioning trigger 3. The first slice remains one page with a fixed layout; multi-sheet documents, arbitrary templates, DXF, selectable text, schedules, and model geometry authoring remain out of scope.

## 0.5.0 — August 29, 2026

- Added source-following Angular Guides with typed degree/radian entry, live line/angle preview, `F` direction flip, and editable angles around an anchored pivot, plus one-object repeated-spacing guide sets in interval/count, interval/extent, and evenly-distributed modes. Repeated lines draw and snap individually without materialized objects, remain one manager entry, and can be baked into equivalent fixed guides. Schema v14 adds the definitions after guide-plane schema v13; existing guides remain unchanged.

- Hardened the 0.5 construction and datum surfaces during Blender 5.1.2 release validation. Active-plane X/Y/Z now resolve consistently across dimensions, Areas, guides, measurements, inference, typed input, and direct label placement; plane snapping uses the visible square extent rather than a circular approximation; lost angular/spacing anchors truthfully enter Needs Repair; evenly distributed sets no longer rewrite their persisted extent while drawing; fresh annotation locators initialize on canonical geometry before capturing user translation; relative elevations preserve the least-authoritative dependency state; and zero-decimal elevation labels remain zero-decimal. A deterministic 200-line spacing benchmark now gates release validation, measuring 0.125 ms draw preparation and 2.287 ms guide snapping on the release host.

- Added persistent bounded guide planes defined by three anchored points, a point plus normal, a persistent base-mesh face, or an offset from another guide plane. Planes follow their sources, expose a dedicated snap target and manager row, keep grid extent presentation-only, refuse degenerate/cyclic definitions, and show a red Needs Repair grid when a source is lost. One saved plane, captured face, or World XY/YZ/ZX plane can be active; free acquisition lands on it, X/Y/Z become its two in-plane axes and normal, typed distances use the same frame, and a prominent amber grid identifies the state. Clearing restores view-derived placement and world axes exactly. Schema v13 adds the plane definitions and scene active-plane state.

- This is a minor release because an active construction plane deliberately changes the documented meaning of X/Y/Z while active, triggering the interaction-contract rule. It does not freeze the schema or claim 1.0 compatibility.

## 0.4.3 — Unreleased

- Defined annotation Empty transforms as translation-only: moving an annotation records a world-space presentation offset, while Rotation and Scale are locked for normal editing and ignored consistently by live drawing, Grease Pencil, SVG, and PDF. Existing scripted or legacy non-identity values are retained without changing appearance but never alter source geometry, measurement values, orientation, or sizing. This uses the existing canonical-frame/offset model and requires no schema change.

- Defined conservative evaluated-modifier semantics for live Areas without adding saved data. Base-mesh persistent face IDs remain the binding source; viewport-evaluated faces are used only when every bound ID propagates exactly once with the same vertex count. Topology-preserving deformation can remain Live, while dropped, duplicated, or structurally changed evaluated identities retain the base numeric value as **Fallback — Modifier Faces Unresolved** and are withheld from Grease Pencil, SVG, and PDF output. No face-index or proximity correspondence is guessed, removing the modifier restores Live state automatically, and existing unmodified/base-mesh Areas are unchanged.

- Added named oriented datums by promoting the existing anchored Guide Point model, plus Coordinate dimensions with X/Y/XY/XYZ components, row/column alignment, and configurable sign conventions, and Elevation dimensions with selectable up axis, absolute/relative modes, conventional level symbols, and independent fixed-decimal/sign formatting. Multiple datums update their dependents live; lost point or datum sources enter guided repair state; valid annotations share the Grease Pencil, SVG, and PDF output paths. Schema v12 stores the additive bindings and presentation settings while existing guide points remain ordinary points.

- Added persistent radial, diameter, and arc-length dimensions from selected mesh vertices, edge loops, or face sets in Object and Mesh Edit Mode. One arbitrary-plane least-squares binding supports fitted, inscribed/across-flats, and circumscribed/across-corners values; open chains retain their arc sweep, labels use `R`, `⌀`, or `⌒` with resolved prefix/suffix/tolerance styling, and a direct label handle controls the leader. Relative RMS fit error above the configurable threshold enters a visible non-authoritative Fallback state, cannot be captured, and is withheld from Grease Pencil, SVG, and PDF output. Persistent point IDs, live updates, manager/repair integration, lifecycle reload coverage, and the additive schema-v10 migration complete DIM-02 without modifying mesh geometry.
- Added persistent offset and centerline guides derived from mesh edges, existing guides, or base-mesh face planes. Offset placement uses the shared unit parser, live mouse-selected side/distance preview, and rebindable `F` flip action; centerlines validate two parallel sources before commit. Relationships follow source transforms and persistent topology identities, support chained guide derivation, refuse cycles, remain native guide snap targets, and detach to an equivalent fixed line in one undoable action. Missing sources enter Needs Repair and draw their last resolved line as a red dashed fallback until the manager-guided source picker repairs them.
- Advanced the saved-data schema from v10 to v11 with additive derived-guide source descriptors, offset/side/direction state, and last-resolved fallback presentation. The migration leaves every existing guide fixed and Live, preserves DIM-02's v9 → v10 step unchanged, and is covered through the released schema-v2 fixture.
- Completed drafting presentation controls with style-owned extension gaps and overshoot; independent Filled Arrow, Open Arrow, Architectural Tick, Dot, or None marks at each end; primary plus secondary unit formats with independent precision and bracket, parenthesis, or stacked arrangement; and aligned/horizontal plus Above/Broken label modes. Tight labels now move consistently to the end side with a leader. The live overlay, Grease Pencil, SVG, and PDF paths share the resolved controls, while schema v9 migrates existing files to explicit appearance-preserving values. The 500-annotation benchmark remains within budget at 28.717 ms rebuilding (35 fps) and 5.000 ms cached (200 fps).
- Added persistent Chain and Baseline dimension sets. One scene object owns the shared alignment, offset, spacing rule, style, and independently repairable member anchors; creation commits each member separately for undo. Chain insert/delete closes and reflows the run, baseline rows derive collision-safe spacing from label size or accept an explicit pitch, and short chain labels alternate outside crowded segments. Sets expand to member rows in the Annotation Manager, survive save/reload, and generate through Grease Pencil, SVG, and PDF output.
- Added persistent guide points in the scene-owned Construction Guides collection. Points can be placed directly through shared snapping/inference, offset from a reference with typed distance and axis constraints, or created at an object/mesh-selection centroid. Vertex, surface, and world anchors reuse the established resolution model; a one-vertex native snap proxy and a dedicated Guide Point snap toggle make them available to every acquisition tool without leaking proxy vertices through the normal mesh target. A constant-pixel square-and-cross marker, Annotation Manager support, manual reattachment for fallback sources, and Clear Guides integration complete the workflow.
- Advanced the saved-data schema additively from v7 to v8 for the scene Guide Point snap and manager-filter defaults. The idempotent migration preserves DIM-01's v6 → v7 step exactly, and the released schema-v2 fixture verifies the complete path to v8.
- Added selected-only direct viewport presentation handles: a fixed-pixel purple diamond adjusts linear offset, a circle adjusts angle radius, and a square moves an area label. Handles win hit testing over annotation bodies and reuse the creation contract for `A`/`X`/`Y`/`Z`, typed scene-unit distance, click/`Enter`, and `Esc`; confirmation is one undo step and cancellation leaves the saved value unchanged. Existing area-label and angle-radius workflows share the same mutation helpers, while linked annotations remain read-only and expose no handles.
- Made **Measure** a transient, per-viewport tape-measure workflow. It acquires through the same snap, inference, typed-distance, and axis paths as saved measurement; displays total distance and signed ΔX/ΔY/ΔZ in configured scene units; and chains each accepted endpoint into the next segment without creating Blender data. Rebindable `P` saves the current segment through the established persistent measurement/proxy path, while rebindable `Ctrl+C` copies the same formatted values without intercepting typed `cm` input. **Measure (Persistent)** remains available through Search and as an unbound add-on keymap entry for direct save-on-confirm use.
- This remains a patch release: the new schemas and presentation fields are additive, existing appearance and bindings are migrated explicitly, and no documented operator or interaction surface is removed.

## 0.4.2 — Unreleased

- Added guided repair for broken or fallback linear, angle, and area bindings. Persistent anchors now distinguish unique-ID, stored-fallback, and unresolvable states; fallback values keep their established numeric behavior but are visibly labeled in the overlay and manager. Repair explains and highlights the lost source, previews a nearest vertex or face candidate, supports explicit accept, normal manual picking, convert-to-world for lost point sources, and cause-scoped bulk repair. Repairs preserve presentation, are single-step undo operations, and refuse linked annotations.
- Added transient drafting inference to Dimension, Measure, and Guide point acquisition: parallel, perpendicular, edge/guide extension, supporting-line intersection, active-face plane, and rotated-object local-axis candidates. Recent eligible hover supplies the implicit reference; rebindable `L` freezes and releases it, while repeated axis presses cycle global → local → global. Distinct orange/blue glyphs and the compact status badge identify candidates, each type can be disabled in preferences, and existing geometry retains priority within a 2 px comparable-distance band. Inference respects the relevant snap-target controls and never authors mesh geometry or persistent constraints.
- Added the Annotation Manager sidebar list for dimensions, measurements, and guides. It shows current values and repair state, searches names, combines kind/state/source-reference filters, synchronizes selection, and provides row rename, visibility, frame, delete, and repair-source actions. Filtered or selected bulk scopes support show, hide, exact-state isolate/restore, delete, named-style assignment, and reset-to-global in one undoable operation. The cached registry is updated by scene synchronization rather than rebuilt during redraw and is covered with 500-item reuse checks.
- Added scene-owned named annotation styles with create, duplicate, rename, delete, selection and filtered-set assignment, and select-users actions. Color, selected color, line width, text size, precision, endpoint style, unit format, prefix, suffix, and tolerance resolve independently through local override → named style → scene default; the UI makes inheritance explicit and can clear all overrides at once. Deleting a style safely returns its users to scene defaults. Cross-file libraries remain a follow-up.
- Added and verified the schema v4 named-style, schema v5 anchor-resolution, and schema v6 vector-export migrations against the released schema-v2 0.4.0 fixture. Existing annotation presentation values become explicit overrides, preserving appearance while new annotations inherit scene defaults or an assigned style; anchors record truthful resolution state and retain their last source name; export settings receive additive defaults. Schemas v3 through v6 are sequential migration steps in this release, not separate shipped formats.
- Added independent snap controls for vertices, edges, midpoints, face centers, face points, guides, and measurement endpoints, midpoints, and segments. The compact sidebar row uses persistent user defaults with an opt-in scene override, `S` cycles targets during every acquisition tool through a rebindable modal action, disabled generators are skipped, and the viewport badge shows the active set. Disabling everything still permits free point placement.
- Reworked the projected snap cache around bulk coordinate reads, array projection, viewport-bounded spatial indexing with an exact lazy fallback, and lazy candidate materialization. On Blender 5.2 the 1M-vertex reference cache now builds in 75.252 ms, reprojects in 0.150 ms, and queries in 0.017 ms, meeting every `FND-11` budget without decimation or changed snap results.
- Added scale-correct single-page SVG and PDF export from an orthographic camera, with A4, A3, and US Letter paper, portrait/landscape orientation, explicit 1:N scale, physical line/text/endpoint sizes, resolved annotation colors, and truthful filtering of Fallback or Needs Repair annotations. The automated 100 mm at 1:10 case measures 10 mm in SVG, and Blender 5.2 exported 100 labeled linear annotations in 0.090 seconds. Labels remain portable vector strokes rather than selectable text.
- Hardened annotation lifecycle behavior on Blender 5.2: actual undo/redo restores persistent anchor IDs and measurement proxies while clearing pointer caches; deleting a bound source produces a visible Needs Repair fallback; duplicates deliberately share sources but receive independent measurement proxies; append stamps the destination scene; and linked or library-override annotations remain read-only during synchronization, drawing, and editing. Background coverage verifies scene-owned copy/move behavior across two scenes, and foreground QA verifies isolated manager, collection, context, and geometry behavior across two main windows.
- This remains a patch release under the version policy: it extends existing annotation presentation and snapping without breaking saved behavior or adding a new product surface.

## 0.4.1 — August 28, 2026

- Repaired the GitHub validation and release workflows so their Windows, Linux, and macOS jobs can start, test against Blender 5.1.2 and 5.2.1, retain only the current validated archive, and reject release tags while the matching changelog section is still marked Unreleased.
- Added Grease Pencil generation for angle and area annotations. Minor, supplement, and reflex angles preserve their rays, arcs, labels, colors, and presentation offsets; valid Live and Captured areas preserve their leaders, labels, colors, and placement.
- Extended Selected and Visible output scope, Camera Relative and World Scale sizing, per-annotation regeneration, and mixed EEVEE/Cycles render coverage across linear, angle, and area annotations. Areas in Needs Repair are skipped with an actionable warning.
- Restored a discoverable pre-placement direction workflow: the main sidebar exposes Auto/X/Y/Z choices, and a compact lower-corner badge identifies the active tool and direction without covering the working geometry.
- Replaced the cursor-following placement instructions with the compact badge. Typed distance appears there only while entering it, and invalid input remains visibly flagged.
- Kept the direction choice directly below the creation tools in tool-first, settings-second order, using four explicitly labeled Auto/X/Y/Z buttons across the full sidebar width so Blender cannot omit their captions.
- Converted the Edit Mode **From Mesh Selection** action box into a contextual, collapsible child panel matching the rest of the Dimensions sidebar.
- Generated Grease Pencil objects now disable Use Lights and use 3D Location stroke depth; generation also enables the active view layer's Depth and Grease Pencil data passes for render-ready output.
- Added **Outside Start** text placement as the mirror of the existing **Outside End** option, with matching live-overlay and generated-output behavior. Existing Outside End settings keep their appearance.
- This remains a patch release under the version policy: it extends the established output and interaction surfaces without breaking saved data or the documented interaction contract.

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
