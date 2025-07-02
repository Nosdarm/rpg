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
    # Ensure generated_details_json and its structure are valid before subscripting for Pyright
    details_json = mock_location_with_details.generated_details_json
    assert details_json is not None, "generated_details_json should not be None"
    interactable_elements = details_json.get("interactable_elements")
    assert isinstance(interactable_elements, list) and len(interactable_elements) > 0, "interactable_elements should be a list with at least 1 element"
    target_object_data = interactable_elements[0]
    assert isinstance(target_object_data, dict), "target_object_data should be a dict"
    description_i18n = target_object_data.get("description_i18n")
    assert isinstance(description_i18n, dict), "description_i18n should be a dict"
    expected_desc = description_i18n.get("en")
    assert expected_desc is not None, "English description should exist"

    assert f"You examine Old Chest: {expected_desc}" in result["message"]

    log_event_mock: AsyncMock = mock_log_event # type: ignore
    log_event_mock.assert_called_once()
    log_args, log_kwargs = log_event_mock.call_args_list[0]
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
    # Ensure generated_details_json and its structure are valid before subscripting for Pyright
    details_json = mock_location_with_details.generated_details_json
    assert details_json is not None, "generated_details_json should not be None"
    interactable_elements = details_json.get("interactable_elements")
    assert isinstance(interactable_elements, list) and len(interactable_elements) > 2, "interactable_elements should be a list with at least 3 elements"
    sublocation_data = interactable_elements[2]
    assert isinstance(sublocation_data, dict), "sublocation_data should be a dict"
    expected_sublocation_name = sublocation_data.get("actual_sublocation_name")
    assert expected_sublocation_name is not None, "actual_sublocation_name should exist"

    assert f"You move to {expected_sublocation_name}." in result["message"]
    assert mock_player.current_sublocation_name == expected_sublocation_name

    commit_mock: AsyncMock = mock_session.commit # type: ignore
    commit_mock.assert_called_once() # Check that player update was committed

    log_event_mock: AsyncMock = mock_log_event # type: ignore
    log_event_mock.assert_called_once()
    log_args, log_kwargs = log_event_mock.call_args_list[0]
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
    commit_mock: AsyncMock = mock_session.commit # type: ignore
    commit_mock.assert_not_called()
    log_event_mock: AsyncMock = mock_log_event # type: ignore
    log_event_mock.assert_not_called()

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
    commit_mock: AsyncMock = mock_session.commit # type: ignore
    commit_mock.assert_not_called()
    log_event_mock: AsyncMock = mock_log_event # type: ignore
    log_event_mock.assert_not_called()


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

# --- Tests for _find_target_in_location ---
from src.core.interaction_handlers import _find_target_in_location

def test_find_target_empty_location_data():
    assert _find_target_in_location(None, "target") is None
    assert _find_target_in_location({}, "target") is None

def test_find_target_no_interactables_key():
    location_data = {"some_other_key": "some_value"}
    assert _find_target_in_location(location_data, "target") is None

def test_find_target_interactables_not_a_list():
    location_data = {"interactable_elements": "not_a_list_string"}
    assert _find_target_in_location(location_data, "target") is None
    location_data_dict = {"interactable_elements": {"not_a_list": "a_dict"}}
    assert _find_target_in_location(location_data_dict, "target") is None


def test_find_target_empty_interactables_list():
    location_data = {"interactable_elements": []}
    assert _find_target_in_location(location_data, "target") is None

def test_find_target_success():
    target_item = {"name": "Shiny Key", "description": "A small shiny key."}
    other_item = {"name": "Dull Rock", "description": "A boring rock."}
    location_data = {"interactable_elements": [other_item, target_item]}
    assert _find_target_in_location(location_data, "Shiny Key") == target_item
    assert _find_target_in_location(location_data, "shiny key") == target_item # Case-insensitive

def test_find_target_not_found():
    other_item = {"name": "Dull Rock", "description": "A boring rock."}
    location_data = {"interactable_elements": [other_item]}
    assert _find_target_in_location(location_data, "Shiny Key") is None

def test_find_target_item_not_a_dict():
    location_data = {"interactable_elements": ["not_a_dict_item", {"name": "Real Item"}]}
    assert _find_target_in_location(location_data, "Real Item") == {"name": "Real Item"}
    assert _find_target_in_location(location_data, "not_a_dict_item") is None

def test_find_target_item_no_name_key():
    location_data = {"interactable_elements": [{"description": "Item without name"}, {"name": "Named Item"}]}
    assert _find_target_in_location(location_data, "Named Item") == {"name": "Named Item"}
    # Attempting to find by a description or other key should fail if logic relies on "name"
    assert _find_target_in_location(location_data, "Item without name") is None

# --- I18n tests for examine intent ---

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_object_player_lang_present(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location # Has "Old Chest"
):
    mock_player.selected_language = "es" # Player prefers Spanish
    mock_player_crud.get.return_value = mock_player
    # Ensure "Old Chest" has a Spanish description
    # The fixture mock_location_with_details already has "es" for "Old Chest"
    mock_location_crud.get.return_value = mock_location_with_details

    action_data = {"intent": "examine", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)

    assert result["success"] is True
    expected_desc_es = "Un viejo cofre polvoriento." # From fixture
    assert f"You examine Old Chest: {expected_desc_es}" in result["message"] # Assuming _format_feedback uses target_name as is
    # For a fully i18n _format_feedback, the "You examine X:" part would also change.
    # Current _format_feedback is simple.

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_object_player_lang_missing_fallback_en(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location
):
    mock_player.selected_language = "de" # German, not in "Old Chest" data
    mock_player_crud.get.return_value = mock_player
    # "Old Chest" has "en" description
    mock_location_crud.get.return_value = mock_location_with_details

    action_data = {"intent": "examine", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)

    assert result["success"] is True
    expected_desc_en = "A dusty old chest. It looks unlocked." # From fixture
    assert f"You examine Old Chest: {expected_desc_en}" in result["message"]

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_object_player_lang_and_en_missing_fallback_default(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
):
    mock_player.selected_language = "fr"
    mock_player_crud.get.return_value = mock_player

    # Create a location with an item that only has 'jp' description
    item_jp_only = {"name": "Mysterious Scroll", "description_i18n": {"jp": "謎の巻物"}}
    location_jp_item = Location(id=2, guild_id=DEFAULT_GUILD_ID, static_id="shrine", name_i18n={"en":"Shrine"}, type=LocationType.GENERIC, generated_details_json={"interactable_elements": [item_jp_only]})
    mock_location_crud.get.return_value = location_jp_item

    action_data = {"intent": "examine", "entities": [{"name": "Mysterious Scroll"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)

    assert result["success"] is True
    assert "You examine Mysterious Scroll: You see nothing special." in result["message"]

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_object_no_description_i18n(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
):
    mock_player.selected_language = "en"
    mock_player_crud.get.return_value = mock_player

    item_no_desc_i18n = {"name": "Plain Stone"} # No description_i18n field
    location_no_desc = Location(id=3, guild_id=DEFAULT_GUILD_ID, static_id="cave", name_i18n={"en":"Cave"}, type=LocationType.GENERIC, generated_details_json={"interactable_elements": [item_no_desc_i18n]})
    mock_location_crud.get.return_value = location_no_desc

    action_data = {"intent": "examine", "entities": [{"name": "Plain Stone"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)

    assert result["success"] is True
    assert "You examine Plain Stone: You see nothing special." in result["message"]
