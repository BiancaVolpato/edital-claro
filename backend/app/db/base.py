"""Declarative base shared by all ORM models (models arrive in later stages)."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
