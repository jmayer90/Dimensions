# OUT-03 — Named, reusable annotation styles

**Milestone:** M4 Output
**Status:** ⏭ Next — follows the completed `OUT-04` output coverage.
**Effort:** M
**Depends on:** FND-02
**Version impact:** Patch, provided existing per-annotation properties keep working.

## Problem

Styling is currently two levels: a global style in `CADDIM_PG_SceneSettings`, and per-annotation overrides. `operators/style.py` provides **Reset to Global**, **Set All Dimensions**, and **Copy to Global**.

This breaks down as soon as a scene needs more than one look, which is most real work:

- Structural dimensions in one color and detail dimensions in another.
- Reference dimensions in a lighter weight than controlling ones.
- Larger text on an overview sheet than on a detail sheet.

With only global-plus-override, achieving that means setting overrides on every annotation individually, and changing your mind means doing it again. **Set All Dimensions** is all-or-nothing.

This becomes more pressing with `OUT-01` and `OUT-02`: producing drawings makes consistent, switchable presentation a requirement rather than a nicety, and `DIM-04` adds more style properties to manage.

## Why it matters for 1.0

Not a 1.0 gate item, but it is the difference between output that looks made and output that looks drafted. It also prevents the per-annotation property set from becoming unmanageable as `DIM-04` expands it.

## Approach

**Styles as datablocks or as a scene collection?** Recommend a `CollectionProperty` of style property groups on the scene, with annotations referencing a style by name or index. Simpler than custom ID datablocks, travels with the file, and works with Blender's existing UI patterns. The trade-off — styles cannot be linked between files without appending the scene — should be recorded; if cross-file style libraries become important, that is a later migration.

**Three-level resolution, documented precisely:** annotation override → assigned style → scene default. Each property resolves independently, so an annotation can override color while inheriting everything else from its style. Make "inherited" versus "overridden" visible in the UI, because a user who cannot tell which is which will be confused when a style change does not take effect.

**Migration.** Existing annotations have per-annotation values that may be deliberate overrides or may be untouched defaults. Distinguishing them is not always possible. Take the safe path: treat all existing values as explicit overrides so nothing changes appearance on upgrade, and provide a "clear overrides and inherit" action so users can opt into styles. Coordinate with `FND-02` — this is a schema change requiring a migration step.

**Operations:** create, duplicate, rename, delete a style; assign to selected annotations; assign by filter using `UX-02`'s filtering; and "select all annotations using this style." Deleting a style must reassign its users to the default rather than leaving dangling references.

**Style properties:** color, selected color, line width, text size, precision, arrow size and variant, prefix and suffix, tolerance display, unit format. Essentially the presentation half of `CADDIM_PG_Dimension`. Keep source and binding properties out — the source/presentation separation invariant applies here directly.

## Acceptance criteria

- [ ] Named styles can be created, duplicated, renamed, and deleted.
- [ ] Annotations reference a style, and resolution is annotation override → style → scene default, per property.
- [ ] The UI distinguishes inherited from overridden values on each property.
- [ ] An action clears an annotation's overrides so it fully inherits its style.
- [ ] Changing a style updates every inheriting annotation immediately in all viewports.
- [ ] Styles can be assigned to a selection, and to a filtered set via `UX-02`.
- [ ] "Select all annotations using this style" works.
- [ ] Deleting a style reassigns its users to the default; no dangling references.
- [ ] Existing annotations upgrade with unchanged appearance.
- [ ] The schema change ships with an `FND-02` migration step and a fixture test.
- [ ] Existing `style.py` operators keep working or have documented replacements.
- [ ] Style resolution does not regress the `FND-03` draw budget — resolve once per annotation per invalidation, not per property per frame.
- [ ] README and `DESIGN.md` document the three-level model.

## Code map

- `dimensions/properties.py` — style property group, scene collection, annotation reference, `CADDIM_PG_SceneSettings`.
- `dimensions/operators/style.py` — existing operators to extend.
- `dimensions/drawing.py` — `_annotation_style()`, the resolution point.
- `dimensions/ui.py` — style list and inherited/overridden presentation.
- `dimensions/migrations.py` — the migration step.

## Verification

- Resolution tests for every combination of override, style value, and default present or absent.
- A test that changing a style updates inheriting annotations and leaves overriding ones alone.
- A test that deleting a style leaves no dangling references.
- A migration test using an `FND-02` fixture asserting appearance is byte-identical before and after upgrade.
- A draw-cost check confirming resolution is not per-frame.

## Out of scope

- Cross-file style libraries. Note the limitation; revisit if demand appears.
- Per-view or per-camera style switching. Interesting for drawing sheets; separate ticket.
- Styles for guides and measurements. Same pattern, follow-up ticket.

## Invariants

- **Source/presentation separation.** Styles carry presentation only; nothing about bindings or sources belongs in a style.
- **Stable presentation.** A style change must never alter an annotation's value, only its appearance.
