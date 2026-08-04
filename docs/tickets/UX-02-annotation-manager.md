# UX-02 — Annotation manager: list, search, isolate, repair, restyle

**Milestone:** M2 Fluency
**Effort:** L
**Depends on:** —
**Version impact:** Patch.

## Problem

Annotations are only reachable by clicking them in the viewport or finding them in the outliner among everything else. `ui.py` draws properties for the **selected** annotation and offers global style operators, but there is no view of what exists.

Once a scene has thirty annotations this breaks down:

- No way to find a specific one without hunting the viewport.
- No way to see which annotations are in a **Needs Repair** state. The state model exists and is carefully maintained, but a user has to click each annotation to discover its state — so the feature effectively does not reach them.
- No way to hide or isolate a subset. Annotating a detail means every other dimension is in the way.
- No bulk operations. Changing precision on twenty dimensions is twenty selections.
- No way to tell which annotations reference a given object.

This is listed as unimplemented in the README and as P1 in the roadmap.

## Why it matters for 1.0

Listed in the 1.0 gate under user control. It is also what makes the Live/Captured/Needs Repair model and the per-annotation styling actually usable — both are built and both are currently hard to reach.

## Approach

**A `UIList` panel in the Dimensions sidebar tab.** Blender users know this pattern from modifiers, vertex groups, and shape keys. Prefer it over a separate editor type or popup.

Per row: an icon for annotation kind, the name, the current value, and a state indicator. Make repair state visually loud — an alert icon in the row is the entire point.

**Filtering and search.** `UIList` provides `filter_name` and sorting for free. Add custom filter toggles for kind (linear, angle, area, measurement, guide) and state (live, captured, needs repair). Add "annotations referencing the active object" as a filter, since that is a common question.

**Selection sync, both directions.** Clicking a row selects the annotation in the scene; selecting in the viewport highlights the row. Use the existing selection mechanism from `FND-01`, not a parallel model.

**Per-row and bulk actions.** Per-row: select, rename, toggle visibility, delete, jump to (frame the view on it). Bulk, applied to filtered or selected rows: show, hide, isolate, delete, apply style, reset style to global.

**Isolate.** Hide every annotation except the selection, with a clear way back. Store what was hidden so exiting isolate restores prior visibility rather than showing everything.

**Repair entry point.** Rows in a repair state get an action that hands off to `UX-07`. Until that lands, the action can select the annotation and its source object, which is already useful.

## Acceptance criteria

- [ ] A `UIList` panel lists every annotation and guide in the scene, grouped or filterable by kind.
- [ ] Each row shows kind, name, current value, and state, with repair states visually distinct.
- [ ] Search by name filters the list.
- [ ] Filter toggles exist for kind, state, and "references the active object."
- [ ] Clicking a row selects the annotation; viewport selection highlights the row.
- [ ] Per-row select, rename, visibility toggle, delete, and jump-to all work.
- [ ] Bulk show, hide, isolate, delete, apply style, and reset style operate on the filtered or selected set.
- [ ] Isolate restores prior visibility on exit, not blanket visibility.
- [ ] The list stays correct as annotations are created, deleted, or renamed, including from outside the panel.
- [ ] Every bulk operation is a single undo step.
- [ ] Performance is acceptable with 500 annotations — the list must not rebuild per redraw.
- [ ] README limitations no longer claim there is no annotation manager.

## Code map

- `dimensions/ui.py` — the panel and `UIList` subclass.
- `dimensions/operators/` — a new module for manager operators (isolate, bulk visibility, jump-to, rename).
- `dimensions/operators/style.py` — existing bulk style operators to reuse rather than duplicate.
- `dimensions/collections.py` — the source of truth for enumerating annotations.
- `dimensions/properties.py` — a scene-level property for isolate state and list index.

## Verification

- Tests for filtering, including combined filters.
- A test that bulk operations produce one undo step.
- A test that isolate/exit restores exactly the prior visibility state, including annotations already hidden before isolate.
- A test that the list reflects annotations created or deleted outside the panel.

## Out of scope

- Guided repair workflow — `UX-07`. This ticket surfaces repair state and provides the entry point.
- Named style presets — `OUT-03`. Bulk style here means applying the existing global style.
- A dedicated editor type. A sidebar panel is the right scope.

## Invariants

- **Blender-native data first.** Visibility uses Blender's own object visibility, and selection goes through the view layer. Do not introduce a private visibility model that the outliner disagrees with.
- **Truthful state.** The list must show current state, not a cached value computed when the row was drawn.
