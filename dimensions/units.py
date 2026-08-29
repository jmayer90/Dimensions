from math import floor, gcd, pi
import re

import bpy


def get_display_settings(context):
    return getattr(context.scene, "dimensions_settings", None)


def get_configured_unit_style(context):
    settings = get_display_settings(context)
    if settings is None:
        return "BLENDER"

    unit_system = context.scene.unit_settings.system
    if unit_system == "METRIC":
        return settings.metric_unit_style

    if unit_system == "IMPERIAL":
        return settings.imperial_unit_style

    return settings.unit_style


def blender_units_to_inches(context, value):
    return blender_units_to_meters(context, value) / 0.0254


def blender_units_to_meters(context, value):
    scale_length = context.scene.unit_settings.scale_length or 1.0
    return value * scale_length


def parse_distance_input(context, text):
    value_text = text.strip()
    if not value_text:
        raise ValueError("Distance input is empty")

    if context is None:
        return float(value_text)

    unit_settings = context.scene.unit_settings
    lowered = value_text.lower()
    if "\"" in value_text or "'" in value_text or re.search(r"(in|inch|inches|ft|foot|feet)\s*$", lowered):
        unit_system = "IMPERIAL"
    elif re.search(r"(mm|millimeter|millimeters|cm|centimeter|centimeters|m|meter|meters)\s*$", lowered):
        unit_system = "METRIC"
    else:
        unit_system = unit_settings.system

    if unit_system not in {"METRIC", "IMPERIAL"}:
        return float(value_text)

    meters = bpy.utils.units.to_value(unit_system, "LENGTH", value_text)
    return meters / (unit_settings.scale_length or 1.0)


def parse_angle_input(context, text):
    """Parse an angle into radians, accepting explicit degrees or radians."""
    value_text = text.strip().lower().replace("°", "deg")
    if not value_text:
        raise ValueError("Angle input is empty")
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(deg|degree|degrees|rad|radian|radians)?", value_text)
    if match is None:
        raise ValueError(f"Invalid angle: {text}")
    value = float(match.group(1))
    unit = match.group(2)
    if unit is None:
        rotation = getattr(getattr(context, "scene", None), "unit_settings", None)
        unit = "rad" if getattr(rotation, "system_rotation", "DEGREES") == "RADIANS" else "deg"
    return value if unit.startswith("rad") else value * pi / 180.0


def infer_unit_style(context):
    unit_settings = context.scene.unit_settings

    if unit_settings.system == "METRIC":
        explicit_metric_styles = {
            "MILLIMETERS": "MILLIMETERS",
            "CENTIMETERS": "CENTIMETERS",
            "METERS": "METERS",
        }
        return explicit_metric_styles.get(unit_settings.length_unit, "METRIC_AUTO")

    if unit_settings.system != "IMPERIAL":
        return "BLENDER"

    if unit_settings.length_unit in {"FEET"} or unit_settings.use_separate:
        return "FEET_INCHES"

    if unit_settings.length_unit in {"INCHES", "THOU"}:
        return "INCH_DECIMAL"

    return "INCH_FRACTION"


def format_length(context, value, precision=3, unit_style=None):
    settings = get_display_settings(context)
    if settings is None:
        return _format_blender_units(context, value, precision)

    style = unit_style or get_configured_unit_style(context)
    if style == "AUTO":
        style = infer_unit_style(context)

    if style == "BLENDER":
        return _format_blender_units(context, value, precision)

    if style == "METRIC_AUTO":
        return format_metric_auto(context, value, precision)

    if style == "MILLIMETERS":
        return format_metric(context, value, precision, 1000.0, "mm")

    if style == "CENTIMETERS":
        return format_metric(context, value, precision, 100.0, "cm")

    if style == "METERS":
        return format_metric(context, value, precision, 1.0, "m")

    denominator = int(settings.imperial_denominator)

    if style == "FEET_INCHES":
        return format_feet_and_inches(context, value, denominator)

    if style == "INCH_DECIMAL":
        return format_inches_decimal(context, value, precision)

    if style == "INCH_FRACTION":
        return format_inches_fraction(context, value, denominator)

    return _format_blender_units(context, value, precision)


def format_dual_length(
    context,
    value,
    precision=3,
    unit_style=None,
    secondary_unit_style="NONE",
    secondary_precision=2,
    arrangement="BRACKETS",
):
    """Format a primary length and an optional independently formatted secondary value."""
    primary = format_length(context, value, precision, unit_style)
    if not secondary_unit_style or secondary_unit_style == "NONE":
        return primary
    secondary = format_length(
        context, value, secondary_precision, secondary_unit_style,
    )
    if arrangement == "STACKED":
        return f"{primary}\n{secondary}"
    if arrangement == "PARENTHESES":
        return f"{primary} ({secondary})"
    return f"{primary} [{secondary}]"


def format_volume(context, value, precision=3):
    settings = get_display_settings(context)
    style = get_configured_unit_style(context) if settings is not None else "BLENDER"
    if style == "AUTO":
        style = infer_unit_style(context)

    if style == "BLENDER":
        return _format_blender_volume(context, value, precision)

    cubic_meters = value * (context.scene.unit_settings.scale_length or 1.0) ** 3
    if style == "METRIC_AUTO":
        magnitude = abs(cubic_meters)
        if magnitude >= 1.0:
            return f"{cubic_meters:.{precision}f} m\u00b3"
        if magnitude >= 1e-6:
            return f"{cubic_meters * 1e6:.{precision}f} cm\u00b3"
        return f"{cubic_meters * 1e9:.{precision}f} mm\u00b3"

    metric_units = {
        "MILLIMETERS": (1e9, "mm\u00b3"),
        "CENTIMETERS": (1e6, "cm\u00b3"),
        "METERS": (1.0, "m\u00b3"),
    }
    if style in metric_units:
        multiplier, suffix = metric_units[style]
        return f"{cubic_meters * multiplier:.{precision}f} {suffix}"

    cubic_inches = cubic_meters / (0.0254 ** 3)
    if style == "FEET_INCHES" and abs(cubic_inches) >= 12.0 ** 3:
        return f"{cubic_inches / (12.0 ** 3):.{precision}f} ft\u00b3"
    if style in {"FEET_INCHES", "INCH_DECIMAL", "INCH_FRACTION"}:
        return f"{cubic_inches:.{precision}f} in\u00b3"

    return _format_blender_volume(context, value, precision)


