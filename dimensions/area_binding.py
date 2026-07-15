"""Persistent face-set bindings and world-space area evaluation."""

import bmesh
from mathutils import Vector


FACE_ID_ATTRIBUTE = "dimensions_area_face_id"
FACE_ID_COUNTER = "dimensions_area_face_next_id"
AREA_EPSILON = 1e-12


def area_label_world(props, center_world, fallback_world=None):
    if not props.area_placement_locked:
        return Vector(fallback_world) if fallback_world is not None else Vector(center_world)
    direction = Vector(props.area_label_direction)
    if direction.length < 1e-6:
        direction = Vector((1.0, 0.0, 0.0))
    return Vector(center_world) + direction.normalized() * props.offset_distance


def bind_area_faces(props, obj, faces):
    """Replace an Area annotation's source binding with the supplied BMesh faces."""
    if obj is None or obj.type != "MESH":
        raise ValueError("Area source must be a mesh object")
    face_indices = [face.index for face in faces]
    metadata = [
        (
            tuple(face.calc_center_median_weighted()),
            tuple(face.normal),
            face.calc_area(),
            len(face.verts),
        )
        for face in faces
    ]
    face_ids = ensure_bmesh_face_ids(obj, face_indices)
    props.area_source_object = obj
    props.area_faces.clear()
    for face_id, (center, normal, area, vertex_count) in zip(face_ids, metadata):
        item = props.area_faces.add()
        item.face_id = face_id
        item.fallback_center = center
        item.fallback_normal = normal
        item.fallback_area = area
        item.vertex_count = vertex_count
    props.measurement_state = "LIVE"
    result = evaluate_area_binding(props)
    if result is None:
        props.measurement_state = "NEEDS_REPAIR"
    return result


def bind_area_face_indices(props, obj, face_indices):
    """Bind an Area from face indices in either Object or Mesh Edit Mode."""
    if obj is None or obj.type != "MESH":
        raise ValueError("Area source must be a mesh object")
    indices = sorted(set(int(index) for index in face_indices))
    if not indices:
        return None
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        if any(index < 0 or index >= len(bm.faces) for index in indices):
            return None
        return bind_area_faces(props, obj, [bm.faces[index] for index in indices])

    mesh = obj.data
    if any(index < 0 or index >= len(mesh.polygons) for index in indices):
        return None
    faces = [_MeshFaceAdapter(mesh.polygons[index]) for index in indices]
    metadata = [
        (tuple(face.calc_center_median_weighted()), tuple(face.normal), face.calc_area(), len(face.verts))
        for face in faces
    ]
    face_ids = ensure_mesh_face_ids(mesh, indices)
    props.area_source_object = obj
    props.area_faces.clear()
    for face_id, (center, normal, area, vertex_count) in zip(face_ids, metadata):
        item = props.area_faces.add()
        item.face_id = face_id
        item.fallback_center = center
        item.fallback_normal = normal
        item.fallback_area = area
        item.vertex_count = vertex_count
    props.measurement_state = "LIVE"
    result = evaluate_area_binding(props)
    if result is None:
        props.measurement_state = "NEEDS_REPAIR"
    return result


def evaluate_area_face_indices(obj, face_indices):
    """Evaluate unbound source faces for modal preview and validation."""
    indices = sorted(set(int(index) for index in face_indices))
    if obj is None or obj.type != "MESH" or not indices:
        return None
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        if any(index < 0 or index >= len(bm.faces) for index in indices):
            return None
        return _evaluate_faces(obj, [bm.faces[index] for index in indices])
    if any(index < 0 or index >= len(obj.data.polygons) for index in indices):
        return None
    return _evaluate_faces(obj, [_MeshFaceAdapter(obj.data.polygons[index]) for index in indices])


