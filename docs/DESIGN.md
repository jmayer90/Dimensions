# Design and Roadmap

## Product definition

Dimensions is a focused, non-destructive precision-annotation companion for Blender. Its shared point-acquisition language supports three workflows:

1. persistent linear, angular, and area annotations;
2. saved finite measurements; and
3. construction guides.

The extension may inspect Edit Mode topology to acquire anchors or calculate values, but it does not create, cut, merge, or otherwise modify mesh geometry. Geometry-authoring tools belong in a separate project with their own interaction model, test budget, release cadence, and topology guarantees.

## Design invariants

- **Non-destructive annotation.** Dimension, measurement, and guide workflows never modify mesh topology.
- **No global preference mutation.** Registration does not alter Auto Merge, snapping, keymaps, or unrelated Blender settings.
- **One interaction contract.** Point, constrain, type, confirm, step back, and cancel behave predictably across tools.
- **Preview before commit.** The active target, constraint, value, and invalid state are visible before an annotation is saved.
- **Stable presentation.** Annotations remain readable during unrelated mode or topology changes. Missing vertex identity uses the stored fallback position. Viewport text and arrowheads are screen-space presentation: zooming or transforming source objects must not change their pixel size.
- **Truthful state.** Live, captured, and invalid measurements are visibly distinct; a stale cached value is never presented as a current live result.
- **Source/presentation separation.** Measurement bindings determine values while label, leader, arc, and extension properties determine placement.
- **Editable placement objects.** An annotation Empty's transform is a user-facing placement offset from source-derived canonical geometry; synchronization preserves that offset when sources move.
- **Scene ownership.** Dimensions and construction objects belong to scene-owned collections and do not leak across scenes.
- **Blender-native data first.** Persistent objects remain inspectable, selectable, undoable, and saveable through normal Blender data.

## Current architecture

| Area | Responsibility |
| --- | --- |
| `anchors.py` | Assign persistent mesh point IDs and resolve vertex, object-local, and world anchors. |
| `area_binding.py` | Assign persistent face IDs, bind Area source sets, and calculate live world-space area. |
| `snapping.py`, `projected_snap.py` | Acquire and score targets; cache and depth-filter projected vertices. |
| `interaction.py` | Shared modal keys, numeric editing, and axis helpers. |
| `operators/` | Own annotation, measurement, guide, selection, and styling workflows. |
| `dimension_geometry.py` | Calculate world-space dimension geometry without viewport or operator state. |
| `drawing.py`, `viewport_state.py` | Draw overlays, hit-test annotations, and isolate transient state per viewport. |
| `scene_sync.py` | Synchronize annotation locations, repair proxies, migrate anchors, and invalidate caches. |
| `collections.py` | Enforce scene-owned collections and manage native measurement snap proxies. |
| `properties.py`, `ui.py` | Persist settings and expose scene and local editing. |
| `preferences.py` | Stores per-user interaction thresholds and defaults without changing Blender settings outside the add-on. |
| `units.py`, `volume.py` | Parse and format units and calculate evaluated closed-mesh volume. |
| `stroke_font.py`, `output_geometry.py`, `grease_pencil_output.py`, `operators/generate_output.py` | Build vector labels and world-space annotation stroke specs, then generate isolated, replaceable Grease Pencil output artifacts. |

Annotations are Empty objects with presentation properties and an annotation kind. Linear annotations use two measurement anchors. Live Areas store persistent face IDs in `dimensions_area_face_id`, source metadata, a cached value, and explicit Live/Captured/Needs Repair state. Two-edge Angles store four persistent endpoint anchors and derive a shared or virtual center. Vertex anchors store integer IDs in the mesh's `dimensions_anchor_id` point attribute. Angle arcs are generated in world space before viewport projection. A canonical source frame plus user presentation offset keeps annotation transforms editable. Guides and measurements are Empty objects in a separate collection.

### Generated output

