# FND-09 — Cross-platform build and validate scripts

**Milestone:** M1 Foundation
**Effort:** S
**Depends on:** —
**Version impact:** Patch.

## Problem

`scripts/build_extension.ps1` and `scripts/validate.ps1` are PowerShell-only, and `.github/workflows/validate.yml` runs exclusively on `windows-latest`. A contributor on macOS or Linux cannot build the extension or run the test suite without reimplementing both scripts.

Blender's user base skews heavily toward Linux and macOS. The add-on itself is platform-neutral Python, so the barrier is entirely in the tooling. Nothing in either script is genuinely Windows-specific — they locate Blender's bundled Python, invoke `blender --command extension build`, and inspect the resulting archive.

CI running only on Windows also means platform-specific bugs — path separators, file locking, case sensitivity — reach users before they reach the maintainer.

## Why it blocks 1.0

Not strictly blocking, but it caps the contributor pool for every other ticket, which matters more than the work costs.

## Approach

Add `scripts/build_extension.sh` and `scripts/validate.sh` mirroring the PowerShell versions exactly. Keep both sets: Windows users should not need a POSIX shell, and the repository is primarily developed on Windows.

The scripts are short enough that duplication is cheaper than a cross-platform abstraction. Prefer two clear implementations over one clever one, and note in `CONTRIBUTING.md` that a change to one requires the same change to the other.

Key differences to handle:

- **Locating bundled Python.** The PowerShell version recursively searches for `python/bin/python.exe`. On macOS Blender is an app bundle — `Blender.app/Contents/Resources/<version>/python/bin/python3.x`. On Linux it is `<version>/python/bin/python3.x`. Accept a `--blender` argument as the PowerShell version does, and fall back to `blender` on `PATH`.
- **Archive inspection.** The PowerShell scripts shell out to `tar -tf`, which is available on all three platforms. Keep it.
- **Exit codes.** `set -euo pipefail` and explicit checks after each Blender invocation.

Extend CI to a matrix over `windows-latest`, `ubuntu-latest`, and `macos-latest`. Linux and macOS Blender downloads are `.tar.xz` and `.dmg` respectively rather than `.zip`, so the download step needs per-platform handling. Keeping both Blender versions on all three platforms is six jobs — if that is too slow, run the full Blender matrix on Linux and one Blender version on the other two.

## Acceptance criteria

- [ ] `scripts/build_extension.sh` produces an archive byte-identical in content to the PowerShell script's output, given the same source.
- [ ] `scripts/validate.sh` runs the same checks in the same order and fails on the same conditions.
- [ ] Both accept a Blender path argument and fall back to `blender` on `PATH`.
- [ ] Both locate Blender's bundled Python on macOS app bundles and Linux installs.
- [ ] Both fail with a clear message, not a stack trace, when Blender cannot be found.
- [ ] CI runs on Windows, Linux, and macOS, and all jobs pass.
- [ ] `CONTRIBUTING.md` documents both invocations and the rule that the two script sets stay in sync.
- [ ] The README no longer implies a Windows-only workflow.

## Code map

- `scripts/build_extension.sh` — new, mirroring `build_extension.ps1`.
- `scripts/validate.sh` — new, mirroring `validate.ps1`.
- `.github/workflows/validate.yml` — OS matrix and per-platform Blender download.
- `CONTRIBUTING.md` — build and test sections.

## Verification

- CI passing on all three platforms is the verification.
- Compare archive contents produced by each script on the same commit: `tar -tf` output should match.

## Out of scope

- Replacing both with a Python build script. Reasonable, and arguably better, but it adds a bootstrap problem — you need a Python to run it, and the point of the current design is to use Blender's. If someone wants to make that case, file it separately.
- Publishing automation.

## Invariants

None specific. This is tooling.
