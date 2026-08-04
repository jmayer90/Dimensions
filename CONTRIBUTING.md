# Contributing

Thanks for taking a look. This is a small, opinionated project — reading this page first will save you rework.

## Scope

Dimensions is a **non-destructive annotation** tool. It may inspect Edit Mode topology to acquire anchors or compute values, but it never creates, cuts, merges, or otherwise modifies mesh geometry.

Mesh-line drawing, face cutting, Push/Pull, Offset, arrays, and eraser-style editing are geometry-authoring tools. They are explicitly out of scope and belong in a separate project with its own interaction model and topology guarantees. An earlier experiment along those lines was removed for exactly this reason; please don't reintroduce it incrementally.

Beyond that, [docs/DESIGN.md](docs/DESIGN.md) lists the design invariants the codebase is expected to hold to. Changes that break one of them need to argue the case in the pull request, not just pass the tests.

## Building

You need Blender 5.1 or newer. The build script stages the extension with its license and README, invokes Blender's official extension builder, then validates the archive and rejects missing release files or stray Python cache files.

```bash
powershell -ExecutionPolicy Bypass -File scripts\build_extension.ps1
```

Pass `-Blender` if Blender isn't at the default install path:

```bash
powershell -ExecutionPolicy Bypass -File scripts\build_extension.ps1 -Blender "D:\blender\blender.exe"
```

The archive is written to `build/dimensions-<version>.zip`. Install it through **Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk**.

## Testing

`scripts/validate.ps1` runs everything CI runs: Python compilation, the Blender background test suites, manifest validation, and a full build-and-validate round trip.

```bash
powershell -ExecutionPolicy Bypass -File scripts\validate.ps1
```

To run one suite directly:

```bash
blender --background --factory-startup --python tests\blender_smoke.py
```

Tests run inside Blender because nearly everything here depends on `bpy`. CI covers Blender 5.1.2 and 5.2.0 on Windows.

The build and validate scripts are currently PowerShell-only. A POSIX equivalent would be a genuinely useful contribution.

### What to test

`tests/blender_smoke.py` is the main suite — anchor resolution, snapping, area and angle binding, unit parsing, geometry math. Add coverage there for anything you change.

Modal operators are the weak spot: they run headless-hostile and are largely untested. If you're changing one, the most valuable thing you can do is pull the state logic into a pure function that the smoke suite can drive.

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

## Versioning

Read [docs/VERSIONING.md](docs/VERSIONING.md) before choosing a version number. The short version: most changes are patches, and the minor component only moves when a change breaks saved data, breaks the documented interaction contract, or adds a new product surface. Shipping a lot of work is not a reason to bump.

The property schema is not yet frozen and there is no `.blend` migration path yet, so breaking changes to property groups are possible but must be called out loudly in the changelog.

## Where to start

[docs/tickets/](docs/tickets/) holds structured, self-contained tickets on the path to 1.0 — problem statement, approach, acceptance criteria, code map, and tests for each. `FND-09` (POSIX build scripts) and `UX-05` (snap target toggles) are reasonable first contributions.

## License

Contributions are accepted under GPL-3.0-or-later, matching the project license.