The live overlay remains the editable source of truth. An explicit operator resolves visible or selected linear, angle, and valid Live or Captured area annotations into world-space stroke specifications, then creates separate Grease Pencil v3 objects in an exclusive scene-owned `Dimensions Output` collection. Areas in Needs Repair are skipped until their sources are repaired. Grease Pencil was chosen over curves or meshes because it is Blender's native stroke surface, remains editable, and is verified to render in EEVEE and Cycles. Generated objects disable Grease Pencil lighting and use 3D Location stroke depth; successful generation enables Depth and Grease Pencil data passes on the active view layer. A scene-owned object-pointer registry assigns persistent source keys without modifying annotation objects; regeneration replaces only the matching artifact, and the UI warns that hand edits are disposable. Existing user collections with the same display name are never adopted.

Camera Relative sizing converts configured render pixels to world units at each annotation's midpoint depth and is the default. World Scale sizing uses explicit scene-unit values. Labels use a bundled single-line vector font so text, tolerances, custom notes, degree signs, and squared-unit suffixes remain Grease Pencil strokes instead of introducing a second render-object type. Linear Inline, Above, Outside Start, Outside End, and custom-text ordering rules mirror the live overlay; angle rays/arcs and area leaders preserve their live world positions and presentation offsets. For a linear annotation whose endpoints share camera depth, camera-relative layout targets agreement within one output pixel. A perspective annotation spanning materially different depths uses the documented midpoint approximation. [OUT-04](tickets/OUT-04-angle-area-output.md) extends the same backend across all persistent annotation kinds.

### Saved-data schema

Each scene containing Dimensions data stores an integer schema version. `load_post` migrates older scenes exactly once per step; a scene from a newer schema is never modified and reports the version mismatch. Schema changes must add an idempotent migration and a fixture before release.

Add-on preferences are per-user defaults and interaction tuning. Scene and annotation settings travel with the file and win once set; changing an add-on preference never rewrites existing annotations.

| Schema | Introduced | Change |
| --- | --- | --- |
| 1 | 0.2.3 | Baseline schema; legacy vertex anchors receive persistent point IDs during `v0 → v1` migration. |
| 2 | 0.4.0 | Additive Grease Pencil output settings and scene-owned source registry; v1 files receive documented defaults without overwriting existing values, and incomplete registry bindings are discarded. |

## Interaction contract

- Hover supplies a target and direction; orange is active and blue is accepted.
- Annotation selection is an explicit `Dimensions Selection` WorkSpaceTool in Object Mode. Its click handler selects annotations and guides; misses fall through to Blender selection.
- Invocation shortcuts are registered as disabled add-on keymap entries. They are visible and editable in Add-on Preferences without claiming potentially conflicting defaults; the shared axis and confirm modal actions are registered in the Dimensions modal keymap.
- `A` selects aligned behavior; `X`, `Y`, and `Z` select global axes.
- Middle-mouse drag chooses a projected global axis after a start point exists; before that, middle mouse remains viewport navigation.
- Typed scene-unit distance can precede or follow an axis choice. `Enter` confirms the current valid stage.
- Creation tools use continuous placement by default. After each commit they retain the session axis and placement offset, clear per-annotation snaps and typed input, and return to their first stage. `Esc` or right-click exits a continuous session; changing mode or the active object ends it without leaking preview state. Users can disable continuous placement in add-on preferences to restore the step-back behavior.
- Active modal tools use a fixed, compact lower-corner badge showing only the tool, direction when applicable, and typed input while present. Shortcut and exit instructions stay in the README key reference instead of following the cursor or obscuring geometry.
- Dimension and measurement point acquisition works in Object and Mesh Edit Mode without modifying the mesh.
- The main Dimension command is selection-first in Edit Mode: exactly one selected edge commits a length immediately; other selections enter interactive point acquisition.
- Edit selection can create a length from one edge, an angle from any two non-parallel edges, or an area leader from one or more faces.
- Area creation has its own source and placement stages: Edit Mode consumes selected faces, while Object Mode acquires base-mesh faces before the user places the leader label.
- Angle and Area use dedicated Remake actions; linear anchor eyedroppers are not reused for their multi-source workflows.
- Angle binds two edges directly. Connected edges use their shared vertex; disconnected edges derive a virtual placement point from their supporting lines and expose smaller, supplementary, and reflex solutions explicitly.
- Modal tools keep their viewport work in Blender adapters, while point-placement stage transitions live in a pure state model covered by the background smoke suite. This protects the shared point, type, confirm, step-back, and cancel contract without synthetic window events.
- Every key above is rebindable. Blender refuses modal key-maps in an add-on key configuration, so the modal actions live in a private `Dimensions Modal` action map that is read through the *user* key configuration on each event; rebinding in the keymap editor therefore takes effect immediately, without a restart. Nothing Dimensions registers can shadow a Blender or Industry Compatible preset binding: invocation entries ship unbound and inactive, and the action map is never dispatched from by Blender. `DimensionsKeymapTests` in `tests/blender_smoke.py` enforces both properties.

