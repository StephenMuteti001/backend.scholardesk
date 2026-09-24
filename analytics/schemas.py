# analytics/schemas.py

from utils.exceptions import ValidationError

# Accepted values for the frontend's `range` query param
# (AnalyticsParams.range in analyticsService.ts), e.g. "30d", "6m".
_RANGE_UNITS = {"d": "days", "m": "months", "y": "years"}


def validate_range_arg(args):
    """
    Parse an optional `range` query param such as "30d" / "6m" / "1y"
    into {"unit": "days"|"months"|"years", "value": int}, or None when
    not supplied - callers fall back to their own sensible default.
    """

    raw = args.get("range")

    if not raw:
        return None

    raw = raw.strip().lower()

    unit_key = raw[-1]
    value_part = raw[:-1]

    if unit_key not in _RANGE_UNITS or not value_part.isdigit():
        raise ValidationError(
            "range must look like '30d', '6m', or '1y'.",
            {"field": "range"},
        )

    return {
        "unit": _RANGE_UNITS[unit_key],
        "value": int(value_part),
    }
