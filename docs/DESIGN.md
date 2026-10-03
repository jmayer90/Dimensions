# Design and Roadmap

## Product definition

Dimensions is a focused, non-destructive precision-annotation companion for Blender. Its shared point-acquisition language supports three workflows:

1. persistent linear, angular, and area annotations;
2. saved finite measurements; and
3. construction guides.

The extension may inspect Edit Mode topology to acquire anchors or calculate values, but it does not create, cut, merge, or otherwise modify the user's mesh geometry. Geometry-authoring tools belong in a separate project with their own interaction model, test budget, release cadence, and topology guarantees.

Since 0.7.0 the toolset is deliberately small: linear dimensions (with a Chain mode), angles, areas, Measure, guide lines, offset guides, guide points, and guide-plane grids. User testing of 0.6 showed that a broader set of partially explained tools made the whole extension harder to trust; new tools must now earn their place with a clear workflow before they ship. See [UX-10](tickets/UX-10-focused-toolset.md).

## Design invariants

- **Non-destructive annotation.** Dimension, measurement, and guide workflows never modify the user's mesh topology. Guide-plane grids are Dimensions-owned reference meshes in the Construction Guides collection — like the measurement and guide-point snap proxies — that are never rendered and never enter generated or vector output.
- **No global preference mutation.** Registration does not alter Auto Merge, snapping, keymaps, or unrelated Blender settings.
- **One interaction contract.** Point, constrain, type, confirm, step back, and cancel behave predictably across tools.
- **Preview before commit.** The active target, constraint, value, and invalid state are visible before an annotation is saved.
- **Stable presentation.** Annotations remain readable during unrelated mode or topology changes. Missing vertex identity uses the stored fallback position. Viewport text and arrowheads are screen-space presentation: zooming or transforming source objects must not change their pixel size.
- **Truthful state.** Live, captured, and invalid measurements are visibly distinct; a stale cached value is never presented as a current live result.
- **Source/presentation separation.** Measurement bindings determine values while label, leader, arc, and extension properties determine placement.
- **Editable placement objects.** An annotation Empty's transform is a user-facing placement offset from source-derived canonical geometry; synchronization preserves that offset when sources move.
- **Construction objects are their transform.** A guide point is its object origin, a guide line runs along its object's local X axis, and a guide plane is its object's local XY plane. Synchronization never moves them back, so Blender's own transform tools always work.
- **Scene ownership.** Dimensions and construction objects belong to scene-owned collections and do not leak across scenes.
- **Blender-native data first.** Persistent objects remain inspectable, selectable, undoable, and saveable through normal Blender data.

## Current architecture

| Area | Responsibility |
| --- | --- |
| `anchors.py`, `repair.py` | Assign persistent mesh point IDs, expose truthful resolution status, and provide explicit candidate-based repair without changing mesh geometry or persistent RNA during queries. |
| `construction.py` | Resolve guide points, lines, measurements, and plane frames from object transforms; build and rebuild guide-plane grid meshes. |
| `area_binding.py` | Assign persistent face IDs, bind Area source sets, and calculate live world-space area. |
| `snapping.py`, `projected_snap.py` | Acquire and score targets; treat grids as see-through; sample around the cursor for outline edges; cache and depth-filter projected vertices. |
| `interaction.py` | Shared modal keys, numeric editing, and axis helpers. |
| `operators/` | Own annotation, measurement, guide, selection, and styling workflows. `operators/construction_tools.py` shares one point-acquisition base across every construction tool. |
| `dimension_geometry.py` | Calculate linear and angle world-space geometry without viewport or operator state. |
| `drawing.py`, `viewport_state.py` | Draw overlays, hit-test annotations, and isolate transient state per viewport. |
| `scene_sync.py` | Own persistent resolution-state writes, synchronize annotation locations and manager selection, repair proxies, migrate anchors, and invalidate caches. |
| `collections.py` | Enforce scene-owned collections and manage native measurement snap proxies. |
| `properties.py`, `ui.py` | Persist settings and expose scene and local editing. |
| `annotation_manager.py`, `operators/annotation_manager.py` | Maintain the redraw-stable manager registry, truthful values/filters, and row or single-step bulk actions. |
| `preferences.py` | Stores per-user interaction thresholds and defaults without changing Blender settings outside the add-on. |
| `units.py`, `volume.py` | Parse and format units and calculate evaluated closed-mesh volume. |
| `stroke_font.py`, `output_geometry.py`, `grease_pencil_output.py`, `operators/generate_output.py` | Build vector labels and world-space annotation stroke specs, then generate isolated, replaceable Grease Pencil output artifacts. |
| `vector_export.py`, `operators/export_vector.py` | Project valid world-space annotation strokes through an orthographic camera and serialize physical-page SVG/PDF output. |
| `sheet_layout.py` | Compose optional physical-mm page borders and a fixed vector title block, validate field fit, and choose a printable annotation rectangle clear of furniture. |

Annotations are Empty objects with presentation properties and an annotation kind. Linear annotations use two measurement anchors. Live Areas store persistent face IDs in `dimensions_area_face_id`, source metadata, a cached value, and explicit Live/Captured/Needs Repair state. Two-edge Angles store four persistent endpoint anchors and derive a shared or virtual center. Vertex anchors store integer IDs in the mesh's `dimensions_anchor_id` point attribute. Angle arcs are generated in world space before viewport projection. A canonical source frame plus user presentation offset keeps annotation transforms editable. Guides and measurements are Empty objects in a separate collection.

The annotation Empty is a translation-only presentation locator. Scene synchronization compares its world-space location with `canonical_location + presentation_offset`; only that delta may update presentation. Rotation and scale are not source or presentation inputs, are locked for ordinary transforms, and are ignored consistently by live drawing and generated/vector output. Existing non-identity values are retained rather than normalized so old Empty display appearance is not rewritten, but they have no annotation meaning. Parent transforms matter only when they change the locator's world translation. This deliberately refuses ambiguous object-level rotation/scale: drafting orientation and size remain explicit annotation/style properties and handles. No schema field is needed because the existing canonical location and offset already represent the complete supported transform state.

