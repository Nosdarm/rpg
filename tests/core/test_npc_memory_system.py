import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.npc_memory_system import add_to_npc_memory, get_npc_memory
from backend.models.player_npc_memory import PlayerNpcMemory
from backend.models.party_npc_memory import PartyNpcMemory

# Mocking CRUD functions directly as they are imported in npc_memory_system
# If they were methods of a class passed around, we'd mock the class.

@pytest.mark.asyncio
class TestNpcMemorySystem:

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @patch('backend.core.npc_memory_system.crud_player_npc_memory', new_callable=AsyncMock)
    @patch('backend.core.npc_memory_system.crud_party_npc_memory', new_callable=AsyncMock)
    async def test_add_to_npc_memory_player(
        self, mock_crud_party_mem: AsyncMock, mock_crud_player_mem: AsyncMock, mock_session: AsyncMock
    ):
        guild_id = 1
        npc_id = 10
        player_id = 100
        event_type = "PLAYER_INTERACTION"
        details = {"action": "talked", "topic": "quest"}

        mock_created_player_memory = PlayerNpcMemory(
            id=1, guild_id=guild_id, player_id=player_id, npc_id=npc_id,
            event_type=event_type, memory_data_json=details
        )
        mock_crud_player_mem.create = AsyncMock(return_value=mock_created_player_memory)

        result = await add_to_npc_memory(
            mock_session, guild_id, npc_id, event_type, details, player_id=player_id
        )

        mock_crud_player_mem.create.assert_called_once()
        # More detailed check of the `obj_in` argument:
        called_args, called_kwargs = mock_crud_player_mem.create.call_args
        assert called_kwargs['obj_in']['guild_id'] == guild_id
        assert called_kwargs['obj_in']['player_id'] == player_id
        assert called_kwargs['obj_in']['npc_id'] == npc_id
        assert called_kwargs['obj_in']['event_type'] == event_type
        assert called_kwargs['obj_in']['memory_data_json'] == details
        assert 'timestamp' in called_kwargs['obj_in'] # Check if timestamp is included

        mock_crud_party_mem.create.assert_not_called()
        assert result == mock_created_player_memory

    @patch('backend.core.npc_memory_system.crud_player_npc_memory', new_callable=AsyncMock)
    @patch('backend.core.npc_memory_system.crud_party_npc_memory', new_callable=AsyncMock)
    async def test_add_to_npc_memory_party(
        self, mock_crud_party_mem: AsyncMock, mock_crud_player_mem: AsyncMock, mock_session: AsyncMock
    ):
        guild_id = 1
        npc_id = 10
        party_id = 200
        event_type = "PARTY_ENCOUNTER"
        details = {"location": "forest", "mood": "tense"}

        mock_created_party_memory = PartyNpcMemory(
            id=2, guild_id=guild_id, party_id=party_id, npc_id=npc_id,
            event_type=event_type, memory_data_json=details
        )
        mock_crud_party_mem.create = AsyncMock(return_value=mock_created_party_memory)

        result = await add_to_npc_memory(
            mock_session, guild_id, npc_id, event_type, details, party_id=party_id
        )

        mock_crud_party_mem.create.assert_called_once()
        called_args, called_kwargs = mock_crud_party_mem.create.call_args
        assert called_kwargs['obj_in']['guild_id'] == guild_id
        assert called_kwargs['obj_in']['party_id'] == party_id
        assert called_kwargs['obj_in']['npc_id'] == npc_id
        assert called_kwargs['obj_in']['event_type'] == event_type
        assert called_kwargs['obj_in']['memory_data_json'] == details
        assert 'timestamp' in called_kwargs['obj_in']

        mock_crud_player_mem.create.assert_not_called()
        assert result == mock_created_party_memory

    @patch('backend.core.npc_memory_system.crud_player_npc_memory', new_callable=AsyncMock)
    @patch('backend.core.npc_memory_system.crud_party_npc_memory', new_callable=AsyncMock)
    async def test_add_to_npc_memory_both_ids_error(
        self, mock_crud_party_mem: AsyncMock, mock_crud_player_mem: AsyncMock, mock_session: AsyncMock
    ):
        result = await add_to_npc_memory(
            mock_session, 1, 10, "ERROR_EVENT", {}, player_id=100, party_id=200
        )
        assert result is None
        mock_crud_player_mem.create.assert_not_called()
        mock_crud_party_mem.create.assert_not_called()

    @patch('backend.core.npc_memory_system.crud_player_npc_memory', new_callable=AsyncMock)
    @patch('backend.core.npc_memory_system.crud_party_npc_memory', new_callable=AsyncMock)
    async def test_add_to_npc_memory_no_ids_error(
        self, mock_crud_party_mem: AsyncMock, mock_crud_player_mem: AsyncMock, mock_session: AsyncMock
    ):
        result = await add_to_npc_memory(
            mock_session, 1, 10, "ERROR_EVENT", {}
        )
        assert result is None
        mock_crud_player_mem.create.assert_not_called()
        mock_crud_party_mem.create.assert_not_called()

    @patch('backend.core.npc_memory_system.crud_player_npc_memory', new_callable=AsyncMock)
    @patch('backend.core.npc_memory_system.crud_party_npc_memory', new_callable=AsyncMock)
    async def test_add_to_npc_memory_crud_exception(
        self, mock_crud_party_mem: AsyncMock, mock_crud_player_mem: AsyncMock, mock_session: AsyncMock
    ):
        mock_crud_player_mem.create.side_effect = Exception("DB error")
        result = await add_to_npc_memory(mock_session, 1, 10, "EVENT", {}, player_id=100)
        assert result is None


    @patch('backend.core.npc_memory_system.crud_player_npc_memory', new_callable=AsyncMock)
    @patch('backend.core.npc_memory_system.crud_party_npc_memory', new_callable=AsyncMock)
    async def test_get_npc_memory_player(
        self, mock_crud_party_mem: AsyncMock, mock_crud_player_mem: AsyncMock, mock_session: AsyncMock
    ):
        guild_id = 1
        npc_id = 10
        player_id = 100
        limit = 50

        mock_player_memories = [PlayerNpcMemory(id=i) for i in range(3)]
        mock_crud_player_mem.get_multi_by_player_and_npc = AsyncMock(return_value=mock_player_memories)

        result = await get_npc_memory(
            mock_session, guild_id, npc_id, player_id=player_id, limit=limit
        )

        mock_crud_player_mem.get_multi_by_player_and_npc.assert_called_once_with(
            mock_session, guild_id=guild_id, player_id=player_id, npc_id=npc_id, limit=limit
        )
        mock_crud_party_mem.get_multi_by_party_and_npc.assert_not_called()
        assert result == mock_player_memories

    @patch('backend.core.npc_memory_system.crud_player_npc_memory', new_callable=AsyncMock)
    @patch('backend.core.npc_memory_system.crud_party_npc_memory', new_callable=AsyncMock)
    async def test_get_npc_memory_party(
        self, mock_crud_party_mem: AsyncMock, mock_crud_player_mem: AsyncMock, mock_session: AsyncMock
    ):
        guild_id = 1
        npc_id = 10
        party_id = 200
        limit = 20

        mock_party_memories = [PartyNpcMemory(id=i) for i in range(2)]
        mock_crud_party_mem.get_multi_by_party_and_npc = AsyncMock(return_value=mock_party_memories)

        result = await get_npc_memory(
            mock_session, guild_id, npc_id, party_id=party_id, limit=limit
        )

        mock_crud_party_mem.get_multi_by_party_and_npc.assert_called_once_with(
            mock_session, guild_id=guild_id, party_id=party_id, npc_id=npc_id, limit=limit
        )
        mock_crud_player_mem.get_multi_by_player_and_npc.assert_not_called()
        assert result == mock_party_memories

    @patch('backend.core.npc_memory_system.crud_player_npc_memory', new_callable=AsyncMock)
    @patch('backend.core.npc_memory_system.crud_party_npc_memory', new_callable=AsyncMock)
    async def test_get_npc_memory_both_ids_error(
        self, mock_crud_party_mem: AsyncMock, mock_crud_player_mem: AsyncMock, mock_session: AsyncMock
    ):
        result = await get_npc_memory(
            mock_session, 1, 10, player_id=100, party_id=200
        )
        assert result == []
        mock_crud_player_mem.get_multi_by_player_and_npc.assert_not_called()
        mock_crud_party_mem.get_multi_by_party_and_npc.assert_not_called()

    @patch('backend.core.npc_memory_system.crud_player_npc_memory', new_callable=AsyncMock)
    @patch('backend.core.npc_memory_system.crud_party_npc_memory', new_callable=AsyncMock)
    async def test_get_npc_memory_no_ids_error(
        self, mock_crud_party_mem: AsyncMock, mock_crud_player_mem: AsyncMock, mock_session: AsyncMock
    ):
        result = await get_npc_memory(mock_session, 1, 10)
        assert result == []
        mock_crud_player_mem.get_multi_by_player_and_npc.assert_not_called()
        mock_crud_party_mem.get_multi_by_party_and_npc.assert_not_called()

    @patch('backend.core.npc_memory_system.crud_player_npc_memory', new_callable=AsyncMock)
    @patch('backend.core.npc_memory_system.crud_party_npc_memory', new_callable=AsyncMock)
    async def test_get_npc_memory_crud_exception(
        self, mock_crud_party_mem: AsyncMock, mock_crud_player_mem: AsyncMock, mock_session: AsyncMock
    ):
        mock_crud_party_mem.get_multi_by_party_and_npc.side_effect = Exception("DB error")
        result = await get_npc_memory(mock_session, 1, 10, party_id=200)
        assert result == []
