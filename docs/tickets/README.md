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

This index and each ticket header carry the durable delivery status. GitHub issues may track active discussion and assignments, but they do not override the repository status recorded here.

| Status | Meaning |
| --- | --- |
| ✅ **Complete** | Shipped and covered by the documented release evidence. |
| 🟨 **Partial** | A useful slice shipped, but the ticket still has remaining scope. |
| ⏭ **Next** | Not shipped; selected for the next delivery phase. |
| ⬜ **Planned** | Accepted roadmap work that has not started. |
| ⛔ **Blocked** | Accepted work waiting on an incomplete dependency. |
| 🔍 **Release QA** | Implemented work awaiting interactive or compatibility verification; used for release gates rather than ticket delivery state. |

Acceptance checkboxes inside a ticket define its intended scope; they are not maintained as a second status tracker. Use the ticket's **Status** header and this index to determine delivery state.

### Milestones at a glance

| Milestone | Status | Delivered | Remaining |
| --- | --- | --- | --- |
| M1 — Foundation | ✅ Complete | `FND-01` through `FND-10`; expanded `FND-07` background matrix and two-window foreground QA completed in 0.4.2 | — |
| M2 — Fluency | ✅ Complete | `UX-01`, `UX-08` in 0.3.1; `FND-11`, `UX-02`, `UX-03`, `UX-05`, `UX-07` in 0.4.2; `UX-04`, `UX-06`, `UX-09` in 0.4.3; final foreground QA in the 0.6.0 candidate | — |
| M3 — Construction | ✅ Complete | `CON-01`, `CON-02` in 0.4.3; validated `CON-03` and `CON-04` in 0.5.0 | — |
| M4 — Output | ✅ Complete | Render/vector output through `OUT-04`; single-sheet `OUT-05` in 0.6.0 | — |
| M5 — Documentation-grade | ✅ Complete | Architectural ticks in 0.3.2; Outside Start placement in 0.4.1; `DIM-01`, `DIM-02`, `DIM-04` in 0.4.3; validated `DIM-03` in 0.5.0 | — |

## Index

### M1 — Foundation

Invisible to users, blocking for everything else. Build here before building on top.

| ID | Title | Status | Delivered | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| [FND-01](FND-01-selection-architecture.md) | Replace the always-on click-select modal | ✅ Complete | 0.3.0 | L | — |
| [FND-02](FND-02-schema-versioning.md) | Saved-data schema versioning and migration | ✅ Complete | 0.3.0 | L | — |
| [FND-03](FND-03-draw-performance.md) | Make draw cost scale with annotations, not scene size | ✅ Complete | 0.3.0 | M | — |
| [FND-04](FND-04-addon-preferences.md) | Add-on preferences | ✅ Complete | 0.3.0 | M | — |
| [FND-05](FND-05-keymaps.md) | Registered, customizable keymaps | ✅ Complete | 0.3.0 | M | FND-01, FND-04 |
| [FND-06](FND-06-modal-testing.md) | Make modal operators testable, then test them | ✅ Complete | 0.3.0; Chain/Baseline, Spacing, and datum acquisition expanded in 0.6.0 candidate | L | — |
| [FND-07](FND-07-lifecycle-hardening.md) | Lifecycle hardening: undo, append, link, multi-scene | ✅ Complete | Background path in 0.3.0; expanded matrix/foreground QA in 0.4.2; query-write hardening in 0.6.0 candidate | M | FND-02 |
| [FND-08](FND-08-snap-performance.md) | Snap performance budgets on dense scenes | ✅ Complete | 0.3.0 | M | — |
| [FND-09](FND-09-posix-scripts.md) | Cross-platform build and validate scripts | ✅ Complete | 0.3.0 | S | — |
| [FND-10](FND-10-error-reporting.md) | Consistent, actionable error reporting | ✅ Complete | 0.3.0 | S | — |

M1 is complete. `FND-07` covers append, link, library overrides, actual undo/redo, deletion, duplication, and two-scene synchronization in Blender 5.2 background tests, plus foreground isolation across two main windows. [FND-11](FND-11-snap-cache-build-cost.md), carried from `FND-08`, now meets its build, reprojection, and query budgets through bulk arrays and compact viewport indexing.

### M2 — Fluency

The difference between a tool that works and one people keep using.

