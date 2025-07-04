import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch # Added patch
from typing import List, Optional, Any

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import Column, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column # For SQLAlchemy 2.0 style models

from src.models.base import Base as ActualBase # Use the project's actual Base
from src.core.crud_base_definitions import CRUDBase


# --- Mock SQLAlchemy Model for Testing ---
class MockUser(ActualBase):
    __tablename__ = "mock_users_for_crud_base_test" # Unique table name for tests

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    guild_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Make it hashable for set operations if needed in tests, though not strictly necessary for these tests
    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, MockUser):
            return NotImplemented
        return self.id == other.id


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    # Mock execute to simulate database returning results
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

    # Simulate SQLAlchemy Result object that execute returns
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [user1, user2]
    mock_db_session.execute.return_value = mock_result # type: ignore[attribute-error]

    ids_to_fetch = [1, 2]
    fetched_users = await user_crud.get_many_by_ids(db=mock_db_session, ids=ids_to_fetch)

    assert len(fetched_users) == 2
    assert user1 in fetched_users
    assert user2 in fetched_users
    mock_db_session.execute.assert_called_once() # type: ignore[attribute-error]
    # We can inspect the statement if needed, but for now, checking call and result is fine.

@pytest.mark.asyncio
async def test_get_many_by_ids_success_with_guild(
    user_crud: CRUDBase[MockUser], mock_db_session: AsyncSession
):
    user_guild1_1 = MockUser(id=1, name="User G1-1", guild_id=100)
    user_guild1_2 = MockUser(id=2, name="User G1-2", guild_id=100)
    # user_guild2_1 = MockUser(id=3, name="User G2-1", guild_id=200) # This user shouldn't be fetched

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [user_guild1_1, user_guild1_2]
    mock_db_session.execute.return_value = mock_result # type: ignore[attribute-error]

    ids_to_fetch = [1, 2, 3] # Ask for ID 3 as well
    guild_id_filter = 100
    fetched_users = await user_crud.get_many_by_ids(
        db=mock_db_session, ids=ids_to_fetch, guild_id=guild_id_filter
    )

    assert len(fetched_users) == 2
    assert user_guild1_1 in fetched_users
    assert user_guild1_2 in fetched_users
    # Test that the generated SQL (if we could inspect it) would filter by guild_id=100 and ids in [1,2,3]
    # For now, trust the mock_result is what the DB would return with that filter.
    mock_db_session.execute.assert_called_once() # type: ignore[attribute-error]


@pytest.mark.asyncio
async def test_get_many_by_ids_some_not_found(
    user_crud: CRUDBase[MockUser], mock_db_session: AsyncSession
):
    user1 = MockUser(id=1, name="User One")
    # ID 3 is requested but not found
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [user1]
    mock_db_session.execute.return_value = mock_result # type: ignore[attribute-error]

    ids_to_fetch = [1, 3]
    fetched_users = await user_crud.get_many_by_ids(db=mock_db_session, ids=ids_to_fetch)

    assert len(fetched_users) == 1
    assert user1 in fetched_users
    mock_db_session.execute.assert_called_once() # type: ignore[attribute-error]

@pytest.mark.asyncio
async def test_get_many_by_ids_all_not_found(
    user_crud: CRUDBase[MockUser], mock_db_session: AsyncSession
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [] # No users found
    mock_db_session.execute.return_value = mock_result # type: ignore[attribute-error]

    ids_to_fetch = [4, 5]
    fetched_users = await user_crud.get_many_by_ids(db=mock_db_session, ids=ids_to_fetch)

    assert len(fetched_users) == 0
    mock_db_session.execute.assert_called_once() # type: ignore[attribute-error]

@pytest.mark.asyncio
async def test_get_many_by_ids_empty_list_input(
    user_crud: CRUDBase[MockUser], mock_db_session: AsyncSession
):
    ids_to_fetch: List[int] = []
    fetched_users = await user_crud.get_many_by_ids(db=mock_db_session, ids=ids_to_fetch)

    assert len(fetched_users) == 0
    mock_db_session.execute.assert_not_called() # type: ignore[attribute-error] # Should return early

@pytest.mark.asyncio
async def test_get_many_by_ids_model_no_pk_logs_error(
    mock_db_session: AsyncSession
):
    class MockNoPK(ActualBase): # type: ignore
        __tablename__ = "mock_no_pk_for_crud_base_test"
        # No id or static_id defined as PK for the test's logic
        name: Mapped[str] = mapped_column(String, primary_key=True) # Name as PK to fail the check

    crud_no_pk = CRUDBase(MockNoPK)

    with patch('src.core.crud_base_definitions.logger.error') as mock_logger_error:
        result = await crud_no_pk.get_many_by_ids(db=mock_db_session, ids=[1])
        assert result == []
        mock_logger_error.assert_called_once_with(
            "Model MockNoPK does not have a recognized PK attribute ('id' or 'static_id') for get_many_by_ids operation."
        )

# Example of a model using static_id as primary key (conceptual)
class MockStaticIdPK(ActualBase):
    __tablename__ = "mock_static_id_pk_for_crud_base_test"
    static_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    guild_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

@pytest.mark.asyncio
async def test_get_many_by_ids_with_static_id_pk(mock_db_session: AsyncSession):
    crud_static_pk = CRUDBase(MockStaticIdPK)
    item1 = MockStaticIdPK(static_id="item_a", name="Item A")

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [item1]
    mock_db_session.execute.return_value = mock_result # type: ignore[attribute-error]

    ids_to_fetch = ["item_a", "item_b"]
    fetched_items = await crud_static_pk.get_many_by_ids(db=mock_db_session, ids=ids_to_fetch)

    assert len(fetched_items) == 1
    assert fetched_items[0].static_id == "item_a"
    mock_db_session.execute.assert_called_once() # type: ignore[attribute-error]
    # To fully test, one would inspect the statement passed to execute
    # and ensure it queries where(MockStaticIdPK.static_id.in_(ids_to_fetch))
    # This is a bit more involved with current mocking.

    # Test with guild_id as well
    mock_db_session.execute.reset_mock() # type: ignore[attribute-error]
    item_guild = MockStaticIdPK(static_id="item_g", name="Item Guild", guild_id=100)
    mock_result.scalars.return_value.all.return_value = [item_guild] # Simulate DB returns only this

    fetched_items_guild = await crud_static_pk.get_many_by_ids(
        db=mock_db_session, ids=["item_g", "item_x"], guild_id=100
    )
    assert len(fetched_items_guild) == 1
    assert fetched_items_guild[0].static_id == "item_g"
    assert fetched_items_guild[0].guild_id == 100
    mock_db_session.execute.assert_called_once() # type: ignore[attribute-error]

# TODO: Could add tests for different types in `ids` list if the method should handle them,
# but current signature `ids: List[Any]` implies it relies on SQLAlchemy's `in_` operator.
# Testing how SQLAlchemy handles mixed types in `in_` is probably out of scope for this unit test.
# The primary responsibility is that CRUDBase forms the query correctly.
