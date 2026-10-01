"""Persistent face-set bindings and world-space area evaluation."""

import bmesh
import bpy
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


def area_source_is_read_only(obj):
    """Return whether face IDs written to ``obj`` would be lost on reload.

    Linked and overridden mesh data is reloaded from its library, so an Area
    bound to it would silently lose its identity when the file is reopened.
    """
    data = getattr(obj, "data", None)
    return bool(
        getattr(obj, "library", None) is not None
        or getattr(obj, "override_library", None) is not None
        or getattr(data, "library", None) is not None
        or getattr(data, "override_library", None) is not None
    )


def _in_edit_mode(obj):
    # Ask the mesh, not the object: a linked duplicate in Edit Mode puts a shared
    # mesh in Edit Mode while this object stays in Object Mode.
    return bool(getattr(obj.data, "is_editmode", False))


def bind_area_faces(props, obj, faces):
    """Replace an Area annotation's source binding with the supplied BMesh faces.

    Returns None without changing ``props`` when the source is read-only.
    """
    if obj is None or obj.type != "MESH":
        raise ValueError("Area source must be a mesh object")
    if area_source_is_read_only(obj):
        return None
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
    # Adding the face-ID layer invalidates every existing BMFace wrapper, even
    # while the BMesh is alive, so ``faces`` must not be read after this call.
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
    props.measurement_state = "NEEDS_REPAIR" if result is None else result.get("state", "LIVE")
    return result


def bind_area_face_indices(props, obj, face_indices):
    """Bind an Area from face indices in either Object or Mesh Edit Mode.

    Returns None without changing ``props`` when the source is read-only or an
    index is out of range.
    """
    if obj is None or obj.type != "MESH":
        raise ValueError("Area source must be a mesh object")
    indices = sorted(set(int(index) for index in face_indices))
    if not indices or area_source_is_read_only(obj):
        return None
    if _in_edit_mode(obj):
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
    props.measurement_state = "NEEDS_REPAIR" if result is None else result.get("state", "LIVE")
    return result


def evaluate_area_face_indices(obj, face_indices):
    """Evaluate unbound source faces for modal preview and validation."""
    indices = sorted(set(int(index) for index in face_indices))
    if obj is None or obj.type != "MESH" or not indices:
        return None
    if _in_edit_mode(obj):
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
    changed, face_ids, next_id = _unique_face_ids(
        [face[layer] for face in bm.faces],
        face_indices,
        int(obj.data.get(FACE_ID_COUNTER, 1)),
    )
    for face_index, value in changed.items():
        bm.faces[face_index][layer] = value
    obj.data[FACE_ID_COUNTER] = next_id
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    return face_ids


def ensure_mesh_face_ids(mesh, face_indices):
    attribute = mesh.attributes.get(FACE_ID_ATTRIBUTE)
    if attribute is None:
        attribute = mesh.attributes.new(FACE_ID_ATTRIBUTE, "INT", "FACE")
    elif attribute.data_type != "INT" or attribute.domain != "FACE":
        raise ValueError(f"Reserved attribute {FACE_ID_ATTRIBUTE!r} must be an INT FACE attribute")
    changed, face_ids, next_id = _unique_face_ids(
        [item.value for item in attribute.data],
        face_indices,
        int(mesh.get(FACE_ID_COUNTER, 1)),
    )
    for face_index, value in changed.items():
        attribute.data[face_index].value = value
    mesh[FACE_ID_COUNTER] = next_id
    mesh.update()
    return face_ids


def _unique_face_ids(values, face_indices, counter):
    """Plan IDs so each requested face owns one, returning ``(changed, ids, next_id)``.

    A duplicated ID no longer names one face, so every face sharing it is
    renumbered. Renumbering only the requested copy would let an existing Area
    bound to that ID silently resolve to whichever copy kept it.
    """
    next_id = max(counter, max(values, default=0) + 1)
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    shared = {values[index] for index in face_indices if values[index] > 0 and counts[values[index]] > 1}
    changed = {}
    for index, value in enumerate(values):
        if value in shared:
            changed[index] = next_id
            next_id += 1
    face_ids = []
    for index in face_indices:
        value = changed.get(index, values[index])
        if value <= 0:
            value = next_id
            next_id += 1
            changed[index] = value
        face_ids.append(value)
    return changed, face_ids, next_id


