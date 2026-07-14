from math import floor, gcd

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


def format_length(context, value, precision=3):
    settings = get_display_settings(context)
    if settings is None:
        return _format_blender_units(context, value, precision)

    style = get_configured_unit_style(context)
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