Construction objects live in the same scene-owned Construction Guides collection and are defined entirely by their transform. A guide point is an Empty whose origin is the point, with a one-vertex snap proxy parented to it for Blender's native snapping. A guide line is an Empty whose local X axis is the line. A guide plane is a wireframe grid mesh flagged `dimensions_guide_plane` whose local XY plane is the plane; its Half Size and Grid Spacing regenerate the grid, which places lines on spacing multiples from the center plus the border and is bounded to 200 cells per side. Because the grid is a real mesh, Blender's selection, transform, and snapping tools work on it. For Dimensions snapping, a grid is see-through: a ray continues past a grid to the model, a model surface hides grid points behind it, and a grid lying exactly on a model face is found with a per-grid ray cast because two surfaces at one depth cannot both be reached by stepping a scene ray forward. Snaps onto a grid, a guide point, or a guide line become object-point anchors in that object's local space, so dimensions follow the construction object they were snapped to and survive a grid spacing change. Construction objects themselves never bind live relationships to their sources; scene synchronization only keeps snap proxies current and lets world-anchored measurements move with their object. Deleting a construction object through Dimensions (Clear Guides or the manager) first converts dependent anchors to fixed world points at their current position, so clearing temporary construction never breaks dimensions; Blender's own Delete leaves them **Needs Repair** like any deleted source.

Chain is a mode of Create Dimension, not a separate object. After the first dimension is placed normally, its end becomes the next start and the tool skips straight to the next end point. The new offset is solved so its dimension line passes through the previous line point along the shared offset direction; a turn in an Auto chain keeps the previous offset instead. Each member is an independent linear dimension with its own undo step, so editing or deleting one never affects the others.

Named annotation styles are scene-owned property-group entries. Each annotation stores a style name and independent override flags. Presentation resolves once per annotation invalidation in the strict order local override → named style → scene default, then the completed snapshot is cached with geometry and reused for drawing. A missing or deleted style falls back to scene defaults; deletion explicitly clears matching references. Styles contain presentation only and never measurement bindings or sources. They travel with their scene, but are not a cross-file library.

The scene-owned Annotation Manager registry stores object pointers and display fields for dimensions, measurements, and guides. Scene synchronization updates fields in place and rebuilds membership only when managed objects change; sidebar redraws only filter cached name/kind/state fields and never mutate scene data. Viewport active-object changes schedule manager-index synchronization through Blender's message bus, outside panel drawing. The search field and a filter toggle sit above the list, because Blender's own list-filter triangle hid them; the active row's state, value, and actions appear below it. Bulk operations apply to Blender's selected managed objects by default — or the highlighted row when nothing is selected — or to every filtered row, and execute as one undoable operator. Isolate shows only that set among Dimensions objects and leaves the model visible; it records both object hiding and the annotation visibility flag, then restores the property flag regardless of view-layer membership and the hide state where the active view layer permits it.

Every anchor records whether it resolved uniquely by persistent identity, used its stored-position fallback, or became unresolvable because its source disappeared. Resolution returns the same fallback coordinate as before; only its state and presentation changed. The manager and overlay distinguish Fallback from Needs Repair. Guided repair keeps its candidate search separate from mutation: the panel and every redraw read the resolution state that scene synchronization recorded, and the nearest vertex/face search over the source mesh runs only when the user accepts a suggestion, so a broken annotation on a dense mesh never stalls the sidebar. A binding changes only after explicit acceptance or manual acquisition. Cause-scoped bulk repair repeats that confirmed rule, convert-to-world is limited to unresolvable point anchors, and linked annotations are never rewritten. Area repair replaces only source faces and preserves label/presentation state.

### Generated output

The live overlay remains the editable source of truth. An explicit operator resolves visible or selected annotations of every persistent kind in valid Live or Captured state into world-space stroke specifications, then creates separate Grease Pencil v3 objects in an exclusive scene-owned `Dimensions Output` collection. A shared authority gate evaluates current anchors and bindings instead of trusting cached state; SVG/PDF export uses the same gate. Generation reconciles its registry before writing: deleted or non-authoritative sources lose their stale artifacts, Visible scope also removes now-hidden sources, and Selected scope deliberately preserves valid output for annotations outside the selection. Grease Pencil was chosen over curves or meshes because it is Blender's native stroke surface, remains editable, and is verified to render in EEVEE and Cycles. Generated objects disable Grease Pencil lighting and use 3D Location stroke depth; successful generation enables Depth and Grease Pencil data passes on the active view layer. A scene-owned object-pointer registry assigns persistent source keys without modifying annotation objects; regeneration replaces only the matching artifact, and the UI warns that hand edits are disposable. Existing user collections with the same display name are never adopted.

Camera Relative sizing converts configured render pixels to world units at each annotation's midpoint depth and is the default. World Scale sizing uses explicit scene-unit values. Labels use a bundled single-line vector font so text, tolerances, custom notes, degree signs, and squared-unit suffixes remain Grease Pencil strokes instead of introducing a second render-object type. Linear Inline, Above, Outside Start, Outside End, and custom-text ordering rules mirror the live overlay; angle rays/arcs and area leaders preserve their live world positions and presentation offsets. For a linear annotation whose endpoints share camera depth, camera-relative layout targets agreement within one output pixel. A perspective annotation spanning materially different depths uses the documented midpoint approximation. [OUT-04](tickets/OUT-04-angle-area-output.md) extends the same backend across all persistent annotation kinds.

Generated output resolves named style color, endpoint variant, precision, unit format, prefix, suffix, and tolerance. Line width, label height, and endpoint size intentionally come from the separate Camera Relative or World Scale output policy rather than viewport-pixel style fields; this keeps sheet output consistently scaled.

