import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.movement_logic import handle_move_action, MovementError
from src.models import Player, Party, Location, LocationType
from src.models.enums import PlayerStatus, PartyTurnStatus


# Default attributes for mock objects
DEFAULT_GUILD_ID = 1
DEFAULT_PLAYER_DISCORD_ID = 100
DEFAULT_PLAYER_DB_ID = 1
DEFAULT_PARTY_DB_ID = 1
START_LOCATION_ID = 1
START_LOCATION_STATIC_ID = "start_zone"
TARGET_LOCATION_ID = 2
TARGET_LOCATION_STATIC_ID = "forest"
UNCONNECTED_LOCATION_ID = 3
UNCONNECTED_LOCATION_STATIC_ID = "mountain"
NON_EXISTENT_LOCATION_STATIC_ID = "void"

@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    return session

@pytest.fixture
def mock_player() -> Player:
    player = Player(
        id=DEFAULT_PLAYER_DB_ID,
        guild_id=DEFAULT_GUILD_ID,
        discord_id=DEFAULT_PLAYER_DISCORD_ID,
        name="TestPlayer",
        current_location_id=START_LOCATION_ID,
        current_status=PlayerStatus.EXPLORING
    )
    return player

@pytest.fixture
def mock_party(mock_player: Player) -> Party:
    party = Party(
        id=DEFAULT_PARTY_DB_ID,
        guild_id=DEFAULT_GUILD_ID,
        name="TestParty",
        player_ids_json=[mock_player.id],
        current_location_id=START_LOCATION_ID,
        turn_status=PartyTurnStatus.IDLE
    )
    mock_player.current_party_id = party.id # Link player to party
    return party


@pytest.fixture
def mock_start_location() -> Location:
    return Location(
        id=START_LOCATION_ID,
        guild_id=DEFAULT_GUILD_ID,
        static_id=START_LOCATION_STATIC_ID,
        name_i18n={"en": "Start Zone"},
        type=LocationType.TOWN,
        neighbor_locations_json=[
            {"location_id": TARGET_LOCATION_ID, "connection_type_i18n": {"en": "path"}}
        ]
    )

@pytest.fixture
def mock_target_location() -> Location:
    return Location(
        id=TARGET_LOCATION_ID,
        guild_id=DEFAULT_GUILD_ID,
        static_id=TARGET_LOCATION_STATIC_ID,
        name_i18n={"en": "Forest"},
        type=LocationType.FOREST,
        neighbor_locations_json=[
            {"location_id": START_LOCATION_ID, "connection_type_i18n": {"en": "path"}}
        ]
    )