## Measured performance

Numbers below are foreground-comparable background measurements taken on the maintainer's hardware: **AMD Ryzen 5 7520U (4 cores / 8 threads), 14 GB RAM, Ubuntu 26.04, Blender 5.2.0 LTS.** Both benchmarks generate their scenes deterministically, so runs are comparable across machines and across releases.

### Overlay draw cost — `tests/draw_benchmark.py`

Measures the per-frame CPU work the overlay performs before it uploads anything: locating annotations, resolving anchors, projecting to screen space, and laying out labels. `rebuild` invalidates the geometry cache every frame (worst case: something moved); `cached` is the steady state of a still view.

| Scene | Scene objects | Dimensions | Rebuild | Cached |
| --- | --- | --- | --- | --- |
| 10 cubes, 10 dimensions | 20 | 10 | 0.312 ms/frame | 0.095 ms/frame |
| 10,000 cubes, 10 dimensions | 10,010 | 10 | 0.310 ms/frame | 0.096 ms/frame |
| 500 dimensions (budget scene) | 510 | 500 | 17.35 ms/frame | 4.76 ms/frame |

Two results matter. Adding 10,000 non-annotation objects changes draw cost by 0.6% — draw now scales with annotation count, not scene size, because the loop iterates the Dimensions collection rather than `scene.objects`. And the documented budget of **500 visible dimensions at 30 fps or better** is met with headroom: 58 fps while rebuilding every annotation every frame, 210 fps in the steady state.

Annotations sharing a color and line width are drawn in one batch, so the common selected/unselected split collapses to roughly two GPU batches plus text regardless of annotation count. Font metrics are measured once per string and size, and label layout is cached per unchanged label and view.

### Projected snap cost — `tests/snap_benchmark.py`

`build` is the first query into a cold cache, `reproject` is a query after a pure view change (which must not rescan mesh data), and `query` is the steady state.

| Reference scene | Build | Reproject | Query |
| --- | --- | --- | --- |
| 10k vertices, 1 object | 35 ms | 21 ms | 0.013 ms |
| 100k vertices, 1 object | 380 ms | 306 ms | 0.013 ms |
| 100k vertices, 50 objects | 380 ms | 314 ms | 0.013 ms |
| 1M vertices, 10 objects | 4,886 ms | 3,729 ms | 0.013 ms |

The **under 8 ms per query** budget is met by a factor of roughly 600, at every density, in both Object and Edit Mode paths. Query cost is flat because the spatial grid bounds candidate count independently of scene size. The **under 100 ms to build the 1M-vertex source cache** budget is *not* met — see known risk 1 and [FND-11](tickets/FND-11-snap-cache-build-cost.md).

Set `DIMENSIONS_SNAP_PROFILE=1` for the add-on's own per-stage build, reproject, query, and occlusion timings. The instrumentation is inert when the variable is unset.

## Known risks