Scale-correct SVG/PDF export reads the same resolved world-space strokes without first creating Grease Pencil objects. An orthographic camera defines the crop; scene-unit scale and the requested 1:N denominator map model coordinates into physical millimetres. The camera frame is centered without rescaling inside the selected printable annotation rectangle on A4, A3, or US Letter in portrait or landscape, and a frame that does not fit is rejected. Export presentation uses explicit paper-millimetre line, label, and endpoint sizes while preserving resolved annotation RGB colors. Fallback and Needs Repair annotations are omitted so a broken binding cannot appear authoritative. Labels use the bundled stroke font and are therefore vector outlines, not selectable text.

The 0.6 single-sheet surface composes page-space furniture and annotation projection from one shared layout. A scene may enable a rectangular border and a fixed lower-right title block with drawing title, number, revision, author, date, and the current scale. Margin and block dimensions are physical millimetres and therefore remain unchanged under camera, scene-unit, or drawing-scale changes. The camera frame is translated to the best-fitting rectangle above or left of the title block, with stroke-width clearance from the border and block. Fit Scale and export use the same rectangle. The 80 × 24 mm minimum block fits ISO dates at the default 2 mm title-block text height, while larger custom metadata is refused rather than silently shrunk. Invalid layouts fail before writing. This is deliberately one bounded sheet, not a multi-sheet registry or arbitrary template engine; sheet furniture does not change model geometry, camera framing, or annotation style.

### Saved-data schema

Each scene containing Dimensions data stores an integer schema version, and since schema 16 each owned object records the schema it was created in or converted to. `load_post` migrates older scenes exactly once per step; object-level steps skip objects already stamped at or past their target, because Append, Link, and a new scene sharing a collection bring current objects into scenes whose own stamp says nothing about them. Unstamped objects appended from a 0.6 file into a current scene receive only the v16 shape conversion. A scene from a newer schema is never modified — neither migration, synchronization, nor creation writes to it — and creation tools report the mismatch. Schema changes must add an idempotent migration and a fixture before release.

Add-on preferences are per-user defaults and interaction tuning. Scene and annotation settings travel with the file and win once set; changing an add-on preference never rewrites existing annotations.

| Schema | Introduced | Change |
| --- | --- | --- |
| 1 | 0.2.3 | Baseline schema; legacy vertex anchors receive persistent point IDs during `v0 → v1` migration. |
| 2 | 0.4.0 | Additive Grease Pencil output settings and scene-owned source registry; v1 files receive documented defaults without overwriting existing values, and incomplete registry bindings are discarded. |
| 3 | 0.4.2 | First migration step in the 0.4.2 working release: additive scene snap-target override; migrated scenes keep the override disabled and all established targets enabled. This schema was not released separately. |
| 4 | 0.4.2 | Named scene styles and per-property annotation override flags; existing annotations migrate with every prior value explicit so their appearance is unchanged. |
| 5 | 0.4.2 | Truthful anchor-resolution status and retained source names for guided repair; the released schema-v2 fixture verifies the sequential v2 → v3 → v4 → v5 path. |
| 6 | 0.4.2 | Additive vector-export paper, orientation, scale, and physical presentation settings. Schema v5 was not released separately; migration preserves its repair metadata exactly. |
| 7 | 0.4.3 | Additive chain/baseline dimension-set storage; independent annotations remain unchanged. |
| 8 | 0.4.3 | Additive Guide Point snap-target and Annotation Manager filter defaults; the released schema-v2 fixture verifies the sequential migration path. |
| 9 | 0.4.3 | Additive drafting-presentation style fields for per-end markers, extension treatment, dual units, and label layout. The v8 → v9 migration maps legacy Arrow/Tick presentation, zero gap/overshoot, single units, and existing Above/Broken behavior into explicit overrides; the released schema-v2 fixture verifies the full sequential path. |
| 10 | 0.4.3 | Additive circular-dimension binding, captured arc-frame storage, and fit-warning threshold; legacy annotations remain unchanged. |
| 11 | 0.4.3 | Additive derived-guide source descriptors, offset/side/direction state, and last-resolved fallback presentation; existing guides migrate as fixed and Live. |
| 12 | 0.4.3 | Additive named/oriented datum flags on guide points plus coordinate/elevation binding, alignment, sign, axis, relative-reference, and independent elevation-format fields. Existing guide points remain ordinary points. |
| 13 | 0.5.0 | Additive saved guide-plane definitions, bounded presentation extent, plane repair state, dedicated snap/manager defaults, and one scene active-plane frame. The v12 → v13 migration is idempotent and the released schema-v2 fixture exercises the full path. |
| 14 | 0.5.0 | Additive angular-guide pivot/angle and repeated-spacing mode/interval/count/extent definitions; existing guides remain fixed or retain their prior derived mode. |
| 15 | 0.6.0 release | Additive scene-owned drawing-sheet toggles, physical margin/title-block dimensions, and title/number/revision/author/date metadata. Existing vector export remains furniture-free by default. |
| 16 | 0.7.0 release | Breaking simplification. Chain/baseline sets become independent linear dimensions; derived, angular, and spaced guides become fixed guide lines at their last position; guide lines and points become transform-defined; guide planes become grid meshes on their last frame; radial, diameter, arc, coordinate, and elevation annotations are deleted with their names printed. Removed fields are read through `bl_system_properties_get()` and then dropped. Steps v6→v7 and v9→v14 that only initialized removed features are now no-ops. Each owned object also stores the schema it was created in or converted to, so later migrations skip it when it is appended, linked, or shown in another scene; conversion keeps hide state per view layer, selectability, and parenting, and removes Grease Pencil output whose source was deleted. The released `schema-v15-0.6.0.blend` fixture verifies the conversion and its idempotence. |

## Interaction contract

