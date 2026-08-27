"""Generate disposable Grease Pencil output from visible linear dimensions."""

from dataclasses import replace
from math import atan, tan
from uuid import uuid4

import bpy
from mathutils import Vector

from .. import messages
from ..anchors import resolve_anchor
from ..angle_binding import resolve_angle_source
from ..area_binding import area_label_world, evaluate_area_binding
from ..dimension_geometry import get_dimension_world_geometry
from ..grease_pencil_output import generate_grease_pencil_output
from ..output_geometry import (
    WorldSizingPolicy,
    angle_dimension_label_strokes,
    angle_dimension_output_spec,
    area_dimension_label_strokes,
    area_dimension_output_spec,
    linear_dimension_label_layout,
    linear_dimension_output_spec,
)
from ..properties import is_dimension_object


def _is_visible(context, obj):
    try:
        return obj.visible_get(
            view_layer=getattr(context, "view_layer", None),
            viewport=getattr(context, "space_data", None),
        )
    except (AttributeError, TypeError, RuntimeError):
        try:
            return obj.visible_get()
        except (AttributeError, RuntimeError):
            return not obj.hide_get()


def annotations_for_output(context, scope):
    """Return eligible visible annotations in deterministic scene order."""
    annotations = []
    for obj in context.scene.objects:
        if not is_dimension_object(obj):
            continue
        props = obj.dimension_props
        if getattr(props, "annotation_kind", "LINEAR") not in {"LINEAR", "ANGLE", "AREA"}:
            continue
        if not props.visible or not _is_visible(context, obj):
            continue
        if scope == "SELECTED" and not obj.select_get():
            continue
        annotations.append(obj)
    return tuple(sorted(annotations, key=lambda obj: obj.name))


def linear_annotations_for_output(context, scope):
    """Backward-compatible filtered view of output annotations."""
    return tuple(
        obj for obj in annotations_for_output(context, scope)
        if getattr(obj.dimension_props, "annotation_kind", "LINEAR") == "LINEAR"
    )


def _is_scene_annotation(scene, annotation):
    return any(obj == annotation for obj in scene.objects)


def _prune_output_source_bindings(scene):
    bindings = scene.dimensions_settings.output_source_bindings
    invalid_indices = []
    seen_sources = set()
    seen_keys = set()
    for index, binding in enumerate(bindings):
        source = binding.source
        source_pointer = source.as_pointer() if source is not None else None
        if (
            source is None
            or not binding.key
            or not _is_scene_annotation(scene, source)
            or source_pointer in seen_sources
            or binding.key in seen_keys
        ):
            invalid_indices.append(index)
            continue
        seen_sources.add(source_pointer)
        seen_keys.add(binding.key)
    for index in reversed(invalid_indices):
        bindings.remove(index)


def annotation_output_key(scene, annotation):
    """Return a persistent scene-owned key for one annotation without mutating it."""
    if not _is_scene_annotation(scene, annotation):
        raise ValueError("annotation must belong to the output scene")

    _prune_output_source_bindings(scene)
    bindings = scene.dimensions_settings.output_source_bindings
    used_keys = {binding.key for binding in bindings if binding.key}
    for binding in bindings:
        if binding.source == annotation:
            return binding.key

    key = f"annotation-{uuid4().hex}"
    while key in used_keys:
        key = f"annotation-{uuid4().hex}"
    binding = bindings.add()
    binding.source = annotation
    binding.key = key
    return key


def annotation_output_keys(scene, annotations):
    """Return persistent keys for the annotations participating in this run."""
    return {
        annotation.name: annotation_output_key(scene, annotation)
        for annotation in annotations
    }


def _camera_world_units_per_pixel(scene, camera, world_co):
    """Resolve vertical world units per output pixel at one camera depth."""
    if camera is None or camera.type != "CAMERA":
        return None
    resolution_y = float(scene.render.resolution_y) * (
        float(scene.render.resolution_percentage) / 100.0
    )
    if resolution_y <= 0.0:
        return None
    camera_co = camera.matrix_world.inverted_safe() @ Vector(world_co)
    depth = -camera_co.z
    if depth <= 1e-6:
        return None
    camera_data = camera.data
    if camera_data.type == "ORTHO":
        return float(camera_data.ortho_scale) / resolution_y
    try:
        vertical_fov = float(camera_data.angle_y)
    except AttributeError:
        vertical_fov = 2.0 * atan(
            float(camera_data.sensor_height) / (2.0 * float(camera_data.lens))
        )
    return (2.0 * depth * tan(vertical_fov * 0.5)) / resolution_y


