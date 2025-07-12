from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs

class Base(AsyncAttrs, DeclarativeBase):
    """
    Базовый класс для всех моделей SQLAlchemy.
    Включает поддержку AsyncAttrs для асинхронных операций.
    """
    pass

target_metadata = Base.metadata

# Здесь можно будет добавить общие столбцы или методы для всех моделей, если потребуется.
# Например:
# from sqlalchemy import Column, DateTime, func
# class TimestampedBase(Base):
#     __abstract__ = True
#     created_at = Column(DateTime, default=func.now())
#     updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import TIMESTAMP
import datetime # Added import for datetime

class TimestampMixin:
    """
    Mixin for adding created_at and updated_at timestamp columns to a model.
    Uses timezone-aware timestamps and provides Python-side defaults.
    """
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
        server_default=func.now(),
        nullable=False
    )
