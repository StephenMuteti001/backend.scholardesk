# dashboard/schemas.py

from utils.exceptions import ValidationError

MIN_MONTHS = 1
MAX_MONTHS = 24


def validate_overview_args(args):
    """
    Shared query-param validation for every /dashboard/overview route
    (admin, customer, and expert). Currently just an optional trailing
    window size in months; kept as its own schema function so routes
    never inline argument parsing, matching the rest of the codebase.
    """

    months = args.get("months")

    if months is None:
        return {"months": None}

    try:
        months = int(months)
    except (TypeError, ValueError):
        raise ValidationError("months must be an integer.")

    if months < MIN_MONTHS or months > MAX_MONTHS:
        raise ValidationError(
            f"months must be between {MIN_MONTHS} and {MAX_MONTHS}."
        )

    return {"months": months}
