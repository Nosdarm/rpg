import pytest
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.fixture
def mock_session() -> AsyncMock:
    """Provides a mock AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    # You can add common mocks for session methods here if needed globally for core tests
    # For example:
    # session.execute = AsyncMock()
    # session.commit = AsyncMock()
    # session.rollback = AsyncMock()
    # session.add = AsyncMock()
    # session.scalar_one_or_none = AsyncMock(return_value=None) # Default to not found
    # session.scalars = AsyncMock(return_value=AsyncMock(all=AsyncMock(return_value=[]))) # Default to empty list
    return session
