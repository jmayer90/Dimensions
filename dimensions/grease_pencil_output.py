"""Explicit, world-space Grease Pencil output for Dimensions annotations.

This module is deliberately independent from the live viewport overlay.  Callers
provide already-resolved world-space polylines, a source key, a color, and a
world-space line width.  The generated object is a presentation artifact: deleting
it cannot affect the annotation or source geometry.

Blender 5.x uses the Grease Pencil v3 API exposed by ``bpy.data.grease_pencils``.
``line_width`` in the public spec is mapped to each Grease Pencil point radius.
Text-to-stroke
conversion and camera-relative sizing are intentionally not implemented here;
the interface leaves those concerns outside this bounded linear-stroke backend.
"""

from dataclasses import dataclass

import bpy
from mathutils import Vector


OUTPUT_COLLECTION_NAME = "Dimensions Output"
OUTPUT_COLLECTION_ROLE = "DIMENSIONS_OUTPUT"
GENERATED_OUTPUT_TAG = "dimensions_generated_output"
OUTPUT_SOURCE_KEY = "dimensions_output_source_key"
OUTPUT_VERSION_KEY = "dimensions_output_version"
OUTPUT_VERSION = 1
OUTPUT_LAYER_NAME = "Dimensions Output"
TEXT_TO_STROKE_SUPPORTED = False


@dataclass(frozen=True)
class OutputStroke:
    """One open world-space stroke in a generated output drawing.

    ``line_width`` is a full world-space width in Blender units.  The output
    object does not reinterpret it as viewport pixels.
    """

    points: tuple
    color: tuple = (1.0, 1.0, 1.0, 1.0)
    line_width: float = 0.01


@dataclass(frozen=True)
class GreasePencilOutputSpec:
    """A complete replacement unit for one generated output source key."""

    source_key: str
    strokes: tuple
    name: str = "Dimensions Output"


def _normalize_color(color):
    values = tuple(float(value) for value in color)
    if len(values) == 3:
        values += (1.0,)
    if len(values) != 4 or any(value < 0.0 or value > 1.0 for value in values):
        raise ValueError("stroke color must contain 3 or 4 channels in the 0..1 range")
    return values


def _normalize_stroke(stroke):
    if isinstance(stroke, OutputStroke):
        points = stroke.points
        color = stroke.color
        line_width = stroke.line_width
    elif isinstance(stroke, dict):
        points = stroke.get("points", ())
        color = stroke.get("color", (1.0, 1.0, 1.0, 1.0))
        line_width = stroke.get("line_width", 0.01)
    else:
        raise TypeError("strokes must be OutputStroke values or mapping values")

    normalized_points = tuple(Vector(point) for point in points)
    if len(normalized_points) < 2:
        raise ValueError("each output stroke must contain at least two points")
    normalized_width = float(line_width)
    if normalized_width <= 0.0:
        raise ValueError("stroke line_width must be greater than zero")
    return OutputStroke(
        points=normalized_points,
        color=_normalize_color(color),
        line_width=normalized_width,
    )


def normalize_output_spec(spec):
    """Validate and normalize a spec before any Blender data is created."""
    if isinstance(spec, GreasePencilOutputSpec):
        source_key = spec.source_key
        strokes = spec.strokes
        name = spec.name
    elif isinstance(spec, dict):
        source_key = spec.get("source_key", "")
        strokes = spec.get("strokes", ())
        name = spec.get("name", "Dimensions Output")
    else:
        raise TypeError("spec must be a GreasePencilOutputSpec or mapping value")

    if not isinstance(source_key, str) or not source_key.strip():
        raise ValueError("output source_key must be a non-empty string")
    normalized_strokes = tuple(_normalize_stroke(stroke) for stroke in strokes)
    if not normalized_strokes:
        raise ValueError("output spec must contain at least one stroke")
    normalized_name = str(name).strip() or "Dimensions Output"
    return GreasePencilOutputSpec(
        source_key=source_key,
        strokes=normalized_strokes,
        name=normalized_name,
    )


def _collection_in_scene(scene, collection):
    return collection == scene.collection or any(
        child == collection for child in scene.collection.children_recursive
    )


def find_output_collection(scene):
    if scene is None:
        return None
    for collection in scene.collection.children_recursive:
        if collection.get("dimensions_collection_role") == OUTPUT_COLLECTION_ROLE:
            return collection
    return None


