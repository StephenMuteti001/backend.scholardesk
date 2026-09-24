from contextlib import contextmanager

from extensions import db


@contextmanager
def transaction():
    try:
        yield

        db.session.commit()

    except Exception:
        db.session.rollback()
        raise