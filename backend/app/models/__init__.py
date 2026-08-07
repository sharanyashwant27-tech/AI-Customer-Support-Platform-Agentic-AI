"""Alias package — ORM models live under `app.db.models`."""

from app.db.models import *  # noqa: F403
from app.db.models import CORE_TABLES

__all__ = ["CORE_TABLES"]
