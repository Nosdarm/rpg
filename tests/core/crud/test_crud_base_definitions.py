import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Optional, Any, cast # Added cast

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import Column, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base as ActualBase
from src.core.crud_base_definitions import CRUDBase


# --- Mock SQLAlchemy Models for Testing ---
class MockUser(ActualBase):
    __tablename__ = "mock_users_for_crud_base_test"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    guild_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, MockUser):
            return NotImplemented
        return self.id == other.id

class MockNoPK(ActualBase):
    __tablename__ = "mock_no_pk_for_crud_base_test"
    name: Mapped[str] = mapped_column(String, primary_key=True)

class MockStaticIdPK(ActualBase):
    __tablename__ = "mock_static_id_pk_for_crud_base_test"
    static_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    guild_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    return session

@pytest.fixture
def user_crud() -> CRUDBase[MockUser]:
    return CRUDBase(MockUser)

@pytest.mark.asyncio
async def test_get_many_by_ids_success_no_guild(
    user_crud: CRUDBase[MockUser], mock_db_session: AsyncSession
):
    user1 = MockUser(id=1, name="User One")
    user2 = MockUser(id=2, name="User Two")
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [user1, user2]
    mock_db_session.execute.return_value = mock_result # type: ignore
    ids_to_fetch = [1, 2]
    fetched_users = await user_crud.get_many_by_ids(db=mock_db_session, ids=ids_to_fetch)
    assert len(fetched_users) == 2
    assert user1 in fetched_users
    assert user2 in fetched_users
    mock_db_session.execute.assert_called_once() # type: ignore

@pytest.mark.asyncio
async def test_get_many_by_ids_success_with_guild(
    user_crud: CRUDBase[MockUser], mock_db_session: AsyncSession
):
    user_guild1_1 = MockUser(id=1, name="User G1-1", guild_id=100)
    user_guild1_2 = MockUser(id=2, name="User G1-2", guild_id=100)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [user_guild1_1, user_guild1_2]
    mock_db_session.execute.return_value = mock_result # type: ignore
    ids_to_fetch = [1, 2, 3]
    guild_id_filter = 100
    fetched_users = await user_crud.get_many_by_ids(
        db=mock_db_session, ids=ids_to_fetch, guild_id=guild_id_filter
    )
    assert len(fetched_users) == 2
    assert user_guild1_1 in fetched_users
    assert user_guild1_2 in fetched_users
    mock_db_session.execute.assert_called_once() # type: ignore


@pytest.mark.asyncio
async def test_get_many_by_ids_some_not_found(
    user_crud: CRUDBase[MockUser], mock_db_session: AsyncSession
):
    user1 = MockUser(id=1, name="User One")
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [user1]
    mock_db_session.execute.return_value = mock_result # type: ignore
    ids_to_fetch = [1, 3]
    fetched_users = await user_crud.get_many_by_ids(db=mock_db_session, ids=ids_to_fetch)
    assert len(fetched_users) == 1
    assert user1 in fetched_users
    mock_db_session.execute.assert_called_once() # type: ignore

@pytest.mark.asyncio
async def test_get_many_by_ids_all_not_found(
    user_crud: CRUDBase[MockUser], mock_db_session: AsyncSession
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result # type: ignore
    ids_to_fetch = [4, 5]
    fetched_users = await user_crud.get_many_by_ids(db=mock_db_session, ids=ids_to_fetch)
    assert len(fetched_users) == 0
    mock_db_session.execute.assert_called_once() # type: ignore

@pytest.mark.asyncio
async def test_get_many_by_ids_empty_list_input(
    user_crud: CRUDBase[MockUser], mock_db_session: AsyncSession
):
    ids_to_fetch: List[int] = []
    fetched_users = await user_crud.get_many_by_ids(db=mock_db_session, ids=ids_to_fetch)
    assert len(fetched_users) == 0
    mock_db_session.execute.assert_not_called() # type: ignore

@pytest.mark.asyncio
async def test_get_many_by_ids_model_no_pk_logs_error(
    mock_db_session: AsyncSession
):
    # MockNoPK is now defined at module level
    crud_no_pk = CRUDBase(MockNoPK)
    with patch('src.core.crud_base_definitions.logger.error') as mock_logger_error:
        result = await crud_no_pk.get_many_by_ids(db=mock_db_session, ids=[1])
        assert result == []
        mock_logger_error.assert_called_once_with( # type: ignore
            "Model MockNoPK does not have a recognized PK attribute ('id' or 'static_id') for get_many_by_ids operation."
        )

@pytest.mark.asyncio
async def test_get_many_by_ids_with_static_id_pk(mock_db_session: AsyncSession):
    # MockStaticIdPK is defined at module level
    crud_static_pk = CRUDBase(MockStaticIdPK)
    item1 = MockStaticIdPK(static_id="item_a", name="Item A")
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [item1]
    mock_db_session.execute.return_value = mock_result # type: ignore
    ids_to_fetch = ["item_a", "item_b"]
    fetched_items = await crud_static_pk.get_many_by_ids(db=mock_db_session, ids=ids_to_fetch)
    assert len(fetched_items) == 1
    assert fetched_items[0].static_id == "item_a"
    mock_db_session.execute.assert_called_once() # type: ignore

    mock_db_session.execute.reset_mock() # type: ignore
    item_guild = MockStaticIdPK(static_id="item_g", name="Item Guild", guild_id=100)
    mock_result.scalars.return_value.all.return_value = [item_guild] # Already a mock, return_value assignment is fine
    fetched_items_guild = await crud_static_pk.get_many_by_ids(
        db=mock_db_session, ids=["item_g", "item_x"], guild_id=100
    )
    assert len(fetched_items_guild) == 1
    assert fetched_items_guild[0].static_id == "item_g"
    assert fetched_items_guild[0].guild_id == 100
    mock_db_session.execute.assert_called_once() # type: ignore