- Hover supplies a target and direction; orange is active and blue is accepted.
- Annotation selection is an explicit `Dimensions Selection` WorkSpaceTool in Object Mode. Its click handler selects annotations and guides; misses fall through to Blender selection.
- The active selected editable dimension exposes one fixed-pixel purple presentation handle: diamond for linear offset, circle for angle radius, and square for area label placement. Handle hit testing precedes annotation-body selection. Manipulation reuses the creation contract (`A`/`X`/`Y`/`Z`, typed scene-unit distance, click/`Enter`, and `Esc`), commits as one undo step, and does not mutate until confirmation so cancellation is exact. Linked and library-override annotations expose no handle. These are custom overlay handles rather than Blender gizmos so selection priority and the existing per-viewport modal contract stay in one path.
- Invocation shortcuts are registered as disabled add-on keymap entries. They are visible and editable in Add-on Preferences without claiming potentially conflicting defaults; the shared axis and confirm modal actions are registered in the Dimensions modal keymap.
- `A` selects aligned behavior and `X`, `Y`, and `Z` select world axes in every acquisition tool. The 0.5 active construction plane, which remapped them, was withdrawn in 0.7.0. Free unsnapped placement uses a view-facing plane through the previous point.
- Every construction tool (Guide Line, Offset Guide, Guide Point, both plane tools) uses the same snapping, inference, `S` cycling, axis locks, typed distance, step back, and continuous placement as Create Dimension, through one shared base in `operators/construction_tools.py`.
- `S` cycles the active snap set from all targets through each target individually and back; the action is rebindable and shared by every acquisition tool.
- Middle mouse always navigates. The 0.6 middle-drag axis gesture took the middle mouse away after the first click in multi-click tools, so 0.7.0 removed it; `X`, `Y`, and `Z` choose axes everywhere.
- Typed scene-unit distance can precede or follow an axis choice. `Enter` confirms the current valid stage. With an axis locked, a typed distance needs no pointer movement; without one, the pointer gives its direction. Once a distance is being typed, letters belong to its unit (`2ft`, `3 meters`), so single-letter shortcuts such as `S` and `L` do not fire mid-number.
- View navigation always reaches Blender while a tool runs: mouse wheel, middle mouse, trackpad, 3D mouse, `Home`, and the numpad view keys. A numpad digit is typed input only while the tool accepts a distance.
- `Backspace` steps back and `Esc` and right-click exit in every tool; these three keys are fixed. The other modal keys live in the rebindable Dimensions Modal keymap.
- Creation tools use continuous placement by default. After each commit they retain the session axis and placement offset, clear per-annotation snaps and typed input, and return to their first stage. `Esc` or right-click exits a continuous session; changing mode or the active object ends it without leaking preview state. Users can disable continuous placement in add-on preferences to restore the step-back behavior.
- Active modal tools use a fixed, compact lower-corner badge showing the tool, the next step, direction when applicable, typed input while present, and the active snap set. Each tool also writes its keys to Blender's status bar for the duration of the session and clears it on every exit path. Nothing follows the cursor or obscures geometry.
- Snap candidates are filtered at generation from independent targets; guide-plane grids snap like meshes when the Guide Plane target is on and are skipped otherwise. Per-user radius and target preferences are the default; an opt-in scene override switches both to document-specific values. Native candidates are scored primarily by screen distance with a bounded type bias, and own the full capture radius ahead of unlocked inference. Every point-picking click revalidates changed cursor coordinates instead of accepting stale hover data. With no targets active, acquisition falls through to free placement on the view-derived plane through the previous point.
- Drafting inference is a transient layer inside the shared acquisition contract. The most recently hovered eligible edge, guide, or face becomes the implicit reference; rebindable `L` freezes that reference until `L` releases it. Edge and guide inference respects the corresponding `UX-05` target, while face-plane inference requires Face Center or Face Point. Exact-topology source and repair workflows stay geometry-only.
- Derived candidates are deterministic: nearest screen distance wins, with a stable inference-type tie break. Existing geometry owns the configured snap aperture; an explicitly locked inference reference is the deliberate override. Parallel, perpendicular, extension, intersection, local-axis, and face-plane glyphs use orange while active and blue after acceptance, and the corner badge names the current inference.
- When the cursor ray misses every surface in Object Mode, acquisition samples a small ring of rays around the cursor and offers the edges, midpoints, and vertices of the faces it finds, so outline edges stay snappable. Face points and face centers still require the cursor to be on the face.
- Repeating `X`, `Y`, or `Z` switches that session constraint from the world axis to the active object's local axis; a third press returns to the world axis. Local-axis inference stores the acquired world point, not a persistent constraint.
- Dimension and measurement point acquisition works in Object and Mesh Edit Mode without modifying the mesh.
- The primary Measure command is a per-viewport transient tape measure. Its preview shows total distance and signed ΔX/ΔY/ΔZ using the configured unit formatter, chains the accepted end into the next start, and creates neither a measurement nor a snap proxy until rebindable `P` explicitly saves. Rebindable `Ctrl+C` copies the same formatted text without colliding with typed `cm` input. `Measure (Persistent)` preserves direct save-on-confirm invocation for scripts, Search, and an optional user key binding.
- The main Dimension command is selection-first in Edit Mode: exactly one selected edge commits a length immediately; other selections enter interactive point acquisition.
- Edit selection can create a length from one edge, an angle from any two non-parallel edges, or an area leader from one or more faces.
- Area creation has its own source and placement stages: Edit Mode consumes selected faces, while Object Mode acquires base-mesh faces before the user places the leader label.
- Angle and Area use dedicated Remake actions; linear anchor eyedroppers are not reused for their multi-source workflows.
- Angle binds two edges directly. Connected edges use their shared vertex; disconnected edges derive a virtual placement point from their supporting lines and expose smaller, supplementary, and reflex solutions explicitly.
- Modal tools keep their viewport work in Blender adapters, while point-placement stage transitions live in a pure state model covered by the background smoke suite. This protects the shared point, type, confirm, step-back, and cancel contract without synthetic window events.
- Every key above is rebindable. Blender refuses modal key-maps in an add-on key configuration, so the modal actions live in a private `Dimensions Modal` action map that is read through the *user* key configuration on each event; rebinding in the keymap editor therefore takes effect immediately, without a restart. Nothing Dimensions registers can shadow a Blender or Industry Compatible preset binding: invocation entries ship unbound and inactive, and the action map is never dispatched from by Blender. `DimensionsKeymapTests` in `tests/blender_smoke.py` enforces both properties.

