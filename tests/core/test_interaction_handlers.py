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
    import copy
    # Allow parameterization of details
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
    }
    # Use deepcopy to ensure tests don't interfere with each other's fixture state
    # Always deepcopy default_details to prevent modification by reference if param is not set.
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
@patch("src.core.interaction_handlers.get_rule", new_callable=AsyncMock) # Mock get_rule
@patch("src.core.interaction_handlers.resolve_check", new_callable=AsyncMock) # Mock resolve_check
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_with_check_success(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_resolve_check: AsyncMock,
    mock_get_rule: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location # Has "Old Chest" with interaction_rules_key
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details # "Old Chest" has "interaction_rules_key": "chest_generic"

    # Mock get_rule to return a rule that requires a check
    mock_rule = {
        "requires_check": True,
        "check_type": "lockpicking",
        "actor_attribute_key": "dexterity", # Assuming player has dexterity
        "base_dc": 15,
            "feedback_success": "interact_check_success", # Use existing key
        "success_consequences_key": "chest_opens_reveals_loot",
            "feedback_failure": "interact_check_failure", # Use existing key
        "failure_consequences_key": "chest_remains_locked_trap_sprung"
    }
    mock_get_rule.return_value = mock_rule

    # Mock resolve_check to return a successful CheckResult
    mock_successful_check_result = MagicMock() # Using MagicMock to set attributes directly
    mock_successful_check_result.outcome = "SUCCESS"
    # Add other CheckResult fields if your code uses them, e.g., roll_value, final_dc
    mock_successful_check_result.model_dump.return_value = {"outcome": "SUCCESS", "roll_value": 18, "dc": 15} # For logging
    mock_resolve_check.return_value = mock_successful_check_result

    action_data = {"intent": "interact", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)

    assert result["success"] is True
    # Check if the custom feedback key from the rule is used
    assert "You attempt to interact with Old Chest... Success! (success)" in result["message"] # Default format for "interact_check_success_custom_chest_open" if not in _format_feedback

    mock_get_rule.assert_called_once_with(db=mock_session, guild_id=DEFAULT_GUILD_ID, key="interactions:chest_generic")
    mock_resolve_check.assert_called_once()
    resolve_args, resolve_kwargs = mock_resolve_check.call_args_list[0]

    assert resolve_kwargs["guild_id"] == DEFAULT_GUILD_ID
    assert resolve_kwargs["check_type"] == "lockpicking"
    assert resolve_kwargs["difficulty_dc"] == 15 # Changed from dc
    assert resolve_kwargs["entity_doing_check_id"] == DEFAULT_PLAYER_ID # Changed from actor_id
    # actor_attributes is now in check_context, check that instead if needed
    # For this specific test, checking the context content:
    assert "actor_attributes" in resolve_kwargs["check_context"]
    assert resolve_kwargs["check_context"]["actor_attributes"]["dexterity"]["value"] == 10

    # Example check for bonus_roll_modifier if it was set and passed
    # assert resolve_kwargs["check_context"].get("bonus_roll_modifier") == expected_bonus_value

    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args_list[0]
    assert log_kwargs["event_type"] == "player_interact"
    assert log_kwargs["details_json"]["target"] == "Old Chest"
    assert log_kwargs["details_json"]["rule_found"] is True
    assert log_kwargs["details_json"]["check_required"] is True
    assert log_kwargs["details_json"]["check_result"]["outcome"] == "SUCCESS"
    assert log_kwargs["details_json"]["applied_consequences_key"] == "chest_opens_reveals_loot"

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.resolve_check", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_with_check_failure(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_resolve_check: AsyncMock,
    mock_get_rule: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location
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
    mock_failed_check_result.outcome = "FAILURE"
    mock_failed_check_result.model_dump.return_value = {"outcome": "FAILURE", "roll_value": 5, "dc": 18}
    mock_resolve_check.return_value = mock_failed_check_result

    action_data = {"intent": "interact", "entities": [{"name": "Old Chest"}]} # Target doesn't matter as much as rule
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)

    assert result["success"] is False # Interaction failed due to check
    assert "You attempt to interact with Old Chest... Failure. (failure)" in result["message"]

    mock_get_rule.assert_called_once_with(db=mock_session, guild_id=DEFAULT_GUILD_ID, key="interactions:chest_generic")
    mock_resolve_check.assert_called_once()

    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args_list[0]
    assert log_kwargs["details_json"]["check_result"]["outcome"] == "FAILURE"
    assert log_kwargs["details_json"]["applied_consequences_key"] == "lever_stuck"


