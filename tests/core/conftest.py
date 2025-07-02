import pytest
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import MagicMock

@pytest.fixture
def mock_db_session() -> AsyncMock: # Переименовано с mock_session
    """Provides a mock AsyncSession with common methods mocked."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    # Можно добавить другие часто используемые методы, если нужно
    # session.execute = AsyncMock()
    # session.add = AsyncMock()
    # session.scalar_one_or_none = AsyncMock(return_value=None)
    # session.scalars = AsyncMock(return_value=AsyncMock(all=AsyncMock(return_value=[])))
    return session

@pytest.fixture
def mock_location_crud() -> MagicMock:
    """Provides a mock CRUD object for Locations."""
    crud = MagicMock()
    crud.create = AsyncMock()
    crud.get = AsyncMock()
    crud.get_by_static_id = AsyncMock()
    crud.get_multi_by_attribute = AsyncMock() # Пример, если используется
    crud.update = AsyncMock()
    crud.remove = AsyncMock(return_value=True) # remove часто возвращает удаленный объект или True/None
    return crud

# Добавьте другие общие фикстуры для core тестов здесь, если необходимо
