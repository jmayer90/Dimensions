# Versioning and release policy

The version number exists to tell users about **compatibility**, not about activity. A release that changed a great deal but breaks nothing is a patch. A release that changed one property group and invalidates saved files is a minor. Shipping a lot is not a reason to bump.

## Current shape: `0.MINOR.PATCH`

### Patch — `0.2.3 → 0.2.4`

The default. Anything that does not trip a minor trigger:

- Bug fixes.
- New capabilities that add properties or operators without changing existing ones.
- Performance work, refactors, and internal restructuring.
- Documentation, tests, CI, and build changes.

Most tickets in [`tickets/`](tickets/) land as patches. A whole milestone can be delivered across a run of patch releases without the minor ever moving. That is the intended behavior, not a sign the policy is being gamed.

### Minor — `0.2.x → 0.3.0`

Reserved for exactly three triggers. If none of them fire, stay on the patch line no matter how much shipped.

1. **Saved-data break.** A `.blend` saved by the previous version no longer loads with equivalent behavior. Migration code that fully preserves behavior keeps a change on the patch line; migration that loses, reinterprets, or cannot recover user data is a minor.
2. **Interaction-contract break.** Removing or incompatibly changing a documented key binding, an operator `bl_idname`, or a workflow stage listed in the interaction contract in [DESIGN.md](DESIGN.md).
3. **New product surface.** A capability that changes the answer to "what is this tool." Dimensions leaving the viewport and appearing in renders or exported files is the clearest example.

**Explicitly not triggers:** number of tickets closed, time elapsed since the last minor, new dimension types that reuse existing contracts, new snap targets, performance improvements, or UI polish.

### 1.0.0 — a promise, not a milestone

1.0 is not "enough features." It is the point where the project commits to the following, and can back the commitment with tests:

- **The saved-data schema is frozen.** Files created at 1.0 open in every later 1.x release with identical behavior.
- **Upgrades preserve work.** A migration path exists, runs automatically, and is covered by tests that load fixture files from earlier versions.
- **Deprecations get a cycle.** Nothing user-facing is removed without one minor release of warning.

See the [1.0 gate](#the-10-gate) below for the full checklist.

## Milestones and their likely version impact

Milestones organize work. Versions track compatibility. They are deliberately not the same axis.

Delivery status is summarized here and maintained in detail in the [work-ticket index](tickets/README.md).

| Milestone | Delivery status | Content | Likely version impact |
| --- | --- | --- | --- |
| **M1 — Foundation** | ✅ Complete | Core implementation shipped in 0.3.0; the expanded `FND-07` lifecycle matrix and two-window foreground QA completed in 0.4.2. | **`0.3.0`** — trips triggers 1 and 2. |
| **M2 — Fluency** | ✅ Complete | `FND-11` and `UX-01` through `UX-09` are complete; final snap-target foreground QA passed for the 0.6.0 candidate. | The delivered fluency work remains on its existing patch/minor lines. |
| **M3 — Construction** | ✅ Complete | `CON-01` and `CON-02` delivered in 0.4.3; validated guide planes, active-plane input, angular guides, and repeated spacing complete in 0.5.0. | `CON-03` deliberately remaps X/Y/Z while active, triggering 0.5.0 under rule 2; other construction work is additive. |
| **M4 — Output** | ✅ Complete | Render, styles, scale-correct SVG/PDF, and the bounded `OUT-05` single-sheet surface are complete. | **`0.4.0`** established renderable output; **`0.6.0`** trips trigger 3 by turning export into an identified drawing-sheet surface. |
| **M5 — Documentation-grade** | ✅ Complete | `DIM-01`, `DIM-02`, and `DIM-04` delivered in 0.4.3; coordinate and elevation validation completed in 0.5.0. | Additive dimension types remain patches when they reuse existing contracts. |
| **M6 — 1.0 gate** | ⬜ Planned | Hardening, migration fixtures, compatibility promise. | **`1.0.0`**. |

Milestone numbers group related work and version impact; they are not a strict delivery queue. M1 gates everything else, because building on an unversioned schema and an unsound selection architecture just increases what has to be unwound later. Early public work delivered continuous placement and stable overlays in 0.3.x, established renderable/vector output in 0.4.x, and completed active-plane construction plus angular/repeated guides in 0.5.0. Schema v14 is the immutable 0.5.0 release shape. Schema v15 adds only scene-owned sheet-layout settings; existing export stays furniture-free by default. `OUT-05` moves to 0.6.0 because composing an identified drawing sheet is a new product surface, not because the additive migration loses data.

## The 1.0 gate

Every item must be true before 1.0. Checked items are already satisfied in the current release; unchecked items remain part of the gate. Ticket IDs point at the supporting work.

**Data integrity**

- [x] Property groups carry a schema version and a migration dispatcher runs on load — `FND-02`.
- [x] Migration is covered by fixture `.blend` files saved by each earlier released schema — `FND-02`, `FND-06`.
- [x] Every persistent object type survives save/reload, undo/redo, append, and link; two-window scene ownership is foreground-verified — `FND-07`.

**Architecture**

- [x] Selection uses a `WorkSpaceTool` or registered keymap, not a self-restarting background modal — `FND-01`.
- [x] Draw cost scales with annotation count, not scene object count, and meets a documented budget — `FND-03`.
- [x] Snap acquisition meets the documented dense-scene budgets — `FND-08`; `FND-11` records the passing 1M-vertex cache-build and reprojection evidence.

**User control**

- [x] Add-on preferences expose thresholds, sizes, and defaults — `FND-04`.
- [x] Keymaps are registered and user-customizable — `FND-05`.
- [x] Annotations can be managed in bulk: list, search, isolate, repair, restyle — `UX-02`.

**Capability**

- [x] Dimensions reach final output through at least one render or export path — `OUT-01`.
- [x] Continuous placement works for the common annotation types — `UX-01`.

**Quality**

- [x] Modal operators have automated coverage — `FND-06`.
- [ ] No known data-loss or crash defects.
- [x] README, DESIGN, and CONTRIBUTING describe shipped behavior, with the limitations list current.

## After 1.0

Standard semantic versioning. `MAJOR` for breaking changes to saved data or the documented interaction contract, `MINOR` for additive capability, `PATCH` for fixes.

## Recording a release

1. Confirm the trigger analysis above and choose the version.
2. Update `version` in `dimensions/blender_manifest.toml`.
3. Add a `docs/CHANGELOG.md` entry. If the version is a minor, state which trigger fired and why.
4. Run `scripts/validate.ps1` and confirm the release gate in [DESIGN.md](DESIGN.md).
5. Put the validated `dimensions-<version>.zip` archive in `builds/` and include it in the version-changing commit. Significant feature commits must include the same kind of retained build even when the version does not change.
6. Tag the commit and attach the workflow-built archive to a GitHub release.
