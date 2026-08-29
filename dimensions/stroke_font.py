"""A compact single-line vector font for world-space Dimensions output.

Glyph coordinates occupy a one-unit-wide, one-unit-tall cell.  ``text_strokes``
maps those coordinates through caller-provided world axes, so this module has no
Blender dependency and its polylines can be passed directly to ``OutputStroke``.
"""

from math import sqrt


_SEGMENTS = {
    "A": ((0.0, 1.0), (1.0, 1.0)),
    "B": ((1.0, 1.0), (1.0, 0.5)),
    "C": ((1.0, 0.5), (1.0, 0.0)),
    "D": ((0.0, 0.0), (1.0, 0.0)),
    "E": ((0.0, 0.5), (1.0, 0.5)),
    "F": ((0.0, 1.0), (0.0, 0.5)),
    "G": ((0.0, 0.5), (0.0, 0.0)),
}

_DIGIT_SEGMENTS = {
    "0": "ABCD F G".replace(" ", ""),
    "1": "BC",
    "2": "ABEDG",
    "3": "ABCD E".replace(" ", ""),
    "4": "FBEC",
    "5": "AFEDC",
    "6": "AFGEDC",
    "7": "ABC",
    "8": "ABCDEFG",
    "9": "ABCFED",
}

_GLYPHS = {
    "A": (((0.0, 0.0), (0.5, 1.0), (1.0, 0.0)), ((0.2, 0.45), (0.8, 0.45))),
    "B": (((0.0, 0.0), (0.0, 1.0), (0.75, 1.0), (1.0, 0.75), (0.75, 0.5), (0.0, 0.5)), ((0.75, 0.5), (1.0, 0.25), (0.75, 0.0), (0.0, 0.0))),
    "C": (((1.0, 0.9), (0.75, 1.0), (0.2, 1.0), (0.0, 0.75), (0.0, 0.25), (0.2, 0.0), (0.75, 0.0), (1.0, 0.1)),),
    "D": (((0.0, 0.0), (0.0, 1.0), (0.65, 1.0), (1.0, 0.75), (1.0, 0.25), (0.65, 0.0), (0.0, 0.0)),),
    "E": (((1.0, 1.0), (0.0, 1.0), (0.0, 0.0), (1.0, 0.0)), ((0.0, 0.5), (0.75, 0.5))),
    "F": (((0.0, 0.0), (0.0, 1.0), (1.0, 1.0)), ((0.0, 0.5), (0.75, 0.5))),
    "G": (((1.0, 0.85), (0.75, 1.0), (0.2, 1.0), (0.0, 0.75), (0.0, 0.25), (0.2, 0.0), (0.8, 0.0), (1.0, 0.2), (1.0, 0.45), (0.55, 0.45)),),
    "H": (((0.0, 0.0), (0.0, 1.0)), ((1.0, 0.0), (1.0, 1.0)), ((0.0, 0.5), (1.0, 0.5))),
    "I": (((0.0, 1.0), (1.0, 1.0)), ((0.5, 1.0), (0.5, 0.0)), ((0.0, 0.0), (1.0, 0.0))),
    "J": (((0.0, 1.0), (1.0, 1.0)), ((0.75, 1.0), (0.75, 0.2), (0.55, 0.0), (0.15, 0.0), (0.0, 0.2))),
    "K": (((0.0, 0.0), (0.0, 1.0)), ((1.0, 1.0), (0.0, 0.5), (1.0, 0.0))),
    "L": (((0.0, 1.0), (0.0, 0.0), (1.0, 0.0)),),
    "M": (((0.0, 0.0), (0.0, 1.0), (0.5, 0.45), (1.0, 1.0), (1.0, 0.0)),),
    "N": (((0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)),),
    "O": (((0.2, 0.0), (0.0, 0.2), (0.0, 0.8), (0.2, 1.0), (0.8, 1.0), (1.0, 0.8), (1.0, 0.2), (0.8, 0.0), (0.2, 0.0)),),
    "P": (((0.0, 0.0), (0.0, 1.0), (0.75, 1.0), (1.0, 0.75), (0.75, 0.5), (0.0, 0.5)),),
    "Q": (((0.2, 0.0), (0.0, 0.2), (0.0, 0.8), (0.2, 1.0), (0.8, 1.0), (1.0, 0.8), (1.0, 0.2), (0.8, 0.0), (0.2, 0.0)), ((0.6, 0.35), (1.05, -0.1))),
    "R": (((0.0, 0.0), (0.0, 1.0), (0.75, 1.0), (1.0, 0.75), (0.75, 0.5), (0.0, 0.5)), ((0.5, 0.5), (1.0, 0.0))),
    "S": (((1.0, 0.85), (0.75, 1.0), (0.2, 1.0), (0.0, 0.8), (0.2, 0.55), (0.8, 0.45), (1.0, 0.2), (0.8, 0.0), (0.2, 0.0), (0.0, 0.15)),),
    "T": (((0.0, 1.0), (1.0, 1.0)), ((0.5, 1.0), (0.5, 0.0))),
    "U": (((0.0, 1.0), (0.0, 0.2), (0.2, 0.0), (0.8, 0.0), (1.0, 0.2), (1.0, 1.0)),),
    "V": (((0.0, 1.0), (0.5, 0.0), (1.0, 1.0)),),
    "W": (((0.0, 1.0), (0.2, 0.0), (0.5, 0.55), (0.8, 0.0), (1.0, 1.0)),),
    "X": (((0.0, 1.0), (1.0, 0.0)), ((0.0, 0.0), (1.0, 1.0))),
    "Y": (((0.0, 1.0), (0.5, 0.5), (1.0, 1.0)), ((0.5, 0.5), (0.5, 0.0))),
    "Z": (((0.0, 1.0), (1.0, 1.0), (0.0, 0.0), (1.0, 0.0)),),
    ".": (((0.5, 0.0), (0.5, 0.04)),),
    "-": (((0.15, 0.5), (0.85, 0.5)),),
    "+": (((0.15, 0.5), (0.85, 0.5)), ((0.5, 0.15), (0.5, 0.85))),
    "/": (((0.0, 0.0), (1.0, 1.0)),),
    "'": (((0.5, 1.0), (0.5, 0.72)),),
    '"': (((0.3, 1.0), (0.3, 0.72)), ((0.7, 1.0), (0.7, 0.72))),
    "(": (((0.8, 1.0), (0.45, 0.75), (0.3, 0.5), (0.45, 0.25), (0.8, 0.0)),),
    ")": (((0.2, 1.0), (0.55, 0.75), (0.7, 0.5), (0.55, 0.25), (0.2, 0.0)),),
    "±": (
        ((0.15, 0.68), (0.85, 0.68)),
        ((0.5, 0.35), (0.5, 1.0)),
        ((0.15, 0.15), (0.85, 0.15)),
    ),
    "°": (((0.3, 0.72), (0.2, 0.82), (0.3, 0.94), (0.45, 0.82), (0.3, 0.72)),),
    "⌀": (
        ((0.2, 0.0), (0.0, 0.2), (0.0, 0.8), (0.2, 1.0), (0.8, 1.0), (1.0, 0.8), (1.0, 0.2), (0.8, 0.0), (0.2, 0.0)),
        ((0.0, 0.0), (1.0, 1.0)),
    ),
    "⌒": (((0.05, 0.35), (0.2, 0.65), (0.5, 0.82), (0.8, 0.65), (0.95, 0.35)),),
    "²": (((0.1, 0.9), (0.3, 1.0), (0.5, 0.9), (0.1, 0.55), (0.5, 0.55)),),
    "³": (((0.1, 0.95), (0.45, 0.95), (0.25, 0.75), (0.45, 0.55), (0.1, 0.55)),),
}

