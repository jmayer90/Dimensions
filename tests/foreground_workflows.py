"""Drive real viewport events through the core workflows in a foreground Blender.

The background suites exercise operators through a scripted snap provider. This
script instead feeds real window events — mouse moves, clicks, and keys — through
Blender's own event system, so modal handlers, snapping, ray casts, and Edit Mode
BMesh lifetimes behave exactly as they do for a user.

Run it with a window (it cannot run with ``--background``)::

    blender --factory-startup --enable-event-simulate --window-geometry 0 0 1600 1000 --python tests/foreground_workflows.py

The script exits with status 1 when any check fails and prints one line per check.
"""

import os
import sys
import time
import traceback
from math import degrees
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

import dimensions
from dimensions import viewport_state
from dimensions.construction import guide_line_world, guide_plane_frame

dimensions.register()

RESULTS = {}
VALUES = {}
STEPS = []
STEP_INTERVAL = 0.35


def report(name, passed, detail=""):
    RESULTS[name] = bool(passed)
    print(f"{'PASS' if passed else 'FAIL'}: {name}{'' if detail in ('', None) else f' ({detail})'}", flush=True)


def view3d():
    window = bpy.context.window_manager.windows[0]
    area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    return window, area, region


def viewport_override():
    window, area, region = view3d()
    return bpy.context.temp_override(window=window, area=area, region=region)


def window_point(world, offset=(0, 0)):
    _window, area, region = view3d()
    point = location_3d_to_region_2d(region, area.spaces.active.region_3d, Vector(world))
    return int(region.x + point.x + offset[0]), int(region.y + point.y + offset[1])


def move(world, offset=(0, 0)):
    window, _area, _region = view3d()
    x, y = window_point(world, offset)
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)


def click(world, offset=(0, 0)):
    window, _area, _region = view3d()
    move(world, offset)
    x, y = window_point(world, offset)
    window.event_simulate(type="LEFTMOUSE", value="PRESS", x=x, y=y)
    window.event_simulate(type="LEFTMOUSE", value="RELEASE", x=x, y=y)


def press(key, character=None):
    window, _area, _region = view3d()
    if character is None:
        window.event_simulate(type=key, value="PRESS")
    else:
        window.event_simulate(type=key, value="PRESS", unicode=character)
    window.event_simulate(type=key, value="RELEASE")


def type_text(text):
    names = {".": "PERIOD", "0": "ZERO", "1": "ONE", "2": "TWO", "3": "THREE", "4": "FOUR", "5": "FIVE"}
    for character in text:
        press(names[character], character)


def invoke(idname, **properties):
    group, name = idname.split(".")
    with viewport_override():
        return getattr(getattr(bpy.ops, group), name)("INVOKE_DEFAULT", **properties)


def construction(kind):
    return [obj for obj in bpy.context.scene.objects if obj.guide_props.enabled and obj.guide_props.kind == kind]


def annotations(kind=None):
    return [
        obj for obj in bpy.context.scene.objects
        if obj.dimension_props.enabled and (kind is None or obj.dimension_props.annotation_kind == kind)
    ]


def tool_state(kind):
    window, area, region = view3d()
    return viewport_state._states[kind].get((window.as_pointer(), area.as_pointer(), region.as_pointer()))


def step(function):
    STEPS.append(function)
    return function


# The factory-startup cube spans -1..1 on every axis.
TOP_FRONT_LEFT = (-1, -1, 1)
TOP_FRONT_RIGHT = (1, -1, 1)
TOP_BACK_RIGHT = (1, 1, 1)


@step
def frame_the_cube():
    _window, area, _region = view3d()
    area.spaces.active.region_3d.view_distance = 9.0
    report("measure starts a modal session", invoke("dimensions.measure") == {"RUNNING_MODAL"})


@step
def measure_hover():
    move(TOP_FRONT_LEFT, (2, 2))


@step
def measure_first_point():
    current = tool_state("MEASURE")
    report("measure shows a snap target on hover", current is not None and current.get("hover_snap") is not None)
    click(TOP_FRONT_LEFT, (1, 1))


