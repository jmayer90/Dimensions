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
| M1 — Foundation | 🟨 Partial | `FND-01` through `FND-06` and `FND-08` through `FND-10` in 0.3.0 | `FND-07` foreground QA remains; `FND-11` is an M2 performance follow-up. |
| M2 — Fluency | 🟨 Partial | `UX-01`, `UX-08` in 0.3.1 | `FND-11` is next; `UX-02` through `UX-07` remain. |
| M3 — Construction | ⬜ Planned | — | `CON-01` through `CON-04`. |
| M4 — Output | 🟨 Partial | `OUT-01` in 0.4.0; angle/area `OUT-04` in 0.4.1 | `OUT-03` is next; `OUT-02` follows. |
| M5 — Documentation-grade | 🟨 Partial | Architectural ticks in 0.3.2; Outside Start placement in 0.4.1 | Remaining `DIM-04` plus `DIM-01` through `DIM-03`. |

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
| [FND-06](FND-06-modal-testing.md) | Make modal operators testable, then test them | ✅ Complete | 0.3.0 | L | — |
| [FND-07](FND-07-lifecycle-hardening.md) | Lifecycle hardening: undo, append, link, multi-scene | 🟨 Partial | Background path in 0.3.0 | M | FND-02 |
| [FND-08](FND-08-snap-performance.md) | Snap performance budgets on dense scenes | ✅ Complete | 0.3.0 | M | — |
| [FND-09](FND-09-posix-scripts.md) | Cross-platform build and validate scripts | ✅ Complete | 0.3.0 | S | — |
| [FND-10](FND-10-error-reporting.md) | Consistent, actionable error reporting | ✅ Complete | 0.3.0 | S | — |

M1 implementation is delivered, but `FND-07` remains partial until append/link and two-window foreground QA are recorded. [FND-11](FND-11-snap-cache-build-cost.md) was filed out of `FND-08`: query and draw budgets are met and measured, but building the projected snap cache on a 1M-vertex scene misses its budget. It carries into M2 rather than blocking the shipped foundation, because scenes at or below 100k vertices are within budget today.

### M2 — Fluency

The difference between a tool that works and one people keep using.

| ID | Title | Status | Delivered | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| [FND-11](FND-11-snap-cache-build-cost.md) | Bring projected snap-cache build within budget | ⏭ Next | — | M | FND-08 |
| [UX-01](UX-01-continuous-placement.md) | Continuous placement with a persistent Auto/X/Y/Z session mode | ✅ Complete | 0.3.1 | M | — |
| [UX-02](UX-02-annotation-manager.md) | Annotation manager: list, search, isolate, repair, restyle | ⬜ Planned | — | L | — |
| [UX-03](UX-03-inference-engine.md) | Inference: parallel, perpendicular, extension, intersection, local axis | ⬜ Planned | — | L | FND-08 |
| [UX-04](UX-04-direct-handles.md) | Direct viewport handles for placement, radius, and offset | ⬜ Planned | — | M | FND-01 |
| [UX-05](UX-05-snap-control.md) | User control over which snap targets are active | ⬜ Planned | — | S | FND-04 |
| [UX-06](UX-06-hover-measurement.md) | Transient hover measurement with delta X/Y/Z | ⬜ Planned | — | M | — |
| [UX-07](UX-07-guided-repair.md) | Guided repair for broken anchors and area bindings | ⛔ Blocked | — | M | UX-02 |
| [UX-08](UX-08-stable-overlay-sizing.md) | Verify and enforce stable screen-space label sizing | ✅ Complete | 0.3.1 | S | — |

### M3 — Construction

Snapping lines and points as a first-class way to build dimensionally, not just to annotate.

| ID | Title | Status | Effort | Depends on |
| --- | --- | --- | --- | --- |
| [CON-01](CON-01-guide-points.md) | Guide points | ⬜ Planned | M | — |
| [CON-02](CON-02-offset-guides.md) | Offset and parallel guides at a typed distance | ⛔ Blocked | M | CON-01 |
| [CON-03](CON-03-guide-planes.md) | Guide planes and an active construction plane | ⛔ Blocked | L | CON-02 |
| [CON-04](CON-04-angular-guides-spacing.md) | Angular guides and repeated spacing | ⛔ Blocked | M | CON-02 |

### M4 — Output

Milestone numbers group related work; they are not a strict delivery queue. The focused `UX-01` and `UX-08` work shipped in 0.3.1, architectural ticks in 0.3.2, linear Grease Pencil generation in 0.4.0, and angle/area generation in 0.4.1. `OUT-02` and `OUT-03` retain their existing scopes and dependencies.

| ID | Title | Status | Delivered | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| [OUT-01](OUT-01-grease-pencil-output.md) | Render path via generated Grease Pencil | ✅ Complete | 0.4.0 | L | FND-03 |
| [OUT-02](OUT-02-vector-export.md) | SVG and PDF vector export | ⬜ Planned | — | L | OUT-01 |
| [OUT-03](OUT-03-styles.md) | Named, reusable annotation styles | ⏭ Next | — | M | FND-02 |
| [OUT-04](OUT-04-angle-area-output.md) | Extend generated output to angle and area annotations | ✅ Complete | 0.4.1 | M | OUT-01 |

### M5 — Documentation-grade dimensions

| ID | Title | Status | Delivered | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| [DIM-01](DIM-01-chain-baseline.md) | Chain and baseline dimensions | ⬜ Planned | — | M | UX-01 |
| [DIM-02](DIM-02-radial-diameter-arc.md) | Radial, diameter, and arc-length dimensions | ⬜ Planned | — | M | — |
| [DIM-03](DIM-03-coordinate-elevation.md) | Coordinate and elevation dimensions | ⬜ Planned | — | M | — |
| [DIM-04](DIM-04-presentation-controls.md) | Drafting presentation controls: ticks, arrows, units, and alignment | 🟨 Partial | Ticks in 0.3.2; Outside Start in 0.4.1 | M | OUT-03 for remaining work |

## Suggested order

The M1 implementation, `UX-01`, `UX-08`, the architectural-tick slice, `OUT-01`, and angle/area `OUT-04` are delivered; `FND-07` still carries foreground QA. Next, complete reusable styles in `OUT-03` and the `FND-11` performance follow-up. `OUT-03` then unlocks the broader remaining `DIM-04` presentation work. Other M2 and M3 tickets can proceed alongside those workstreams.

## Effort key

**S** — a focused session. **M** — a substantial change across a few modules. **L** — a design decision plus implementation; worth writing the approach down before starting.