_FALLBACK = (((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)), ((0.15, 0.15), (0.85, 0.85)), ((0.15, 0.85), (0.85, 0.15)))
_ADVANCE = 1.2
_SPACE_ADVANCE = 0.65
_LINE_ADVANCE = 1.45


def _glyph(character):
    if character in _DIGIT_SEGMENTS:
        return tuple(_SEGMENTS[name] for name in _DIGIT_SEGMENTS[character])
    return _GLYPHS.get(character, _FALLBACK)


def _advance(character):
    return _SPACE_ADVANCE if character == " " else _ADVANCE


def _vector(value, name):
    try:
        vector = tuple(float(component) for component in value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must contain three numeric components") from None
    if len(vector) != 3:
        raise ValueError(f"{name} must contain three numeric components")
    return vector


def _unit_vector(value, name):
    vector = _vector(value, name)
    length = sqrt(sum(component * component for component in vector))
    if length <= 1e-9:
        raise ValueError(f"{name} must be non-zero")
    return tuple(component / length for component in vector)


def text_block_dimensions(text, height):
    """Return the width and height occupied by a centered text block."""
    try:
        height = float(height)
    except (TypeError, ValueError):
        raise ValueError("height must be greater than zero") from None
    if height <= 0.0:
        raise ValueError("height must be greater than zero")
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    lines = text.split("\n")
    width = max(
        (sum(_advance(character.upper()) for character in line) for line in lines),
        default=0.0,
    )
    block_height = 1.0 + max(0, len(lines) - 1) * _LINE_ADVANCE
    return width * height, block_height * height


def _world_point(origin, x_axis, y_axis, local_x, local_y, height):
    return tuple(
        origin[index] + (x_axis[index] * local_x + y_axis[index] * local_y) * height
        for index in range(3)
    )


def text_strokes(text, origin, x_axis, y_axis, height, align="CENTER"):
    """Return world-space polylines for text using a compact vector alphabet.

    ``origin`` is the horizontal alignment point on the first line's baseline.
    New lines advance downward along ``y_axis``.  Lowercase glyphs map to their
    uppercase equivalent and unsupported characters become a visible boxed-X.
    """
    try:
        height = float(height)
    except (TypeError, ValueError):
        raise ValueError("height must be greater than zero") from None
    if height <= 0.0:
        raise ValueError("height must be greater than zero")
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    align = str(align).upper()
    if align not in {"CENTER", "LEFT", "RIGHT"}:
        raise ValueError("align must be CENTER, LEFT, or RIGHT")

    origin = _vector(origin, "origin")
    x_axis = _unit_vector(x_axis, "x_axis")
    y_axis = _unit_vector(y_axis, "y_axis")
    strokes = []
    for line_index, line in enumerate(text.split("\n")):
        characters = [character.upper() for character in line]
        line_width = sum(_advance(character) for character in characters)
        if align == "CENTER":
            cursor = -line_width * 0.5
        elif align == "RIGHT":
            cursor = -line_width
        else:
            cursor = 0.0
        baseline = -line_index * _LINE_ADVANCE
        for character in characters:
            if character != " ":
                for polyline in _glyph(character):
                    strokes.append(
                        tuple(
                            _world_point(origin, x_axis, y_axis, cursor + x, baseline + y, height)
                            for x, y in polyline
                        )
                    )
            cursor += _advance(character)
    return tuple(strokes)
