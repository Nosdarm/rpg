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
