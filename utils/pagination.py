# utils/pagination.py
"""
Shared pagination helpers.

A few existing modules (orders/schemas.py, requests/schemas.py, ...)
each define their own near-identical `serialize_pagination()`. New
modules should import this one instead of adding yet another copy.
"""


def serialize_pagination(pagination):
    """
    Serialize a Flask-SQLAlchemy `Pagination` object.
    """
    return {
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
        "total": pagination.total,
    }


def paginate_query(query, page, per_page):
    """
    Apply pagination to a query and return (items, pagination_dict).
    """
    pagination = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    return pagination.items, serialize_pagination(pagination)
