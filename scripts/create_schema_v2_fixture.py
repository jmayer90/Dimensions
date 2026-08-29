"""Create the released 0.4.0/schema-v2 migration fixture inside Blender.

Run this with Blender rather than the repository's current Python environment. The
script deliberately imports Dimensions from the retained 0.4.0 release archive, opens
the released schema-v1 fixture, lets that release migrate it to schema v2, and saves a
new immutable migration input for current lifecycle tests.
"""

from pathlib import Path
import sys
import tempfile
import zipfile

import bpy


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = REPOSITORY_ROOT / "builds" / "dimensions-0.4.0.zip"
SOURCE_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "schema-v1-0.3.2.blend"
OUTPUT_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "schema-v2-0.4.0.blend"
EXPECTED_SCHEMA_VERSION = 2


def main():
    for path in (ARCHIVE, SOURCE_FIXTURE):
        if not path.is_file():
            raise FileNotFoundError(f"Required released artifact is missing: {path}")
    if OUTPUT_FIXTURE.exists():
        raise FileExistsError(
            f"Refusing to overwrite the released-file fixture: {OUTPUT_FIXTURE}"
        )

    with tempfile.TemporaryDirectory(prefix="dimensions-schema-v2-") as temporary:
        package_directory = Path(temporary) / "dimensions"
        package_directory.mkdir()
        with zipfile.ZipFile(ARCHIVE) as archive:
            archive.extractall(package_directory)

        sys.path.insert(0, temporary)
        try:
            import dimensions

            imported_package = Path(dimensions.__file__).resolve().parent
            if imported_package != package_directory.resolve():
                raise RuntimeError(
                    "Fixture generation imported the wrong Dimensions package: "
                    f"{imported_package}"
                )
            dimensions.register()
            bpy.ops.wm.open_mainfile(filepath=str(SOURCE_FIXTURE), load_ui=False)
            scene = bpy.context.scene
            actual_version = scene.dimensions_settings.schema_version
            if actual_version != EXPECTED_SCHEMA_VERSION:
                raise RuntimeError(
                    "The retained 0.4.0 extension did not produce schema v2: "
                    f"got schema v{actual_version}"
                )
            bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_FIXTURE))
        finally:
            sys.path.remove(temporary)

    print(f"Created released migration fixture: {OUTPUT_FIXTURE}")


if __name__ == "__main__":
    main()