def get_or_create_output_collection(scene):
    """Return the scene-owned output collection without borrowing another scene's data."""
    if scene is None:
        raise ValueError("a scene is required for Dimensions output")

    existing = find_output_collection(scene)
    if existing is not None:
        return existing

    named_collection = bpy.data.collections.get(OUTPUT_COLLECTION_NAME)
    if named_collection is not None and _collection_in_scene(scene, named_collection):
        named_collection["dimensions_collection_role"] = OUTPUT_COLLECTION_ROLE
        return named_collection

    collection_name = OUTPUT_COLLECTION_NAME
    if named_collection is not None:
        collection_name = f"{OUTPUT_COLLECTION_NAME} ({scene.name})"
    collection = bpy.data.collections.new(collection_name)
    collection["dimensions_collection_role"] = OUTPUT_COLLECTION_ROLE
    scene.collection.children.link(collection)
    return collection


def _generated_objects(collection, source_key=None):
    return [
        obj
        for obj in collection.objects
        if obj.get(GENERATED_OUTPUT_TAG, False)
        and (source_key is None or obj.get(OUTPUT_SOURCE_KEY) == source_key)
    ]


def _remove_generated_object(obj):
    data = obj.data if obj.type == "GREASEPENCIL" else None
    materials = list(data.materials) if data is not None else []
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and data.users == 0:
        bpy.data.grease_pencils.remove(data)
    for material in materials:
        if material.users == 0:
            bpy.data.materials.remove(material)


def _grease_pencil_material(color, source_key, index):
    material = None
    try:
        material = bpy.data.materials.new(f"Dimensions Output {source_key} {index}")
        bpy.data.materials.create_gpencil_data(material)
        material.grease_pencil.show_stroke = True
        material.grease_pencil.color = color
        return material
    except Exception:
        if material is not None and material.users == 0:
            bpy.data.materials.remove(material)
        raise


def _build_data(spec, frame_number=1):
    data = None
    materials = []
    try:
        data = bpy.data.grease_pencils.new(spec.name)
        layer = data.layers.new(OUTPUT_LAYER_NAME)
        frame = layer.frames.new(frame_number)
        drawing = frame.drawing
        drawing.add_strokes([len(stroke.points) for stroke in spec.strokes])

        material_indices = {}
        for stroke in spec.strokes:
            if stroke.color not in material_indices:
                material_indices[stroke.color] = len(materials)
                materials.append(_grease_pencil_material(stroke.color, spec.source_key, len(materials)))

        for material in materials:
            data.materials.append(material)

        for stroke, grease_pencil_stroke in zip(spec.strokes, drawing.strokes):
            grease_pencil_stroke.material_index = material_indices[stroke.color]
            for point, world_co in zip(grease_pencil_stroke.points, stroke.points):
                point.position = world_co
                point.radius = stroke.line_width * 0.5
                point.opacity = stroke.color[3]
        drawing.tag_positions_changed()
        return data
    except Exception:
        if data is not None and data.users == 0:
            bpy.data.grease_pencils.remove(data)
        for material in materials:
            if material.users == 0:
                bpy.data.materials.remove(material)
        raise


def generate_grease_pencil_output(scene, spec):
    """Create or replace one tagged GPv3 object for ``spec.source_key``.

    Regeneration intentionally replaces all prior tagged objects with this key.
    Callers should treat generated output as disposable and should not hand-edit
    it expecting edits to survive regeneration.
    """
    spec = normalize_output_spec(spec)
    collection = get_or_create_output_collection(scene)
    previous_objects = tuple(_generated_objects(collection, spec.source_key))
    data = None
    output_object = None
    try:
        data = _build_data(spec, scene.frame_current)
        object_name = f"{spec.name} [{spec.source_key}]"
        output_object = bpy.data.objects.new(object_name, data)
        output_object[GENERATED_OUTPUT_TAG] = True
        output_object[OUTPUT_SOURCE_KEY] = spec.source_key
        output_object[OUTPUT_VERSION_KEY] = OUTPUT_VERSION
        output_object.hide_render = False
        collection.objects.link(output_object)
    except Exception:
        if output_object is not None and output_object.name in bpy.data.objects:
            _remove_generated_object(output_object)
        elif data is not None:
            materials = list(data.materials)
            if data.users == 0:
                bpy.data.grease_pencils.remove(data)
            for material in materials:
                if material.users == 0:
                    bpy.data.materials.remove(material)
        raise

    for previous in previous_objects:
        _remove_generated_object(previous)
    return output_object


def generated_output_objects(scene, source_key=None):
    """List tagged output objects owned by this scene's output collection."""
    collection = find_output_collection(scene)
    if collection is None:
        return ()
    return tuple(_generated_objects(collection, source_key))
