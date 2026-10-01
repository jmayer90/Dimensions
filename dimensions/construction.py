"""Geometry of construction objects: guide points, guide lines, measurements, and planes.

Guide points, lines, and planes are ordinary movable Blender objects. Their object
transform is the definition: a point is the object origin, a line runs through the
origin along the local X axis, and a plane is the local XY plane. Moving, rotating,
or scaling the object with Blender's own tools therefore moves the construction.
"""

from math import ceil, floor, log10

from mathutils import Matrix, Vector

from .anchors import resolve_anchor


EPSILON = 1e-6
GUIDE_PLANE_FLAG = "dimensions_guide_plane"
MAX_GRID_CELLS_PER_SIDE = 200


def construction_kind(obj):
    props = getattr(obj, "guide_props", None)
    if props is None or not props.enabled:
        return None
    return getattr(props, "kind", "GUIDE")


def guide_point_world(obj):
    if construction_kind(obj) != "POINT":
        return None
    return obj.matrix_world.translation.copy()


def guide_line_world(obj):
    """Return (origin, unit direction) for a guide line, or None."""
    if construction_kind(obj) != "GUIDE":
        return None
    direction = obj.matrix_world.to_3x3() @ Vector((1.0, 0.0, 0.0))
    if direction.length < EPSILON:
        return None
    return obj.matrix_world.translation.copy(), direction.normalized()


def construction_segment_world(obj):
    """Return the two world endpoints of a saved measurement."""
    if construction_kind(obj) != "MEASUREMENT":
        return None
    start_world = resolve_anchor(obj.guide_props.start)
    end_world = resolve_anchor(obj.guide_props.end)
    if start_world is None or end_world is None or (end_world - start_world).length < EPSILON:
        return None
    return start_world, end_world


def guide_segment_world(obj, extent=10000.0):
    """Return a drawable segment for a guide line or measurement."""
    kind = construction_kind(obj)
    if kind == "MEASUREMENT":
        return construction_segment_world(obj)
    line = guide_line_world(obj)
    if line is None:
        return None
    origin, direction = line
    return origin - direction * extent, origin + direction * extent


def line_rotation(direction, up_hint=None):
    """Return a rotation matrix whose local X axis follows ``direction``."""
    direction = Vector(direction)
    if direction.length < EPSILON:
        return Matrix.Identity(3)
    axis_x = direction.normalized()
    candidates = [Vector(up_hint)] if up_hint is not None else []
    candidates += [Vector((0.0, 0.0, 1.0)), Vector((0.0, 1.0, 0.0)), Vector((1.0, 0.0, 0.0))]
    for candidate in candidates:
        axis_y = candidate.cross(axis_x)
        if axis_y.length >= EPSILON:
            break
    axis_y.normalize()
    axis_z = axis_x.cross(axis_y).normalized()
    return Matrix((axis_x, axis_y, axis_z)).transposed()


def set_guide_line_transform(obj, origin, direction):
    matrix = line_rotation(direction).to_4x4()
    matrix.translation = Vector(origin)
    obj.matrix_world = matrix


def plane_frame(origin, normal, preferred_axis=None):
    """Return a stable orthonormal (origin, U, V, normal) frame."""
    origin = Vector(origin)
    normal = Vector(normal)
    if normal.length < EPSILON:
        return None
    normal.normalize()
    candidates = (preferred_axis,) if preferred_axis is not None else ()
    candidates += ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    axis_u = None
    for candidate in candidates:
        projected = Vector(candidate)
        projected -= normal * projected.dot(normal)
        if projected.length >= EPSILON:
            axis_u = projected
            break
    if axis_u is None:
        return None
    axis_u.normalize()
    axis_v = normal.cross(axis_u)
    if axis_v.length < EPSILON:
        return None
    axis_v.normalize()
    return origin, axis_u, axis_v, normal


def plane_frame_from_points(points):
    """Frame through the first point, with U toward the second point."""
    if len(points) != 3:
        return None
    first, second, third = (Vector(point) for point in points)
    edge_u = second - first
    normal = edge_u.cross(third - first)
    if edge_u.length < EPSILON or normal.length < EPSILON * max(edge_u.length, 1.0):
        return None
    return plane_frame(first, normal, edge_u)


def plane_frame_from_face(face_points_world, normal_world=None):
    """Frame centered on a face, with U along its longest edge."""
    points = [Vector(point) for point in face_points_world]
    if len(points) < 3:
        return None
    center = sum(points, Vector()) / len(points)
    normal = Vector(normal_world) if normal_world is not None else Vector()
    if normal.length < EPSILON:
        for index in range(len(points)):
            current = points[index]
            following = points[(index + 1) % len(points)]
            normal += Vector((
                (current.y - following.y) * (current.z + following.z),
                (current.z - following.z) * (current.x + following.x),
                (current.x - following.x) * (current.y + following.y),
            ))
    longest = max(
        (points[(index + 1) % len(points)] - points[index] for index in range(len(points))),
        key=lambda edge: edge.length,
    )
    return plane_frame(center, normal, longest)


