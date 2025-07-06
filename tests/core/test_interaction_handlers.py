import sys
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession
from src.models.check_results import CheckOutcome # Removed CheckOutcomeStatus

from src.core.interaction_handlers import handle_intra_location_action
from src.models import Player, Location, LocationType # Added LocationType
from src.models.enums import PlayerStatus
from src.models.check_results import CheckOutcome # Import CheckOutcome

DEFAULT_GUILD_ID = 1
DEFAULT_PLAYER_ID = 1
DEFAULT_LOCATION_ID = 1
DEFAULT_LOCATION_STATIC_ID = "test_room"

@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session

@pytest.fixture
def mock_location() -> Location:
    return Location(
        id=DEFAULT_LOCATION_ID,
        guild_id=DEFAULT_GUILD_ID,
        static_id=DEFAULT_LOCATION_STATIC_ID,
        name_i18n={"en": "Generic Test Room"},
        type=LocationType.GENERIC,
        generated_details_json={}
    )

@pytest.fixture
def mock_player() -> Player:
    return Player(
        id=DEFAULT_PLAYER_ID,
        guild_id=DEFAULT_GUILD_ID,
        discord_id=12345,
        name="TestPlayer",
        current_location_id=DEFAULT_LOCATION_ID,
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
        generated_details_json=None
    )

