from math import floor, gcd

import bpy


def get_display_settings(context):
    return getattr(context.scene, "dimensions_settings", None)


def blender_units_to_inches(context, value):
    scale_length = context.scene.unit_settings.scale_length or 1.0
    meters = value * scale_length
    return meters / 0.0254


def infer_unit_style(context):
    unit_settings = context.scene.unit_settings

    if unit_settings.system != "IMPERIAL":
        return "BLENDER"

    if unit_settings.length_unit in {"FEET"} or unit_settings.use_separate:
        return "FEET_INCHES"

    if unit_settings.length_unit in {"INCHES", "THOU"}:
        return "INCH_DECIMAL"

    return "INCH_FRACTION"


def format_length(context, value, precision=3):
    settings = get_display_settings(context)
    if settings is None:
        return _format_blender_units(context, value, precision)

    style = settings.unit_style
    if style == "AUTO":
        style = infer_unit_style(context)

    if style == "BLENDER":
        return _format_blender_units(context, value, precision)

    denominator = int(settings.imperial_denominator)

    if style == "FEET_INCHES":
        return format_feet_and_inches(context, value, denominator)

    if style == "INCH_DECIMAL":
        return format_inches_decimal(context, value, precision)

    if style == "INCH_FRACTION":
        return format_inches_fraction(context, value, denominator)

    return _format_blender_units(context, value, precision)


def _format_blender_units(context, value, precision):
    try:
        return bpy.utils.units.to_string(
            context.scene.unit_settings.system,
            "LENGTH",
            value,
            precision=precision,
            split_unit=context.scene.unit_settings.use_separate,
        )
    except Exception:
        return f"{value:.{precision}f}"


def format_inches_decimal(context, value, precision):
    inches = blender_units_to_inches(context, value)
    return f'{inches:.{precision}f}"'


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
