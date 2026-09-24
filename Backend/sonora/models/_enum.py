from enum import StrEnum

from sqlalchemy import Enum


def enum_column[E: StrEnum](enum_cls: type[E], length: int = 20) -> Enum:
    """Stores enum *values* as VARCHAR (no native DB enum: simpler migrations on both DBs)."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        validate_strings=True,
        values_callable=lambda members: [m.value for m in members],
    )