1. **Snap cache build cost on very dense scenes.** Query and draw costs are measured and within budget (see [Measured performance](#measured-performance)). Building the projected snap source cache is not: a 1M-vertex scene takes about 4.9 s because `_build_sources()` allocates one dictionary per vertex and projects each one individually. Caching around the outside cannot fix a per-vertex constant, so [FND-11](tickets/FND-11-snap-cache-build-cost.md) tracks replacing the per-vertex objects with bulk array reads. Scenes at or below 100k vertices build in under 0.4 s and are usable now.
2. **Duplicated anchor IDs.** Blender topology duplication may copy a point ID. Resolution chooses the candidate closest to the stored fallback coordinate.
3. **Face identity after topology duplication.** Live Areas use persistent face IDs. Missing, structurally changed, or duplicated identities intentionally enter Needs Repair instead of guessing; modifier-evaluated face correspondence is not yet defined.
4. **Snapshot output.** Renderable linear dimensions shipped in 0.4.0 and angle/area coverage in 0.4.1. Generated objects are snapshots and intentionally lose hand edits when regenerated; measurements and construction guides remain viewport/construction data.
5. **Proxy lifecycle.** Native measurement snap proxies clear transient caches on undo/redo and linked annotations are read-only. Background lifecycle tests cover save/reload, proxy repair, duplicate proxy cleanup, and visibility. Append/link, library override, and two-window foreground QA remain release requirements because Blender background mode cannot exercise them.

## Lifecycle behavior matrix

The expected result is shared across linear, angle, and area annotations, measurements and their snap proxies, and construction guides unless noted. `✓` means the binding survives; `Repair` means the annotation stays visible but declares the broken source; `Read-only` means Dimensions does not write linked data.

| Object type | Save/reload | Undo/redo | Duplicate | Delete source | Delete annotation | Append | Link | Move/copy scene | Library override |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Linear dimension | ✓ | ✓ | Copy shares sources | Repair | Deletes annotation | Current schema on first sync | Read-only | Scene-owned collection | Read-only |
| Angle dimension | ✓ | ✓ | Copy shares sources | Repair | Deletes annotation | Current schema on first sync | Read-only | Scene-owned collection | Read-only |
| Area dimension | ✓ | ✓ | Copy shares source faces | Needs Repair | Deletes annotation | Current schema on first sync | Read-only | Scene-owned collection | Read-only |
| Measurement | ✓ | ✓ | Copy has independent proxy | World anchors remain valid | Deletes proxy too | Current schema on first sync | Read-only | Scene-owned collection | Read-only |
| Measurement proxy | Recreated if absent | Recreated if absent | Parent-specific proxy | Recreated if parent remains | Deleted with parent | Never appended alone | Not edited | Recreated for owning scene | Read-only |
| Construction guide | ✓ | ✓ | Copy shares anchors | World anchors remain valid; mesh anchors repair | Deletes guide | Current schema on first sync | Read-only | Scene-owned collection | Read-only |

## Prioritized roadmap

The canonical ticket status, milestone rollup, and status legend live in the [work-ticket index](tickets/README.md). The items below explain priority and product direction; status labels use the same meanings as that index.

### Current delivery sequence

| Order | Work | Status | Outcome |
| --- | --- | --- | --- |
| 1 | 0.4.1 foreground and Blender 5.1 release QA | 🔍 Release QA | Validate direction preselection and all-kind output in a clean interactive install. |
| 2 | [OUT-04](tickets/OUT-04-angle-area-output.md) | ✅ Complete | Angle and area Grease Pencil generation delivered in 0.4.1. |
| 3 | [OUT-03](tickets/OUT-03-styles.md) | ⏭ Next | Add reusable named styles and unblock remaining presentation controls. |
| Parallel | [FND-11](tickets/FND-11-snap-cache-build-cost.md) | ⏭ Next | Bring the 1M-vertex projected snap-cache build within budget. |
| After OUT-03 | [DIM-04](tickets/DIM-04-presentation-controls.md) | 🟨 Partial | Complete the presentation controls beyond shipped ticks and manual Outside Start/End placement. |
| Later | [OUT-02](tickets/OUT-02-vector-export.md) | ⬜ Planned | Add scaled SVG/PDF output after generated output and styles stabilize. |

Early public feedback reinforces the product definition rather than expanding it: every request concerns faster annotation, clearer presentation, or usable output. None requires mesh authoring. The disposition is:

| User request | Decision | Roadmap placement |
| --- | --- | --- |
| Keep placing dimensions without leaving the tool | Accepted and delivered | [UX-01](tickets/UX-01-continuous-placement.md), delivered in 0.3.1 |
| Choose Auto/X/Y/Z once, place a group, then switch direction | Accepted and delivered with repeated placement | [UX-01](tickets/UX-01-continuous-placement.md), delivered in 0.3.1 |
| Render dimensions | Accepted and delivered for all annotation kinds | Linear [OUT-01](tickets/OUT-01-grease-pencil-output.md) in 0.4.0; angle and area [OUT-04](tickets/OUT-04-angle-area-output.md) in 0.4.1 |
| Replace arrows with architectural tick marks | Accepted and delivered | First slice of [DIM-04](tickets/DIM-04-presentation-controls.md), delivered in 0.3.2 with global and per-annotation controls |
| Keep numeric labels from growing | Existing behavior verified and documented | [UX-08](tickets/UX-08-stable-overlay-sizing.md), delivered in 0.3.1; any zoom- or transform-driven growth is a bug |

### P0 — Trustworthy acquisition and repeated placement

- ⬜ **Planned** — add an explicit rebind or convert-to-world action for users who need to override fallback anchor resolution.
- ⛔ **Blocked** — extend the Live/Captured/Needs Repair model with a guided repair picker and source highlighting in [UX-07](tickets/UX-07-guided-repair.md), after [UX-02](tickets/UX-02-annotation-manager.md).
- ⬜ **Planned** — add direct viewport handles for Angle radius and Area label placement in [UX-04](tickets/UX-04-direct-handles.md).
- ⬜ **Planned** — define evaluated-modifier semantics for live Area bindings.
- ⬜ **Planned** — give the canonical-frame and placement-offset model deliberate rotation and scale semantics.
- 🔍 **Release QA** — add foreground modal coverage for the constrained Area and two-edge Angle workflows.
- 🟨 **Partial** — dense-scene budgets and background tests exist; [FND-11](tickets/FND-11-snap-cache-build-cost.md) and foreground modal-event coverage remain.
- 🔍 **Release QA** — complete foreground lifecycle QA for measurement proxies and annotations.

### P1 — Renderable output, precision inference, and management

- ✅ **Complete** — extend the shipped linear Grease Pencil path to angle and area annotations in [OUT-04](tickets/OUT-04-angle-area-output.md), delivered in 0.4.1.
- ⬜ **Planned** — add local-axis, parallel, perpendicular, extension, intersection, and active-plane inference in [UX-03](tickets/UX-03-inference-engine.md).
- ⬜ **Planned** — add search, rename, select, hide, isolate, repair, and bulk style operations in [UX-02](tickets/UX-02-annotation-manager.md).
- ⬜ **Planned** — add temporary hover measurement with delta X/Y/Z in [UX-06](tickets/UX-06-hover-measurement.md).
- ⬜ **Planned / blocked by sequence** — start construction with [CON-01](tickets/CON-01-guide-points.md); `CON-02` through `CON-04` follow its dependency chain.

### P2 — Documentation-grade dimensions

- ⬜ **Planned** — extend true/global-axis projected length with local-axis and view-plane modes through [UX-03](tickets/UX-03-inference-engine.md).
- ⬜ **Planned** — add chain, baseline, radial, diameter, arc-length, coordinate, and elevation dimensions in [DIM-01](tickets/DIM-01-chain-baseline.md), [DIM-02](tickets/DIM-02-radial-diameter-arc.md), and [DIM-03](tickets/DIM-03-coordinate-elevation.md).
- 🟨 **Partial** — architectural ticks shipped in 0.3.2 and manual Outside Start placement in 0.4.1; extension gaps, overshoot, arrow variants, automatic tight-space layout, alignment, and dual units remain in [DIM-04](tickets/DIM-04-presentation-controls.md).
- ⬜ **Planned** — add scaled SVG and PDF export in [OUT-02](tickets/OUT-02-vector-export.md) after generated output and styles stabilize.

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
- foreground viewport checks for selection, visibility, native measurement snapping, unit display, and broken anchors;
- tests on the declared Blender 5.1 and 5.2 targets; and
- snap performance checks on representative dense scenes.
