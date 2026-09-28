"""Create a no-annotation settings fixture with the retained 0.4.2 extension."""

from pathlib import Path
import sys
import tempfile
import zipfile

import bpy


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "builds" / "dimensions-0.4.2.zip"
OUTPUT = ROOT / "tests" / "fixtures" / "schema-v6-settings-only-0.4.2.blend"


def main():
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to replace released-file fixture: {OUTPUT}")
    with tempfile.TemporaryDirectory(prefix="dimensions-v6-settings-") as temporary:
        package = Path(temporary) / "dimensions"
        package.mkdir()
        with zipfile.ZipFile(ARCHIVE) as archive:
            archive.extractall(package)
        sys.path.insert(0, temporary)
        try:
            import dimensions

            if Path(dimensions.__file__).resolve().parent != package.resolve():
                raise RuntimeError("The retained 0.4.2 package was not imported")
            dimensions.register()
            scene = bpy.context.scene
            settings = scene.dimensions_settings
            settings.schema_version = 6
            settings.precision = 4
            settings.output_scope = "SELECTED"
            style = settings.annotation_styles.add()
            style.name = "Legacy Settings Style"
            if any(obj.dimension_props.enabled for obj in scene.objects):
                raise RuntimeError("Fixture must not contain annotation objects")
            bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
        finally:
            sys.path.remove(temporary)
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