def ensure_bmesh_face_ids(obj, face_indices):
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    layer = bm.faces.layers.int.get(FACE_ID_ATTRIBUTE)
    if layer is None:
        layer = bm.faces.layers.int.new(FACE_ID_ATTRIBUTE)
        bm.faces.ensure_lookup_table()
    next_id = max(
        int(obj.data.get(FACE_ID_COUNTER, 1)),
        max((face[layer] for face in bm.faces), default=0) + 1,
    )
    values = []
    for face_index in face_indices:
        face = bm.faces[face_index]
        value = face[layer]
        if value <= 0:
            value = next_id
            next_id += 1
            face[layer] = value
        values.append(value)
    obj.data[FACE_ID_COUNTER] = next_id
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    return values


def ensure_mesh_face_ids(mesh, face_indices):
    attribute = mesh.attributes.get(FACE_ID_ATTRIBUTE)
    if attribute is None:
        attribute = mesh.attributes.new(FACE_ID_ATTRIBUTE, "INT", "FACE")
    elif attribute.data_type != "INT" or attribute.domain != "FACE":
        raise ValueError(f"Reserved attribute {FACE_ID_ATTRIBUTE!r} must be an INT FACE attribute")
    next_id = max(
        int(mesh.get(FACE_ID_COUNTER, 1)),
        max((item.value for item in attribute.data), default=0) + 1,
    )
    values = []
    for face_index in face_indices:
        value = attribute.data[face_index].value
        if value <= 0:
            value = next_id
            next_id += 1
            attribute.data[face_index].value = value
        values.append(value)
    mesh[FACE_ID_COUNTER] = next_id
    mesh.update()
    return values


def evaluate_area_binding(props):
    """Return area, weighted center, normal, and count, or None for an invalid binding."""
    obj = props.area_source_object
    bindings = list(props.area_faces)
    if obj is None or obj.type != "MESH" or not bindings:
        return None

    faces_by_id = _faces_by_id(obj)
    resolved = []
    for binding in bindings:
        matches = faces_by_id.get(binding.face_id, ())
        if len(matches) != 1:
            return None
        face = matches[0]
        if len(face.verts) != binding.vertex_count:
            return None
        resolved.append(face)

    return _evaluate_faces(obj, resolved)


def _evaluate_faces(obj, faces):
    linear = obj.matrix_world.to_3x3()
    normal_matrix = linear.inverted_safe().transposed()
    determinant = abs(linear.determinant())
    total_area = 0.0
    weighted_center = Vector((0.0, 0.0, 0.0))
    weighted_normal = Vector((0.0, 0.0, 0.0))
    for face in faces:
        world_normal = normal_matrix @ face.normal
        area = face.calc_area() * determinant * world_normal.length
        if area <= AREA_EPSILON:
            continue
        world_normal.normalize()
        center = obj.matrix_world @ face.calc_center_median_weighted()
        total_area += area
        weighted_center += center * area
        weighted_normal += world_normal * area
    if total_area <= AREA_EPSILON:
        return None
    center = weighted_center / total_area
    normal = weighted_normal.normalized() if weighted_normal.length > 1e-8 else Vector((0.0, 0.0, 1.0))
    return {
        "area": total_area,
        "center": center,
        "normal": normal,
        "face_count": len(faces),
    }


def _faces_by_id(obj):
    result = {}
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        layer = bm.faces.layers.int.get(FACE_ID_ATTRIBUTE)
        if layer is None:
            return result
        for face in bm.faces:
            value = face[layer]
            if value > 0:
                result.setdefault(value, []).append(face)
        return result

    mesh = obj.data
    attribute = mesh.attributes.get(FACE_ID_ATTRIBUTE)
    if attribute is None or attribute.data_type != "INT" or attribute.domain != "FACE":
        return result
    for index, item in enumerate(attribute.data):
        if item.value > 0:
            result.setdefault(item.value, []).append(_MeshFaceAdapter(mesh.polygons[index]))
    return result


class _MeshFaceAdapter:
    """Expose MeshPolygon data through the small BMesh-face interface used above."""

    def __init__(self, polygon):
        self._polygon = polygon
        self.normal = polygon.normal
        self.verts = polygon.vertices

    def calc_area(self):
        return self._polygon.area

    def calc_center_median_weighted(self):
        return self._polygon.center
