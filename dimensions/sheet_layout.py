"""Pure physical-page geometry for a bordered single-sheet drawing layout."""

from dataclasses import dataclass
from math import isfinite

from .stroke_font import text_block_dimensions, text_strokes


DEFAULT_COLOR = (0.0, 0.0, 0.0, 1.0)
MINIMUM_BLOCK_WIDTH_MM = 60.0
MINIMUM_BLOCK_HEIGHT_MM = 24.0


class SheetLayoutError(ValueError):
    """Expected invalid page-layout configuration."""


@dataclass(frozen=True)
class SheetMetadata:
    title: str = "UNTITLED"
    drawing_number: str = "-"
    revision: str = "-"
    author: str = "-"
    date: str = "-"
    scale: str = "-"


@dataclass(frozen=True)
class PageMargins:
    left_mm: float
    top_mm: float
    right_mm: float
    bottom_mm: float


@dataclass(frozen=True)
class SheetStroke:
    points: tuple
    color: tuple
    line_width_mm: float
    role: str


@dataclass(frozen=True)
class SheetLayout:
    width_mm: float
    height_mm: float
    margins: PageMargins
    border_bounds: tuple
    title_block_bounds: tuple
    strokes: tuple


def build_sheet_layout(
    width_mm,
    height_mm,
    *,
    margins_mm=10.0,
    title_block_width_mm=85.0,
    title_block_height_mm=36.0,
    metadata=None,
    line_width_mm=0.25,
    text_height_mm=2.0,
    color=DEFAULT_COLOR,
    border_enabled=True,
    title_block_enabled=True,
):
    """Build deterministic border, title-block, and vector-text strokes in mm.

    All inputs and output coordinates are physical page millimetres. Model units,
    camera framing, and drawing scale therefore cannot change border, cell, text,
    or line-weight dimensions.
    """
    width = _positive_number(width_mm, "page width")
    height = _positive_number(height_mm, "page height")
    margins = _margins(margins_mm)
    if not isinstance(border_enabled, bool) or not isinstance(title_block_enabled, bool):
        raise TypeError("furniture enable flags must be bool values")
    furniture_enabled = border_enabled or title_block_enabled
    line_width = _positive_number(line_width_mm, "line width") if furniture_enabled else None
    color = _color(color) if furniture_enabled else None

    left = margins.left_mm
    top = margins.top_mm
    right = width - margins.right_mm
    bottom = height - margins.bottom_mm
    if right <= left or bottom <= top:
        raise SheetLayoutError("Margins leave no drawable page area")

    border_bounds = (left, top, right, bottom)
    strokes = []
    if border_enabled:
        strokes.append(_polyline(
            ((left, top), (right, top), (right, bottom), (left, bottom), (left, top)),
            color, line_width, "BORDER",
        ))

    block_bounds = None
    if title_block_enabled:
        text_height = _positive_number(text_height_mm, "text height")
        metadata = SheetMetadata() if metadata is None else metadata
        if not isinstance(metadata, SheetMetadata):
            raise TypeError("metadata must be a SheetMetadata value")
        _validate_metadata(metadata)
        block_width = _positive_number(title_block_width_mm, "title block width")
        block_height = _positive_number(title_block_height_mm, "title block height")
        if block_width < MINIMUM_BLOCK_WIDTH_MM or block_height < MINIMUM_BLOCK_HEIGHT_MM:
            raise SheetLayoutError(
                f"Title block must be at least {MINIMUM_BLOCK_WIDTH_MM:g} × "
                f"{MINIMUM_BLOCK_HEIGHT_MM:g} mm"
            )
        if block_width > right - left or block_height > bottom - top:
            raise SheetLayoutError("Title block does not fit inside the page margins")

        block_left = right - block_width
        block_top = bottom - block_height
        block_bounds = (block_left, block_top, right, bottom)
        strokes.append(_polyline(
            ((block_left, block_top), (right, block_top), (right, bottom), (block_left, bottom), (block_left, block_top)),
            color, line_width, "TITLE_BLOCK",
        ))

        title_bottom = block_top + block_height * 0.40
        details_bottom = block_top + block_height * 0.70
        middle_split = block_left + block_width * 0.72
        author_split = block_left + block_width * 0.38
        date_split = block_left + block_width * 0.72
        for points in (
            ((block_left, title_bottom), (right, title_bottom)),
            ((block_left, details_bottom), (right, details_bottom)),
            ((middle_split, title_bottom), (middle_split, details_bottom)),
            ((author_split, details_bottom), (author_split, bottom)),
            ((date_split, details_bottom), (date_split, bottom)),
        ):
            strokes.append(_polyline(points, color, line_width, "TITLE_GRID"))

        padding = max(1.0, text_height * 0.45)
        fields = (
            ("TITLE", metadata.title, block_left, block_top, right, title_bottom),
            ("DRAWING_NUMBER", metadata.drawing_number, block_left, title_bottom, middle_split, details_bottom),
            ("REVISION", metadata.revision, middle_split, title_bottom, right, details_bottom),
            ("AUTHOR", metadata.author, block_left, details_bottom, author_split, bottom),
            ("DATE", metadata.date, author_split, details_bottom, date_split, bottom),
            ("SCALE", metadata.scale, date_split, details_bottom, right, bottom),
        )
        for name, value, cell_left, cell_top, cell_right, cell_bottom in fields:
            label = _field_text(name, value)
            available_width = cell_right - cell_left - padding * 2.0
            available_height = cell_bottom - cell_top - padding * 2.0
            text_width, text_block_height = text_block_dimensions(label, text_height)
            if text_width > available_width + 1e-9 or text_block_height > available_height + 1e-9:
                raise SheetLayoutError(f"{name.replace('_', ' ').title()} does not fit in the title block")
            origin = (cell_left + padding, cell_top + padding + text_height, 0.0)
            for points in text_strokes(
                label, origin, (1.0, 0.0, 0.0), (0.0, -1.0, 0.0), text_height, "LEFT",
            ):
                strokes.append(_polyline(
                    tuple((point[0], point[1]) for point in points),
                    color,
                    line_width,
                    f"TEXT_{name}",
                ))

    return SheetLayout(
        width_mm=width,
        height_mm=height,
        margins=margins,
        border_bounds=border_bounds,
        title_block_bounds=block_bounds,
        strokes=tuple(strokes),
    )


