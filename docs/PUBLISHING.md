# Publishing on Blender Extensions

Dimensions is packaged as a Blender Extension and is intended for publication on the official Blender Extensions platform. The manifest supports Blender 5.1.x, identifies Cynic Wild as the maintainer, uses the official `3D View` tag, requests no elevated extension permissions, and intentionally does not declare a website.

## Create the package

From the repository root, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate.ps1
```

This runs compilation, the Blender smoke and lifecycle suites, manifest validation, and the release build. The uploadable file is `build/dimensions-<version>.zip`. The build script validates that archive with Blender and confirms that it contains `__init__.py`, `blender_manifest.toml`, `LICENSE`, and `README.md`, with no Python bytecode caches.

GitHub Actions runs the same validation and retains the ZIP as the `dimensions-extension` workflow artifact.

## Release checklist

1. Confirm the manifest version is the intended release version. Keep the `0.2.x` release line unless the project owner expressly approves changing the minor component; increment only the patch component for routine adjustments.
2. Confirm the changelog describes all user-visible changes in the package.
3. Run the complete validation command above with the declared minimum Blender version.
4. Install the generated ZIP through **Edit > Preferences > Add-ons > Install from Disk** using a clean Blender profile.
5. Enable, disable, and re-enable Dimensions; create and save each persistent annotation type; reopen the file; and confirm the viewport tools and sidebar remain functional.
6. Inspect the ZIP itself, not a repository-generated ZIP such as GitHub's source download. The manifest and `__init__.py` must be at the archive root.
7. Prepare current screenshots and a concise listing description that accurately states the viewport-only output and the limitations documented in the README.

## Submit for review

1. Sign in to [Blender Extensions](https://extensions.blender.org/) with a Blender ID.
2. Start an add-on submission and upload `build/dimensions-<version>.zip`.
3. Complete the listing details, screenshots, and support information. The support URL is entered on the platform rather than declared as the manifest website.
4. Submit the extension for moderation and respond to reviewer feedback. Publication occurs after approval.

The platform account, listing text, screenshots, and final upload are release-owner actions and are not embedded in the package.