@step
def measure_second_point():
    move(TOP_FRONT_RIGHT, (1, 1))


@step
def measure_exit():
    current = tool_state("MEASURE") or {}
    report("measure reads distance and components", bool(current.get("measurement_lines")), current.get("measurement_lines"))
    press("ESC")


@step
def guide_line_start():
    report("measure exit leaves no state or objects", tool_state("MEASURE") is None and not construction("MEASUREMENT"))
    VALUES["guides"] = len(construction("GUIDE"))
    invoke("dimensions.create_guide")


@step
def guide_line_first_point():
    click(TOP_FRONT_LEFT, (1, 1))


@step
def guide_line_hover():
    move(TOP_FRONT_RIGHT, (1, 1))


@step
def guide_line_second_point():
    click(TOP_FRONT_RIGHT, (1, 1))


@step
def guide_line_exit():
    created = construction("GUIDE")
    report("guide line is created from two snapped points", len(created) == VALUES["guides"] + 1)
    if created:
        _origin, direction = guide_line_world(created[-1])
        report("guide line follows the picked edge", abs(abs(direction.x) - 1.0) < 1e-4, tuple(direction))
    press("ESC")


@step
def guide_point_start():
    invoke("dimensions.create_guide_point", placement_mode="DIRECT")


@step
def guide_point_place():
    click(TOP_BACK_RIGHT, (1, 1))


@step
def guide_point_move():
    points = construction("POINT")
    report("guide point is placed", len(points) == 1)
    press("ESC")
    if not points:
        return
    point = points[0]
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    point.select_set(True)
    bpy.context.view_layer.objects.active = point
    VALUES["point"] = Vector(point.location)
    with viewport_override():
        bpy.ops.transform.translate(value=(0.0, 0.0, 2.0))


@step
def chain_start():
    point = construction("POINT")[0]
    expected = VALUES["point"] + Vector((0.0, 0.0, 2.0))
    report("guide point keeps a move", (Vector(point.location) - expected).length < 1e-4, tuple(point.location))
    proxy = next((child for child in point.children if child.get("dimensions_guide_point_snap_proxy")), None)
    proxy_world = None if proxy is None else proxy.matrix_world @ proxy.data.vertices[0].co
    report("guide point snap proxy follows the move", proxy_world is not None and (proxy_world - expected).length < 1e-4)
    cube = bpy.data.objects["Cube"]
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    VALUES["dimensions"] = len(annotations())
    invoke("dimensions.create_dimension", chain=True)


@step
def chain_first_point():
    click(TOP_FRONT_LEFT, (1, 1))


@step
def chain_second_point():
    click((0, -1, 1), (0, 1))


@step
def chain_place_line():
    click((0, -1.6, 1))


@step
def chain_third_point():
    click(TOP_FRONT_RIGHT, (-1, 1))


@step
def chain_exit():
    created = annotations()[VALUES["dimensions"]:]
    report("chain creates separate linear dimensions", len(created) == 2 and all(
        obj.dimension_props.annotation_kind == "LINEAR" for obj in created))
    if len(created) == 2:
        first, second = sorted(created, key=lambda obj: obj.dimension_props.start.world_co[0])
        joined = (Vector(first.dimension_props.end.world_co) - Vector(second.dimension_props.start.world_co)).length
        report("chain continues from the previous end point", joined < 1e-5)
    press("ESC")


@step
def area_from_selected_face():
    cube = bpy.data.objects["Cube"]
    bpy.context.view_layer.objects.active = cube
    with viewport_override():
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        bpy.ops.mesh.select_all(action="DESELECT")
    mesh = bmesh.from_edit_mesh(cube.data)
    mesh.faces.ensure_lookup_table()
    top = max(mesh.faces, key=lambda face: face.calc_center_median().z)
    top.select = True
    mesh.faces.active = top
    bmesh.update_edit_mesh(cube.data)
    VALUES["areas"] = len(annotations("AREA"))
    invoke("dimensions.area_selected_faces")