def format_area(context, value, precision=3, unit_style=None):
    settings = get_display_settings(context)
    style = unit_style or (get_configured_unit_style(context) if settings is not None else "BLENDER")
    if style == "AUTO":
        style = infer_unit_style(context)
    square_meters = value * (context.scene.unit_settings.scale_length or 1.0) ** 2
    if style == "METRIC_AUTO":
        magnitude = abs(square_meters)
        if magnitude >= 1.0:
            return f"{square_meters:.{precision}f} m\u00b2"
        if magnitude >= 1e-4:
            return f"{square_meters * 1e4:.{precision}f} cm\u00b2"
        return f"{square_meters * 1e6:.{precision}f} mm\u00b2"
    metric_units = {
        "MILLIMETERS": (1e6, "mm\u00b2"),
        "CENTIMETERS": (1e4, "cm\u00b2"),
        "METERS": (1.0, "m\u00b2"),
    }
    if style in metric_units:
        multiplier, suffix = metric_units[style]
        return f"{square_meters * multiplier:.{precision}f} {suffix}"
    square_inches = square_meters / (0.0254 ** 2)
    if style == "FEET_INCHES" and abs(square_inches) >= 144.0:
        return f"{square_inches / 144.0:.{precision}f} ft\u00b2"
    if style in {"FEET_INCHES", "INCH_DECIMAL", "INCH_FRACTION"}:
        return f"{square_inches:.{precision}f} in\u00b2"
    try:
        unit_settings = context.scene.unit_settings
        return bpy.utils.units.to_string(
            unit_settings.system,
            "AREA",
            square_meters if unit_settings.system in {"METRIC", "IMPERIAL"} else value,
            precision=precision,
            split_unit=False,
        )
    except Exception:
        return f"{value:.{precision}f} BU\u00b2"


def _format_blender_units(context, value, precision):
    try:
        unit_settings = context.scene.unit_settings
        display_value = value
        if unit_settings.system in {"METRIC", "IMPERIAL"}:
            display_value = blender_units_to_meters(context, value)

        return bpy.utils.units.to_string(
            unit_settings.system,
            "LENGTH",
            display_value,
            precision=precision,
            split_unit=unit_settings.use_separate,
        )
    except Exception:
        return f"{value:.{precision}f}"


def _format_blender_volume(context, value, precision):
    try:
        unit_settings = context.scene.unit_settings
        display_value = value
        if unit_settings.system in {"METRIC", "IMPERIAL"}:
            display_value *= (unit_settings.scale_length or 1.0) ** 3

        return bpy.utils.units.to_string(
            unit_settings.system,
            "VOLUME",
            display_value,
            precision=precision,
            split_unit=False,
        )
    except Exception:
        return f"{value:.{precision}f} BU\u00b3"


def format_inches_decimal(context, value, precision):
    inches = blender_units_to_inches(context, value)
    return f'{inches:.{precision}f}"'


def format_metric(context, value, precision, units_per_meter, suffix):
    metric_value = blender_units_to_meters(context, value) * units_per_meter
    return f"{metric_value:.{precision}f} {suffix}"


def format_metric_auto(context, value, precision):
    meters = blender_units_to_meters(context, value)
    magnitude = abs(meters)

    if magnitude >= 1.0:
        return format_metric(context, value, precision, 1.0, "m")

    if magnitude >= 0.01:
        return format_metric(context, value, precision, 100.0, "cm")

    return format_metric(context, value, precision, 1000.0, "mm")


def format_inches_fraction(context, value, denominator):
    inches = blender_units_to_inches(context, value)
    return _format_fractional_inches(inches, denominator, include_feet=False)


def format_feet_and_inches(context, value, denominator):
    inches = blender_units_to_inches(context, value)
    return _format_fractional_inches(inches, denominator, include_feet=True)


def _format_fractional_inches(total_inches, denominator, include_feet):
    sign = "-" if total_inches < 0 else ""
    remaining_inches = abs(total_inches)

    feet = 0
    if include_feet:
        feet = int(floor(remaining_inches / 12.0))
        remaining_inches -= feet * 12.0

    whole_inches = int(floor(remaining_inches))
    fraction = remaining_inches - whole_inches

    numerator = int(round(fraction * denominator))
    if numerator == denominator:
        whole_inches += 1
        numerator = 0

    if whole_inches == 12 and include_feet:
        feet += 1
        whole_inches = 0

    if numerator > 0:
        common_divisor = gcd(numerator, denominator)
        numerator //= common_divisor
        reduced_denominator = denominator // common_divisor
        inch_text = f"{whole_inches} {numerator}/{reduced_denominator}" if whole_inches else f"{numerator}/{reduced_denominator}"
    else:
        inch_text = f"{whole_inches}"

    if include_feet:
        if feet and whole_inches == 0 and numerator == 0:
            return f"{sign}{feet}' 0\""

        if feet:
            return f"{sign}{feet}' {inch_text}\""

    return f'{sign}{inch_text}"'
