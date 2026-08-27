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

| Milestone | Content | Likely version impact |
| --- | --- | --- |
| **M1 — Foundation** | `FND-*`. Schema versioning, selection architecture, draw performance, preferences, keymaps, test infrastructure. | **`0.3.0`** — trips triggers 1 and 2. |
| **M2 — Fluency** | `UX-*`. Continuous placement, annotation manager, inference, direct handles, snap control. | Patches on the `0.3.x` line, unless a specific ticket trips trigger 2. |
| **M3 — Construction** | `CON-*`. Guide points, offset and angular guides, guide planes, spacing. | Patches. New surfaces that reuse the existing contract. |
| **M4 — Output** | `OUT-*`. Grease Pencil generation, vector export, styles. | **`0.4.0`** — trips trigger 3. |
| **M5 — Documentation-grade** | `DIM-*`. Chain, baseline, radial, diameter, arc-length, coordinate dimensions. | Patches, mostly additive. |
| **M6 — 1.0 gate** | Hardening, migration fixtures, compatibility promise. | **`1.0.0`**. |

Milestone numbers group related work and version impact; they are not a strict delivery queue. M1 gates everything else, because building on an unversioned schema and an unsound selection architecture just increases what has to be unwound later. Early user feedback moved `UX-01` and `UX-08` into 0.3.1, architectural ticks into 0.3.2, and the first renderable linear output surface into 0.4.0. The 0.4.0 release also advances the saved-data schema additively from v1 to v2; existing values are preserved. `OUT-04` completes angle and area coverage on the 0.4.x line while other M2 and M3 work can proceed in parallel.

## The 1.0 gate

Every item must be true. Ticket IDs point at the work that makes it true.

**Data integrity**

- [ ] Property groups carry a schema version and a migration dispatcher runs on load — `FND-02`.
- [ ] Migration is covered by fixture `.blend` files saved by each earlier released version — `FND-02`, `FND-06`.
- [ ] Every persistent object type survives save/reload, undo/redo, append, and link — `FND-07`.

**Architecture**

- [ ] Selection uses a `WorkSpaceTool` or registered keymap, not a self-restarting background modal — `FND-01`.
- [ ] Draw cost scales with annotation count, not scene object count, and meets a documented budget — `FND-03`.
- [ ] Snap acquisition meets a documented budget on a dense reference scene — `FND-08`.

**User control**

- [ ] Add-on preferences expose thresholds, sizes, and defaults — `FND-04`.
- [ ] Keymaps are registered and user-customizable — `FND-05`.
- [ ] Annotations can be managed in bulk: list, search, isolate, repair, restyle — `UX-02`.

**Capability**

- [ ] Dimensions reach final output through at least one render or export path — `OUT-01`.
- [ ] Continuous placement works for the common annotation types — `UX-01`.

**Quality**

- [ ] Modal operators have automated coverage — `FND-06`.
- [ ] No known data-loss or crash defects.
- [ ] README, DESIGN, and CONTRIBUTING describe shipped behavior, with the limitations list current.

## After 1.0

Standard semantic versioning. `MAJOR` for breaking changes to saved data or the documented interaction contract, `MINOR` for additive capability, `PATCH` for fixes.

## Recording a release

1. Confirm the trigger analysis above and choose the version.
2. Update `version` in `dimensions/blender_manifest.toml`.
3. Add a `docs/CHANGELOG.md` entry. If the version is a minor, state which trigger fired and why.
4. Run `scripts/validate.ps1` and confirm the release gate in [DESIGN.md](DESIGN.md).
5. Tag the commit and attach the built archive to a GitHub release.
