import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.interaction_handlers import handle_intra_location_action
from src.models import Player, Location, LocationType
from src.models.enums import PlayerStatus

DEFAULT_GUILD_ID = 1
DEFAULT_PLAYER_ID = 1
DEFAULT_LOCATION_ID = 1
DEFAULT_LOCATION_STATIC_ID = "test_room"

@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock() # Needed for move_to_sublocation
    session.add = MagicMock() # Though not directly used by handler, good to have if models change
    return session

@pytest.fixture
def mock_location() -> Location: # Generic location fixture
    return Location(
        id=DEFAULT_LOCATION_ID,
        guild_id=DEFAULT_GUILD_ID,
        static_id=DEFAULT_LOCATION_STATIC_ID,
        name_i18n={"en": "Generic Test Room"},
        type=LocationType.GENERIC,
        generated_details_json={}
    )

@pytest.fixture
def mock_player() -> Player: # No longer depends on mock_location directly
    return Player(
        id=DEFAULT_PLAYER_ID,
        guild_id=DEFAULT_GUILD_ID,
        discord_id=12345, # Some discord ID
        name="TestPlayer",
        current_location_id=DEFAULT_LOCATION_ID, # Uses default ID
        current_status=PlayerStatus.EXPLORING,
        selected_language="en"
    )

@pytest.fixture
def mock_location_no_details() -> Location:
    return Location(
        id=DEFAULT_LOCATION_ID,
        guild_id=DEFAULT_GUILD_ID,
        static_id=DEFAULT_LOCATION_STATIC_ID,
        name_i18n={"en": "Test Room"},
        type=LocationType.GENERIC,
        generated_details_json=None # No details
    )

@pytest.fixture
def mock_location_with_details(request) -> Location:
    # Allow parameterization of details
    details = getattr(request, "param", {
        "interactable_elements": [
            {
                "name": "Old Chest",
                "description_i18n": {"en": "A dusty old chest. It looks unlocked.", "es": "Un viejo cofre polvoriento."},
                "can_examine": True,
                "can_interact": True,
                "interaction_rules_key": "chest_generic"
            },
            {
                "name": "Hidden Lever",
                "description_i18n": {"en": "A small lever hidden in the shadows."},
                "can_examine": True,
                "can_interact": True,
            },
            {
                "name": "Secret Alcove",
                "type": "sublocation",
                "description_i18n": {"en": "A small, dark alcove."},
                "actual_sublocation_name": "The Alcove", # For player.current_sublocation_name
                "can_examine": True,
            },
            {
                "name": "Unexaminable Rock",
                "description_i18n": {"en": "Just a rock."},
                "can_examine": False, # Explicitly not examinable
                "can_interact": False,
            }
        ]
    })
    return Location(
        id=DEFAULT_LOCATION_ID,
        guild_id=DEFAULT_GUILD_ID,
        static_id=DEFAULT_LOCATION_STATIC_ID,
        name_i18n={"en": "Detailed Room"},
        type=LocationType.DUNGEON,
        generated_details_json=details
    )


@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_existing_object(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player, # Uses default player linked to DEFAULT_LOCATION_ID
    mock_location_with_details: Location # Has "Old Chest"
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details

    action_data = {
        "intent": "examine",
        "entities": [{"name": "Old Chest"}]
    }

    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )

    assert result["success"] is True
    expected_desc = mock_location_with_details.generated_details_json["interactable_elements"][0]["description_i18n"]["en"]
    assert f"You examine Old Chest: {expected_desc}" in result["message"]
    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args_list[0]
    assert log_kwargs["event_type"] == "player_examine"
    assert log_kwargs["details_json"]["target"] == "Old Chest"

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_non_existent_object(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details

    action_data = {
        "intent": "examine",
        "entities": [{"name": "NonExistent Thing"}]
    }

    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )

    assert result["success"] is False
    assert "You don't see any 'NonExistent Thing' here to examine." in result["message"]
    mock_log_event.assert_not_called()

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_unexaminable_object(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location # Contains "Unexaminable Rock"
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details

    action_data = {
        "intent": "examine",
        "entities": [{"name": "Unexaminable Rock"}]
    }

    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )

    assert result["success"] is False # Because can_examine is false
    assert "You don't see any 'Unexaminable Rock' here to examine." in result["message"]
    mock_log_event.assert_not_called()