def _annotation_world_depth_point(annotation):
    props = annotation.dimension_props
    annotation_kind = getattr(props, "annotation_kind", "LINEAR")
    if annotation_kind == "ANGLE":
        source = resolve_angle_source(props)
        if source is None:
            return None
        return Vector(source["center"]) + Vector(
            getattr(props, "presentation_offset", (0.0, 0.0, 0.0))
        )
    if annotation_kind == "AREA":
        if props.measurement_state == "NEEDS_REPAIR":
            return None
        result = evaluate_area_binding(props) if props.measurement_state != "CAPTURED" else None
        if result is None:
            if props.measurement_state != "CAPTURED":
                return None
            center = resolve_anchor(props.start)
            if center is None:
                return None
        else:
            center = result["center"]
        end = area_label_world(props, center, resolve_anchor(props.end))
        label_offset = Vector(getattr(props, "presentation_offset", (0.0, 0.0, 0.0)))
        return (Vector(center) + Vector(end) + label_offset) * 0.5
    start_world = resolve_anchor(props.start)
    end_world = resolve_anchor(props.end)
    if start_world is None or end_world is None:
        return None
    geometry = get_dimension_world_geometry(
        props.dimension_type,
        start_world,
        end_world,
        Vector(props.offset_plane_normal),
        props.offset_distance,
        props.offset_angle,
        props.measurement_mode,
    )
    if geometry is None:
        return None
    return geometry["line_mid_world"] + Vector(
        getattr(props, "presentation_offset", (0.0, 0.0, 0.0))
    )


def output_sizing_for_annotation(scene, annotation, settings):
    """Return world-space output policy, or None when camera-relative sizing is invalid."""
    if settings.output_sizing_mode == "WORLD":
        return WorldSizingPolicy(
            settings.output_world_line_width,
            settings.output_world_arrow_size,
        )
    depth_point = _annotation_world_depth_point(annotation)
    if depth_point is None:
        return None
    pixels_to_world = _camera_world_units_per_pixel(scene, scene.camera, depth_point)
    if pixels_to_world is None:
        return None
    return WorldSizingPolicy(
        settings.output_line_width * pixels_to_world,
        settings.output_arrow_size * pixels_to_world,
    )


def output_text_height_for_annotation(scene, annotation, settings):
    """Resolve label height using the same depth conversion as linework."""
    if settings.output_sizing_mode == "WORLD":
        return float(settings.output_world_text_height)
    depth_point = _annotation_world_depth_point(annotation)
    if depth_point is None:
        return None
    pixels_to_world = _camera_world_units_per_pixel(scene, scene.camera, depth_point)
    if pixels_to_world is None:
        return None
    return float(settings.output_text_height) * pixels_to_world


class DIMENSIONS_OT_GenerateOutput(bpy.types.Operator):
    bl_idname = "dimensions.generate_output"
    bl_label = "Generate Grease Pencil Output"
    bl_description = "Generate disposable renderable output for visible dimensions"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.mode in {"OBJECT", "EDIT_MESH"}

    def execute(self, context):
        settings = context.scene.dimensions_settings
        scope = settings.output_scope
        annotations = annotations_for_output(context, scope)
        if not annotations:
            self.report(messages.WARNING, messages.OUTPUT_NO_ANNOTATIONS)
            return {"CANCELLED"}
        if settings.output_sizing_mode == "CAMERA" and context.scene.camera is None:
            self.report(messages.WARNING, messages.OUTPUT_CAMERA_REQUIRED)
            return {"CANCELLED"}

        generated = 0
        skipped = 0
        skipped_repair = 0
        output_keys = annotation_output_keys(context.scene, annotations)
        for annotation in annotations:
            sizing = output_sizing_for_annotation(context.scene, annotation, settings)
            if sizing is None:
                skipped += 1
                if (
                    getattr(annotation.dimension_props, "annotation_kind", "LINEAR") == "AREA"
                    and annotation.dimension_props.measurement_state == "NEEDS_REPAIR"
                ):
                    skipped_repair += 1
                continue
            annotation_kind = getattr(annotation.dimension_props, "annotation_kind", "LINEAR")
            spec_builder = {
                "LINEAR": linear_dimension_output_spec,
                "ANGLE": angle_dimension_output_spec,
                "AREA": area_dimension_output_spec,
            }.get(annotation_kind)
            spec = spec_builder(annotation, output_keys[annotation.name], sizing)
            if spec is None:
                skipped += 1
                if annotation_kind == "AREA" and annotation.dimension_props.measurement_state == "NEEDS_REPAIR":
                    skipped_repair += 1
                continue
            text_height = output_text_height_for_annotation(context.scene, annotation, settings)
            if annotation_kind == "LINEAR":
                label_layout = linear_dimension_label_layout(
                    context,
                    annotation,
                    text_height,
                    sizing.line_width,
                    sizing.arrow_size,
                    context.scene.camera,
                )
                line_strokes = label_layout.dimension_line_strokes
                base_strokes = spec.strokes[1:] if line_strokes else spec.strokes
                label_strokes = label_layout.strokes
                output_strokes = line_strokes + base_strokes + label_strokes
            elif annotation_kind == "ANGLE":
                output_strokes = spec.strokes + angle_dimension_label_strokes(
                    context, annotation, text_height, sizing.line_width, context.scene.camera
                )
            else:
                output_strokes = spec.strokes + area_dimension_label_strokes(
                    context, annotation, text_height, sizing.line_width, context.scene.camera
                )
            spec = replace(spec, strokes=output_strokes)
            generate_grease_pencil_output(context.scene, spec)
            generated += 1

        if generated == 0:
            report_message = (
                messages.OUTPUT_AREA_REPAIR_REQUIRED
                if skipped_repair
                else messages.OUTPUT_NO_VALID_ANNOTATIONS
            )
            self.report(messages.WARNING, report_message)
            return {"CANCELLED"}
        self.report(messages.INFO, messages.generated_output(generated, skipped, skipped_repair))
        return {"FINISHED"}


classes = (DIMENSIONS_OT_GenerateOutput,)