@pytest.mark.asyncio
@patch("src.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.resolve_check", new_callable=AsyncMock) # Still need to mock it even if not called
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_no_check_required(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_resolve_check: AsyncMock,
    mock_get_rule: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location # Has "Hidden Lever" without interaction_rules_key
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details # "Hidden Lever" interaction_rules_key is None in fixture

    # Mock get_rule for "Hidden Lever" (assuming it has a rule, but no check)
    # Let's assume "Hidden Lever" in fixture has "interaction_rules_key": "lever_simple"
    # We need to update the fixture or mock _find_target_in_location to return this.
    # For this test, let's assume "Hidden Lever" object in mock_location_with_details has:
    # "interaction_rules_key": "lever_simple"
    # And we update the fixture to reflect this.

    # Find "Hidden Lever" and update its rule key for this test scenario
    lever_data = None
    for item in mock_location_with_details.generated_details_json["interactable_elements"]:
        if item["name"] == "Hidden Lever":
            item["interaction_rules_key"] = "lever_simple" # Assign a rule key
            lever_data = item
            break
    assert lever_data is not None, "Test setup error: Hidden Lever not found in fixture"


    mock_rule_no_check = {
        "requires_check": False,
        "direct_consequences_key": "lever_activates_passage",
        "feedback_direct": "interact_direct_success" # Use existing key
    }
    mock_get_rule.return_value = mock_rule_no_check

    action_data = {"intent": "interact", "entities": [{"name": "Hidden Lever"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)

    assert result["success"] is True
    assert "You interact with Hidden Lever. It seems to have worked." in result["message"] # Default for "interact_direct_lever_opens"

    mock_get_rule.assert_called_once_with(db=mock_session, guild_id=DEFAULT_GUILD_ID, key="interactions:lever_simple")
    mock_resolve_check.assert_not_called() # IMPORTANT: check resolver should not be called

    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args_list[0]
    assert log_kwargs["details_json"]["target"] == "Hidden Lever"
    assert log_kwargs["details_json"]["rule_found"] is True
    assert log_kwargs["details_json"]["check_required"] is False
    assert "check_result" not in log_kwargs["details_json"] # No check result
    assert log_kwargs["details_json"]["applied_consequences_key"] == "lever_activates_passage"

@pytest.mark.asyncio
@patch("src.core.interaction_handlers.get_rule", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_rule_not_found(
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_get_rule: AsyncMock, # Added mock_get_rule
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player
    mock_location_crud.get.return_value = mock_location_with_details # "Old Chest" has "interaction_rules_key": "chest_generic"

    mock_get_rule.return_value = None # Simulate rule not found in RuleConfig

    action_data = {"intent": "interact", "entities": [{"name": "Old Chest"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)

    assert result["success"] is True # Still true, but nothing happens
    assert "You try to interact with Old Chest, but nothing interesting happens." in result["message"]

    mock_get_rule.assert_called_once_with(db=mock_session, guild_id=DEFAULT_GUILD_ID, key="interactions:chest_generic")
    mock_log_event.assert_called_once() # Log event should still be called
    log_args, log_kwargs = mock_log_event.call_args_list[0]
    assert log_kwargs["details_json"]["rule_found"] is False


@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_object_no_interaction_key( # Renamed from test_interact_existing_object_no_rules
    mock_log_event: AsyncMock,
    mock_location_crud: AsyncMock,
    mock_player_crud: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_location_with_details: Location
):
    mock_player_crud.get.return_value = mock_player

    # Create a specific location setup for this test to avoid fixture state issues
    location_for_test_details = {
        "interactable_elements": [
            {
                "name": "Old Chest", # Keep one other item to ensure list structure
                "description_i18n": {"en": "A dusty old chest."},
                "interaction_rules_key": "chest_generic"
            },
            {
                "name": "Hidden Lever", # This is our target
                "description_i18n": {"en": "A small lever hidden in the shadows."},
                # NO "interaction_rules_key"
            }
        ]
    }
    location_for_test = Location(
        id=DEFAULT_LOCATION_ID,
        guild_id=DEFAULT_GUILD_ID,
        static_id="lever_room",
        name_i18n={"en": "Lever Room"},
        type=LocationType.DUNGEON,
        generated_details_json=location_for_test_details
    )
    mock_location_crud.get.return_value = location_for_test

    action_data = {"intent": "interact", "entities": [{"name": "Hidden Lever"}]}
    result = await handle_intra_location_action(DEFAULT_GUILD_ID, mock_session, DEFAULT_PLAYER_ID, action_data)

    assert result["success"] is True # Should be true, as "nothing interesting happens" is a success
    assert "You try to interact with Hidden Lever, but nothing interesting happens." in result["message"]
    mock_log_event.assert_called_once()
    log_args, log_kwargs = mock_log_event.call_args_list[0]
    assert log_kwargs["details_json"]["interaction_rules_key"] is None


@pytest.mark.asyncio
@patch("src.core.interaction_handlers.player_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.location_crud", new_callable=AsyncMock)
@patch("src.core.interaction_handlers.log_event", new_callable=AsyncMock)
async def test_interact_non_existent_object( # Unchanged
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
    assert _find_target_in_location(None, "target") is None # type: ignore[arg-type]
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