@pytest.fixture
def mock_location_with_details(request) -> Location:
    import copy
    default_details = {
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
                "actual_sublocation_name": "The Alcove",
                "can_examine": True,
            },
            {
                "name": "Unexaminable Rock",
                "description_i18n": {"en": "Just a rock."},
                "can_examine": False,
                "can_interact": False,
            }
        ]
    }
    details_to_use = default_details
    if hasattr(request, "param"):
        details_to_use = request.param
    final_details = copy.deepcopy(details_to_use)
    return Location(
        id=DEFAULT_LOCATION_ID,
        guild_id=DEFAULT_GUILD_ID,
        static_id=DEFAULT_LOCATION_STATIC_ID,
        name_i18n={"en": "Detailed Room"},
        type=LocationType.DUNGEON,
        generated_details_json=final_details
    )

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_existing_object(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    action_data = {"intent": "examine", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is True
    details_json = mock_location_with_details.generated_details_json
    assert details_json is not None; interactable_elements = details_json.get("interactable_elements")
    assert isinstance(interactable_elements, list) and len(interactable_elements) > 0
    target_object_data = interactable_elements[0]; assert isinstance(target_object_data, dict)
    description_i18n = target_object_data.get("description_i18n"); assert isinstance(description_i18n, dict)
    expected_desc = description_i18n.get("en"); assert expected_desc is not None
    assert f"You examine Old Chest: {expected_desc}" in result["message"]
    log_event_mock: AsyncMock = mock_log_event; log_event_mock.assert_called_once()
    log_args, log_kwargs = log_event_mock.call_args_list[0]
    assert log_kwargs["event_type"] == "player_examine"
    assert log_kwargs["details_json"]["target"] == "Old Chest"

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_non_existent_object(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    action_data = {"intent": "examine", "entities": [{"name": "NonExistent Thing"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is False
    assert "You don't see any 'NonExistent Thing' here to examine." in result["message"]
    mock_log_event.assert_not_called()

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_unexaminable_object(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    action_data = {"intent": "examine", "entities": [{"name": "Unexaminable Rock"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is False
    assert "You don't see any 'Unexaminable Rock' here to examine." in result["message"]
    mock_log_event.assert_not_called()

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.resolve_check", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_with_check_success(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_resolve_check: AsyncMock, mock_get_rule: AsyncMock, mock_session: AsyncSession,
    mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    mock_rule = {
        "requires_check": True, "check_type": "lockpicking", "actor_attribute_key": "dexterity",
        "base_dc": 15, "feedback_success": "interact_check_success",
        "success_consequences_key": "chest_opens_reveals_loot",
        "feedback_failure": "interact_check_failure",
        "failure_consequences_key": "chest_remains_locked_trap_sprung"
    }
    mock_get_rule.return_value = mock_rule
    mock_successful_check_result = MagicMock()
    mock_successful_check_result.outcome = CheckOutcome(status="success", description="Test Success") # Reverted
    mock_successful_check_result.model_dump.return_value = {"outcome": {"status":"success", "description":"Test Success"}, "roll_value": 18, "dc": 15}
    mock_resolve_check.return_value = mock_successful_check_result
    action_data = {"intent": "interact", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is True
    assert "You attempt to interact with Old Chest... Success! (success)" in result["message"]
    mock_get_rule.assert_called_once_with(session=mock_session, guild_id=DEFAULT_GUILD_ID, key="interactions:chest_generic")
    mock_resolve_check.assert_called_once()
    resolve_kwargs = mock_resolve_check.call_args.kwargs
    assert resolve_kwargs["guild_id"] == DEFAULT_GUILD_ID
    assert resolve_kwargs["check_type"] == "lockpicking"
    assert resolve_kwargs["difficulty_dc"] == 15
    assert resolve_kwargs["actor_entity_id"] == DEFAULT_PLAYER_ID
    assert "actor_attributes" in resolve_kwargs["check_context"]
    assert resolve_kwargs["check_context"]["actor_attributes"]["dexterity"]["value"] == 10
    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args_list[0]
    assert log_kwargs["event_type"] == "player_interact"
    assert log_kwargs["details_json"]["target"] == "Old Chest"
    assert log_kwargs["details_json"]["rule_found"] is True
    assert log_kwargs["details_json"]["check_required"] is True
    assert log_kwargs["details_json"]["check_result"]["outcome"]["status"] == "success"
    assert log_kwargs["details_json"]["applied_consequences_key"] == "chest_opens_reveals_loot"

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.resolve_check", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_with_check_failure(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_resolve_check: AsyncMock, mock_get_rule: AsyncMock, mock_session: AsyncSession,
    mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    mock_rule = {
        "requires_check": True, "check_type": "strength", "actor_attribute_key": "strength",
        "base_dc": 18, "success_consequences_key": "lever_pulled",
        "failure_consequences_key": "lever_stuck"
    }
    mock_get_rule.return_value = mock_rule
    mock_failed_check_result = MagicMock()
    mock_failed_check_result.outcome = CheckOutcome(status="failure", description="Test Failure") # Reverted
    mock_failed_check_result.model_dump.return_value = {"outcome": {"status":"failure", "description":"Test Failure"}, "roll_value": 5, "dc": 18}
    mock_resolve_check.return_value = mock_failed_check_result
    action_data = {"intent": "interact", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is False
    assert "You attempt to interact with Old Chest... Failure. (failure)" in result["message"]
    mock_get_rule.assert_called_once_with(session=mock_session, guild_id=DEFAULT_GUILD_ID, key="interactions:chest_generic")
    mock_resolve_check.assert_called_once()
    mock_log_event.assert_called_once()
    log_kwargs = mock_log_event.call_args.kwargs
    details_json_val = log_kwargs.get("details_json")
    assert details_json_val is not None; assert isinstance(details_json_val, dict)
    check_result_val = details_json_val.get("check_result")
    assert check_result_val is not None; assert isinstance(check_result_val, dict)
    assert check_result_val.get("outcome")["status"] == "failure"
    assert details_json_val.get("applied_consequences_key") == "lever_stuck"

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.resolve_check", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_no_check_required(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_resolve_check: AsyncMock, mock_get_rule: AsyncMock, mock_session: AsyncSession,
    mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    lever_data = None
    assert mock_location_with_details.generated_details_json is not None
    for item in mock_location_with_details.generated_details_json["interactable_elements"]:
        if item["name"] == "Hidden Lever":
            item["interaction_rules_key"] = "lever_simple"; lever_data = item; break
    assert lever_data is not None
    mock_rule_no_check = {
        "requires_check": False, "direct_consequences_key": "lever_activates_passage",
        "feedback_direct": "interact_direct_success"
    }
    mock_get_rule.return_value = mock_rule_no_check
    action_data = {"intent": "interact", "entities": [{"name": "Hidden Lever"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is True
    assert "You interact with Hidden Lever. It seems to have worked." in result["message"]
    mock_get_rule.assert_called_once_with(session=mock_session, guild_id=DEFAULT_GUILD_ID, key="interactions:lever_simple")
    mock_resolve_check.assert_not_called()
    mock_log_event.assert_called_once()
    assert mock_log_event.call_args is not None
    log_kwargs = mock_log_event.call_args.kwargs
    details_json_val = log_kwargs.get("details_json"); assert details_json_val is not None; assert isinstance(details_json_val, dict)
    assert details_json_val.get("target") == "Hidden Lever"
    assert details_json_val.get("rule_found") is True
    assert details_json_val.get("check_required") is False
    assert "check_result" not in details_json_val
    assert details_json_val.get("applied_consequences_key") == "lever_activates_passage"

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_rule_not_found(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_get_rule: AsyncMock, mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    mock_get_rule.return_value = None
    action_data = {"intent": "interact", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is True
    assert "You try to interact with Old Chest, but nothing interesting happens." in result["message"]
    mock_get_rule.assert_called_once_with(session=mock_session, guild_id=DEFAULT_GUILD_ID, key="interactions:chest_generic")

    mock_log_event.assert_called_once()
    call_args_tuple = mock_log_event.call_args
    assert call_args_tuple is not None, "log_event.call_args should not be None if called once"

    log_kwargs = call_args_tuple.kwargs
    assert isinstance(log_kwargs, dict), "log_event.call_args.kwargs should be a dict"

    details_json_val = log_kwargs.get("details_json")
    assert isinstance(details_json_val, dict), f"details_json should be a dict, got {type(details_json_val)}"
    assert details_json_val.get("rule_found") is False

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_no_interaction_key(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    location_for_test_details = {
        "interactable_elements": [
            {"name": "Old Chest", "description_i18n": {"en": "A dusty old chest."}, "interaction_rules_key": "chest_generic"},
            {"name": "Hidden Lever", "description_i18n": {"en": "A small lever hidden in the shadows."}}
        ]
    }
    location_for_test = Location(id=DEFAULT_LOCATION_ID, guild_id=DEFAULT_GUILD_ID, static_id="lever_room", name_i18n={"en": "Lever Room"}, type=LocationType.DUNGEON, generated_details_json=location_for_test_details)
    mock_location_crud.get.return_value = location_for_test
    action_data = {"intent": "interact", "entities": [{"name": "Hidden Lever"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is True
    assert "You try to interact with Hidden Lever, but nothing interesting happens." in result["message"]
    mock_log_event.assert_called_once()
    assert mock_log_event.call_args is not None
    log_kwargs = mock_log_event.call_args.kwargs
    details_json_val = log_kwargs.get("details_json"); assert details_json_val is not None; assert isinstance(details_json_val, dict)
    assert details_json_val.get("interaction_rules_key") is None

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_non_existent_object(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    action_data = {"intent": "interact", "entities": [{"name": "Ghost Button"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is False
    assert "You don't see any 'Ghost Button' here to interact with." in result["message"]
    mock_log_event.assert_not_called()

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_move_to_valid_sublocation(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    action_data = {"intent": "move_to_sublocation", "entities": [{"name": "Secret Alcove"}]}
    original_sublocation = mock_player.current_sublocation_name
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is True
    details_json = mock_location_with_details.generated_details_json
    assert details_json is not None; interactable_elements = details_json.get("interactable_elements")
    assert isinstance(interactable_elements, list) and len(interactable_elements) > 2
    sublocation_data = interactable_elements[2]; assert isinstance(sublocation_data, dict)
    expected_sublocation_name = sublocation_data.get("actual_sublocation_name"); assert expected_sublocation_name is not None
    assert f"You move to {expected_sublocation_name}." in result["message"]
    assert mock_player.current_sublocation_name == expected_sublocation_name
    commit_mock: AsyncMock = mock_session.commit; commit_mock.assert_called_once()
    log_event_mock: AsyncMock = mock_log_event; log_event_mock.assert_called_once()
    log_args, log_kwargs = log_event_mock.call_args_list[0]
    assert log_kwargs["event_type"] == "player_move_sublocation"
    assert log_kwargs["details_json"]["target_sublocation"] == expected_sublocation_name

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_move_to_invalid_sublocation_not_a_sublocation_type(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    action_data = {"intent": "move_to_sublocation", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is False
    assert "'Old Chest' is not a place you can move to" in result["message"]
    commit_mock: AsyncMock = mock_session.commit; commit_mock.assert_not_called()
    log_event_mock: AsyncMock = mock_log_event; log_event_mock.assert_not_called()

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_move_to_non_existent_sublocation(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    action_data = {"intent": "move_to_sublocation", "entities": [{"name": "Imaginary Room"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is False
    assert "There is no sub-location called 'Imaginary Room' here." in result["message"]
    commit_mock: AsyncMock = mock_session.commit; commit_mock.assert_not_called()
    log_event_mock: AsyncMock = mock_log_event; log_event_mock.assert_not_called()

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
async def test_handle_action_player_not_found(
    mock_location_crud: AsyncMock, mock_player_crud: AsyncMock, mock_session: AsyncSession,
):
    mock_player_crud.get.return_value = None
    action_data = {"intent": "examine", "entities": [{"name": "anything"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data) # type: ignore[misc]
    assert result["success"] is False
    assert "Error: Player not found." in result["message"]

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
async def test_handle_action_location_not_found(
    mock_location_crud: AsyncMock, mock_player_crud: AsyncMock, mock_session: AsyncSession, mock_player: Player,
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = None
    action_data = {"intent": "examine", "entities": [{"name": "anything"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data) # type: ignore[misc]
    assert result["success"] is False
    assert "Error: Current location not found." in result["message"]

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
async def test_handle_action_no_target_name(
    mock_location_crud: AsyncMock, mock_player_crud: AsyncMock, mock_session: AsyncSession,
    mock_player: Player, mock_location_no_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_no_details
    action_data = {"intent": "examine", "entities": [{"name": ""}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data) # type: ignore[misc]
    assert result["success"] is False
    assert "What do you want to interact with?" in result["message"]
    action_data_no_entities = {"intent": "examine"}
    result_no_entities = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data_no_entities) # type: ignore[misc]
    assert result_no_entities["success"] is False
    assert "What do you want to interact with?" in result_no_entities["message"]

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
async def test_handle_action_unknown_intent(
    mock_location_crud: AsyncMock, mock_player_crud: AsyncMock, mock_session: AsyncSession,
    mock_player: Player, mock_location_no_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_no_details
    action_data = {"intent": "sing", "entities": [{"name": "a song"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is False
    assert "You are not sure how to 'sing'." in result["message"]

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
@pytest.mark.parametrize("mock_location_with_details", [({"interactable_elements": "not a list"})], indirect=True)
async def test_find_target_malformed_interactable_elements(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    action_data = {"intent": "examine", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is False
    assert "You don't see any 'Old Chest' here to examine." in result["message"]
    mock_log_event.assert_not_called()

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
    assert _find_target_in_location(location_data, "shiny key") == target_item

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
    assert _find_target_in_location(location_data, "Item without name") is None

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_object_player_lang_present(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
):
    mock_player.selected_language = "es"
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    action_data = {"intent": "examine", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is True
    expected_desc_es = "Un viejo cofre polvoriento."
    assert f"You examine Old Chest: {expected_desc_es}" in result["message"]

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_object_player_lang_missing_fallback_en(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
):
    mock_player.selected_language = "de"
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    action_data = {"intent": "examine", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is True
    expected_desc_en = "A dusty old chest. It looks unlocked."
    assert f"You examine Old Chest: {expected_desc_en}" in result["message"]

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_object_player_lang_and_en_missing_fallback_default(
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player,
):
    mock_player.selected_language = "fr"
    mock_player_crud.get.return_value = mock_player
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
    mock_log_event: AsyncMock, mock_location_crud: AsyncMock, mock_player_crud: AsyncMock,
    mock_session: AsyncSession, mock_player: Player,
):
    mock_player.selected_language = "en"
    mock_player_crud.get.return_value = mock_player
    item_no_desc_i18n = {"name": "Plain Stone"}
    location_no_desc = Location(id=3, guild_id=DEFAULT_GUILD_ID, static_id="cave", name_i18n={"en":"Cave"}, type=LocationType.GENERIC, generated_details_json={"interactable_elements": [item_no_desc_i18n]})
    mock_location_crud.get.return_value = location_no_desc
    action_data = {"intent": "examine", "entities": [{"name": "Plain Stone"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is True
    assert "You examine Plain Stone: You see nothing special." in result["message"]

from src.core import localization_utils as localization_utils_module # Added for logger patch
localization_utils_logger = localization_utils_module.logger
# [end of tests/core/test_interaction_handlers.py] # This line was causing syntax error