def guide_plane_frame(obj):
    """Return the world (origin, U, V, normal) frame of a guide plane object."""
    if construction_kind(obj) != "PLANE":
        return None
    matrix = obj.matrix_world.to_3x3()
    axis_u = matrix @ Vector((1.0, 0.0, 0.0))
    axis_v = matrix @ Vector((0.0, 1.0, 0.0))
    normal = axis_u.cross(axis_v)
    if axis_u.length < EPSILON or axis_v.length < EPSILON or normal.length < EPSILON:
        return None
    return obj.matrix_world.translation.copy(), axis_u.normalized(), axis_v.normalized(), normal.normalized()


def frame_matrix(frame):
    origin, axis_u, axis_v, normal = frame
    matrix = Matrix((axis_u, axis_v, normal)).transposed().to_4x4()
    matrix.translation = origin
    return matrix


def nice_grid_spacing(extent):
    """Choose a 1/2/5 x 10^n spacing giving roughly eight cells per half size."""
    target = max(float(extent), EPSILON) / 8.0
    exponent = floor(log10(target))
    base = 10.0 ** exponent
    for multiple in (1.0, 2.0, 5.0, 10.0):
        if base * multiple >= target * 0.999:
            return base * multiple
    return base * 10.0


def grid_coordinates(extent, spacing):
    """Return sorted grid-line offsets: spacing multiples from the center plus the border."""
    extent = max(float(extent), 0.001)
    spacing = max(float(spacing), 0.001)
    count = floor(extent / spacing + 1e-9)
    if count > MAX_GRID_CELLS_PER_SIDE // 2:
        spacing *= ceil(count / (MAX_GRID_CELLS_PER_SIDE // 2))
        count = floor(extent / spacing + 1e-9)
    values = {round(index * spacing, 9) for index in range(-count, count + 1)}
    values.update((round(-extent, 9), round(extent, 9)))
    return sorted(values)


def fill_grid_mesh(mesh, extent, spacing):
    """Replace ``mesh`` with a planar quad grid on local XY."""
    coordinates = grid_coordinates(extent, spacing)
    size = len(coordinates)
    vertices = [(u, v, 0.0) for v in coordinates for u in coordinates]
    faces = [
        (row * size + column, row * size + column + 1, (row + 1) * size + column + 1, (row + 1) * size + column)
        for row in range(size - 1)
        for column in range(size - 1)
    ]
    mesh.clear_geometry()
    mesh.from_pydata(vertices, [], faces)
    mesh.update()


def frame_grid_segments(frame, extent, spacing):
    """Return world-space line pairs for a grid on ``frame`` (used for previews)."""
    origin, axis_u, axis_v, _normal = frame
    coordinates = grid_coordinates(extent, spacing)
    low, high = coordinates[0], coordinates[-1]
    segments = []
    for value in coordinates:
        segments.extend((origin + axis_u * value + axis_v * low, origin + axis_u * value + axis_v * high))
        segments.extend((origin + axis_u * low + axis_v * value, origin + axis_u * high + axis_v * value))
    return segments


def guide_plane_grid_segments(obj):
    """Return world-space line pairs for the plane grid overlay."""
    if construction_kind(obj) != "PLANE":
        return []
    props = obj.guide_props
    coordinates = grid_coordinates(props.plane_extent, props.plane_spacing)
    low, high = coordinates[0], coordinates[-1]
    matrix = obj.matrix_world
    segments = []
    for value in coordinates:
        segments.extend((matrix @ Vector((value, low, 0.0)), matrix @ Vector((value, high, 0.0))))
        segments.extend((matrix @ Vector((low, value, 0.0)), matrix @ Vector((high, value, 0.0))))
    return segments


def rebuild_guide_plane_grid(obj):
    """Regenerate a plane's grid mesh after its size or spacing changed."""
    if construction_kind(obj) != "PLANE" or getattr(obj, "type", None) != "MESH":
        return
    from .properties import is_read_only_dimensions_object

    if is_read_only_dimensions_object(obj):
        return
    mesh = obj.data
    if mesh.users > 1:
        mesh = mesh.copy()
        obj.data = mesh
    fill_grid_mesh(mesh, obj.guide_props.plane_extent, obj.guide_props.plane_spacing)


def point_within_plane_extent(point, frame, extent, tolerance=EPSILON):
    """Return whether a coplanar point lies inside a square grid of the given half size."""
    origin, axis_u, axis_v, _normal = frame
    delta = Vector(point) - origin
    limit = max(float(extent), 0.0) + max(float(tolerance), 0.0)
    return abs(delta.dot(axis_u)) <= limit and abs(delta.dot(axis_v)) <= limit


def extent_covering(frame, points, margin=1.25, minimum=0.05):
    """Half size that keeps every point inside the grid with some margin."""
    origin, axis_u, axis_v, _normal = frame
    reach = max(
        (max(abs((Vector(point) - origin).dot(axis_u)), abs((Vector(point) - origin).dot(axis_v))) for point in points),
        default=0.0,
    )
    return max(reach * margin, minimum)


def is_guide_plane_object(obj):
    return bool(obj is not None and obj.get(GUIDE_PLANE_FLAG, False) and construction_kind(obj) == "PLANE")


def iter_guide_plane_objects(scene):
    if scene is None:
        return
    for obj in scene.objects:
        if obj.get(GUIDE_PLANE_FLAG, False):
            yield obj


def ray_hits_guide_plane(obj):
    """Return whether a ray-cast hit belongs to a construction plane."""
    if obj is None:
        return False
    original = getattr(obj, "original", obj)
    return bool(original.get(GUIDE_PLANE_FLAG, False))
