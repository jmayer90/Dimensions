"""Camera-framed, scale-correct SVG and PDF export operators."""

from dataclasses import replace
from types import SimpleNamespace

import bpy
from bpy_extras.io_utils import ExportHelper

from .. import messages
from ..output_geometry import (
    WorldSizingPolicy,
    angle_dimension_label_strokes,
    angle_dimension_output_spec,
    area_dimension_label_strokes,
    area_dimension_output_spec,
    linear_dimension_label_layout,
    linear_dimension_output_spec,
    dimension_set_output_spec,
    circle_dimension_output_spec,
    coordinate_elevation_output_spec,
    annotation_output_state,
)
from ..operators.generate_output import annotations_for_output
from ..properties import resolve_dimension_style
from ..sheet_layout import SheetLayoutError, SheetMetadata, build_sheet_layout
from ..vector_export import (
    VectorExportError,
    build_vector_document,
    paper_dimensions_mm,
    paper_mm_to_model,
    write_pdf,
    write_svg,
)


def vector_output_strokes(context):
    """Resolve valid visible annotations into scale-aware world-space strokes."""
    scene = context.scene
    settings = scene.dimensions_settings
    annotations = annotations_for_output(context, settings.output_scope)
    if not annotations:
        return (), 0, 0

    denominator = settings.vector_scale_denominator
    sizing = WorldSizingPolicy(
        paper_mm_to_model(scene, settings.vector_line_width_mm, denominator),
        paper_mm_to_model(scene, settings.vector_arrow_size_mm, denominator),
    )
    text_height = paper_mm_to_model(scene, settings.vector_text_height_mm, denominator)
    strokes = []
    exported = 0
    skipped = 0
    for index, annotation in enumerate(annotations):
        props = annotation.dimension_props
        annotation_kind = getattr(props, "annotation_kind", "LINEAR")
        state = annotation_output_state(annotation)
        if state not in {"LIVE", "CAPTURED"}:
            skipped += 1
            continue
        resolved = SimpleNamespace(
            name=annotation.name,
            dimension_props=resolve_dimension_style(settings, props),
        )
        if annotation_kind == "DIMENSION_SET":
            spec = dimension_set_output_spec(
                context, resolved, f"vector-{index}", sizing, text_height, scene.camera,
            )
            if spec is None:
                skipped += 1
                continue
            strokes.extend(spec.strokes)
            exported += 1
            continue
        if annotation_kind == "CIRCLE":
            spec = circle_dimension_output_spec(
                context, resolved, f"vector-{index}", sizing, text_height, scene.camera,
            )
            if spec is None:
                skipped += 1
                continue
            strokes.extend(spec.strokes)
            exported += 1
            continue
        if annotation_kind in {"COORDINATE", "ELEVATION"}:
            spec = coordinate_elevation_output_spec(
                context, resolved, f"vector-{index}", sizing, text_height, scene.camera,
            )
            if spec is None:
                skipped += 1
                continue
            strokes.extend(spec.strokes)
            exported += 1
            continue
        builder = {
            "LINEAR": linear_dimension_output_spec,
            "ANGLE": angle_dimension_output_spec,
            "AREA": area_dimension_output_spec,
        }.get(annotation_kind)
        if builder is None:
            skipped += 1
            continue
        spec = builder(resolved, f"vector-{index}", sizing)
        if spec is None:
            skipped += 1
            continue
        if annotation_kind == "LINEAR":
            label_layout = linear_dimension_label_layout(
                context,
                resolved,
                text_height,
                sizing.line_width,
                sizing.arrow_size,
                scene.camera,
            )
            base_strokes = spec.strokes[1:] if label_layout.dimension_line_strokes else spec.strokes
            output_strokes = label_layout.dimension_line_strokes + base_strokes + label_layout.strokes
        elif annotation_kind == "ANGLE":
            output_strokes = spec.strokes + angle_dimension_label_strokes(
                context, resolved, text_height, sizing.line_width, scene.camera,
            )
        else:
            output_strokes = spec.strokes + area_dimension_label_strokes(
                context, resolved, text_height, sizing.line_width, scene.camera,
            )
        strokes.extend(replace(spec, strokes=output_strokes).strokes)
        exported += 1
    return tuple(strokes), exported, skipped


