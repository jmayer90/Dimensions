# Work tickets

Structured, self-contained tickets on the path to 1.0. Each is written so that a contributor — or a coding agent — can pick it up without reconstructing context from the commit history.

Read [../VERSIONING.md](../VERSIONING.md) first for how this work maps to version numbers, and [../DESIGN.md](../DESIGN.md) for the design invariants every ticket must respect.

## How to work a ticket

1. Read the ticket end to end, including **Out of scope** and **Invariants**. The out-of-scope section is load-bearing: it is where past attempts went wrong.
2. Read the files listed under **Code map**. They are a starting point, not an exhaustive list.
3. Work only that ticket. If you find an unrelated problem, note it in the PR rather than fixing it inline.
4. Satisfy every **Acceptance criterion**. They are written to be checkable, not aspirational.
5. Add the tests named under **Verification**. `scripts/validate.ps1` must pass.
6. Update docs per [../../CONTRIBUTING.md](../../CONTRIBUTING.md) — always a `CHANGELOG.md` entry, plus README limitations and DESIGN risks where they change.
7. Apply the version policy. Most tickets are patches; the ones that are not say so in **Version impact**.

## Status

Tickets do not carry a status field — GitHub issues are the source of truth for what is in progress. These files define the work; the tracker tracks it.

## Index

### M1 — Foundation

Invisible to users, blocking for everything else. Build here before building on top.

| ID | Title | Effort | Depends on |
| --- | --- | --- | --- |
| [FND-01](FND-01-selection-architecture.md) | Replace the always-on click-select modal | L | — |
| [FND-02](FND-02-schema-versioning.md) | Saved-data schema versioning and migration | L | — |
| [FND-03](FND-03-draw-performance.md) | Make draw cost scale with annotations, not scene size | M | — |
| [FND-04](FND-04-addon-preferences.md) | Add-on preferences | M | — |
| [FND-05](FND-05-keymaps.md) | Registered, customizable keymaps | M | FND-01, FND-04 |
| [FND-06](FND-06-modal-testing.md) | Make modal operators testable, then test them | L | — |
| [FND-07](FND-07-lifecycle-hardening.md) | Lifecycle hardening: undo, append, link, multi-scene | M | FND-02 |
| [FND-08](FND-08-snap-performance.md) | Snap performance budgets on dense scenes | M | — |
| [FND-09](FND-09-posix-scripts.md) | Cross-platform build and validate scripts | S | — |
| [FND-10](FND-10-error-reporting.md) | Consistent, actionable error reporting | S | — |

M1 is complete. [FND-11](FND-11-snap-cache-build-cost.md) was filed out of `FND-08`: query and draw budgets are met and measured, but building the projected snap cache on a 1M-vertex scene misses its budget. It carries into M2 rather than blocking M1, because scenes at or below 100k vertices are within budget today.

### M2 — Fluency

The difference between a tool that works and one people keep using.

| ID | Title | Effort | Depends on |
| --- | --- | --- | --- |
| [UX-01](UX-01-continuous-placement.md) | Continuous placement — keep dimensioning without re-invoking | M | — |
| [UX-02](UX-02-annotation-manager.md) | Annotation manager: list, search, isolate, repair, restyle | L | — |
| [UX-03](UX-03-inference-engine.md) | Inference: parallel, perpendicular, extension, intersection, local axis | L | FND-08 |
| [UX-04](UX-04-direct-handles.md) | Direct viewport handles for placement, radius, and offset | M | FND-01 |
| [UX-05](UX-05-snap-control.md) | User control over which snap targets are active | S | FND-04 |
| [UX-06](UX-06-hover-measurement.md) | Transient hover measurement with delta X/Y/Z | M | — |
| [UX-07](UX-07-guided-repair.md) | Guided repair for broken anchors and area bindings | M | UX-02 |

### M3 — Construction

Snapping lines and points as a first-class way to build dimensionally, not just to annotate.

| ID | Title | Effort | Depends on |
| --- | --- | --- | --- |
| [CON-01](CON-01-guide-points.md) | Guide points | M | — |
| [CON-02](CON-02-offset-guides.md) | Offset and parallel guides at a typed distance | M | CON-01 |
| [CON-03](CON-03-guide-planes.md) | Guide planes and an active construction plane | L | CON-02 |
| [CON-04](CON-04-angular-guides-spacing.md) | Angular guides and repeated spacing | M | CON-02 |

### M4 — Output

| ID | Title | Effort | Depends on |
| --- | --- | --- | --- |
| [OUT-01](OUT-01-grease-pencil-output.md) | Render path via generated Grease Pencil | L | FND-03 |
| [OUT-02](OUT-02-vector-export.md) | SVG and PDF vector export | L | OUT-01 |
| [OUT-03](OUT-03-styles.md) | Named, reusable annotation styles | M | FND-02 |

### M5 — Documentation-grade dimensions

| ID | Title | Effort | Depends on |
| --- | --- | --- | --- |
| [DIM-01](DIM-01-chain-baseline.md) | Chain and baseline dimensions | M | UX-01 |
| [DIM-02](DIM-02-radial-diameter-arc.md) | Radial, diameter, and arc-length dimensions | M | — |
| [DIM-03](DIM-03-coordinate-elevation.md) | Coordinate and elevation dimensions | M | — |
| [DIM-04](DIM-04-presentation-controls.md) | Extension gaps, arrow variants, dual units, alignment | M | OUT-03 |

## Suggested order

`FND-02` and `FND-01` first — schema versioning becomes more expensive with every release that ships without it, and `FND-01` is the architectural decision the most other work sits on. `FND-03` pairs naturally with `OUT-01` later. `UX-01` is small, highly visible, and a good early win once `FND-06` gives it test coverage.

## Effort key

**S** — a focused session. **M** — a substantial change across a few modules. **L** — a design decision plus implementation; worth writing the approach down before starting.