@step
def area_label_hover():
    move((1.8, -1.8, 1.0))


@step
def area_label_place():
    click((1.8, -1.8, 1.0))


@step
def plane_from_face():
    report("area from selected faces creates a live area", len(annotations("AREA")) == VALUES["areas"] + 1)
    VALUES["planes"] = len(construction("PLANE"))
    try:
        VALUES["face_plane"] = invoke("dimensions.create_guide_plane", definition="FACE")
    except RuntimeError:
        traceback.print_exc()
        VALUES["face_plane"] = None


@step
def offset_guide_start():
    planes = construction("PLANE")
    report("plane from the selected face is created", VALUES["face_plane"] == {"FINISHED"} and len(planes) == VALUES["planes"] + 1)
    if planes:
        origin, _axis_u, _axis_v, normal = guide_plane_frame(planes[-1])
        report("face plane lies on the face", abs(abs(normal.z) - 1.0) < 1e-5 and abs(origin.z - 1.0) < 1e-5)
        report("face plane extends past the face", planes[-1].guide_props.plane_extent > 1.0)
    with viewport_override():
        bpy.ops.object.mode_set(mode="OBJECT")
    VALUES["guides"] = len(construction("GUIDE"))
    invoke("dimensions.create_offset_guide")


@step
def offset_guide_pick_outline_edge():
    click((0, -1, -1))


@step
def offset_guide_hover():
    move((0, -2, -1))


@step
def offset_guide_type():
    type_text("0.5")


@step
def offset_guide_confirm():
    press("RET")


@step
def offset_guide_exit():
    created = construction("GUIDE")
    report("offset guide is created at a typed distance", len(created) == VALUES["guides"] + 1)
    if len(created) == VALUES["guides"] + 1:
        origin, direction = guide_line_world(created[-1])
        relative = origin - Vector((0, -1, -1))
        distance = (relative - direction * relative.dot(direction)).length
        report("offset guide is parallel at the typed distance", abs(abs(direction.x) - 1.0) < 1e-4 and abs(distance - 0.5) < 1e-4)
    press("ESC")


@step
def three_point_plane_start():
    VALUES["planes"] = len(construction("PLANE"))
    invoke("dimensions.create_guide_plane", definition="THREE_POINTS")


@step
def three_point_plane_first():
    click(TOP_FRONT_LEFT, (1, 1))


@step
def three_point_plane_second():
    click(TOP_FRONT_RIGHT, (-1, 1))


@step
def three_point_plane_third():
    click((-1, -1, -1), (1, 1))


@step
def isolate_start():
    report("three-point plane is created", len(construction("PLANE")) == VALUES["planes"] + 1)
    press("ESC")


@step
def isolate_selected():
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    keep = annotations()[0]
    keep.select_set(True)
    bpy.context.view_layer.objects.active = keep
    VALUES["keep"] = keep.name
    report("bulk actions default to the selection", bpy.context.scene.dimensions_settings.annotation_manager_bulk_scope == "SELECTED")
    invoke("dimensions.manager_bulk_visibility", action="ISOLATE")


@step
def isolate_restore():
    keep = bpy.data.objects[VALUES["keep"]]
    others = [obj for obj in annotations() + construction("GUIDE") + construction("POINT") + construction("PLANE") if obj != keep]
    report("isolate shows only the selection", not keep.hide_get() and all(obj.hide_get() for obj in others))
    report("isolate keeps the model visible", not bpy.data.objects["Cube"].hide_get())
    invoke("dimensions.manager_bulk_visibility", action="RESTORE")


@step
def clear_for_release_checks():
    managed = annotations() + construction("GUIDE") + construction("POINT") + construction("PLANE")
    report("exit isolate restores visibility", not any(obj.hide_get() for obj in managed))
    with viewport_override():
        bpy.ops.dimensions.clear_guides()
    report("clear guides removes every guide and grid", not construction("GUIDE") + construction("POINT") + construction("PLANE"))
    VALUES["dimensions"] = len(annotations())
    invoke("dimensions.create_dimension")


