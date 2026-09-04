"""Scale-correct SVG and PDF documents from Dimensions output strokes."""

from dataclasses import dataclass
from html import escape
from math import isfinite

from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

from .grease_pencil_output import OutputStroke
from .sheet_layout import SheetStroke


PAPER_SIZES_MM = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "LETTER": (215.9, 279.4),
}


class VectorExportError(ValueError):
    """Expected configuration or framing error suitable for an operator warning."""


@dataclass(frozen=True)
class PageStroke:
    points: tuple
    color: tuple
    line_width_mm: float
    role: str = "ANNOTATION"


@dataclass(frozen=True)
class VectorDocument:
    width_mm: float
    height_mm: float
    strokes: tuple
    annotation_count: int = 0
    skipped_count: int = 0


def paper_dimensions_mm(paper_size, orientation):
    try:
        width, height = PAPER_SIZES_MM[paper_size]
    except KeyError as error:
        raise VectorExportError(f"Unsupported paper size: {paper_size}") from error
    if orientation == "LANDSCAPE":
        return height, width
    if orientation != "PORTRAIT":
        raise VectorExportError(f"Unsupported paper orientation: {orientation}")
    return width, height


def model_to_paper_factor(scene, scale_denominator):
    """Return paper millimetres per Blender unit at a 1:N drawing scale."""
    denominator = float(scale_denominator)
    if not isfinite(denominator) or denominator <= 0.0:
        raise VectorExportError("Drawing scale must be greater than zero")
    scale_length = float(getattr(scene.unit_settings, "scale_length", 1.0))
    if not isfinite(scale_length) or scale_length <= 0.0:
        raise VectorExportError("Scene unit scale must be greater than zero")
    return scale_length * 1000.0 / denominator


def paper_mm_to_model(scene, paper_mm, scale_denominator):
    return float(paper_mm) / model_to_paper_factor(scene, scale_denominator)


def _camera_frame_world_size(scene, camera):
    if camera is None or camera.type != "CAMERA":
        raise VectorExportError("Set an active camera before exporting")
    if camera.data.type != "ORTHO":
        raise VectorExportError("Use an orthographic camera for scale-correct vector export")

    rotation = camera.matrix_world.to_quaternion()
    center = camera.matrix_world.translation + rotation @ Vector((0.0, 0.0, -1.0))
    center_ndc = world_to_camera_view(scene, camera, center)
    x_ndc = world_to_camera_view(scene, camera, center + rotation @ Vector((1.0, 0.0, 0.0)))
    y_ndc = world_to_camera_view(scene, camera, center + rotation @ Vector((0.0, 1.0, 0.0)))
    x_delta = abs(float(x_ndc.x - center_ndc.x))
    y_delta = abs(float(y_ndc.y - center_ndc.y))
    if x_delta <= 1e-12 or y_delta <= 1e-12:
        raise VectorExportError("The active camera frame could not be resolved")
    return 1.0 / x_delta, 1.0 / y_delta


def _clip_segment(first, second):
    """Liang-Barsky clip against the normalized camera frame."""
    x0, y0 = first
    x1, y1 = second
    dx = x1 - x0
    dy = y1 - y0
    lower = 0.0
    upper = 1.0
    for p, q in ((-dx, x0), (dx, 1.0 - x0), (-dy, y0), (dy, 1.0 - y0)):
        if abs(p) <= 1e-15:
            if q < 0.0:
                return None
            continue
        ratio = q / p
        if p < 0.0:
            lower = max(lower, ratio)
        else:
            upper = min(upper, ratio)
        if lower > upper:
            return None
    return (
        (x0 + lower * dx, y0 + lower * dy),
        (x0 + upper * dx, y0 + upper * dy),
    )