def build_scene_vector_document(context):
    scene = context.scene
    settings = scene.dimensions_settings
    if scene.camera is None:
        raise VectorExportError(messages.VECTOR_CAMERA_REQUIRED)
    strokes, exported, skipped = vector_output_strokes(context)
    if exported == 0:
        raise VectorExportError(messages.VECTOR_NO_VALID_ANNOTATIONS)
    sheet_strokes = ()
    if settings.sheet_border_enabled or settings.sheet_title_block_enabled:
        width_mm, height_mm = paper_dimensions_mm(
            settings.vector_paper_size, settings.vector_orientation,
        )
        metadata = SheetMetadata(
            title=settings.sheet_drawing_title,
            drawing_number=settings.sheet_drawing_number,
            revision=settings.sheet_revision,
            author=settings.sheet_author,
            date=settings.sheet_date,
            scale=f"1:{settings.vector_scale_denominator:g}",
        )
        try:
            sheet_strokes = build_sheet_layout(
                width_mm,
                height_mm,
                margins_mm=settings.sheet_margin_mm,
                title_block_width_mm=settings.sheet_title_block_width_mm,
                title_block_height_mm=settings.sheet_title_block_height_mm,
                metadata=metadata,
                line_width_mm=settings.vector_line_width_mm,
                border_enabled=settings.sheet_border_enabled,
                title_block_enabled=settings.sheet_title_block_enabled,
            ).strokes
        except SheetLayoutError as error:
            raise VectorExportError(str(error)) from error
    return build_vector_document(
        scene,
        scene.camera,
        strokes,
        paper_size=settings.vector_paper_size,
        orientation=settings.vector_orientation,
        scale_denominator=settings.vector_scale_denominator,
        annotation_count=exported,
        skipped_count=skipped,
        sheet_strokes=sheet_strokes,
    )


class _VectorExportOperator:
    writer = None
    format_label = "Vector"

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.mode in {"OBJECT", "EDIT_MESH"}

    def execute(self, context):
        try:
            document = build_scene_vector_document(context)
            self.writer(self.filepath, document)
        except VectorExportError as error:
            self.report(messages.WARNING, str(error))
            return {"CANCELLED"}
        except OSError as error:
            self.report(messages.ERROR, messages.vector_export_failed(str(error)))
            return {"CANCELLED"}
        report_message = messages.exported_vector(
            self.format_label, document.annotation_count, document.skipped_count,
        )
        self.report(messages.INFO, report_message)
        return {"FINISHED"}


class DIMENSIONS_OT_ExportSVG(bpy.types.Operator, ExportHelper, _VectorExportOperator):
    bl_idname = "dimensions.export_svg"
    bl_label = "Export SVG"
    bl_description = "Export scale-correct vector annotations through the active camera"

    filename_ext = ".svg"
    filter_glob: bpy.props.StringProperty(default="*.svg", options={"HIDDEN"})
    writer = staticmethod(write_svg)
    format_label = "SVG"


class DIMENSIONS_OT_ExportPDF(bpy.types.Operator, ExportHelper, _VectorExportOperator):
    bl_idname = "dimensions.export_pdf"
    bl_label = "Export PDF"
    bl_description = "Export a scale-correct single-page PDF through the active camera"

    filename_ext = ".pdf"
    filter_glob: bpy.props.StringProperty(default="*.pdf", options={"HIDDEN"})
    writer = staticmethod(write_pdf)
    format_label = "PDF"


classes = (DIMENSIONS_OT_ExportSVG, DIMENSIONS_OT_ExportPDF)