## Measured performance

Numbers below are foreground-comparable background measurements from the current **Windows validation host (28 logical processors), Blender 5.2.0 LTS**. Both benchmarks generate their scenes deterministically. Compare runs on the same host for regression analysis; absolute timings across hosts are supporting evidence rather than a direct before/after ratio.

### Overlay draw cost — `tests/draw_benchmark.py`

Measures the per-frame CPU work the overlay performs before it uploads anything: locating annotations, resolving anchors, projecting to screen space, and laying out labels. `rebuild` invalidates the geometry cache every frame (worst case: something moved); `cached` is the steady state of a still view.

| Scene | Scene objects | Dimensions | Rebuild | Cached |
| --- | --- | --- | --- | --- |
| 10 cubes, 10 dimensions | 20 | 10 | 0.413 ms/frame | 0.073 ms/frame |
| 10,000 cubes, 10 dimensions | 10,010 | 10 | 0.416 ms/frame | 0.078 ms/frame |
| 500 dimensions (budget scene) | 510 | 500 | 20.175 ms/frame | 3.715 ms/frame |

Two results matter. Adding 10,000 non-annotation objects does not make draw cost scale with scene size, because the loop iterates the Dimensions collection rather than `scene.objects`; the small-case timing remains sub-millisecond-scale and unrelated to the 10,000 bystanders. And the documented budget of **500 visible dimensions at 30 fps or better** remains met after the hardening pass: 50 fps while rebuilding every annotation every frame, 269 fps in the steady state.

On the September 28, 2026 Linux/Blender 5.2.2 review host, the same 500-dimension case measured 29.099 ms rebuilding (34 fps) and 5.110 ms cached. Ten dimensions measured 0.518 ms with 10 cubes and 0.498 ms with 10,000 cubes. The 30 fps rebuild margin is narrow on this host; keep this benchmark in the release gate when changing geometry or label layout.

Annotations sharing a color and line width are drawn in one batch, so the common selected/unselected split collapses to roughly two GPU batches plus text regardless of annotation count. Font metrics are measured once per string and size, and label layout is cached per unchanged label and view.

### Projected snap cost — `tests/snap_benchmark.py`

`build` is the first query into a cold cache, `reproject` is a query after a pure view change (which must not rescan mesh data), and `query` is the steady state.

| Reference scene | Build | Reproject | Query |
| --- | --- | --- | --- |
| 10k vertices, 1 object | 1.313 ms | 0.095 ms | 0.022 ms |
| 100k vertices, 1 object | 8.376 ms | 0.132 ms | 0.034 ms |
| 100k vertices, 50 objects | 6.732 ms | 0.185 ms | 0.016 ms |
| 1M vertices, 10 objects | **50.128 ms** | **0.179 ms** | 0.028 ms |

The **under 8 ms per query**, **under 100 ms 1M-vertex build**, and **under 50 ms reprojection** budgets are all met. Query cost stays flat because the spatial grid bounds candidate count independently of scene size. Bulk coordinate reads and array projection retain every source, while the normal grid indexes only the viewport plus the maximum snap radius; an out-of-band query lazily builds the complete spatial index from the retained coordinates, preserving exact results without charging ordinary queries for unsnappable offscreen points.

The September 28 Linux/Blender 5.2.2 run measured 60.707 ms build, 0.118 ms reprojection, and 0.019 ms steady query at 1 million vertices. These are supporting Linux measurements, separate from the Windows reference table.

Set `DIMENSIONS_SNAP_PROFILE=1` for the add-on's own per-stage build, reproject, query, and occlusion timings. The instrumentation is inert when the variable is unset.

## Known risks

1. **Duplicated anchor IDs.** Blender topology duplication may copy a point ID. Resolution still chooses the candidate closest to the stored fallback coordinate, but now labels the annotation **Fallback**, highlights both positions, and requires explicit confirmation before rebinding.
2. **Face identity after topology duplication.** Live Areas resolve persistent IDs on the base mesh first. With viewport modifiers active, evaluated geometry is authoritative only when Blender propagates every bound ID exactly once and the resolved face keeps its bound vertex count. Unique topology-preserving deformation stays Live. Missing, duplicated, or structurally changed evaluated identity never falls back to index or proximity: the base value remains visible as **Fallback — Modifier Faces Unresolved** and is withheld from output. Missing or ambiguous base identity remains **Needs Repair**.
3. **Snapshot output.** Generated objects are snapshots and intentionally lose hand edits when regenerated. Each generation pass removes artifacts that no longer have an authoritative source, but source changes do not update a snapshot until the operator runs again. Measurements and construction guides remain viewport/construction data.
4. **Coplanar grid ties.** A grid created on a model face sits at exactly the face's depth. Dimensions finds both surfaces when the model wins Blender's ray-cast tie, but when the grid wins, only the grid's targets and the model's projected vertices are offered under the cursor. Blender's own face snapping also lands on visible grids.
5. **Edit Mode BMesh lifetimes.** Blender invalidates every BMesh element wrapper when the `bmesh.from_edit_mesh()` object that produced it is freed. Code that returns BMesh elements must keep that object alive for as long as the elements are used; `area_binding.evaluate_area_binding` does so explicitly. Background tests can hide this because a test-held reference keeps the wrapper alive, so `tests/foreground_workflows.py` covers the Edit Mode Area and Plane: Face paths.
6. **Release compatibility evidence.** The September 2026 audit defects are fixed
   under [FND-12](tickets/FND-12-critical-stability-hardening.md),
   [OUT-06](tickets/OUT-06-vector-typography-page-bounds.md), and
   [FND-13](tickets/FND-13-lifecycle-modal-cleanup.md). The 0.6.0 suite passed on Linux
   Blender 5.1.2 and 5.2.2. The 0.7.0 background suites (358 tests) and the 36 foreground
   workflow checks pass on Windows Blender 5.1.2 and 5.2.0; the 0.7.1 suites (359 tests)
   and release archive pass on Windows Blender 5.1.2. Schema v16 shipped in 0.7.0, so
   final 1.0 release QA still needs the supported platform matrix and a deliberate
   schema freeze.

