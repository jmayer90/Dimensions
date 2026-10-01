"""Create the released 0.6.0/schema-v15 migration fixture inside Blender.

The retained 0.6.0 archive is the authority for the saved shape. The script
registers that released extension and builds one scene containing every
annotation and construction kind that 0.7.0 removes or reshapes, plus the kept
kinds beside them, so the 0.7.0 migration can be verified against data written
by the released code rather than by the current working tree.
"""

from math import cos, radians, sin
from pathlib import Path
import sys
import tempfile
import zipfile

import bpy
from mathutils import Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = REPOSITORY_ROOT / "builds" / "dimensions-0.6.0.zip"
OUTPUT_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "schema-v15-0.6.0.blend"
EXPECTED_SCHEMA_VERSION = 15


def _mesh(name, vertices, faces=(), location=(0.0, 0.0, 0.0)):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _build_scene():
    from dimensions.anchors import set_anchor, set_world_anchor
    from dimensions.circle_binding import bind_circle_vertices
    from dimensions.collections import (
        create_dimension_object,
        create_guide_object,
        create_guide_plane_object,
        create_guide_point_object,
        create_measurement_object,
        ensure_guide_point_snap_proxy,
        ensure_measurement_snap_proxy,
    )
    from dimensions.derived_guides import bind_face_source, bind_guide_source
    from dimensions.scene_sync import sync_scene_objects

    context = bpy.context
    scene = context.scene
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    block = _mesh(
        "Fixture Block",
        [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)],
        [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    ring_points = [
        (0.75 * cos(radians(360.0 * index / 16)), 0.75 * sin(radians(360.0 * index / 16)), 0.0)
        for index in range(16)
    ]
    ring = _mesh("Fixture Ring", ring_points, [tuple(range(16))], location=(5.0, 0.0, 0.0))

    linear = create_dimension_object(context, "DIM Linear Kept")
    set_anchor(linear.dimension_props.start, block, 0)
    set_anchor(linear.dimension_props.end, block, 1)
    linear.dimension_props.dimension_type = "X"
    linear.dimension_props.offset_distance = 0.4
    linear.location = (0.0, -1.4, -1.0)

    def dimension_set(name, kind, points, spacing=0.0):
        obj = create_dimension_object(context, name)
        props = obj.dimension_props
        props.annotation_kind = "DIMENSION_SET"
        props.set_kind = kind
        props.dimension_type = "X"
        props.offset_distance = 0.3
        props.offset_plane_normal = (0.0, 0.0, 1.0)
        props.set_spacing = spacing
        props.override_color = True
        props.color = (1.0, 0.2, 0.1, 1.0)
        pairs = list(zip(points, points[1:])) if kind == "CHAIN" else [(points[0], point) for point in points[1:]]
        for start, end in pairs:
            member = props.set_members.add()
            set_world_anchor(member.start, Vector(start))
            set_world_anchor(member.end, Vector(end))
        obj.location = Vector(points[0])
        return obj

    dimension_set("DIM Chain Set", "CHAIN", ((0, -3, 0), (1, -3, 0), (3, -3, 0)))
    dimension_set("DIM Baseline Set", "BASELINE", ((0, -5, 0), (1, -5, 0), (2.5, -5, 0)), spacing=0.4)

    circle = create_dimension_object(context, "DIM Circle Removed")
    circle.dimension_props.annotation_kind = "CIRCLE"
    circle.dimension_props.circle_kind = "DIAMETER"
    bind_circle_vertices(circle.dimension_props, ring, range(16), True)

    datum = create_guide_point_object(context, "DATUM Origin")
    datum.guide_props.is_datum = True
    datum.guide_props.datum_name = "Origin"
    set_world_anchor(datum.guide_props.start, Vector((0.0, 0.0, 0.0)))
    for kind, name in (("COORDINATE", "DIM Coordinate Removed"), ("ELEVATION", "DIM Elevation Removed")):
        annotation = create_dimension_object(context, name)
        annotation.dimension_props.annotation_kind = kind
        annotation.dimension_props.datum_object = datum
        set_world_anchor(annotation.dimension_props.start, Vector((1.0, 1.0, 1.0)))
        set_world_anchor(annotation.dimension_props.end, Vector((1.5, 1.5, 1.0)))

    fixed = create_guide_object(context, "GUIDE Fixed")
    set_world_anchor(fixed.guide_props.start, Vector((0.0, 5.0, 0.0)))
    set_world_anchor(fixed.guide_props.end, Vector((1.0, 5.0, 0.0)))

    vertex_guide = create_guide_object(context, "GUIDE Vertex Anchored")
    set_anchor(vertex_guide.guide_props.start, block, 4)
    set_anchor(vertex_guide.guide_props.end, block, 7)

    axis_guide = create_guide_object(context, "GUIDE Axis Z")
    set_world_anchor(axis_guide.guide_props.start, Vector((3.0, 3.0, 0.0)))
    set_world_anchor(axis_guide.guide_props.end, Vector((4.0, 3.0, 0.0)))
    axis_guide.guide_props.axis = "Z"

    offset = create_guide_object(context, "GUIDE Offset Derived")
    offset.guide_props.derived = True
    offset.guide_props.derivation_mode = "OFFSET"
    offset.guide_props.offset_distance = 1.0
    offset.guide_props.offset_side = 1
    offset.guide_props.derived_direction = (0.0, 1.0, 0.0)
    bind_guide_source(offset.guide_props.source_a, fixed)

    spacing = create_guide_object(context, "GUIDE Spacing Derived")
    props = spacing.guide_props
    props.derived = True
    props.derivation_mode = "SPACING"
    bind_guide_source(props.source_a, fixed)
    set_world_anchor(props.construction_pivot, Vector((0.0, 5.0, 0.0)))
    props.derived_direction = (0.0, 1.0, 0.0)
    props.spacing_interval = 0.5
    props.spacing_count = 3

    angular = create_guide_object(context, "GUIDE Angular Derived")
    props = angular.guide_props
    props.derived = True
    props.derivation_mode = "ANGULAR"
    props.guide_angle = radians(45.0)
    props.derived_direction = (0.0, 0.0, 1.0)
    set_world_anchor(props.construction_pivot, Vector((0.0, 5.0, 0.0)))
    bind_guide_source(props.source_a, fixed)

    anchored_point = create_guide_point_object(context, "POINT Vertex Anchored")
    set_anchor(anchored_point.guide_props.start, block, 6)
    ensure_guide_point_snap_proxy(anchored_point, scene)
    world_point = create_guide_point_object(context, "POINT World")
    set_world_anchor(world_point.guide_props.start, Vector((2.0, 2.0, 2.0)))
    ensure_guide_point_snap_proxy(world_point, scene)

    three = create_guide_plane_object(context, "PLANE Three Points")
    three.guide_props.plane_definition = "THREE_POINTS"
    three.guide_props.plane_extent = 1.5
    for anchor, index in zip(
        (three.guide_props.plane_point_a, three.guide_props.plane_point_b, three.guide_props.plane_point_c),
        (4, 5, 7),
    ):
        set_anchor(anchor, block, index)
    face = create_guide_plane_object(context, "PLANE Face")
    face.guide_props.plane_definition = "FACE"
    bind_face_source(face.guide_props.source_a, block, 3)
    point_normal = create_guide_plane_object(context, "PLANE Point Normal")
    point_normal.guide_props.plane_definition = "POINT_NORMAL"
    set_world_anchor(point_normal.guide_props.plane_point_a, Vector((0.0, 8.0, 0.0)))
    point_normal.guide_props.plane_normal = (0.0, 1.0, 0.0)
    offset_plane = create_guide_plane_object(context, "PLANE Offset")
    offset_plane.guide_props.plane_definition = "OFFSET"
    bind_guide_source(offset_plane.guide_props.source_a, point_normal)
    offset_plane.guide_props.offset_distance = 0.5

    measurement = create_measurement_object(context, "MEASURE Segment")
    set_world_anchor(measurement.guide_props.start, Vector((0.0, -7.0, 0.0)))
    set_world_anchor(measurement.guide_props.end, Vector((2.0, -7.0, 0.0)))
    ensure_measurement_snap_proxy(measurement, scene)

    settings = scene.dimensions_settings
    settings.active_plane_object = three
    settings.active_plane_mode = "GUIDE"
    settings.annotation_manager_kind_circle = False

    sync_scene_objects(scene)
    sync_scene_objects(scene)


def main():
    if not ARCHIVE.is_file():
        raise FileNotFoundError(f"Required released artifact is missing: {ARCHIVE}")
    if OUTPUT_FIXTURE.exists():
        raise FileExistsError(f"Refusing to overwrite the released-file fixture: {OUTPUT_FIXTURE}")

    with tempfile.TemporaryDirectory(prefix="dimensions-schema-v15-") as temporary:
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
                    f"Fixture generation imported the wrong Dimensions package: {imported_package}"
                )
            dimensions.register()
            _build_scene()
            actual_version = bpy.context.scene.dimensions_settings.schema_version
            if actual_version != EXPECTED_SCHEMA_VERSION:
                raise RuntimeError(
                    f"The retained 0.6.0 extension did not produce schema v15: got schema v{actual_version}"
                )
            bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_FIXTURE))
        finally:
            sys.path.remove(temporary)

    print(f"Created released migration fixture: {OUTPUT_FIXTURE}")


if __name__ == "__main__":
    main()