@step
def typed_axis_first_point():
    press("X")
    click(TOP_FRONT_LEFT, (1, 1))


@step
def typed_axis_distance():
    press("TWO", "2")
    press("RET")


@step
def typed_axis_place():
    state = tool_state("DIMENSION") or {}
    report("a locked axis gives a typed distance its direction", state.get("state") == "SET_OFFSET", state.get("state"))
    click((0, -1.8, 1))


@step
def typed_axis_check():
    created = annotations()[VALUES["dimensions"]:]
    span = None
    if len(created) == 1:
        props = created[0].dimension_props
        span = Vector(props.end.world_co) - Vector(props.start.world_co)
    report("typing 2 with X locked makes a 2 m dimension", span is not None and (span - Vector((2, 0, 0))).length < 1e-4, span)
    press("ESC")


@step
def angle_start():
    VALUES["angles"] = len(annotations("ANGLE"))
    invoke("dimensions.create_angle")
    move((0, -1, 1), (0, 1))


@step
def angle_first_edge():
    state = tool_state("DIMENSION") or {}
    report("angle names its next step", state.get("prompt") == "Click the first edge", state.get("prompt"))
    click((0, -1, 1), (0, 1))


@step
def angle_second_edge():
    click((-1, 0, 1), (1, 0))


@step
def angle_place():
    click((-0.4, -0.4, 1))


@step
def angle_check():
    from dimensions.angle_binding import resolve_angle_source

    created = annotations("ANGLE")[VALUES["angles"]:]
    source = None if len(created) != 1 else resolve_angle_source(created[0].dimension_props)
    value = None if source is None else round(degrees(source["value"]), 3)
    report("angle between two cube edges is 90 degrees", value == 90.0, value)
    press("ESC")


@step
def object_area_start():
    VALUES["areas"] = len(annotations("AREA"))
    invoke("dimensions.create_area")
    move((0.3, 0.3, 1))


@step
def object_area_pick():
    click((0.3, 0.3, 1))


@step
def object_area_place():
    state = tool_state("DIMENSION") or {}
    report("area names its label step", state.get("prompt") == "Click to place the label", state.get("prompt"))
    click((1.8, -1.8, 1.0))


@step
def object_area_check():
    created = annotations("AREA")[VALUES["areas"]:]
    value = None if len(created) != 1 else round(created[0].dimension_props.area_value, 4)
    report("object-mode area of the top face is 4", value == 4.0, value)
    press("ESC")


@step
def followed_point_start():
    from dimensions.collections import create_guide_point_object, ensure_guide_point_snap_proxy

    with viewport_override():
        point = create_guide_point_object(bpy.context, "POINT Followed", location=Vector((-1.0, -2.5, 1.0)))
        ensure_guide_point_snap_proxy(point, bpy.context.scene)
    VALUES["point"] = point.name
    VALUES["dimensions"] = len(annotations())
    invoke("dimensions.create_dimension")
    move((-1.0, -2.5, 1.0), (1, 1))


@step
def followed_point_first():
    state = tool_state("DIMENSION") or {}
    report("a guide point is a snap target", state.get("hover_label") == "Guide Point", state.get("hover_label"))
    click((-1.0, -2.5, 1.0), (1, 1))


@step
def followed_point_second():
    click(TOP_FRONT_RIGHT, (-1, 1))


@step
def followed_point_place():
    click((0.0, -3.2, 1.0))


@step
def followed_point_move():
    press("ESC")
    created = annotations()[VALUES["dimensions"]:]
    VALUES["followed"] = created[0].name if len(created) == 1 else None
    point = bpy.data.objects[VALUES["point"]]
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    point.select_set(True)
    bpy.context.view_layer.objects.active = point
    with viewport_override():
        bpy.ops.transform.translate(value=(0.0, 0.0, 1.5))