def evaluate_area_binding(props):
    """Resolve base identity, then use evaluated faces only when identity stays unique.

    Modifiers are never matched by face index or proximity. If Blender does not
    propagate each bound persistent face ID exactly once, the base result remains
    visible as an explicit non-authoritative Fallback and output stays withheld.
    """
    obj = props.area_source_object
    bindings = list(props.area_faces)
    if obj is None or obj.type != "MESH" or not bindings:
        return None

    # Hold the Edit Mode BMesh wrapper for the whole evaluation: when it is freed,
    # Blender invalidates every BMFace object created from it.
    editing = _in_edit_mode(obj)
    edit_mesh = bmesh.from_edit_mesh(obj.data) if editing else None
    faces_by_id = _faces_by_id(obj, edit_mesh)
    resolved = []
    for binding in bindings:
        matches = faces_by_id.get(binding.face_id, ())
        if len(matches) != 1:
            return None
        face = matches[0]
        if len(face.verts) != binding.vertex_count:
            return None
        resolved.append(face)

    base_result = _evaluate_faces(obj, resolved)
    if base_result is None:
        return None
    base_result.update({"state": "LIVE", "evaluation_mode": "BASE", "evaluation_reason": ""})

    active_modifiers = tuple(
        modifier for modifier in obj.modifiers
        if modifier.show_viewport and (obj.mode != "EDIT" or modifier.show_in_editmode)
    )
    if not active_modifiers:
        return base_result
    if editing:
        return _base_fallback(base_result, "Edit Mode uses base faces while viewport modifiers are active")

    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated_object = obj.evaluated_get(depsgraph)
        evaluated_mesh = evaluated_object.data
    except (AttributeError, ReferenceError, RuntimeError):
        return _base_fallback(base_result, "Evaluated modifier geometry is unavailable")
    if evaluated_object is obj or evaluated_mesh is obj.data:
        return _base_fallback(base_result, "Evaluated modifier geometry is unavailable")

    evaluated_by_id = _mesh_faces_by_id(evaluated_mesh)
    evaluated_faces = []
    for binding in bindings:
        matches = evaluated_by_id.get(binding.face_id, ())
        if len(matches) != 1:
            return _base_fallback(base_result, "Modifiers did not preserve one unique face identity")
        face = matches[0]
        if len(face.verts) != binding.vertex_count:
            return _base_fallback(base_result, "Modifiers changed a bound face's topology")
        evaluated_faces.append(face)
    result = _evaluate_faces(evaluated_object, evaluated_faces)
    if result is None:
        return _base_fallback(base_result, "Evaluated bound faces have no measurable area")
    result.update({"state": "LIVE", "evaluation_mode": "EVALUATED", "evaluation_reason": ""})
    return result


def _base_fallback(base_result, reason):
    result = dict(base_result)
    result.update({"state": "FALLBACK", "evaluation_mode": "BASE_FALLBACK", "evaluation_reason": reason})
    return result


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


def _faces_by_id(obj, edit_mesh=None):
    """Map persistent face IDs to faces; ``edit_mesh`` must outlive the returned faces."""
    result = {}
    if _in_edit_mode(obj):
        bm = edit_mesh if edit_mesh is not None else bmesh.from_edit_mesh(obj.data)
        layer = bm.faces.layers.int.get(FACE_ID_ATTRIBUTE)
        if layer is None:
            return result
        for face in bm.faces:
            value = face[layer]
            if value > 0:
                result.setdefault(value, []).append(face)
        return result

    return _mesh_faces_by_id(obj.data)


def _mesh_faces_by_id(mesh):
    result = {}
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