@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_existing_object_with_rules_placeholder(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location # Has "Old Chest" with interaction_rules_key
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details

    action_data = {
        "intent": "interact",
        "entities": [{"name": "Old Chest"}]
    }

    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )

    assert result["success"] is True
    assert "You interact with Old Chest. (Interaction effects TBD)" in result["message"]
    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args_list[0]
    assert log_kwargs["event_type"] == "player_interact"
    assert log_kwargs["details_json"]["target"] == "Old Chest"

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_existing_object_no_rules(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location # Has "Hidden Lever" without interaction_rules_key
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details

    action_data = {
        "intent": "interact",
        "entities": [{"name": "Hidden Lever"}]
    }

    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )

    assert result["success"] is True # Interaction is "successful" but does nothing
    assert "You try to interact with Hidden Lever, but nothing interesting happens." in result["message"]
    mock_log_event.assert_not_called() # Or called with a "nothing_happened" event if desired

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_non_existent_object(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details

    action_data = {
        "intent": "interact",
        "entities": [{"name": "Ghost Button"}]
    }

    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )

    assert result["success"] is False
    assert "You don't see any 'Ghost Button' here to interact with." in result["message"]
    mock_log_event.assert_not_called()

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_move_to_valid_sublocation(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession, # SQLAlchemy session mock
    mock_player: Player,
    mock_location_with_details: Location # Has "Secret Alcove"
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details

    action_data = {
        "intent": "move_to_sublocation",
        "entities": [{"name": "Secret Alcove"}]
    }

    original_sublocation = mock_player.current_sublocation_name

    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )

    assert result["success"] is True
    expected_sublocation_name = mock_location_with_details.generated_details_json["interactable_elements"][2]["actual_sublocation_name"]
    assert f"You move to {expected_sublocation_name}." in result["message"]
    assert mock_player.current_sublocation_name == expected_sublocation_name
    mock_session.commit.assert_called_once() # Check that player update was committed
    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args_list[0]
    assert log_kwargs["event_type"] == "player_move_sublocation"
    assert log_kwargs["details_json"]["target_sublocation"] == expected_sublocation_name

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_move_to_invalid_sublocation_not_a_sublocation_type(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location # Has "Old Chest" (not a sublocation)
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details

    action_data = {
        "intent": "move_to_sublocation",
        "entities": [{"name": "Old Chest"}] # Trying to move to an object
    }

    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )

    assert result["success"] is False
    assert "'Old Chest' is not a place you can move to" in result["message"]
    mock_session.commit.assert_not_called()
    mock_log_event.assert_not_called()

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_move_to_non_existent_sublocation(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details

    action_data = {
        "intent": "move_to_sublocation",
        "entities": [{"name": "Imaginary Room"}]
    }

    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )

    assert result["success"] is False
    assert "There is no sub-location called 'Imaginary Room' here." in result["message"]
    mock_session.commit.assert_not_called()
    mock_log_event.assert_not_called()


@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
async def test_handle_action_player_not_found(
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
):
    mock_player_crud.get.return_value = None # Player not found

    action_data = {"intent": "examine", "entities": [{"name": "anything"}]}
    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )
    assert result["success"] is False
    assert "Error: Player not found." in result["message"]

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
async def test_handle_action_location_not_found(
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player, # Player found
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = None # Location not found

    action_data = {"intent": "examine", "entities": [{"name": "anything"}]}
    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )
    assert result["success"] is False
    assert "Error: Current location not found." in result["message"]

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
async def test_handle_action_no_target_name(
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_no_details: Location # Location has no details
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_no_details

    action_data = {"intent": "examine", "entities": [{"name": ""}]} # Empty name
    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )
    assert result["success"] is False
    assert "What do you want to interact with?" in result["message"]

    action_data_no_entities = {"intent": "examine"} # No entities list
    result_no_entities = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data_no_entities
    )
    assert result_no_entities["success"] is False
    assert "What do you want to interact with?" in result_no_entities["message"]

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
async def test_handle_action_unknown_intent(
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_no_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_no_details

    action_data = {"intent": "sing", "entities": [{"name": "a song"}]}
    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )
    assert result["success"] is False
    assert "You are not sure how to 'sing'." in result["message"]

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
@pytest.mark.parametrize("mock_location_with_details", [({"interactable_elements": "not a list"})], indirect=True)
async def test_find_target_malformed_interactable_elements(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location # This will now have malformed details
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details

    action_data = {
        "intent": "examine",
        "entities": [{"name": "Old Chest"}]
    }

    result = await handle_intra_location_action(
        DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data
    )

    assert result["success"] is False # Target won't be found
    assert "You don't see any 'Old Chest' here to examine." in result["message"]
    mock_log_event.assert_not_called()