## Lifecycle behavior matrix

The expected result is shared across linear, angle, and area annotations, measurements and their snap proxies, and construction objects unless noted. `✓` means the binding survives; **Needs Repair** means an annotation keeps its stored fallback visible and labels the broken binding rather than silently presenting a live value; **Read-only** means Dimensions neither synchronizes nor caches presentation values back into linked or overridden RNA. `Shift+D` and `Alt+D` have the same source-binding semantics for these Empty-based objects because they have no shareable object-data block.

| Object type | Save/reload | Undo | Redo | Undo past creation | `Shift+D` / `Alt+D` |
| --- | --- | --- | --- | --- | --- |
| Linear dimension | ✓ | Restores object, anchors, and mesh IDs | Reapplies deletion and Needs Repair | Removes object | Copy deliberately shares source anchors |
| Angle dimension | ✓ | Restores object, edge anchors, and mesh IDs | Reapplies deletion and Needs Repair | Removes object | Copy deliberately shares source edges |
| Area dimension | ✓ | Restores object, face IDs, and cached fallback | Reapplies deletion and Needs Repair | Removes object | Copy deliberately shares source faces |
| Measurement | ✓ | Restores object and proxy | Reapplies deletion | Removes object | Copy receives an independent proxy |
| Measurement proxy | Recreated if absent | Restored or rebuilt for its parent | Removed with deleted parent | Removed with parent | Never shared between copies |
| Guide line | ✓ | Restores object and transform | Reapplies deletion | Removes object | Independent copy at the same place |
| Guide point | ✓ | Restores object, transform, and proxy | Reapplies deletion | Removes object and proxy | Copy receives an independent proxy |
| Guide plane grid | ✓ | Restores object, transform, and grid mesh | Reapplies deletion | Removes object | `Shift+D` copies the grid mesh; `Alt+D` shares it, and a size change then regenerates a private copy |

| Object type | Delete source | Delete annotation | Append | Link | Move scene | Copy to scene | Library override |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Linear dimension | Visible **Needs Repair** fallback | Deletes annotation | Local object; destination stamped current on first sync | Read-only; no sync or draw writes | Destination collection only | Independent object in destination; source binding shared deliberately | Read-only |
| Angle dimension | Visible **Needs Repair** fallback | Deletes annotation | Local object; destination stamped current on first sync | Read-only; no sync or draw writes | Destination collection only | Independent object in destination; source binding shared deliberately | Read-only |
| Area dimension | Visible **Needs Repair** fallback | Deletes annotation | Local object; destination stamped current on first sync | Read-only; no sync or draw writes | Destination collection only | Independent object in destination; source-face binding shared deliberately | Read-only |
| Measurement | World anchors remain valid | Deletes its proxy too | Local object; destination stamped current on first sync | Read-only | Destination collection only | Independent object and proxy in destination | Read-only |
| Measurement proxy | Rebuilt if parent remains | Deleted with parent | Rebuilt for appended parent; never transferred alone | Never edited | Rebuilt for owning scene | Parent-specific proxy | Read-only |
| Guide line | Unaffected; it has no source | Deletes guide; Dimensions' Clear Guides and manager Delete first fix dependent anchors as world points, Blender's Delete leaves them **Needs Repair** | Local object; destination stamped current on first sync | Read-only | Destination collection only | Independent object in destination | Read-only |
| Guide point | Unaffected; it has no source | Deletes point and proxy; dependent anchors as for a guide line | Local object; destination stamped current on first sync | Read-only | Destination collection only | Independent object and proxy | Read-only |
| Guide plane grid | Unaffected; dimensions snapped to it keep their object-point anchors | Deletes grid; dependent anchors as for a guide line | Local object and mesh; destination stamped current | Read-only | Destination collection only | Independent object | Read-only |

`tests/blender_lifecycle.py` verifies the headless cells above on Blender 5.2 with real undo/redo operators, a temporary append/link library, an actual library override, source and parent deletion, and two simultaneously populated scenes. Undo/redo clears projected-snap, volume, drawing-geometry, and per-viewport pointer caches. The scheduled sync iterates explicit scenes rather than whichever scene happens to be active in `bpy.context`.

A Blender 5.2 foreground check created a second main window with `bpy.ops.wm.window_new_main()` and assigned two temporary scenes, each containing one distinct world-anchored dimension. Both window contexts matched their assigned scenes; each Annotation Manager registry and scene-owned `Dimensions` collection contained only its own object; the other object was absent; and evaluated geometry values remained 2.0 and 3.0 respectively. Cleanup restored the original single-window `Scene` and removed the temporary data. This is recorded foreground evidence, not a background automation claim.

## Prioritized roadmap

The canonical ticket status, milestone rollup, and status legend live in the [work-ticket index](tickets/README.md). The items below explain priority and product direction; status labels use the same meanings as that index.

The [0.7 release scope](RELEASE-SCOPE-0.7.md) records the features removed after 0.6 user testing and why.
The [0.6 release scope](RELEASE-SCOPE-0.6.md) keeps the tested single-sheet workflow
and explicitly defers topology-changing face correspondence, arbitrary set-member
reordering, and general drawing-document templates. The reviewed pre-cut candidate
is preserved on `experimental/post-0.6-feature-candidates`.

### Current delivery sequence

