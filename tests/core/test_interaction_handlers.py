import sys
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call # Ensured 'call' is imported

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.check_results import CheckOutcome # Removed CheckOutcomeStatus

from backend.core.interaction_handlers import handle_intra_location_action
from backend.models import Player, Location, LocationType # Added LocationType
from backend.models.enums import PlayerStatus, EventType # Added EventType
print(f"DEBUG GLOBAL: dir(EventType) at import time in test_interaction_handlers: {dir(EventType)}") # DEBUG PRINT
from backend.models.check_results import CheckOutcome # Import CheckOutcome

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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_existing_object(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_non_existent_object(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_unexaminable_object(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
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
@patch("backend.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.resolve_check", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_with_check_success(
    mock_log_event: AsyncMock, # type: ignore
    mock_location_crud: AsyncMock, # type: ignore
    mock_player_crud: AsyncMock, # type: ignore
    mock_resolve_check: AsyncMock, # type: ignore
    mock_get_rule: AsyncMock, # type: ignore
    mock_session: AsyncSession,
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
    # mock_get_rule.return_value = mock_rule # Will be replaced by side_effect

    # Consequence rule content for this test (can be empty if not testing consequence details here)
    consequence_rule_for_chest_opens = [{"type": "placeholder_effect"}]

    def get_rule_side_effect_check_success(session, guild_id, key):
        # import logging # Can't use logger directly in test side_effect easily without setup
        # print(f"DEBUG: get_rule_side_effect_check_success called with key: {key}") # For local debugging
        if key == "interactions:chest_generic":
            return mock_rule
        if key == "consequences:chest_opens_reveals_loot":
            return consequence_rule_for_chest_opens
        return None # Default fallback
    mock_get_rule.side_effect = get_rule_side_effect_check_success

    mock_successful_check_result = MagicMock()
    mock_successful_check_result.outcome = CheckOutcome(status="success", description="Test Success") # Reverted
    mock_successful_check_result.model_dump.return_value = {"outcome": {"status":"success", "description":"Test Success"}, "roll_value": 18, "dc": 15}
    mock_resolve_check.return_value = mock_successful_check_result
    action_data = {"intent": "interact", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is True
    # The message might now include feedback from placeholder consequence if _apply_consequences adds it.
    # For now, let's ensure the primary feedback is there.
    assert "You attempt to interact with Old Chest... Success! (success)" in result["message"]

    # Verify get_rule was called for both interaction and consequence rules
    assert mock_get_rule.call_count == 2
    # First call from handle_intra_location_action (seems to be recorded with kwargs by mock)
    mock_get_rule.assert_any_call(session=mock_session, guild_id=DEFAULT_GUILD_ID, key="interactions:chest_generic")
    # Second call from _apply_consequences (recorded with positional guild_id, key)
    mock_get_rule.assert_any_call(mock_session, DEFAULT_GUILD_ID, "consequences:chest_opens_reveals_loot")

    mock_resolve_check.assert_called_once()
    resolve_kwargs = mock_resolve_check.call_args.kwargs
    assert resolve_kwargs["guild_id"] == DEFAULT_GUILD_ID
    assert resolve_kwargs["check_type"] == "lockpicking"
    assert resolve_kwargs["difficulty_dc"] == 15
    assert resolve_kwargs["actor_entity_id"] == DEFAULT_PLAYER_ID
    assert "actor_attributes" in resolve_kwargs["check_context"]
    assert resolve_kwargs["check_context"]["actor_attributes"]["dexterity"]["value"] == 10

    # Check for player_interact log AND consequence_effect_error log
    player_interact_log_found = False
    consequence_error_log_found = False
    for call_item in mock_log_event.call_args_list:
        args, kwargs = call_item
        event_type = kwargs.get("event_type") # Main log in handle_intra_location_action uses kwargs for event_type
        if not event_type and args: # _apply_consequences logs event_type positionally
            event_type = args[0]

        if event_type == "player_interact": # This is from handle_intra_location_action's direct log
            player_interact_log_found = True
            assert kwargs["details_json"]["target"] == "Old Chest"
            assert kwargs["details_json"]["rule_found"] is True
            assert kwargs["details_json"]["check_required"] is True
            assert kwargs["details_json"]["check_result"]["outcome"]["status"] == "success"
            assert kwargs["details_json"]["applied_consequences_key"] == "chest_opens_reveals_loot"
        elif event_type == EventType.CONSEQUENCE_EFFECT_ERROR: # This is from _apply_consequences for placeholder
                # print(f"DEBUG SUCCESS CHECK: Found CONSEQUENCE_EFFECT_ERROR log. Args: {args}, Kwargs: {kwargs}")
            consequence_error_log_found = True
            assert "Unknown consequence effect_type: 'placeholder_effect'" in kwargs['details_json']['error']
            assert kwargs['details_json']['rule_key'] == "consequences:chest_opens_reveals_loot" # Ensure it's for the correct rule

    assert player_interact_log_found, "player_interact event not logged"
    assert consequence_error_log_found, f"CONSEQUENCE_EFFECT_ERROR for placeholder_effect not logged. All logs: {mock_log_event.call_args_list}"

@pytest.mark.asyncio
@patch("backend.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.resolve_check", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_with_check_failure(
    mock_log_event: AsyncMock, # type: ignore
    mock_location_crud: AsyncMock, # type: ignore
    mock_player_crud: AsyncMock, # type: ignore
    mock_resolve_check: AsyncMock, # type: ignore
    mock_get_rule: AsyncMock, # type: ignore
    mock_session: AsyncSession,
    mock_player: Player, mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    mock_rule = {
        "requires_check": True, "check_type": "strength", "actor_attribute_key": "strength",
        "base_dc": 18, "success_consequences_key": "lever_pulled",
        "failure_consequences_key": "lever_stuck"
    }
    # mock_get_rule.return_value = mock_rule # Will be replaced by side_effect

    consequence_rule_for_lever_stuck = [{"type": "placeholder_failure_effect"}]

    def get_rule_side_effect_check_failure(session, guild_id, key):
        if key == "interactions:chest_generic": # Assuming chest_generic for this test too for simplicity of target
            return mock_rule
        if key == "consequences:lever_stuck":
            return consequence_rule_for_lever_stuck
        return None
    mock_get_rule.side_effect = get_rule_side_effect_check_failure

    mock_failed_check_result = MagicMock()
    mock_failed_check_result.outcome = CheckOutcome(status="failure", description="Test Failure") # Reverted
    mock_failed_check_result.model_dump.return_value = {"outcome": {"status":"failure", "description":"Test Failure"}, "roll_value": 5, "dc": 18}
    mock_resolve_check.return_value = mock_failed_check_result
    action_data = {"intent": "interact", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is False
    assert "You attempt to interact with Old Chest... Failure. (failure)" in result["message"]

    assert mock_get_rule.call_count == 2
    mock_get_rule.assert_any_call(session=mock_session, guild_id=DEFAULT_GUILD_ID, key="interactions:chest_generic")
    mock_get_rule.assert_any_call(mock_session, DEFAULT_GUILD_ID, "consequences:lever_stuck")

    mock_resolve_check.assert_called_once()

    player_interact_log_found = False
    consequence_error_log_found = False
    for call_item in mock_log_event.call_args_list:
        args, kwargs = call_item
        event_type = kwargs.get("event_type")
        if not event_type and args:
            event_type = args[0]

        if event_type == "player_interact":
            player_interact_log_found = True
            details_json_val = kwargs.get("details_json")
            assert details_json_val is not None; assert isinstance(details_json_val, dict)
            check_result_val = details_json_val.get("check_result")
            assert check_result_val is not None; assert isinstance(check_result_val, dict)
            outcome_dict = check_result_val.get("outcome")
            assert outcome_dict is not None; assert isinstance(outcome_dict, dict)
            assert outcome_dict.get("status") == "failure"
            assert details_json_val.get("applied_consequences_key") == "lever_stuck"
        elif event_type == EventType.CONSEQUENCE_EFFECT_ERROR:
                # print(f"DEBUG FAILURE CHECK: Found CONSEQUENCE_EFFECT_ERROR log. Args: {args}, Kwargs: {kwargs}")
            consequence_error_log_found = True
            assert "Unknown consequence effect_type: 'placeholder_failure_effect'" in kwargs['details_json']['error']
            assert kwargs['details_json']['rule_key'] == "consequences:lever_stuck"

    assert player_interact_log_found, "player_interact event not logged for failure case"
    assert consequence_error_log_found, f"CONSEQUENCE_EFFECT_ERROR for placeholder_failure_effect not logged. All logs: {mock_log_event.call_args_list}"

@pytest.mark.asyncio
@patch("backend.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.resolve_check", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_no_check_required(
    mock_log_event: AsyncMock, # type: ignore
    mock_location_crud: AsyncMock, # type: ignore
    mock_player_crud: AsyncMock, # type: ignore
    mock_resolve_check: AsyncMock, # type: ignore
    mock_get_rule: AsyncMock, # type: ignore
    mock_session: AsyncSession,
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
    # mock_get_rule.return_value = mock_rule_no_check # Will be replaced by side_effect

    consequence_rule_for_lever_passage = [{"type": "placeholder_passage_effect"}]

    def get_rule_side_effect_no_check(session, guild_id, key):
        if key == "interactions:lever_simple":
            return mock_rule_no_check
        if key == "consequences:lever_activates_passage":
            return consequence_rule_for_lever_passage
        return None
    mock_get_rule.side_effect = get_rule_side_effect_no_check

    action_data = {"intent": "interact", "entities": [{"name": "Hidden Lever"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)
    assert result["success"] is True
    assert "You interact with Hidden Lever. It seems to have worked." in result["message"]

    assert mock_get_rule.call_count == 2
    mock_get_rule.assert_any_call(session=mock_session, guild_id=DEFAULT_GUILD_ID, key="interactions:lever_simple")
    mock_get_rule.assert_any_call(mock_session, DEFAULT_GUILD_ID, "consequences:lever_activates_passage")

    mock_resolve_check.assert_not_called()

    player_interact_log_found = False
    consequence_error_log_found = False
    for call_item in mock_log_event.call_args_list:
        args, kwargs = call_item
        event_type = kwargs.get("event_type")
        if not event_type and args:
            event_type = args[0]

        if event_type == "player_interact":
            player_interact_log_found = True
            details_json_val = kwargs.get("details_json"); assert details_json_val is not None; assert isinstance(details_json_val, dict)
            assert details_json_val.get("target") == "Hidden Lever"
            assert details_json_val.get("rule_found") is True
            assert details_json_val.get("check_required") is False
            assert "check_result" not in details_json_val
            assert details_json_val.get("applied_consequences_key") == "lever_activates_passage"
        elif event_type == EventType.CONSEQUENCE_EFFECT_ERROR:
                # print(f"DEBUG NO_CHECK CHECK: Found CONSEQUENCE_EFFECT_ERROR log. Args: {args}, Kwargs: {kwargs}")
            consequence_error_log_found = True
            assert "Unknown consequence effect_type: 'placeholder_passage_effect'" in kwargs['details_json']['error']
            assert kwargs['details_json']['rule_key'] == "consequences:lever_activates_passage"

    assert player_interact_log_found, "player_interact event not logged for no_check case"
    assert consequence_error_log_found, f"CONSEQUENCE_EFFECT_ERROR for placeholder_passage_effect not logged. All logs: {mock_log_event.call_args_list}"

@pytest.mark.asyncio
@patch("backend.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_rule_not_found(
    mock_log_event: AsyncMock, # type: ignore
    mock_location_crud: AsyncMock, # type: ignore
    mock_player_crud: AsyncMock, # type: ignore
    mock_get_rule: AsyncMock, # type: ignore
    mock_session: AsyncSession, mock_player: Player, mock_location_with_details: Location
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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_no_interaction_key(
    mock_log_event: AsyncMock, # type: ignore
    mock_location_crud: AsyncMock, # type: ignore
    mock_player_crud: AsyncMock, # type: ignore
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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_non_existent_object(
    mock_log_event: AsyncMock, # type: ignore
    mock_location_crud: AsyncMock, # type: ignore
    mock_player_crud: AsyncMock, # type: ignore
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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_move_to_valid_sublocation(
    mock_log_event: AsyncMock, # type: ignore
    mock_location_crud: AsyncMock, # type: ignore
    mock_player_crud: AsyncMock, # type: ignore
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
    commit_mock: AsyncMock = mock_session.commit # type: ignore
    commit_mock.assert_called_once()
    log_event_mock: AsyncMock = mock_log_event; log_event_mock.assert_called_once()
    log_args, log_kwargs = log_event_mock.call_args_list[0]
    assert log_kwargs["event_type"] == "player_move_sublocation"
    assert log_kwargs["details_json"]["target_sublocation"] == expected_sublocation_name

@pytest.mark.asyncio
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
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
    commit_mock: AsyncMock = mock_session.commit # type: ignore
    commit_mock.assert_not_called()
    log_event_mock: AsyncMock = mock_log_event; log_event_mock.assert_not_called()

@pytest.mark.asyncio
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
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
    commit_mock: AsyncMock = mock_session.commit # type: ignore
    commit_mock.assert_not_called()
    log_event_mock: AsyncMock = mock_log_event; log_event_mock.assert_not_called()

@pytest.mark.asyncio
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
async def test_handle_action_player_not_found(
    mock_location_crud: AsyncMock, mock_player_crud: AsyncMock, mock_session: AsyncSession,
):
    mock_player_crud.get.return_value = None
    action_data = {"intent": "examine", "entities": [{"name": "anything"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data) # type: ignore[misc]
    assert result["success"] is False
    assert "Error: Player not found." in result["message"]

@pytest.mark.asyncio
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
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

from backend.core.interaction_handlers import _find_target_in_location

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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_object_player_lang_present(
    mock_log_event: AsyncMock, # type: ignore
    mock_location_crud: AsyncMock, # type: ignore
    mock_player_crud: AsyncMock, # type: ignore
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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_object_player_lang_missing_fallback_en(
    mock_log_event: AsyncMock, # type: ignore
    mock_location_crud: AsyncMock, # type: ignore
    mock_player_crud: AsyncMock, # type: ignore
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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_examine_object_player_lang_and_en_missing_fallback_default(
    mock_log_event: AsyncMock, # type: ignore
    mock_location_crud: AsyncMock, # type: ignore
    mock_player_crud: AsyncMock, # type: ignore
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
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
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

# Removed erroneous line:
# from backend.core import localization_utils as localization_utils_module
# localization_utils_logger = localization_utils_module.logger
# [end of tests/core/test_interaction_handlers.py] # This line was causing syntax error


# --- Tests for _apply_consequences ---

# Use the globally imported EventType as the pristine version for patching into SUT
from backend.models.enums import EventType as PristineEventType

@pytest.mark.asyncio
@patch("backend.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
# Patches for consequence effect handlers if they were external, but they are internal for now or mocked directly
@patch("backend.core.entity_stats_utils.change_entity_stat", new_callable=MagicMock) # Corrected patch path
@patch("backend.core.interaction_handlers.EventType", new=PristineEventType) # Added EventType patch
async def test_apply_consequences_update_location_state(
    mock_sut_event_type_patch: MagicMock, # For EventType patch
    mock_change_stat: MagicMock,
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_get_rule: AsyncMock, # For interaction rule AND consequence rule
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location # Location with interactables
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details

    # Target object for interaction
    target_object_name = "Old Chest"
    target_object_original_state = "locked"

    # Ensure the target object exists and set its initial state
    found_chest = False
    if mock_location_with_details.generated_details_json and "interactable_elements" in mock_location_with_details.generated_details_json:
        for item in mock_location_with_details.generated_details_json["interactable_elements"]:
            if item.get("name") == target_object_name:
                item["state"] = target_object_original_state # Set initial state
                item["interaction_rules_key"] = "unlockable_chest" # Key for interaction rule
                found_chest = True
                break
    assert found_chest, "Test setup error: Old Chest not found in mock_location_with_details"

    # 1. Mock the interaction rule (e.g., for a successful check)
    interaction_rule_content = {
        "requires_check": False, # Or True with a mocked successful check leading to these consequences
        "direct_consequences_key": "chest_unlocked_consequences"
        # If requires_check=True: "success_consequences_key": "chest_unlocked_consequences"
    }

    # 2. Mock the consequence rule
    consequence_key = "chest_unlocked_consequences"
    consequence_rule_content = [
        {
            "type": "update_location_state",
            "target_object_name": target_object_name,
            "property_name": "state",
            "new_value": "unlocked",
            "feedback_message_key": "chest_now_unlocked_feedback" # Optional feedback
        }
    ]

    # get_rule will be called twice: once for interaction, once for consequence
    def get_rule_side_effect(session, guild_id, key):
        if key == "interactions:unlockable_chest":
            return interaction_rule_content
        if key == f"consequences:{consequence_key}":
            return consequence_rule_content
        return None
    mock_get_rule.side_effect = get_rule_side_effect

    # Mock _format_feedback for the consequence message
    with patch("backend.core.interaction_handlers._format_feedback") as mock_format_feedback:
        mock_format_feedback.side_effect = lambda mk, lang, **kw: f"Feedback for {mk}: {kw.get('target_name', '')}"

        action_data = {"intent": "interact", "entities": [{"name": target_object_name}]}
        result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)

    assert result["success"] is True
    # Check if main feedback includes consequence feedback
    assert "Feedback for chest_now_unlocked_feedback: Old Chest" in result["message"]

    # Verify location state was updated
    updated_chest_data = None
    if mock_location_with_details.generated_details_json and "interactable_elements" in mock_location_with_details.generated_details_json:
        for item in mock_location_with_details.generated_details_json["interactable_elements"]:
            if item.get("name") == target_object_name:
                updated_chest_data = item
                break

    assert updated_chest_data is not None, "Updated chest data not found"
    assert updated_chest_data.get("state") == "unlocked"

    # Verify log_event for CONSEQUENCE_EFFECT_APPLIED
    consequence_log_found = False

    expected_consequence_details = {
        "player_id": mock_player.id,
        "location_id": mock_location_with_details.id,
        "rule_key": f"consequences:{consequence_key}",
        "effect_index": 0,
        "effect_rule_content": consequence_rule_content[0],
        "outcome_details": {
            "updated_object": target_object_name,
            "property": "state",
            "new_value": "unlocked"
        }
    }

    for call_item in mock_log_event.call_args_list:
        args, kwargs = call_item
        current_call_event_type = args[0] if args else None

        if current_call_event_type == PristineEventType.CONSEQUENCE_EFFECT_APPLIED:
            details_json = kwargs.get("details_json", {})
            if details_json.get("effect_rule_content", {}).get("type") == "update_location_state":
                consequence_log_found = True
                assert args[1] == mock_session, "Session not passed correctly to log_event"
                assert kwargs.get("guild_id") == DEFAULT_GUILD_ID, "Guild ID not passed correctly"
                assert "player_id" not in [k for k in kwargs if k not in ['details_json', 'guild_id', 'event_type', 'session']]
                assert details_json == expected_consequence_details, \
                    f"CONSEQUENCE_EFFECT_APPLIED details mismatch. Got: {details_json}, Expected: {expected_consequence_details}"
                break
    assert consequence_log_found, f"CONSEQUENCE_EFFECT_APPLIED event for update_location_state not logged correctly. Log calls: {mock_log_event.call_args_list}"

    mock_session.add.assert_any_call(mock_location_with_details) # Check if location was marked for update
    # session.flush should be called by _apply_consequences
    mock_session.flush.assert_called() # Check if flush was called on the session object


@pytest.mark.asyncio
@patch("backend.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
@patch("backend.core.entity_stats_utils.change_entity_stat") # Corrected patch path
@patch("backend.core.interaction_handlers.EventType", new=PristineEventType) # Added EventType patch
async def test_apply_consequences_change_player_stat(
    mock_sut_event_type_patch: MagicMock, # For EventType patch
    mock_change_entity_stat: MagicMock,
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_get_rule: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details
    target_object_name = "Old Chest" # Interaction target

    interaction_rule_content = {"direct_consequences_key": "buff_strength_consequence"}
    consequence_key = "buff_strength_consequence"
    consequence_rule_content = [{
        "type": "change_player_stat", "stat_name": "strength", "change_amount": 2,
        "feedback_message_key": "player_feels_stronger"
    }]

    def get_rule_side_effect(session, guild_id, key):
        if key == f"interactions:{mock_location_with_details.generated_details_json['interactable_elements'][0].get('interaction_rules_key')}": # Assuming chest is first
            return interaction_rule_content
        if key == f"consequences:{consequence_key}":
            return consequence_rule_content
        return None
    mock_get_rule.side_effect = get_rule_side_effect

    with patch("backend.core.interaction_handlers._format_feedback") as mock_format_feedback:
        mock_format_feedback.return_value = "You feel stronger." # For player_feels_stronger
        action_data = {"intent": "interact", "entities": [{"name": target_object_name}]}
        result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)

    assert result["success"] is True
    assert "You feel stronger." in result["message"]
    mock_change_entity_stat.assert_called_once_with(mock_player, "strength", 2)

    consequence_log_found = False
    expected_consequence_details = {
        "player_id": mock_player.id,
        "location_id": mock_location_with_details.id,
        "rule_key": f"consequences:{consequence_key}",
        "effect_index": 0,
        "effect_rule_content": consequence_rule_content[0],
        "outcome_details": {
            "stat": "strength",
            "change": 2
        }
    }

    for call_item in mock_log_event.call_args_list:
        args, kwargs = call_item
        current_call_event_type = args[0] if args else None

        if current_call_event_type == PristineEventType.CONSEQUENCE_EFFECT_APPLIED:
            details_json = kwargs.get("details_json", {})
            if details_json.get("effect_rule_content", {}).get("type") == "change_player_stat":
                consequence_log_found = True
                assert args[1] == mock_session, "Session not passed correctly to log_event"
                assert kwargs.get("guild_id") == DEFAULT_GUILD_ID, "Guild ID not passed correctly"
                assert "player_id" not in [k for k in kwargs if k not in ['details_json', 'guild_id', 'event_type', 'session']]
                assert details_json == expected_consequence_details, \
                    f"CONSEQUENCE_EFFECT_APPLIED details mismatch. Got: {details_json}, Expected: {expected_consequence_details}"
                break
    assert consequence_log_found, f"CONSEQUENCE_EFFECT_APPLIED for change_player_stat not logged correctly. Log calls: {mock_log_event.call_args_list}"
    mock_session.flush.assert_called()


@pytest.mark.asyncio
@patch("backend.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("backend.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_apply_consequences_teleport_player(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock, # Patched instance
    mock_player_crud: AsyncMock,  # Patched instance
    mock_get_rule: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location # Starting location
):
    # mock_event_type_patch is the MagicMock from @patch("backend.core.interaction_handlers.EventType", new=PristineEventType)
    # It ensures that 'EventType' inside interaction_handlers module refers to PristineEventType for this test.

    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details # For current location

    target_object_name = "Mystic Portal"
    # Add portal to current location's details
    if mock_location_with_details.generated_details_json and "interactable_elements" in mock_location_with_details.generated_details_json:
        mock_location_with_details.generated_details_json["interactable_elements"].append({
            "name": target_object_name, "interaction_rules_key": "portal_activation"
        })
    else: # Should not happen with fixture
        mock_location_with_details.generated_details_json = {"interactable_elements": [{"name": target_object_name, "interaction_rules_key": "portal_activation"}]}


    target_location_static_id = "secret_chamber"
    target_location_name_en = "Secret Chamber"
    mock_target_location = Location(id=DEFAULT_LOCATION_ID + 1, static_id=target_location_static_id, name_i18n={"en": target_location_name_en}, guild_id=DEFAULT_GUILD_ID, type=LocationType.GENERIC)

    interaction_rule_content = {"direct_consequences_key": "portal_teleports_player"}
    consequence_key = "portal_teleports_player"
    consequence_rule_content = [{
        "type": "teleport_player",
        "target_location_static_id": target_location_static_id,
        "feedback_message_key": "player_teleported" # This key is not used by teleport, it makes its own
    }]

    def get_rule_side_effect_teleport(session, guild_id, key):
        if key == "interactions:portal_activation": return interaction_rule_content
        if key == f"consequences:{consequence_key}": return consequence_rule_content
        return None
    mock_get_rule.side_effect = get_rule_side_effect_teleport

    mock_location_crud.get_by_static_id = AsyncMock(return_value=mock_target_location)


    action_data = {"intent": "interact", "entities": [{"name": target_object_name}]}
    # SUT (_apply_consequences) will now use the PristineEventType due to the patch
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)

    assert result["success"] is True
    assert f"You suddenly find yourself in {target_location_name_en}" in result["message"]

    assert mock_player.current_location_id == mock_target_location.id
    mock_session.add.assert_any_call(mock_player)
    mock_session.flush.assert_called()


    movement_log_found = False
    consequence_applied_log_found = False

    expected_player_moved_details = {
        "old_location_id": mock_location_with_details.id,
        "new_location_id": mock_target_location.id,
        "method": "teleport"
    }

    # Corrected expected_consequence_applied_details
    # consequence_rule_content is defined earlier in this test
    effect_rule_for_teleport = consequence_rule_content[0]

    expected_consequence_applied_details = {
        "player_id": mock_player.id,
        "location_id": mock_location_with_details.id, # Location *before* teleport
        "rule_key": f"consequences:{consequence_key}",
        "effect_index": 0, # Assuming this is the first and only effect
        "effect_rule_content": effect_rule_for_teleport,
        "outcome_details": {
            "teleported_to_static_id": target_location_static_id,
            "teleported_to_location_id": mock_target_location.id
        }
    }

    # Debug prints to verify PristineEventType state
    print(f"DEBUG TELEPORT: Using PristineEventType for assertions. ID: {id(PristineEventType)}")
    if hasattr(PristineEventType, 'PLAYER_MOVED'):
        print(f"DEBUG TELEPORT: PristineEventType.PLAYER_MOVED exists. Value: '{PristineEventType.PLAYER_MOVED.value}'")
    else:
        print(f"DEBUG TELEPORT: PristineEventType.PLAYER_MOVED DOES NOT EXIST. Dir: {dir(PristineEventType)}")
    if hasattr(PristineEventType, 'CONSEQUENCE_EFFECT_APPLIED'):
        print(f"DEBUG TELEPORT: PristineEventType.CONSEQUENCE_EFFECT_APPLIED exists. Value: '{PristineEventType.CONSEQUENCE_EFFECT_APPLIED.value}'")
    else:
        print(f"DEBUG TELEPORT: PristineEventType.CONSEQUENCE_EFFECT_APPLIED DOES NOT EXIST. Dir: {dir(PristineEventType)}")


    for i, call_item in enumerate(mock_log_event.call_args_list):
        args, kwargs = call_item
        current_call_event_type = None
        if 'event_type' in kwargs:
            current_call_event_type = kwargs['event_type']
        elif args:
            current_call_event_type = args[0]

        print(f"DEBUG TELEPORT: Log call {i} - Extracted event type: '{current_call_event_type}', Type: {type(current_call_event_type)}")
        # The SUT should have called log_event with members from PristineEventType
        # So current_call_event_type should be an actual member of PristineEventType

        if hasattr(PristineEventType, 'PLAYER_MOVED') and current_call_event_type == PristineEventType.PLAYER_MOVED:
            print(f"DEBUG TELEPORT: Matched PristineEventType.PLAYER_MOVED for call {i}")
            movement_log_found = True
            # Check positional args: log_event(EventType.PLAYER_MOVED, session, ...)
            assert args[1] == mock_session
            # Check keyword args
            assert kwargs.get("guild_id") == DEFAULT_GUILD_ID
            assert kwargs.get("player_id") == mock_player.id # player_id is a direct kwarg for PLAYER_MOVED
            assert kwargs.get("details_json") == expected_player_moved_details, \
                f"PLAYER_MOVED details mismatch. Got: {kwargs.get('details_json')}, Expected: {expected_player_moved_details}"

        elif hasattr(PristineEventType, 'CONSEQUENCE_EFFECT_APPLIED') and current_call_event_type == PristineEventType.CONSEQUENCE_EFFECT_APPLIED:
            print(f"DEBUG TELEPORT: Matched PristineEventType.CONSEQUENCE_EFFECT_APPLIED for call {i}")
            details_json = kwargs.get("details_json")
            # Corrected condition to identify the teleport consequence log
            if details_json and details_json.get("effect_rule_content", {}).get("type") == "teleport_player":
                consequence_applied_log_found = True
                # Check positional args: log_event(EventType.CONSEQUENCE_EFFECT_APPLIED, session, ...)
                assert args[1] == mock_session
                # Check keyword args
                assert kwargs.get("guild_id") == DEFAULT_GUILD_ID
                # player_id is in details_json, not a direct kwarg for this event type
                assert "player_id" not in [k for k, v in kwargs.items() if k not in ['details_json', 'guild_id', 'event_type', 'session']]
                assert details_json == expected_consequence_applied_details, \
                    f"CONSEQUENCE_EFFECT_APPLIED for teleport_player details mismatch. Got: {details_json}, Expected: {expected_consequence_applied_details}"

    assert movement_log_found, f"PLAYER_MOVED event for teleport not logged. Log calls: {mock_log_event.call_args_list}"
    assert consequence_applied_log_found, f"CONSEQUENCE_EFFECT_APPLIED for teleport_player not logged. Log calls: {mock_log_event.call_args_list}"
