# Dimension and Measurement Tools Improvement Plan

## Goal

Make Dimensions a trustworthy inspection and documentation tool rather than a collection of viewport labels. Every persistent annotation should answer four questions:

1. What geometry is being measured?
2. Is the displayed value live or intentionally captured?
3. Can the annotation be placed and styled without changing its measurement?
4. Can the user tell when its source is missing, ambiguous, or invalid?

Area and Angle are the first priority because their current data and drawing models do not meet that standard.

## Current diagnosis

### Area

- The command is available only from selected Edit Mode faces.
- It calculates a correct combined world-space area at creation time, but persists only the resulting number.
- The two saved anchors describe the leader position, not the measured faces.
- Geometry edits, modifiers, and topology changes cannot update or validate the value.
- The area label cannot show which faces contribute to the result, and its leader placement is not directly editable.

This makes Area a captured note, not a persistent dimension.

### Angle

- The command requires exactly two selected, connected Edit Mode edges.
- Its three vertex anchors keep the numeric angle live, but there is no interactive three-point workflow.
- The arc is constructed as a fixed-size circle in screen space between projected rays. It is not a projected world-space arc, so perspective can make the graphic misleading.
- There is no editable radius, arc side, minor/reflex choice, extension control, or anchor editing in the sidebar.
- Degenerate or missing inputs disappear instead of presenting a repairable invalid state.

This makes Angle difficult to create, visually unreliable, and effectively uneditable.

## Product decisions

### Live and captured measurements are explicit

- New Area annotations are **Live** by default and retain a binding to their source face set.
- A user can deliberately convert a live Area to **Captured** when a historical value is wanted.
- Migrated legacy Areas remain Captured and are labeled as such until rebound.
- The selected-dimension panel shows `Live`, `Captured`, or `Needs Repair`; stale values are never presented as if they are current.

### Measurement geometry and presentation are separate

- Source anchors and face bindings define the measured value.
- Presentation properties define leader elbow, label offset, angle radius, arc side, text placement, arrows, and extension lines.
- Moving a label or arc must not alter the measured geometry.

### Invalid annotations remain visible and repairable

- Deleted, duplicated, or incompatible source geometry produces a visible `Needs Repair` state.
- The last valid value may be shown with a stale indicator, but never as an unqualified current value.
- Rebind, convert to captured/world anchors, and delete are explicit actions.

## Area redesign

### Persistent source model

Add a face-set binding owned by the Area annotation:

- source mesh object;
- stable face IDs stored in a mesh face-domain integer attribute;
- fallback per-face center, normal, area, and vertex-count signature for migration and ambiguity handling;
- evaluation mode: `BASE_MESH` initially, with `EVALUATED` added only when modifier semantics and performance are defined;
- aggregation mode: `SURFACE_AREA` initially, leaving room for `PROJECTED_AREA` later;
- cached last valid area and binding status.

Face IDs should follow the same principle as point IDs, but face duplication must not silently choose a result. When a duplicated or missing ID cannot be resolved confidently, the annotation becomes `Needs Repair`.

### Creation and editing workflow

1. Select one or more faces and choose **Area Dimension**.
2. Preview the contributing faces with a restrained tint and preview the live value.
3. Click to place the label; optional second click places a leader elbow.
4. After creation, drag the label or elbow independently of the face binding.
5. From the sidebar, use **Select Source Faces**, **Rebind from Selection**, **Capture Value**, or **Repair**.

The first release should support one mesh object per Area. Multi-object aggregation can follow after its ownership and edit-mode interaction are tested.

### Area presentation

- Leader styles: none, straight, and elbow.
- Optional boundary highlight while selected or hovered.
- Label can include a name, area, face count, and live/captured status.
- Surface and projected area must use distinct labels and symbols when projected area is introduced.

## Angle redesign

### Measurement modes

Support these modes in order:

1. **Three Point**: ray point, vertex, ray point; usable in Object and Edit Mode.
2. **Two Connected Edges**: fast selection-based creation using the shared vertex.
3. **Two Directions**: parallel-translated or disconnected edges, using their directions and an explicit placement vertex.
4. **Dihedral**: angle between two face normals, clearly distinguished from a planar three-point angle.

The first implementation milestone needs Three Point and Two Connected Edges. Disconnected directions and dihedral angles should not be squeezed into the same ambiguous command.

### Correct world-space geometry

- Define the measurement plane from the two normalized world-space rays.
- Generate the arc in that plane at an editable world-space radius, then project the arc points for overlay drawing.
- Store an arc-side vector so the chosen placement remains stable when the view changes.
- Support `MINOR`, `MAJOR`, and `REFLEX` display, plus a **Flip Arc** action.
- Provide configurable extension gaps and overshoot.
- Keep label placement attached to the arc midpoint by default, with a separate text offset.