@pytest.fixture
def mock_unconnected_location() -> Location:
    return Location(
        id=UNCONNECTED_LOCATION_ID,
        guild_id=DEFAULT_GUILD_ID,
        static_id=UNCONNECTED_LOCATION_STATIC_ID,
        name_i18n={"en": "Mountain"},
        type=LocationType.MOUNTAIN,
        neighbor_locations_json=[] # No connection to start_zone
    )

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.party_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.log_event", new_callable=AsyncMock)
@patch("src.core.movement_logic.on_enter_location", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_db_session") # For handle_move_action's own session
@patch("src.core.database.get_db_session") # For @transactional on _update_entities_location
async def test_handle_move_action_successful_solo_player(
    mock_db_get_db_session: MagicMock, # For @transactional
    mock_logic_get_db_session: MagicMock, # For handle_move_action
    mock_on_enter_location: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud: AsyncMock, # Not used but patched
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player: Player,
    mock_start_location: Location,
    mock_target_location: Location,
):
    # Both get_db_session contexts should yield the same mock_session for this test
    mock_logic_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_db_get_db_session.return_value.__aenter__.return_value = mock_session

    mock_player_crud.get_by_discord_id.return_value = mock_player
    mock_location_crud.get.side_effect = [mock_start_location] # First call for current_location
    mock_location_crud.get_by_static_id.return_value = mock_target_location

    success, message = await handle_move_action(
        DEFAULT_GUILD_ID, DEFAULT_PLAYER_DISCORD_ID, TARGET_LOCATION_STATIC_ID
    )

    assert success is True
    assert f"You have moved to '{mock_target_location.name_i18n['en']}'" in message
    assert mock_player.current_location_id == mock_target_location.id

    original_player_location_id = mock_start_location.id # Or START_LOCATION_ID directly

    mock_player_crud.get_by_discord_id.assert_called_once_with(
        mock_session, guild_id=DEFAULT_GUILD_ID, discord_id=DEFAULT_PLAYER_DISCORD_ID
    )
    mock_location_crud.get.assert_called_once_with(mock_session, id=original_player_location_id) # Check with original id
    mock_location_crud.get_by_static_id.assert_called_once_with(
        mock_session, guild_id=DEFAULT_GUILD_ID, static_id=TARGET_LOCATION_STATIC_ID
    )

    # Check log_event call (inside _update_entities_location)
    # The session is passed to _update_entities_location, which then passes it to log_event
    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args
    assert log_kwargs["session"] == mock_session
    assert log_kwargs["guild_id"] == DEFAULT_GUILD_ID
    assert log_kwargs["event_type"] == "player_move"
    assert log_kwargs["details_json"]["player_id"] == mock_player.id
    assert log_kwargs["details_json"]["to_location_id"] == mock_target_location.id

    mock_on_enter_location.assert_called_once_with(
        guild_id=DEFAULT_GUILD_ID,
        entity_id=mock_player.id,
        entity_type="player",
        location_id=mock_target_location.id,
    )
    mock_session.add.assert_called_with(mock_player) # From _update_entities_location
    # mock_session.commit should be called by @transactional on _update_entities_location
    # but testing the commit directly is hard without deeper mock of the decorator.
    # We trust the decorator works if session.add is called.

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.party_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.log_event", new_callable=AsyncMock)
@patch("src.core.movement_logic.on_enter_location", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_db_session") # For handle_move_action
@patch("src.core.database.get_db_session")      # For @transactional on _update_entities_location
async def test_handle_move_action_successful_party_move(
    mock_db_get_db_session: MagicMock,
    mock_logic_get_db_session: MagicMock,
    mock_on_enter_location: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player: Player, # Player is now part of mock_party
    mock_party: Party,
    mock_start_location: Location,
    mock_target_location: Location,
):
    mock_logic_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_db_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player_crud.get_by_discord_id.return_value = mock_player # Player is in mock_party
    mock_location_crud.get.return_value = mock_start_location
    mock_location_crud.get_by_static_id.return_value = mock_target_location
    mock_party_crud.get.return_value = mock_party

    success, message = await handle_move_action(
        DEFAULT_GUILD_ID, DEFAULT_PLAYER_DISCORD_ID, TARGET_LOCATION_STATIC_ID
    )

    assert success is True
    assert f"You and your party have moved to '{mock_target_location.name_i18n['en']}'" in message
    assert mock_player.current_location_id == mock_target_location.id
    assert mock_party.current_location_id == mock_target_location.id

    mock_party_crud.get.assert_called_once_with(mock_session, id=mock_player.current_party_id)

    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args
    assert log_kwargs["event_type"] == "party_move"
    assert log_kwargs["details_json"]["party_id"] == mock_party.id
    assert log_kwargs["details_json"]["to_location_id"] == mock_target_location.id

    mock_on_enter_location.assert_called_once_with(
        guild_id=DEFAULT_GUILD_ID,
        entity_id=mock_party.id,
        entity_type="party",
        location_id=mock_target_location.id,
    )
    # Check that both player and party were added to session for update
    assert mock_session.add.call_count == 2
    mock_session.add.assert_any_call(mock_player)
    mock_session.add.assert_any_call(mock_party)


@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_db_session")
async def test_handle_move_action_player_not_found(
    mock_get_db_session: MagicMock,
    mock_location_crud: AsyncMock, # Patched but not directly asserted
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player_crud.get_by_discord_id.return_value = None # Player not found

    success, message = await handle_move_action(
        DEFAULT_GUILD_ID, DEFAULT_PLAYER_DISCORD_ID, TARGET_LOCATION_STATIC_ID
    )
    assert success is False
    assert f"Player with Discord ID {DEFAULT_PLAYER_DISCORD_ID} not found" in message

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_db_session")
async def test_handle_move_action_target_location_not_found(
    mock_get_db_session: MagicMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player: Player,
    mock_start_location: Location,
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player_crud.get_by_discord_id.return_value = mock_player
    mock_location_crud.get.return_value = mock_start_location
    mock_location_crud.get_by_static_id.return_value = None # Target location not found

    success, message = await handle_move_action(
        DEFAULT_GUILD_ID, DEFAULT_PLAYER_DISCORD_ID, NON_EXISTENT_LOCATION_STATIC_ID
    )
    assert success is False
    assert f"Location with ID '{NON_EXISTENT_LOCATION_STATIC_ID}' not found" in message

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_db_session")
async def test_handle_move_action_already_at_target_location(
    mock_get_db_session: MagicMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player: Player, # player's current_location_id is START_LOCATION_ID
    mock_start_location: Location, # start_location's static_id is START_LOCATION_STATIC_ID
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player_crud.get_by_discord_id.return_value = mock_player
    mock_location_crud.get.return_value = mock_start_location # Current location
    mock_location_crud.get_by_static_id.return_value = mock_start_location # Target is same as current

    success, message = await handle_move_action(
        DEFAULT_GUILD_ID, DEFAULT_PLAYER_DISCORD_ID, START_LOCATION_STATIC_ID # Target is current
    )
    assert success is False
    assert f"You are already at '{mock_start_location.name_i18n['en']}'" in message

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_db_session")
async def test_handle_move_action_not_connected(
    mock_get_db_session: MagicMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player: Player,
    mock_start_location: Location,
    mock_unconnected_location: Location,
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player_crud.get_by_discord_id.return_value = mock_player
    mock_location_crud.get.return_value = mock_start_location
    mock_location_crud.get_by_static_id.return_value = mock_unconnected_location # Target is unconnected

    # Ensure start_location does not list unconnected_location as a neighbor
    mock_start_location.neighbor_locations_json = [
        {"location_id": TARGET_LOCATION_ID} # Only connected to target_location
    ]

    success, message = await handle_move_action(
        DEFAULT_GUILD_ID, DEFAULT_PLAYER_DISCORD_ID, UNCONNECTED_LOCATION_STATIC_ID
    )
    assert success is False
    assert f"You cannot move directly from '{mock_start_location.name_i18n['en']}' to '{mock_unconnected_location.name_i18n['en']}'" in message


@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_db_session")
async def test_handle_move_action_malformed_neighbors_json(
    mock_get_db_session: MagicMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player: Player,
    mock_start_location: Location,
    mock_target_location: Location,
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player_crud.get_by_discord_id.return_value = mock_player
    mock_location_crud.get.return_value = mock_start_location
    mock_location_crud.get_by_static_id.return_value = mock_target_location

    # Intentionally setting an invalid type to test runtime handling.
    mock_start_location.neighbor_locations_json = "not a list or dict"  # type: ignore[assignment]

    success, message = await handle_move_action(
        DEFAULT_GUILD_ID, DEFAULT_PLAYER_DISCORD_ID, TARGET_LOCATION_STATIC_ID
    )
    assert success is False
    assert "You cannot move directly" in message # Should fail connectivity check

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.party_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.log_event", new_callable=AsyncMock)
@patch("src.core.movement_logic.on_enter_location", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_db_session")
async def test_handle_move_action_player_no_current_location_id(
    mock_get_db_session: MagicMock,
    mock_on_enter_location: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player: Player,
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player.current_location_id = None # Player has no current location
    mock_player_crud.get_by_discord_id.return_value = mock_player

    success, message = await handle_move_action(
        DEFAULT_GUILD_ID, DEFAULT_PLAYER_DISCORD_ID, TARGET_LOCATION_STATIC_ID
    )
    assert success is False
    assert "has no current location set" in message

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.party_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.log_event", new_callable=AsyncMock)
@patch("src.core.movement_logic.on_enter_location", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_db_session")
async def test_handle_move_action_current_location_not_found_in_db(
    mock_get_db_session: MagicMock,
    mock_on_enter_location: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player: Player, # Has current_location_id = START_LOCATION_ID
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player_crud.get_by_discord_id.return_value = mock_player
    mock_location_crud.get.return_value = None # Current location not found in DB

    success, message = await handle_move_action(
        DEFAULT_GUILD_ID, DEFAULT_PLAYER_DISCORD_ID, TARGET_LOCATION_STATIC_ID
    )
    assert success is False
    assert f"Current location ID {mock_player.current_location_id} for player {mock_player.id} not found" in message

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.party_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.log_event", new_callable=AsyncMock)
@patch("src.core.movement_logic.on_enter_location", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_db_session")
async def test_handle_move_action_current_location_wrong_guild(
    mock_get_db_session: MagicMock,
    mock_on_enter_location: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player: Player,
    mock_start_location: Location,
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player_crud.get_by_discord_id.return_value = mock_player
    mock_start_location.guild_id = DEFAULT_GUILD_ID + 100 # Different guild
    mock_location_crud.get.return_value = mock_start_location

    success, message = await handle_move_action(
        DEFAULT_GUILD_ID, DEFAULT_PLAYER_DISCORD_ID, TARGET_LOCATION_STATIC_ID
    )
    assert success is False
    assert f"Data integrity issue: Player's current location {mock_start_location.id} does not belong to guild {DEFAULT_GUILD_ID}" in message

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.party_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.log_event", new_callable=AsyncMock)
@patch("src.core.movement_logic.on_enter_location", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_db_session") # For handle_move_action
@patch("src.core.database.get_db_session")      # For @transactional on _update_entities_location
async def test_handle_move_action_party_not_found_proceeds_solo(
    mock_db_get_db_session: MagicMock,
    mock_logic_get_db_session: MagicMock,
    mock_on_enter_location: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player: Player,
    mock_start_location: Location,
    mock_target_location: Location,
):
    mock_logic_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_db_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player.current_party_id = DEFAULT_PARTY_DB_ID + 50 # Some party ID
    mock_player_crud.get_by_discord_id.return_value = mock_player
    mock_location_crud.get.return_value = mock_start_location
    mock_location_crud.get_by_static_id.return_value = mock_target_location
    mock_party_crud.get.return_value = None # Party not found

    success, message = await handle_move_action(
        DEFAULT_GUILD_ID, DEFAULT_PLAYER_DISCORD_ID, TARGET_LOCATION_STATIC_ID
    )

    assert success is True # Should succeed as solo move
    assert f"You have moved to '{mock_target_location.name_i18n['en']}'" in message # Solo message
    assert mock_player.current_location_id == mock_target_location.id

    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args
    assert log_kwargs["event_type"] == "player_move" # Solo move logged

    mock_on_enter_location.assert_called_once_with(
        guild_id=DEFAULT_GUILD_ID,
        entity_id=mock_player.id,
        entity_type="player", # Solo
        location_id=mock_target_location.id,
    )
    mock_session.add.assert_called_once_with(mock_player) # Only player

# --- Tests for execute_move_for_player_action ---

@pytest.fixture
def mock_player_pk() -> Player: # Player identified by PK for new function
    player = Player(
        id=DEFAULT_PLAYER_DB_ID, # PK
        guild_id=DEFAULT_GUILD_ID,
        discord_id=DEFAULT_PLAYER_DISCORD_ID, # Still present but not primary lookup
        name="TestPlayerPK",
        current_location_id=START_LOCATION_ID,
        current_status=PlayerStatus.EXPLORING,
        selected_language="en"
    )
    return player

@pytest.fixture
def mock_party_for_pk_player(mock_player_pk: Player) -> Party:
    party = Party(
        id=DEFAULT_PARTY_DB_ID,
        guild_id=DEFAULT_GUILD_ID,
        name="TestPartyForPK",
        player_ids_json=[mock_player_pk.id],
        current_location_id=START_LOCATION_ID,
        turn_status=PartyTurnStatus.IDLE
    )
    mock_player_pk.current_party_id = party.id
    return party


@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.party_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.log_event", new_callable=AsyncMock)
@patch("src.core.movement_logic.on_enter_location", new_callable=AsyncMock)
# No need to patch get_db_session for execute_move_for_player_action as session is passed in
# However, _update_entities_location uses @transactional which uses database.get_db_session
@patch("src.core.database.get_db_session")
async def test_execute_move_successful_solo_player(
    mock_db_get_db_session: MagicMock, # For @transactional on _update_entities_location
    mock_on_enter_location: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock, # Passed directly to execute_move_for_player_action
    mock_player_pk: Player,
    mock_start_location: Location,
    mock_target_location: Location,
):
    mock_db_get_db_session.return_value.__aenter__.return_value = mock_session # for _update_entities_location's @transactional

    mock_player_crud.get.return_value = mock_player_pk # Get by PK
    # This mock_location_crud is for the one imported at module level in movement_logic.py
    # It will be used by _find_location_by_identifier if called.
    mock_location_crud.get.return_value = mock_start_location # For current_location
    mock_location_crud.get_by_static_id.return_value = mock_target_location # For _find_location_by_identifier's static_id search

    # Setup mock_session.execute for the call from get_rule (via load_rules_config_for_guild)
    mock_execution_result_rules = MagicMock() # Result of session.execute() for rules
    # We need to handle multiple calls to session.execute if _find_location_by_identifier also calls it.
    # For this test, _find_location_by_identifier primarily uses get_by_static_id.
    # So, one execute call from get_rule is expected.
    mock_session.execute.return_value = mock_execution_result_rules

    mock_scalar_result_rules = MagicMock() # Result of execution_result.scalars()
    mock_execution_result_rules.scalars.return_value = mock_scalar_result_rules

    mock_scalar_result_rules.all = MagicMock(return_value=[]) # Corrected: No rules found, get_rule returns default

    from src.core.movement_logic import execute_move_for_player_action # Import here
    result = await execute_move_for_player_action(
        mock_session, DEFAULT_GUILD_ID, DEFAULT_PLAYER_DB_ID, TARGET_LOCATION_STATIC_ID
    )

    assert result["status"] == "success"
    assert f"You have moved to '{mock_target_location.name_i18n['en']}'" in result["message"]
    assert mock_player_pk.current_location_id == mock_target_location.id

    mock_player_crud.get.assert_called_once_with(mock_session, id=DEFAULT_PLAYER_DB_ID)
    mock_location_crud.get.assert_called_once_with(mock_session, id=START_LOCATION_ID)
    mock_location_crud.get_by_static_id.assert_called_once_with(
        mock_session, guild_id=DEFAULT_GUILD_ID, static_id=TARGET_LOCATION_STATIC_ID
    )

    # _update_entities_location is called, which then calls log_event
    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args
    assert log_kwargs["session"] == mock_session # Session propagated by _update_entities_location
    assert log_kwargs["event_type"] == "player_move"
    assert log_kwargs["details_json"]["player_id"] == mock_player_pk.id
    assert log_kwargs["details_json"]["to_location_id"] == mock_target_location.id

    mock_on_enter_location.assert_called_once_with(
        guild_id=DEFAULT_GUILD_ID,
        entity_id=mock_player_pk.id,
        entity_type="player",
        location_id=mock_target_location.id,
    )
    mock_session.add.assert_called_with(mock_player_pk)


@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.party_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.log_event", new_callable=AsyncMock)
@patch("src.core.movement_logic.on_enter_location", new_callable=AsyncMock)
@patch("src.core.database.get_db_session")
async def test_execute_move_successful_party_move(
    mock_db_get_db_session: MagicMock,
    mock_on_enter_location: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player_pk: Player,
    mock_party_for_pk_player: Party, # Use the party linked to mock_player_pk
    mock_start_location: Location,
    mock_target_location: Location,
):
    mock_db_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player_crud.get.return_value = mock_player_pk
    mock_location_crud.get.return_value = mock_start_location # For current_location
    mock_location_crud.get_by_static_id.return_value = mock_target_location # For _find_location_by_identifier
    mock_party_crud.get.return_value = mock_party_for_pk_player

    # Setup mock_session.execute for the call from get_rule (via load_rules_config_for_guild)
    mock_execution_result_rules = MagicMock()
    mock_session.execute.return_value = mock_execution_result_rules
    mock_scalar_result_rules = MagicMock()
    mock_execution_result_rules.scalars.return_value = mock_scalar_result_rules
    mock_scalar_result_rules.all = MagicMock(return_value=[]) # Corrected: No rules found

    from src.core.movement_logic import execute_move_for_player_action
    result = await execute_move_for_player_action(
        mock_session, DEFAULT_GUILD_ID, DEFAULT_PLAYER_DB_ID, TARGET_LOCATION_STATIC_ID
    )

    assert result["status"] == "success"
    assert f"You and your party have moved to '{mock_target_location.name_i18n['en']}'" in result["message"]
    assert mock_player_pk.current_location_id == mock_target_location.id
    assert mock_party_for_pk_player.current_location_id == mock_target_location.id

    mock_party_crud.get.assert_called_once_with(mock_session, id=mock_player_pk.current_party_id)
    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args
    assert log_kwargs["event_type"] == "party_move"

    mock_on_enter_location.assert_called_once_with(
        guild_id=DEFAULT_GUILD_ID,
        entity_id=mock_party_for_pk_player.id,
        entity_type="party",
        location_id=mock_target_location.id,
    )
    assert mock_session.add.call_count == 2
    mock_session.add.assert_any_call(mock_player_pk)
    mock_session.add.assert_any_call(mock_party_for_pk_player)


@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
async def test_execute_move_player_not_found(
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
):
    mock_player_crud.get.return_value = None # Player not found by PK

    from src.core.movement_logic import execute_move_for_player_action
    result = await execute_move_for_player_action(
        mock_session, DEFAULT_GUILD_ID, DEFAULT_PLAYER_DB_ID, TARGET_LOCATION_STATIC_ID
    )
    assert result["status"] == "error"
    assert f"Player with ID {DEFAULT_PLAYER_DB_ID} not found" in result["message"]


@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
async def test_execute_move_player_wrong_guild(
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player_pk: Player,
):
    mock_player_pk.guild_id = DEFAULT_GUILD_ID + 1 # Player in wrong guild
    mock_player_crud.get.return_value = mock_player_pk

    from src.core.movement_logic import execute_move_for_player_action
    result = await execute_move_for_player_action(
        mock_session, DEFAULT_GUILD_ID, DEFAULT_PLAYER_DB_ID, TARGET_LOCATION_STATIC_ID
    )
    assert result["status"] == "error"
    assert f"Player {DEFAULT_PLAYER_DB_ID} does not belong to guild {DEFAULT_GUILD_ID}" in result["message"]


@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
async def test_execute_move_target_location_not_found_by_static_id(
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player_pk: Player,
    mock_start_location: Location,
):
    mock_player_crud.get.return_value = mock_player_pk
    mock_location_crud.get.return_value = mock_start_location
    # _find_location_by_identifier will first call get_by_static_id
    mock_location_crud.get_by_static_id.return_value = None
    # Then it will try to search by name, which involves session.execute
    mock_execute_result_name_search = AsyncMock()
    mock_scalars_name_search = MagicMock()
    mock_scalars_name_search.all = MagicMock(return_value=[]) # Name search also finds nothing
    mock_execute_result_name_search.scalars = MagicMock(return_value=mock_scalars_name_search)

    # Setup mock_session.execute for calls from load_rules_config_for_guild AND _find_location_by_identifier (name search)

    # Mock setup for rule fetching (first call to session.execute)
    mock_exec_rules_result = MagicMock()
    mock_rules_scalars_obj = MagicMock()
    mock_rules_scalars_obj.all = MagicMock(return_value=[]) # Corrected
    mock_exec_rules_result.scalars.return_value = mock_rules_scalars_obj

    # Mock setup for name searching (next 3 calls to session.execute)
    mock_exec_name_search_result = MagicMock()
    mock_name_search_scalars_obj = MagicMock()
    mock_name_search_scalars_obj.all = MagicMock(return_value=[]) # Corrected
    mock_exec_name_search_result.scalars.return_value = mock_name_search_scalars_obj

    mock_session.execute.side_effect = [
        mock_exec_rules_result, # For get_rule
        mock_exec_name_search_result, # For name search lang 1
        mock_exec_name_search_result, # For name search lang 2
        mock_exec_name_search_result  # For name search lang 3 (en fallback)
    ]

    from src.core.movement_logic import execute_move_for_player_action
    result = await execute_move_for_player_action(
        mock_session, DEFAULT_GUILD_ID, DEFAULT_PLAYER_DB_ID, NON_EXISTENT_LOCATION_STATIC_ID
    )
    assert result["status"] == "error"
    assert f"Location '{NON_EXISTENT_LOCATION_STATIC_ID}' could not be found" in result["message"]
    # TODO: Add test for name search once implemented


@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
async def test_execute_move_not_connected(
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player_pk: Player,
    mock_start_location: Location,
    mock_unconnected_location: Location,
):
    mock_player_crud.get.return_value = mock_player_pk
    mock_location_crud.get.return_value = mock_start_location # For current_location
    # _find_location_by_identifier will find mock_unconnected_location by static_id
    mock_location_crud.get_by_static_id.return_value = mock_unconnected_location

    # Setup mock_session.execute for the call from get_rule (via load_rules_config_for_guild)
    mock_execution_result_rules = MagicMock()
    mock_session.execute.return_value = mock_execution_result_rules
    mock_scalar_result_rules = MagicMock()
    mock_execution_result_rules.scalars.return_value = mock_scalar_result_rules
    mock_scalar_result_rules.all = MagicMock(return_value=[]) # Corrected: No rules found

    # Ensure start_location does not list unconnected_location as a neighbor
    mock_start_location.neighbor_locations_json = [
        {"location_id": TARGET_LOCATION_ID, "connection_type_i18n": {"en": "path"}}
    ]

    from src.core.movement_logic import execute_move_for_player_action
    result = await execute_move_for_player_action(
        mock_session, DEFAULT_GUILD_ID, DEFAULT_PLAYER_DB_ID, UNCONNECTED_LOCATION_STATIC_ID
    )
    assert result["status"] == "error"
    assert f"You cannot move directly from '{mock_start_location.name_i18n['en']}' to '{mock_unconnected_location.name_i18n['en']}'" in result["message"]

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.party_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.on_enter_location", new_callable=AsyncMock) # To check it's NOT called on failure
async def test_execute_move_failure_does_not_call_on_enter_location(
    mock_on_enter_location: AsyncMock,
    mock_party_crud: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player_pk: Player,
    mock_start_location: Location,
):
    mock_player_crud.get.return_value = mock_player_pk
    mock_location_crud.get.return_value = mock_start_location
    mock_location_crud.get_by_static_id.return_value = None # Target not found leading to failure

    from src.core.movement_logic import execute_move_for_player_action
    result = await execute_move_for_player_action(
        mock_session, DEFAULT_GUILD_ID, DEFAULT_PLAYER_DB_ID, NON_EXISTENT_LOCATION_STATIC_ID
    )
    assert result["status"] == "error"
    mock_on_enter_location.assert_not_called()

# --- Tests for _find_location_by_identifier ---

from src.core.movement_logic import _find_location_by_identifier
from src.models.rule_config import RuleConfig # For mock_rule

@pytest.mark.asyncio
@patch("src.core.movement_logic.location_crud.get_by_static_id", new_callable=AsyncMock)
@patch("sqlalchemy.ext.asyncio.AsyncSession.execute", new_callable=AsyncMock) # To mock session.execute for name search
async def test_find_location_by_static_id_success(
    mock_session_execute: AsyncMock,
    mock_get_by_static_id: AsyncMock,
    mock_session: AsyncMock, # Standard mock session
    mock_target_location: Location
):
    identifier = TARGET_LOCATION_STATIC_ID
    mock_get_by_static_id.return_value = mock_target_location

    found_location = await _find_location_by_identifier(
        mock_session, DEFAULT_GUILD_ID, identifier, "en", "en"
    )

    assert found_location == mock_target_location
    mock_get_by_static_id.assert_called_once_with(
        mock_session, guild_id=DEFAULT_GUILD_ID, static_id=identifier
    )
    mock_session_execute.assert_not_called() # Should not search by name if static_id matches

@pytest.mark.asyncio
@patch("src.core.movement_logic.location_crud.get_by_static_id", new_callable=AsyncMock)
# Patch the execute method on the mock_session instance that will be passed to the function
async def test_find_location_by_name_player_language_actual_logic(
    mock_get_by_static_id: AsyncMock,
    mock_session: AsyncMock, # This mock_session's .execute will be configured
    mock_target_location: Location # Target location to be "found"
):
    identifier = "лес" # Russian name
    player_lang = "ru"
    guild_lang = "en"

    mock_target_location.name_i18n = {"ru": "лес", "en": "Forest"} # Ensure target has the name

    # 1. Static ID search fails
    mock_get_by_static_id.return_value = None

    # 2. Name search succeeds (mocking the session.execute().scalars().all() chain)
    mock_execution_result = MagicMock() # Result of session.execute()
    mock_session.execute.return_value = mock_execution_result

    mock_scalar_result = MagicMock() # Result of execution_result.scalars()
    mock_execution_result.scalars.return_value = mock_scalar_result

    # Result of scalar_result.all()
    mock_scalar_result.all = MagicMock(return_value=[mock_target_location]) # Corrected

    found_location = await _find_location_by_identifier(
        mock_session, DEFAULT_GUILD_ID, identifier, player_lang, guild_lang
    )

    assert found_location == mock_target_location
    mock_get_by_static_id.assert_called_once_with(
        mock_session, guild_id=DEFAULT_GUILD_ID, static_id=identifier
    )
    # Check that session.execute was called (for the name search in 'ru')
    mock_session.execute.assert_called_once()
    # We could add more detailed assertions about the SQL statement passed to execute if needed.


@pytest.mark.asyncio
@patch("src.core.movement_logic.location_crud.get_by_static_id", new_callable=AsyncMock)
async def test_find_location_by_name_guild_language_fallback_actual_logic(
    mock_get_by_static_id: AsyncMock,
    mock_session: AsyncMock,
    mock_target_location: Location
):
    identifier = "Forest" # English name
    player_lang = "de"    # Player prefers German
    guild_lang = "en"     # Guild main language is English

    mock_target_location.name_i18n = {"en": "Forest", "de": "Wald"}

    mock_get_by_static_id.return_value = None # Static ID search fails

    # Mock session.execute for name search
    # First call (for 'de') will find nothing
    mock_exec_result_de = MagicMock()
    mock_scalars_de = MagicMock()
    mock_scalars_de.all = MagicMock(return_value=[]) # Corrected
    mock_exec_result_de.scalars.return_value = mock_scalars_de

    # Second call (for 'en' - guild language) will find the location
    mock_exec_result_en = MagicMock()
    mock_scalars_en = MagicMock()
    mock_scalars_en.all = MagicMock(return_value=[mock_target_location]) # Corrected
    mock_exec_result_en.scalars.return_value = mock_scalars_en

    mock_session.execute.side_effect = [mock_exec_result_de, mock_exec_result_en]

    found_location = await _find_location_by_identifier(
        mock_session, DEFAULT_GUILD_ID, identifier, player_lang, guild_lang
    )

    assert found_location == mock_target_location
    assert mock_session.execute.call_count == 2 # Called for 'de', then 'en'

@pytest.mark.asyncio
@patch("src.core.movement_logic.location_crud.get_by_static_id", new_callable=AsyncMock)
async def test_find_location_by_name_english_fallback_actual_logic(
    mock_get_by_static_id: AsyncMock,
    mock_session: AsyncMock,
    mock_target_location: Location
):
    identifier = "Forest"
    player_lang = "de"
    guild_lang = "fr" # Neither player nor guild lang is 'en'

    mock_target_location.name_i18n = {"en": "Forest"}

    mock_get_by_static_id.return_value = None

    # Mock session.execute for name search
    # de
    mock_exec_result_de = MagicMock()
    mock_scalars_de = MagicMock()
    mock_scalars_de.all = MagicMock(return_value=[]) # Corrected
    mock_exec_result_de.scalars.return_value = mock_scalars_de
    # fr
    mock_exec_result_fr = MagicMock()
    mock_scalars_fr = MagicMock()
    mock_scalars_fr.all = MagicMock(return_value=[]) # Corrected
    mock_exec_result_fr.scalars.return_value = mock_scalars_fr
    # en
    mock_exec_result_en = MagicMock()
    mock_scalars_en = MagicMock()
    mock_scalars_en.all = MagicMock(return_value=[mock_target_location]) # Corrected
    mock_exec_result_en.scalars.return_value = mock_scalars_en

    mock_session.execute.side_effect = [mock_exec_result_de, mock_exec_result_fr, mock_exec_result_en]

    found_location = await _find_location_by_identifier(
        mock_session, DEFAULT_GUILD_ID, identifier, player_lang, guild_lang
    )
    assert found_location == mock_target_location
    assert mock_session.execute.call_count == 3 # de, fr, en

@pytest.mark.asyncio
@patch("src.core.movement_logic.location_crud.get_by_static_id", new_callable=AsyncMock)
async def test_find_location_by_name_case_insensitive_actual_logic(
    mock_get_by_static_id: AsyncMock,
    mock_session: AsyncMock,
    mock_target_location: Location
):
    identifier = "fOrEsT" # Mixed case
    player_lang = "en"
    guild_lang = "en"
    mock_target_location.name_i18n = {"en": "Forest"} # DB stores "Forest"

    mock_get_by_static_id.return_value = None

    mock_execution_result = MagicMock()
    mock_session.execute.return_value = mock_execution_result
    mock_scalar_result = MagicMock()
    mock_execution_result.scalars.return_value = mock_scalar_result
    mock_scalar_result.all = MagicMock(return_value=[mock_target_location]) # Corrected: Simulates DB finding it case-insensitively

    found_location = await _find_location_by_identifier(
        mock_session, DEFAULT_GUILD_ID, identifier, player_lang, guild_lang
    )
    assert found_location == mock_target_location
    mock_session.execute.assert_called_once() # Should be called for 'en'


@pytest.mark.asyncio
@patch("src.core.movement_logic.location_crud.get_by_static_id", new_callable=AsyncMock)
async def test_find_location_not_found_actual_logic(
    mock_get_by_static_id: AsyncMock,
    mock_session: AsyncMock
):
    identifier = "non_existent_place"
    player_lang = "de"
    guild_lang = "fr"

    mock_get_by_static_id.return_value = None # Static ID search fails

    # Name search also fails for all priority languages
    # de
    mock_exec_result_de = MagicMock()
    mock_scalars_de = MagicMock(); mock_scalars_de.all = MagicMock(return_value=[]) # Corrected
    mock_exec_result_de.scalars.return_value = mock_scalars_de
    # fr
    mock_exec_result_fr = MagicMock()
    mock_scalars_fr = MagicMock(); mock_scalars_fr.all = MagicMock(return_value=[]) # Corrected
    mock_exec_result_fr.scalars.return_value = mock_scalars_fr
    # en
    mock_exec_result_en = MagicMock()
    mock_scalars_en = MagicMock(); mock_scalars_en.all = MagicMock(return_value=[]) # Corrected
    mock_exec_result_en.scalars.return_value = mock_scalars_en

    mock_session.execute.side_effect = [mock_exec_result_de, mock_exec_result_fr, mock_exec_result_en]

    found_location = await _find_location_by_identifier(
        mock_session, DEFAULT_GUILD_ID, identifier, player_lang, guild_lang
    )
    assert found_location is None
    assert mock_session.execute.call_count == 3


@pytest.mark.asyncio
@patch("src.core.movement_logic.location_crud.get_by_static_id", new_callable=AsyncMock)
@patch("src.core.movement_logic.logger.warning")
async def test_find_location_by_name_ambiguous_returns_first_and_logs_actual_logic(
    mock_logger_warning: MagicMock,
    mock_get_by_static_id: AsyncMock,
    mock_session: AsyncMock,
    mock_start_location: Location, # Will be the first returned
    mock_target_location: Location  # Another location with the same name for ambiguity
):
    identifier = "Ambiguous Tavern"
    player_lang = "en"
    guild_lang = "en"

    mock_start_location.name_i18n = {"en": "Ambiguous Tavern"}
    mock_target_location.name_i18n = {"en": "Ambiguous Tavern"} # Same name

    mock_get_by_static_id.return_value = None # Static ID search fails

    # Name search returns multiple locations
    mock_execution_result = MagicMock()
    mock_session.execute.return_value = mock_execution_result
    mock_scalar_result = MagicMock()
    mock_execution_result.scalars.return_value = mock_scalar_result
    # IMPORTANT: Order matters if the function just takes the first one.
    mock_scalar_result.all = MagicMock(return_value=[mock_start_location, mock_target_location]) # Corrected

    found_location = await _find_location_by_identifier(
        mock_session, DEFAULT_GUILD_ID, identifier, player_lang, guild_lang
    )

    assert found_location == mock_start_location # Should return the first one
    mock_logger_warning.assert_called_once()
    args, kwargs = mock_logger_warning.call_args
    assert f"Ambiguous location name '{identifier}' (lang: {player_lang})" in args[0]
    assert f"Found 2 locations" in args[0]


# --- Update tests for execute_move_for_player_action to use _find_location_by_identifier ---

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
# Patch the helper directly within its module
@patch("src.core.movement_logic._find_location_by_identifier", new_callable=AsyncMock)
@patch("src.core.movement_logic.party_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.log_event", new_callable=AsyncMock)
@patch("src.core.movement_logic.on_enter_location", new_callable=AsyncMock)
@patch("src.core.database.get_db_session") # For @transactional on _update_entities_location
@patch("src.core.movement_logic.get_rule", new_callable=AsyncMock) # For guild_main_language
async def test_execute_move_uses_find_location_helper_success(
    mock_get_rule: AsyncMock,
    mock_db_get_db_session: MagicMock,
    mock_on_enter_location: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud: AsyncMock,
    mock_find_loc_helper: AsyncMock, # Patched _find_location_by_identifier
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player_pk: Player,
    mock_start_location: Location,
    mock_target_location: Location,
):
    mock_db_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player_crud.get.return_value = mock_player_pk
    mock_location_crud = AsyncMock() # Need a generic mock for current_location loading
    mock_location_crud.get.return_value = mock_start_location # Used for current_location

    # Simulate _find_location_by_identifier finding the target
    mock_find_loc_helper.return_value = mock_target_location

    # Mock get_rule for guild_main_language to return the language string directly
    mock_get_rule.return_value = "en" # Assume guild lang is 'en'

    # We need to patch location_crud.get inside execute_move_for_player_action for current_location
    with patch("src.core.movement_logic.location_crud", mock_location_crud):
        from src.core.movement_logic import execute_move_for_player_action
        result = await execute_move_for_player_action(
            mock_session, DEFAULT_GUILD_ID, DEFAULT_PLAYER_DB_ID, TARGET_LOCATION_STATIC_ID
        )

    assert result["status"] == "success"
    mock_find_loc_helper.assert_called_once_with(
        mock_session, DEFAULT_GUILD_ID, TARGET_LOCATION_STATIC_ID,
        player_language=mock_player_pk.selected_language,
        guild_main_language="en"
    )
    mock_get_rule.assert_called_once_with(mock_session, DEFAULT_GUILD_ID, "guild_main_language", default="en")
    # Other assertions (log_event, on_enter_location, player state) remain similar to test_execute_move_successful_solo_player
    assert mock_player_pk.current_location_id == mock_target_location.id
    mock_log_event.assert_called_once()
    mock_on_enter_location.assert_called_once()

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic._find_location_by_identifier", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_rule", new_callable=AsyncMock)
async def test_execute_move_when_find_location_helper_returns_none(
    mock_get_rule: AsyncMock,
    mock_find_loc_helper: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player_pk: Player,
    mock_start_location: Location,
):
    mock_player_crud.get.return_value = mock_player_pk
    mock_location_crud_instance = AsyncMock() # For current location
    mock_location_crud_instance.get.return_value = mock_start_location

    mock_find_loc_helper.return_value = None # Target location not found by helper

    mock_rule_obj = MagicMock(spec=RuleConfig); mock_rule_obj.value_json = "en"
    mock_get_rule.return_value = mock_rule_obj

    with patch("src.core.movement_logic.location_crud", mock_location_crud_instance):
        from src.core.movement_logic import execute_move_for_player_action
        result = await execute_move_for_player_action(
            mock_session, DEFAULT_GUILD_ID, DEFAULT_PLAYER_DB_ID, "some_unknown_place"
        )

    assert result["status"] == "error"
    assert "Location 'some_unknown_place' could not be found" in result["message"]
    mock_find_loc_helper.assert_called_once()

@pytest.mark.asyncio
@patch("src.core.movement_logic.player_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.location_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.party_crud", new_callable=AsyncMock)
@patch("src.core.movement_logic.log_event", new_callable=AsyncMock)
@patch("src.core.movement_logic.on_enter_location", new_callable=AsyncMock)
@patch("src.core.movement_logic.get_db_session") # For handle_move_action
@patch("src.core.database.get_db_session")      # For @transactional on _update_entities_location
async def test_handle_move_action_party_in_wrong_guild_proceeds_solo(
    mock_db_get_db_session: MagicMock,
    mock_logic_get_db_session: MagicMock,
    mock_on_enter_location: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncMock,
    mock_player: Player,
    mock_party: Party,
    mock_start_location: Location,
    mock_target_location: Location,
):
    mock_logic_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_db_get_db_session.return_value.__aenter__.return_value = mock_session
    mock_player.current_party_id = mock_party.id
    mock_player_crud.get_by_discord_id.return_value = mock_player
    mock_location_crud.get.return_value = mock_start_location
    mock_location_crud.get_by_static_id.return_value = mock_target_location

    mock_party.guild_id = DEFAULT_GUILD_ID + 100 # Party in wrong guild
    mock_party_crud.get.return_value = mock_party

    success, message = await handle_move_action(
        DEFAULT_GUILD_ID, DEFAULT_PLAYER_DISCORD_ID, TARGET_LOCATION_STATIC_ID
    )

    assert success is True # Should succeed as solo move
    assert f"You have moved to '{mock_target_location.name_i18n['en']}'" in message # Solo message
    assert mock_player.current_location_id == mock_target_location.id

    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args
    assert log_kwargs["event_type"] == "player_move" # Solo move logged

    mock_on_enter_location.assert_called_once_with(
        guild_id=DEFAULT_GUILD_ID,
        entity_id=mock_player.id,
        entity_type="player", # Solo
        location_id=mock_target_location.id,
    )
    mock_session.add.assert_called_once_with(mock_player) # Only player
