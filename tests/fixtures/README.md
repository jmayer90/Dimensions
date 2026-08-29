# Released-file migration fixtures

These `.blend` files are immutable inputs saved by earlier Dimensions releases. They
must be created with the release code named in the filename, not with the current
working tree.

The schema-v2 fixture for the retained 0.4.0 release was created reproducibly with:

```bash
blender --background --factory-startup --python scripts/create_schema_v2_fixture.py
```

The script extracts `builds/dimensions-0.4.0.zip` into a temporary package, registers
that released extension, opens `schema-v1-0.3.2.blend`, verifies that the release
migrated it to schema v2, and saves `schema-v2-0.4.0.blend`. It refuses to overwrite an
existing fixture. `tests/blender_lifecycle.py` verifies the schema-v2 source state and
the snap/style migration and the sequential additive path through schema v14 angular and repeated-spacing guide defaults.

The schema-v14 fixture uses the same release-authentic process with the retained
0.5.0 archive and the schema-v2 input:

```bash
blender --background --factory-startup --python scripts/create_schema_v14_fixture.py
```

It is the immutable starting point for migrations introduced after 0.5.0.