| Order | Work | Status | Outcome |
| --- | --- | --- | --- |
| 1 | Foreground interaction and output QA | ✅ Complete | Direction preselection, mixed-kind output, snap-target disable/re-enable, and clean install registration are verified in interactive Blender; the automated suites cover Blender 5.1 and 5.2. |
| 2 | [OUT-04](tickets/OUT-04-angle-area-output.md) | ✅ Complete | Angle and area Grease Pencil generation delivered in 0.4.1. |
| 3 | [UX-02](tickets/UX-02-annotation-manager.md), [UX-07](tickets/UX-07-guided-repair.md), and [OUT-03](tickets/OUT-03-styles.md) | ✅ Complete | Manager, guided repair, named styles, and filtered assignment delivered in 0.4.2. |
| Parallel | [FND-11](tickets/FND-11-snap-cache-build-cost.md) | ✅ Complete | The current host revalidates the 1M-vertex cache at 50.128 ms build and 0.179 ms reprojection. |
| After OUT-03 | [DIM-04](tickets/DIM-04-presentation-controls.md) | ✅ Complete | Per-end markers, extension treatment, dual units, label modes, and tight-space leaders delivered in 0.4.3. |
| 4 | [OUT-02](tickets/OUT-02-vector-export.md) | ✅ Complete | Camera-framed, scale-correct SVG/PDF output delivered in 0.4.2. |
| 5 | [UX-04](tickets/UX-04-direct-handles.md) and [UX-06](tickets/UX-06-hover-measurement.md) | ✅ Complete | Selected-only direct presentation handles and transient chained tape measurement delivered in 0.4.3. |
| 6 | [CON-01](tickets/CON-01-guide-points.md) | ✅ Complete | Persistent anchored/free guide points, native snapping, and manager integration delivered in 0.4.3. |
| 7 | [DIM-01](tickets/DIM-01-chain-baseline.md) | 🚫 Withdrawn | Persistent chain/baseline sets, reflow editing, repair, and output delivered in 0.4.3. Withdrawn in 0.7.0. |
| 8 | [CON-02](tickets/CON-02-offset-guides.md) | 🚫 Withdrawn | Persistent edge/guide/face offsets and centerlines, detach, repair, and cycle refusal delivered in 0.4.3. Withdrawn in 0.7.0; `UX-10`'s fixed Offset Guide replaces it. |
| 9 | [DIM-03](tickets/DIM-03-coordinate-elevation.md), [CON-03](tickets/CON-03-guide-planes.md), and [CON-04](tickets/CON-04-angular-guides-spacing.md) | 🚫 Withdrawn | Validated datums, coordinate/elevation annotations, active planes, angular guides, and repeated spacing in 0.5.0. Withdrawn in 0.7.0. |
| 10 | [OUT-05](tickets/OUT-05-drawing-sheet.md) | ✅ Complete | Composed the existing physical-page SVG/PDF export into a bounded single drawing sheet in 0.6.0. |
| 11 | [FND-12](tickets/FND-12-critical-stability-hardening.md) | ✅ Complete | Crash, unbounded spacing, ray/frame, newline, color, and fit-scale fixes pass full Blender 5.1.2/5.2.2 validation. |
| 12a | [OUT-06](tickets/OUT-06-vector-typography-page-bounds.md) | ✅ Complete | Printable bounds, field-fit validation, and deterministic drafting typography pass Blender 5.1.2/5.2.2 validation. |
| 12b | [FND-13](tickets/FND-13-lifecycle-modal-cleanup.md) | ✅ Complete | Released settings-only migration fixture, read-only boundaries, exact viewport cleanup, and lifecycle matrix pass Blender 5.1.2/5.2.2 validation. |
| 13 | [UX-10](tickets/UX-10-focused-toolset.md) | ✅ Complete | 0.7.0 focuses the toolset after user testing: working Measure and guide tools, Chain as a Create Dimension mode, movable construction objects, snappable grid planes, visible manager filters, and the schema-v16 conversion. |

Early public feedback reinforces the product definition rather than expanding it: every request concerns faster annotation, clearer presentation, or usable output. None requires mesh authoring. The disposition is:

| User request | Decision | Roadmap placement |
| --- | --- | --- |
| Keep placing dimensions without leaving the tool | Accepted and delivered | [UX-01](tickets/UX-01-continuous-placement.md), delivered in 0.3.1 |
| Choose Auto/X/Y/Z once, place a group, then switch direction | Accepted and delivered with repeated placement | [UX-01](tickets/UX-01-continuous-placement.md), delivered in 0.3.1 |
| Render dimensions | Accepted and delivered for all annotation kinds | Linear [OUT-01](tickets/OUT-01-grease-pencil-output.md) in 0.4.0; angle and area [OUT-04](tickets/OUT-04-angle-area-output.md) in 0.4.1 |
| Replace arrows with architectural tick marks | Accepted and delivered | First slice of [DIM-04](tickets/DIM-04-presentation-controls.md), delivered in 0.3.2 with global and per-annotation controls |
| Keep numeric labels from growing | Existing behavior verified and documented | [UX-08](tickets/UX-08-stable-overlay-sizing.md), delivered in 0.3.1; any zoom- or transform-driven growth is a bug |

### Accepted product expansion

The next roadmap keeps the non-destructive product boundary while broadening measurement types, annotation vocabulary, management, reuse, and discovery. Completed foundations stay closed and receive focused follow-up tickets.

| Need | Ticket | Direction |
| --- | --- | --- |
| Saved/view/face/world construction planes | [CON-03](tickets/CON-03-guide-planes.md) | Delivered in 0.5.0; withdrawn in 0.7.0 in favor of movable grid planes ([UX-10](tickets/UX-10-focused-toolset.md)). |
| Named datums, ordinate coordinates, and elevations | [DIM-03](tickets/DIM-03-coordinate-elevation.md) | Delivered in 0.5.0; withdrawn in 0.7.0. |
| Angular and repeated construction guides | [CON-04](tickets/CON-04-angular-guides-spacing.md) | Delivered in 0.5.0; withdrawn in 0.7.0. |
| Physical border and fixed title block | [OUT-05](tickets/OUT-05-drawing-sheet.md) | Delivered and validated as the bounded 0.6.0 drawing-sheet surface. |

