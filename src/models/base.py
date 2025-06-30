from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs

class Base(AsyncAttrs, DeclarativeBase):
    """
    Базовый класс для всех моделей SQLAlchemy.
    Включает поддержку AsyncAttrs для асинхронных операций.
    """
    pass

# Здесь можно будет добавить общие столбцы или методы для всех моделей, если потребуется.
# Например:
# from sqlalchemy import Column, DateTime, func
# class TimestampedBase(Base):
#     __abstract__ = True
#     created_at = Column(DateTime, default=func.now())
#     updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
