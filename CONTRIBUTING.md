# Contributing

Thanks for taking a look. This is a small, opinionated project — reading this page first will save you rework.

## Scope

Dimensions is a **non-destructive annotation** tool. It may inspect Edit Mode topology to acquire anchors or compute values, but it never creates, cuts, merges, or otherwise modifies mesh geometry.

Mesh-line drawing, face cutting, Push/Pull, Offset, arrays, and eraser-style editing are geometry-authoring tools. They are explicitly out of scope and belong in a separate project with its own interaction model and topology guarantees. An earlier experiment along those lines was removed for exactly this reason; please don't reintroduce it incrementally.

Beyond that, [docs/DESIGN.md](docs/DESIGN.md) lists the design invariants the codebase is expected to hold to. Changes that break one of them need to argue the case in the pull request, not just pass the tests.

## Building

You need Blender 5.1 or newer. The build scripts stage the extension with its license and README, invoke Blender's official extension builder, then validate the archive and reject missing release files or stray Python cache files. Keep the PowerShell and POSIX scripts behaviorally in sync when changing either one.

```bash
powershell -ExecutionPolicy Bypass -File scripts\build_extension.ps1
```

On Linux or macOS:

```bash
scripts/build_extension.sh --blender /path/to/blender
```

Pass `-Blender` if Blender isn't at the default install path:

```bash
powershell -ExecutionPolicy Bypass -File scripts\build_extension.ps1 -Blender "D:\blender\blender.exe"
```

The archive is written to `build/dimensions-<version>.zip`. Install it through **Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk**. The POSIX scripts use the standard `unzip` utility to inspect the release archive.

## Testing

`scripts/validate.ps1` runs everything CI runs: Python compilation, the Blender background test suites, manifest validation, and a full build-and-validate round trip.

```bash
powershell -ExecutionPolicy Bypass -File scripts\validate.ps1
```

On Linux or macOS:

```bash
scripts/validate.sh --blender /path/to/blender
```

To run one suite directly:

```bash
blender --background --factory-startup --python tests\blender_smoke.py
```

Tests run inside Blender because nearly everything here depends on `bpy`. CI covers Blender 5.1.2 and 5.2.0 on Windows, Linux, and macOS.

Both scripts accept an explicit Blender executable path; on POSIX systems they fall back to `blender` on `PATH`.

### What to test

`tests/blender_smoke.py` is the main suite — anchor resolution, snapping, area and angle binding, unit parsing, geometry math, draw caching, and keymap registration. Add coverage there for anything you change.

`tests/blender_modal.py` covers modal interaction: stage transitions, axis locks, typed distances, step-back, and cancellation. It runs headlessly using `tests/support/`, which provides a fake viewport context, a scripted snap provider, and an operator harness that binds an operator's methods without instantiating a `bpy` type. If you're changing a modal tool, put the decision logic in the state machine in `dimensions/modal_state.py` and drive it from there rather than adding another untested `modal()` branch.

`tests/blender_lifecycle.py` covers persistent data: measurement proxies, save/reload, and schema migration against the released-file fixtures in `tests/fixtures/`.

Two differences between the test environment and a real install have hidden real bugs, and `DimensionsPackagingTests` now guards both. The suites import the add-on as a top-level `dimensions` package, but Blender installs it as `bl_ext.<repository>.dimensions` — so anything deriving an identifier from `__package__` must use the full name. And Blender restricts `bpy.data` while an add-on registers, so registration must not read scene data directly.

### Benchmarks

`tests/draw_benchmark.py` and `tests/snap_benchmark.py` generate deterministic scenes and report timings. They do not gate CI, but they must stay runnable by hand, and any change that moves the numbers in [docs/DESIGN.md](docs/DESIGN.md#measured-performance) should update that table in the same PR.

## Pull requests

- Keep the change focused. Interaction changes and refactors in the same PR are hard to review.
- Match the surrounding style. The codebase avoids abbreviations, uses full words in names, and keeps comments sparse.
- Run `scripts/validate.ps1` before pushing.

### Documentation

Docs are treated as part of the change, not a follow-up. If your change alters product behavior, a workflow, or the architecture, update the relevant durable documentation in the same PR — `README.md`, files under `docs/`, the extension manifest, and this file.

In particular:

- **Every user-visible change gets a `docs/CHANGELOG.md` entry.**
- Bug fixes need a docs update when the fix changes user-visible behavior or corrects something the docs currently claim.
- New limitations discovered along the way belong in the README's limitations list and `docs/DESIGN.md`'s known risks.
- A change that sets a clear product direction should update the roadmap in `docs/DESIGN.md`.

### Operator reports

Use the shared messages in `dimensions/messages.py` for every `self.report()` call. `INFO` confirms a completed action, `WARNING` tells the user how to correct a condition that prevented an action, and `ERROR` is reserved for unexpected failures or conditions a user cannot resolve. Keep short messages actionable and without trailing periods.

## Versioning

Read [docs/VERSIONING.md](docs/VERSIONING.md) before choosing a version number. The short version: most changes are patches, and the minor component only moves when a change breaks saved data, breaks the documented interaction contract, or adds a new product surface. Shipping a lot of work is not a reason to bump.

The property schema is not yet frozen. Every schema change must add an idempotent migration in `dimensions/migrations.py` and a released-file fixture under `tests/fixtures/`; breaking changes must be called out loudly in the changelog.

## Where to start

[docs/tickets/](docs/tickets/) holds structured, self-contained tickets on the path to 1.0 — problem statement, approach, acceptance criteria, code map, and tests for each. `FND-09` (POSIX build scripts) and `UX-05` (snap target toggles) are reasonable first contributions.

## License

Contributions are accepted under GPL-3.0-or-later, matching the project license.