### P0 — Trustworthy acquisition and repeated placement

- ✅ **Complete** — user-controlled snap targets in [UX-05](tickets/UX-05-snap-control.md) passed foreground disable/re-enable QA, while [FND-11](tickets/FND-11-snap-cache-build-cost.md) records passing dense-scene cache budgets.
- ✅ **Complete** — explicit rebind, convert-to-world, candidate preview, and cause-scoped bulk repair are delivered in [UX-07](tickets/UX-07-guided-repair.md).
- ✅ **Complete** — selected-only direct viewport handles for linear offset, Angle radius, and Area label placement shipped in 0.4.3 through [UX-04](tickets/UX-04-direct-handles.md).
- ✅ **Complete** — live Area modifier semantics are conservative and explicit: exact evaluated ID propagation with unchanged per-face topology is Live; every ambiguous evaluated case shows a non-authoritative base fallback and is withheld from output, without face-index or proximity correspondence.
- ✅ **Complete** — [UX-09](tickets/UX-09-annotation-transform-semantics.md) defines the canonical-frame and placement-offset model as translation-only; object rotation and scale are locked for ordinary editing and ignored consistently by live and generated output.
- ✅ **Complete** — constrained Area and two-edge Angle modal-event workflows have dedicated adapter tests and Blender 5.2 foreground verification.
- ✅ **Complete** — dense-scene budgets pass with [FND-11](tickets/FND-11-snap-cache-build-cost.md), and foreground modal-event coverage exercises the live viewport context.
- ✅ **Complete** — [FND-07](tickets/FND-07-lifecycle-hardening.md) covers measurement proxies and annotations through the background lifecycle matrix and two-window foreground isolation.

### P1 — Renderable output, precision inference, and management

- ✅ **Complete** — extend the shipped linear Grease Pencil path to angle and area annotations in [OUT-04](tickets/OUT-04-angle-area-output.md), delivered in 0.4.1.
- ✅ **Complete** — named reusable styles and selection/filtered assignment are delivered in [OUT-03](tickets/OUT-03-styles.md), with management operations supplied by [UX-02](tickets/UX-02-annotation-manager.md).
- ✅ **Complete** — local-axis, parallel, perpendicular, extension, intersection, and face-plane inference is delivered in [UX-03](tickets/UX-03-inference-engine.md).
- ✅ **Complete** — search, rename, select, hide, exact-state isolate, repair-state/source surfacing, and bulk style operations shipped in [UX-02](tickets/UX-02-annotation-manager.md).
- ✅ **Complete** — transient chained measurement with total, ΔX/ΔY/ΔZ, copy, and explicit save is delivered in [UX-06](tickets/UX-06-hover-measurement.md).
- ✅ **Complete** — guide points from [CON-01](tickets/CON-01-guide-points.md), reworked in 0.7.0 into movable fixed points.
- 🚫 **Withdrawn** — live offsets and centerlines from [CON-02](tickets/CON-02-offset-guides.md) and the active plane from [CON-03](tickets/CON-03-guide-planes.md) were removed in 0.7.0; [UX-10](tickets/UX-10-focused-toolset.md) provides a fixed Offset Guide and snappable grid planes.

### P2 — Documentation-grade dimensions

- ✅ **Complete** — [UX-03](tickets/UX-03-inference-engine.md) supplies transient face-plane inference.
- 🚫 **Withdrawn** — chain and baseline sets ([DIM-01](tickets/DIM-01-chain-baseline.md)), radial, diameter, and arc-length fitting ([DIM-02](tickets/DIM-02-radial-diameter-arc.md)), and coordinate and elevation dimensions ([DIM-03](tickets/DIM-03-coordinate-elevation.md)) were removed in 0.7.0. Chain returned as a Create Dimension mode.
- ✅ **Complete** — architectural ticks shipped in 0.3.2, manual Outside Start in 0.4.1, and extension treatment, independent endpoint variants, dual units, label modes, and deterministic tight-space leaders in 0.4.3 through [DIM-04](tickets/DIM-04-presentation-controls.md).
- ✅ **Complete** — camera-framed, physical-page SVG and PDF export shipped in [OUT-02](tickets/OUT-02-vector-export.md), with an automated 100 mm at 1:10 → 10 mm scale check.

## Explicitly excluded scope

Mesh-line drawing, face cutting, rectangles, Push/Pull, general Offset, Move/Copy arrays, Circle/Arc, and eraser-style mesh editing are geometry-authoring tools. They are not part of Dimensions. Any future implementation should start in a separate project rather than re-enter this extension incrementally.

## Release gate

Version policy, the triggers that move the minor component, and the full 1.0 checklist are defined in [Versioning and release policy](VERSIONING.md). In short: the minor component only moves when a change breaks saved data, breaks the interaction contract, or adds a new product surface. M1 tripped the first two for 0.3.0; renderable Grease Pencil output tripped the third for 0.4.0.

A release candidate should pass:

- Python compilation and the Blender background suites — smoke, modal interaction, and lifecycle;
- foreground modal coverage, which is now a described mechanism rather than an aspiration: `tests/support/` supplies a fake viewport context, a scripted snap provider, and an operator harness, so modal stage transitions, axis locks, typed input, step-back, and cancellation run headlessly in `tests/blender_modal.py`;
- schema migration against the released-file fixtures under `tests/fixtures/`;
- Blender extension manifest validation and build;
- clean-profile register, unregister, install, disable, and re-enable;
- save/reload and undo/redo for every persistent object type;
- foreground viewport checks for selection, visibility, native measurement snapping, unit display, broken anchors, and two-window scene isolation;
- `tests/foreground_workflows.py`, which drives real window events through Measure, the construction tools, Chain, Edit Mode Area and Plane: Face, and Isolate;
- tests on the declared Blender 5.1 and 5.2 targets; and
- snap performance checks on representative dense scenes.