@step
def followed_point_check():
    from dimensions.anchors import resolve_anchor

    dimension = bpy.data.objects.get(VALUES["followed"] or "")
    start = None if dimension is None else resolve_anchor(dimension.dimension_props.start)
    report(
        "a dimension follows the guide point it was snapped to",
        start is not None and (start - Vector((-1.0, -2.5, 2.5))).length < 1e-4,
        None if start is None else tuple(round(value, 4) for value in start),
    )
    VALUES["guides"] = len(construction("GUIDE"))
    invoke("dimensions.create_offset_guide")


@step
def feet_offset_edge():
    click((0, -1, -1))


@step
def feet_offset_hover():
    move((0, -2, -1))


@step
def feet_offset_type():
    for key, character in (("TWO", "2"), ("F", "f"), ("T", "t")):
        press(key, character)


@step
def feet_offset_confirm():
    state = tool_state("GUIDE") or {}
    report("unit letters stay part of a typed distance", state.get("distance_text") == "2ft", state.get("distance_text"))
    press("RET")


@step
def feet_offset_check():
    created = construction("GUIDE")
    distance = None
    if len(created) == VALUES["guides"] + 1:
        origin, direction = guide_line_world(created[-1])
        relative = origin - Vector((0, -1, -1))
        distance = (relative - direction * relative.dot(direction)).length
    report("offset guide typed as 2ft is 0.6096 m from the edge", distance is not None and abs(distance - 0.6096) < 1e-4, distance)
    press("ESC")


@step
def middle_mouse_start():
    invoke("dimensions.measure")
    click(TOP_FRONT_LEFT, (1, 1))


@step
def middle_mouse_drag():
    window, _area, region = view3d()
    x, y = region.x + region.width // 2, region.y + region.height // 2
    window.event_simulate(type="MIDDLEMOUSE", value="PRESS", x=x, y=y)
    for offset in range(20, 180, 20):
        window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x + offset, y=y)
    window.event_simulate(type="MIDDLEMOUSE", value="RELEASE", x=x + 160, y=y)


@step
def middle_mouse_check():
    # The event simulator cannot drive view navigation itself; the modal tests check
    # that middle mouse passes through. Here it must not lock an axis.
    state = tool_state("MEASURE") or {}
    report("middle drag leaves Measure running without locking an axis", state.get("axis") == "ALIGNED", state.get("axis"))
    press("ESC")


@step
def dense_mesh_start():
    mesh = bpy.data.meshes.new("Dense Sphere")
    sphere = bmesh.new()
    bmesh.ops.create_icosphere(sphere, subdivisions=7, radius=1.5)
    sphere.to_mesh(mesh)
    sphere.free()
    dense = bpy.data.objects.new("Dense Sphere", mesh)
    dense.location = (0.0, 0.0, 3.5)
    bpy.context.scene.collection.objects.link(dense)
    VALUES["dense"] = dense.name
    invoke("dimensions.measure")


@step
def dense_mesh_hover():
    move((0.0, -1.5, 3.5))


@step
def dense_mesh_redraw():
    state = tool_state("MEASURE") or {}
    hover = state.get("hover_snap")
    report("hovering a dense mesh finds a snap", hover is not None and getattr(hover.get("object"), "name", "") == VALUES["dense"])
    with viewport_override():
        started = time.perf_counter()
        bpy.ops.wm.redraw_timer(type="DRAW", iterations=20)
        per_redraw = (time.perf_counter() - started) / 20.0
    report("hovering a dense mesh keeps redraws interactive", per_redraw < 0.05, f"{per_redraw * 1000:.1f} ms per redraw")
    press("ESC")


@step
def finish():
    failed = [name for name, passed in RESULTS.items() if not passed]
    print(f"Foreground workflows: {len(RESULTS) - len(failed)} passed, {len(failed)} failed", flush=True)
    os._exit(1 if failed else 0)


def run_next_step():
    if not STEPS:
        return None
    function = STEPS.pop(0)
    try:
        function()
    except Exception:
        traceback.print_exc()
        report(f"step {function.__name__} raised", False)
    return STEP_INTERVAL


bpy.app.timers.register(run_next_step, first_interval=2.0)