def _field_text(name, value):
    labels = {
        "TITLE": "TITLE",
        "DRAWING_NUMBER": "NO",
        "REVISION": "REV",
        "AUTHOR": "BY",
        "DATE": "DATE",
        "SCALE": "SCALE",
    }
    return f"{labels[name]}\n{value}"


def _polyline(points, color, line_width, role):
    return SheetStroke(
        points=tuple((float(x), float(y)) for x, y in points),
        color=color,
        line_width_mm=line_width,
        role=role,
    )


def _positive_number(value, name):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise SheetLayoutError(f"{name.title()} must be greater than zero") from None
    if not isfinite(result) or result <= 0.0:
        raise SheetLayoutError(f"{name.title()} must be greater than zero")
    return result


def _nonnegative_number(value, name):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise SheetLayoutError(f"{name.title()} must be zero or greater") from None
    if not isfinite(result) or result < 0.0:
        raise SheetLayoutError(f"{name.title()} must be zero or greater")
    return result


def _margins(value):
    if isinstance(value, (int, float)):
        values = (value, value, value, value)
    else:
        try:
            values = tuple(value)
        except TypeError:
            raise SheetLayoutError("Margins must be one number or four numbers") from None
        if len(values) != 4:
            raise SheetLayoutError("Margins must be one number or four numbers")
    return PageMargins(*(
        _nonnegative_number(component, "margin") for component in values
    ))


def _color(value):
    try:
        color = tuple(float(channel) for channel in value)
    except (TypeError, ValueError):
        raise SheetLayoutError("Color must contain four finite channels") from None
    if len(color) != 4 or not all(isfinite(channel) for channel in color):
        raise SheetLayoutError("Color must contain four finite channels")
    return color


def _validate_metadata(metadata):
    for name in ("title", "drawing_number", "revision", "author", "date", "scale"):
        if not isinstance(getattr(metadata, name), str):
            raise TypeError(f"metadata {name} must be a string")