def build_vector_document(
    scene,
    camera,
    strokes,
    *,
    paper_size="A4",
    orientation="PORTRAIT",
    scale_denominator=10.0,
    annotation_count=0,
    skipped_count=0,
    sheet_strokes=(),
):
    """Project world strokes through an orthographic camera onto a physical page."""
    width_mm, height_mm = paper_dimensions_mm(paper_size, orientation)
    factor = model_to_paper_factor(scene, scale_denominator)
    frame_width_world, frame_height_world = _camera_frame_world_size(scene, camera)
    frame_width_mm = frame_width_world * factor
    frame_height_mm = frame_height_world * factor
    if frame_width_mm > width_mm + 1e-6 or frame_height_mm > height_mm + 1e-6:
        raise VectorExportError(
            f"Camera frame is {frame_width_mm:.1f} × {frame_height_mm:.1f} mm at 1:{scale_denominator:g}; "
            f"choose a larger page, a larger scale denominator, or a tighter camera frame"
        )

    left = (width_mm - frame_width_mm) * 0.5
    top = (height_mm - frame_height_mm) * 0.5
    page_strokes = []
    for stroke in strokes:
        if not isinstance(stroke, OutputStroke):
            raise TypeError("strokes must contain OutputStroke values")
        projected = [world_to_camera_view(scene, camera, Vector(point)) for point in stroke.points]
        for first, second in zip(projected, projected[1:]):
            if first.z < 0.0 or second.z < 0.0:
                continue
            clipped = _clip_segment((first.x, first.y), (second.x, second.y))
            if clipped is None:
                continue
            page_points = tuple(
                (
                    left + point[0] * frame_width_mm,
                    top + (1.0 - point[1]) * frame_height_mm,
                )
                for point in clipped
            )
            page_strokes.append(PageStroke(
                points=page_points,
                color=tuple(float(channel) for channel in stroke.color),
                line_width_mm=float(stroke.line_width) * factor,
            ))
    if not page_strokes:
        raise VectorExportError("No valid annotation strokes fall inside the camera frame")
    for stroke in sheet_strokes:
        if not isinstance(stroke, SheetStroke):
            raise TypeError("sheet_strokes must contain SheetStroke values")
        page_strokes.append(PageStroke(
            points=stroke.points,
            color=stroke.color,
            line_width_mm=stroke.line_width_mm,
            role=stroke.role,
        ))
    return VectorDocument(
        width_mm=width_mm,
        height_mm=height_mm,
        strokes=tuple(page_strokes),
        annotation_count=int(annotation_count),
        skipped_count=int(skipped_count),
    )


def svg_text(document):
    """Serialize a physical-size SVG using millimetres for page and stroke units."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            f'width="{document.width_mm:g}mm" height="{document.height_mm:g}mm" '
            f'viewBox="0 0 {document.width_mm:g} {document.height_mm:g}">'
        ),
        (
            f'  <metadata>Dimensions vector export; annotations={document.annotation_count}; '
            f'skipped={document.skipped_count}</metadata>'
        ),
        '  <g fill="none" stroke-linecap="round" stroke-linejoin="round">',
    ]
    for stroke in document.strokes:
        points = " ".join(f"{x:.6f},{y:.6f}" for x, y in stroke.points)
        red, green, blue, alpha = stroke.color
        color = "#{:02x}{:02x}{:02x}".format(
            round(max(0.0, min(1.0, red)) * 255),
            round(max(0.0, min(1.0, green)) * 255),
            round(max(0.0, min(1.0, blue)) * 255),
        )
        lines.append(
            f'    <polyline points="{escape(points)}" stroke="{color}" '
            f'stroke-opacity="{max(0.0, min(1.0, alpha)):.6f}" '
            f'stroke-width="{stroke.line_width_mm:.6f}" />'
        )
    lines.extend(("  </g>", "</svg>", ""))
    return "\n".join(lines)


def pdf_bytes(document):
    """Serialize a single-page PDF 1.4 with vector line segments."""
    points_per_mm = 72.0 / 25.4
    content = ["1 J", "1 j"]
    for stroke in document.strokes:
        red = max(0.0, min(1.0, float(stroke.color[0])))
        green = max(0.0, min(1.0, float(stroke.color[1])))
        blue = max(0.0, min(1.0, float(stroke.color[2])))
        content.append(f"{red:.6f} {green:.6f} {blue:.6f} RG")
        content.append(f"{stroke.line_width_mm * points_per_mm:.6f} w")
        first_x, first_y = stroke.points[0]
        content.append(
            f"{first_x * points_per_mm:.6f} "
            f"{(document.height_mm - first_y) * points_per_mm:.6f} m"
        )
        for x, y in stroke.points[1:]:
            content.append(
                f"{x * points_per_mm:.6f} "
                f"{(document.height_mm - y) * points_per_mm:.6f} l"
            )
        content.append("S")
    stream = ("\n".join(content) + "\n").encode("ascii")
    width_points = document.width_mm * points_per_mm
    height_points = document.height_mm * points_per_mm
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width_points:.6f} {height_points:.6f}] "
            "/Resources << >> /Contents 4 0 R >>"
        ).encode("ascii"),
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"endstream",
    )
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


def write_svg(filepath, document):
    with open(filepath, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(svg_text(document))


def write_pdf(filepath, document):
    with open(filepath, "wb") as handle:
        handle.write(pdf_bytes(document))
