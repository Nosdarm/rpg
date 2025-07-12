import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.utils import log_event
from backend.models.enums import EventType
from backend.models.story_log import StoryLog # To inspect the object passed to session.add


@pytest.mark.asyncio
async def test_log_event_successful():
    mock_session = AsyncMock(spec=AsyncSession)
    guild_id = 1
    event_type_str = "PLAYER_ACTION"
    details_json = {"action": "looked_around"}
    player_id = 100
    party_id = 200
    location_id = 300
    initial_entity_ids = {"npcs": [400]}

    await log_event(
        session=mock_session,
        guild_id=guild_id,
        event_type=event_type_str,
        details_json=details_json,
        player_id=player_id,
        party_id=party_id,
        location_id=location_id,
        entity_ids_json=initial_entity_ids.copy(), # Pass a copy
    )

    mock_session.add.assert_called_once()
    added_log_entry = mock_session.add.call_args[0][0]

    assert isinstance(added_log_entry, StoryLog)
    assert added_log_entry.guild_id == guild_id
    assert added_log_entry.event_type == EventType.PLAYER_ACTION
    assert added_log_entry.details_json == details_json
    assert added_log_entry.location_id == location_id

    expected_entity_ids = {
        "npcs": [400],
        "players": [player_id],
        "parties": [party_id],
    }
    # Sort lists within dicts for comparison if order doesn't matter and might vary
    for key in expected_entity_ids:
        if isinstance(expected_entity_ids[key], list):
            expected_entity_ids[key].sort()
            if added_log_entry.entity_ids_json and key in added_log_entry.entity_ids_json:
                 added_log_entry.entity_ids_json[key].sort()

    assert added_log_entry.entity_ids_json == expected_entity_ids
    # added_log_entry.timestamp will be None here as server_default is a DB-level instruction
    # and we are not hitting the DB in this unit test.

@pytest.mark.asyncio
async def test_log_event_invalid_event_type_string(caplog):
    mock_session = AsyncMock(spec=AsyncSession)
    guild_id = 1
    event_type_str = "INVALID_EVENT_TYPE_XYZ"
    details_json = {"info": "test"}

    await log_event(
        session=mock_session,
        guild_id=guild_id,
        event_type=event_type_str,
        details_json=details_json,
    )

    mock_session.add.assert_not_called()
    assert f"Invalid event_type string: {event_type_str}" in caplog.text
    assert f"Cannot log event for guild {guild_id}" in caplog.text

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "player_id_in, party_id_in, initial_entities_in, expected_entities_out",
    [
        (1, 2, None, {"players": [1], "parties": [2]}),
        (1, None, {"npcs": [101]}, {"npcs": [101], "players": [1]}),
        (None, 2, {"npcs": [101]}, {"npcs": [101], "parties": [2]}),
        (1, 2, {"players": [3], "parties": [4]}, {"players": [3, 1], "parties": [4, 2]}),
        (1, None, {"players": [1, 3]}, {"players": [1, 3]}), # Test uniqueness
        (None, None, None, None), # Model stores None if empty
        (None, None, {}, None),   # Model stores None if empty
    ],
)
async def test_log_event_entity_ids_handling(
    player_id_in, party_id_in, initial_entities_in, expected_entities_out
):
    mock_session = AsyncMock(spec=AsyncSession)

    await log_event(
        session=mock_session,
        guild_id=1,
        event_type="SYSTEM_EVENT", # A valid event type
        details_json={"data": "test"},
        player_id=player_id_in,
        party_id=party_id_in,
        entity_ids_json=initial_entities_in.copy() if initial_entities_in else None,
    )

    mock_session.add.assert_called_once()
    added_log_entry = mock_session.add.call_args[0][0]

    # Sort lists if expected_entities_out is a dict, for consistent comparison
    if isinstance(expected_entities_out, dict):
        for key in expected_entities_out:
            if isinstance(expected_entities_out[key], list):
                expected_entities_out[key].sort()
        result_entities = added_log_entry.entity_ids_json
        if isinstance(result_entities, dict):
            for key in result_entities:
                if isinstance(result_entities[key], list):
                    result_entities[key].sort()
            assert result_entities == expected_entities_out
        else: # handles case where expected_entities_out is None
            assert result_entities == expected_entities_out
    else: # handles case where expected_entities_out is None
         assert added_log_entry.entity_ids_json == expected_entities_out


@pytest.mark.asyncio
async def test_log_event_minimal_parameters():
    mock_session = AsyncMock(spec=AsyncSession)
    guild_id = 1
    event_type_str = "NPC_ACTION"
    details_json = {"npc_id": 50, "action": "patrol"}

    await log_event(
        session=mock_session,
        guild_id=guild_id,
        event_type=event_type_str,
        details_json=details_json,
    )

    mock_session.add.assert_called_once()
    added_log_entry = mock_session.add.call_args[0][0]

    assert isinstance(added_log_entry, StoryLog)
    assert added_log_entry.guild_id == guild_id
    assert added_log_entry.event_type == EventType.NPC_ACTION
    assert added_log_entry.details_json == details_json
    assert added_log_entry.location_id is None
    assert added_log_entry.entity_ids_json is None # Because no player/party/initial provided
    # added_log_entry.timestamp will be None here as server_default is a DB-level instruction