For nearly collinear or zero-length rays, retain the annotation in `Needs Repair` state and explain the invalid input.

### Creation and editing workflow

1. Choose **Angle Dimension** and pick the vertex first.
2. Pick the first and second ray points with the shared snapping and inference system.
3. Move to set radius and arc side; click to commit.
4. Edit vertex, ray anchors, radius, arc mode, flip, text offset, and style from the sidebar or viewport handles.

Selection-first creation remains a shortcut, but it should enter the same placement stage instead of committing an unplaced fixed-size annotation.

## Unified dimension workflow

Replace the current split between a generic linear command and hidden selection-only commands with visible dimension modes:

- Linear
- Angle
- Area
- Radius
- Diameter
- Arc Length
- Coordinate / Elevation

The main panel may remember the last-used mode. Edit Mode selection can prefill a compatible mode, but it should not unexpectedly commit before the user can preview placement. Tooltips and status text must state the required picks and current stage.

All modes share:

- snapping, inference, numeric entry, step-back, and cancel behavior;
- hover and accepted-source highlighting;
- a placement stage separate from source acquisition;
- explicit binding health;
- local style overrides and consistent hit testing.

## Broader measurement improvements

### Precision and inspection

- Temporary hover measurement with distance, delta X/Y/Z, angle, and optional face area.
- True/aligned, global-axis projected, local-axis projected, and view-plane distance modes.
- Local-axis, parallel, perpendicular, extension, intersection, center, and tangent inference with a visible lock.
- Configurable precision, trailing-zero policy, rounding, dual units, prefix/suffix, nominal value, plus/minus or limit tolerances.
- Coordinate and elevation annotations relative to world, 3D Cursor, object origin, or a named datum.

### Documentation dimension types

- Chain and baseline dimensions with shared placement and spacing.
- Radius, diameter, arc length, and center marks for circular geometry.
- Overall and bounding-box dimensions for selected objects or mesh elements.
- Ordinate dimensions and repeated/equal-spacing annotations.

### Management and output

- Scene annotation manager with search, rename, type and status filters, select, hide, isolate, repair, delete, and bulk style actions.
- Named style presets with per-annotation overrides and a clear reset path.
- Annotation sets/layers for design alternatives, views, sheets, or export groups.
- Copy/paste style and duplicate/rebind workflows.
- Render/export path through generated curves/text or vector output after viewport behavior is stable.

## Delivery plan

### Implemented in 0.2.0

- Live base-mesh face-set Area bindings with persistent face IDs and automatic world-space recalculation.
- Explicit Live, Captured, and Needs Repair states, legacy Area migration, source-face selection, rebind, and capture actions.
- True world-space Angle arcs with editable radius, minor/reflex display, three-point creation, and all three anchor controls.
- True and global X/Y/Z projected linear distance modes.
- Per-annotation prefixes, suffixes, symmetric tolerances, and upper/lower deviations.

The 0.2.0 three-point Angle workflow was superseded by the persistent two-edge workflow in 0.3.0.

### Implemented in 0.2.1

- Replaced Angle's linear anchor-eyedropper editor with a dedicated Remake Angle workflow.
- Added dedicated Area creation in Object and Mesh Edit Mode.
- Added an Area placement stage so creation no longer commits an automatically positioned label.
- Added Move Label and Remake Area actions plus a Select Source Faces / Apply Faces replacement workflow.
- Made live Area drawing evaluate its bound faces directly so viewport values and leader origins update during geometry edits.
- Added Object Mode face binding and geometry-change regression coverage.

Direct Area/Angle viewport handles, evaluated-modifier Areas, multi-object Areas, richer repair guidance, and the later dimension types below remain planned.

### Revised placement and edge-angle direction

The next interaction revision should make the annotation Empty a user-editable placement object instead of a synchronization cache.

- Measurement sources calculate a canonical origin and orientation.
- The Empty's local translation is a persistent presentation offset from that canonical frame.
- Moving the Empty moves the dimension line, Area tag, or angle arc while extension/leader lines remain attached to source geometry.
- Source-object transforms move the canonical frame and preserve the user's local presentation offset.
- Synchronization must distinguish source-driven canonical movement from user-driven annotation transforms rather than overwriting both.
- Overlay text remains screen-facing; Empty rotation and scale should not silently distort text. Translation is the first supported transform, with explicit rotation/scale semantics deferred.

Area placement should consume the shared placement controls used by Linear dimensions:

- `A`, `X`, `Y`, and `Z` constrain the leader/tag direction;
- typed scene-unit distance sets the tag offset;
- pointer placement remains available when no axis or numeric distance is locked;
- Move Label and creation use the same placement engine and persisted offset model.

Angle acquisition should use two edges as its primary source model:

- Each edge retains two persistent vertex anchors, allowing either edge to update dynamically as its endpoints or owning object transform changes.
- Connected edges place the arc at their shared vertex and orient both rays away from it.
- Intersecting disconnected edges place the arc at the virtual intersection of their infinite supporting lines.
- Skew non-intersecting 3D edges measure their directions and place the arc at the midpoint of the closest points between their supporting lines.
- Parallel edges produce a zero/parallel state rather than an invented arc.
- The selected-dimension panel exposes **Replace Edge A**, **Replace Edge B**, and **Remake Angle**; it does not expose point-anchor eyedroppers.
- Source acquisition and arc placement remain separate stages.

Because two undirected disconnected edges do not uniquely define an interior sector, the default should be the smaller direction angle, with explicit **Supplement** and **Reflex** choices. Connected edges may preserve their natural included angle from the shared vertex.

### Implemented in 0.3.0

- Annotation synchronization now preserves user translation as a presentation offset from source-derived canonical geometry.
- Moving Linear and Area Empties adjusts presentation without detaching measurement sources; later source movement preserves the offset.
- Area creation and Move Label now accept `A`, `X`, `Y`, and `Z` plus typed scene-unit distance.
- Constrained live Area labels preserve their direction and distance as the measured face center changes.
- Angle creation now acquires two edges instead of a vertex and two ray points.
- Two-edge bindings retain four persistent endpoint anchors and update after vertex or owning-object transforms.
- Connected edges use their shared vertex; intersecting and skew disconnected edges derive a virtual center from closest points on their supporting lines.
- Minor, Supplement, and Reflex solutions are explicit.
- Replace Edge A and Replace Edge B update one source independently while preserving the other edge and local presentation.

### Phase 0: Trust and repairability

- Add binding-health state and visible invalid/stale presentation.
- Replace Angle screen-space construction with a world-space arc.
- Add editable angle radius, minor/reflex mode, flip, and three anchor controls.
- Add live face-set Area bindings for base-mesh faces.
- Add Area rebind, select-source, and convert-to-captured actions.
- Migrate legacy Areas as explicitly Captured.

### Phase 1: Usable creation and placement

- Add interactive three-point Angle creation.
- Add preview and placement stages to selection-created Angle and Area.
- Add draggable angle radius, area label, and leader elbow handles.
- Unify tool mode selection and contextual instructions.

### Phase 2: Precision toolset

- Add projected/local-axis lengths, temporary inspection HUD, and richer inference.
- Add radius, diameter, arc length, coordinate, and elevation dimensions.
- Add tolerance, dual-unit, and expanded text/line style controls.

### Phase 3: Documentation workflow

- Add chain, baseline, ordinate, and repeated dimensions.
- Add the scene annotation manager, annotation sets, and style presets.
- Add a tested vector or renderable export path.

## Acceptance criteria

### Area

- Editing a bound face updates its area without recreating the annotation.
- Object rotation and non-uniform scale produce the correct world-space surface area.
- Adding or removing a source face through an explicit rebind updates the binding and value.
- Missing or duplicated face identity produces `Needs Repair`, not a silently stale live value.
- Legacy snapshot Areas load as Captured with their original value.
- Label and leader placement can change without changing the source binding.

### Angle

- Three arbitrary snapped points can create an angle in Object or Edit Mode.
- A selection-created angle reaches a placement preview before commit.
- The displayed arc is a projection of the measured world-space plane and remains consistent while orbiting the view.
- Radius, arc side, and minor/reflex choice survive save/reload and undo/redo.
- Moving any bound source vertex updates the value and arc.
- Degenerate or missing rays remain selectable and report `Needs Repair`.

### Regression and performance

- Background tests cover geometry math, source migration, live updates, invalid states, formatting, and save/reload.
- Foreground tests cover modal stages, handles, hit testing, view changes, undo/redo, and repair actions.
- Dependency-graph updates are filtered to relevant source meshes; large face sets use cached aggregation and have a documented performance budget.

## Recommended implementation order

Do not begin with additional dimension types. First land the shared binding-status model and presentation/source separation, then rebuild Angle, then rebuild Area. Angle is the smaller vertical slice and will prove the placement and repair UI. Area then adds the more difficult persistent face-set binding. New radius, diameter, chain, and export work should build on those verified foundations.