| ID | Title | Status | Delivered | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| [FND-11](FND-11-snap-cache-build-cost.md) | Bring projected snap-cache build within budget | ✅ Complete | 0.4.2 | M | FND-08 |
| [UX-01](UX-01-continuous-placement.md) | Continuous placement with a persistent Auto/X/Y/Z session mode | ✅ Complete | 0.3.1 | M | — |
| [UX-02](UX-02-annotation-manager.md) | Annotation manager: list, search, isolate, repair, restyle | ✅ Complete | 0.4.2; redraw/repair routing hardened in 0.6.0 candidate | L | — |
| [UX-03](UX-03-inference-engine.md) | Inference: parallel, perpendicular, extension, intersection, local axis | ✅ Complete | 0.4.2 | L | FND-08 |
| [UX-04](UX-04-direct-handles.md) | Direct viewport handles for placement, radius, and offset | ✅ Complete | 0.4.3 | M | FND-01 |
| [UX-05](UX-05-snap-control.md) | User control over which snap targets are active | ✅ Complete | 0.4.2; foreground QA in 0.6.0 candidate | S | FND-04 |
| [UX-06](UX-06-hover-measurement.md) | Transient hover measurement with delta X/Y/Z | ✅ Complete | 0.4.3 | M | — |
| [UX-07](UX-07-guided-repair.md) | Guided repair for broken anchors and area bindings | ✅ Complete | 0.4.2 | M | UX-02 |
| [UX-08](UX-08-stable-overlay-sizing.md) | Verify and enforce stable screen-space label sizing | ✅ Complete | 0.3.1 | S | — |
| [UX-09](UX-09-annotation-transform-semantics.md) | Define annotation rotation and scale semantics | ✅ Complete | 0.4.3 work; verified in 0.6.0 candidate | S | UX-04, UX-08 |

### M3 — Construction

Snapping lines and points as a first-class way to build dimensionally, not just to annotate.

| ID | Title | Status | Delivered | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| [CON-01](CON-01-guide-points.md) | Guide points | ✅ Complete | 0.4.3 | M | — |
| [CON-02](CON-02-offset-guides.md) | Offset and parallel guides at a typed distance | ✅ Complete | 0.4.3 | M | CON-01 |
| [CON-03](CON-03-guide-planes.md) | Guide planes and an active construction plane | ✅ Complete | 0.5.0 | L | CON-02 |
| [CON-04](CON-04-angular-guides-spacing.md) | Angular guides and repeated spacing | ✅ Complete | 0.5.0; anchored acquisition/repair hardened in 0.6.0 candidate | M | CON-02 |

### M4 — Output

Milestone numbers group related work; they are not a strict delivery queue. The focused `UX-01` and `UX-08` work shipped in 0.3.1, architectural ticks in 0.3.2, linear Grease Pencil generation in 0.4.0, angle/area generation in 0.4.1, named styles plus scale-correct SVG/PDF export in 0.4.2, and direct presentation handles, transient tape measurement, guide points, and chain/baseline sets in 0.4.3.

| ID | Title | Status | Delivered | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| [OUT-01](OUT-01-grease-pencil-output.md) | Render path via generated Grease Pencil | ✅ Complete | 0.4.0; live authority/stale cleanup hardened in 0.6.0 candidate | L | FND-03 |
| [OUT-02](OUT-02-vector-export.md) | SVG and PDF vector export | ✅ Complete | 0.4.2 | L | OUT-01 |
| [OUT-03](OUT-03-styles.md) | Named, reusable annotation styles | ✅ Complete | 0.4.2 | M | FND-02 |
| [OUT-04](OUT-04-angle-area-output.md) | Extend generated output to angle and area annotations | ✅ Complete | 0.4.1 | M | OUT-01 |
| [OUT-05](OUT-05-drawing-sheet.md) | Single-sheet drawing frame and title block | ✅ Complete | 0.6.0 | M | OUT-02, OUT-03 |

### M5 — Documentation-grade dimensions

| ID | Title | Status | Delivered | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| [DIM-01](DIM-01-chain-baseline.md) | Chain and baseline dimensions | ✅ Complete | 0.4.3; interaction/geometry/output hardened in 0.6.0 candidate | M | UX-01 |
| [DIM-02](DIM-02-radial-diameter-arc.md) | Radial, diameter, and arc-length dimensions | ✅ Complete | 0.4.3 | M | — |
| [DIM-03](DIM-03-coordinate-elevation.md) | Coordinate and elevation dimensions | ✅ Complete | 0.5.0; explicit datum/point acquisition hardened in 0.6.0 candidate | M | — |
| [DIM-04](DIM-04-presentation-controls.md) | Drafting presentation controls: ticks, arrows, units, and alignment | ✅ Complete | 0.4.3 | M | OUT-03 |

## Suggested order

M1 through M5 and every indexed implementation ticket are delivered. Remaining work is the explicit 1.0 release gate in `VERSIONING.md`, not an untracked feature ticket.

## Effort key

**S** — a focused session. **M** — a substantial change across a few modules. **L** — a design decision plus implementation; worth writing the approach down before starting.
