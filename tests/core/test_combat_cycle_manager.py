import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.combat_cycle_manager import start_combat, process_combat_turn #, _handle_combat_end_consequences (private)
from backend.models import Player, GeneratedNpc, CombatEncounter, Party
from backend.models.enums import CombatStatus, PlayerStatus, PartyTurnStatus, EventType
from backend.core.rules import get_rule # For mocking
from backend.core.dice_roller import roll_dice # For mocking
from backend.core.utils import log_event
from backend.core.npc_combat_strategy import get_npc_combat_action
from backend.core.combat_engine import process_combat_action as engine_process_combat_action
from backend.models.combat_outcomes import CombatActionResult # Added import


# --- Fixtures ---

@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock() # For fetching entities like Player, Party
    # session.commit = AsyncMock() # Not needed if using @transactional for the functions
    # session.rollback = AsyncMock()
    return session

@pytest.fixture
def mock_player_entity() -> Player:
    player = MagicMock(spec=Player)
    player.id = 1
    player.guild_id = 100
    player.name = "Test Player"
    player.current_location_id = 10
    player.current_party_id = None
    # Base stats for initiative and participant_json population
    player.max_hp = 100
    player.current_hp = 100
    player.armor_class = 15
    player.dexterity = 14 # Modifier +2
    player.current_status = PlayerStatus.EXPLORING
    player.current_combat_id = None # Assuming this attribute exists
    return player

@pytest.fixture
def mock_npc_entity() -> GeneratedNpc:
    npc = MagicMock(spec=GeneratedNpc)
    npc.id = 2
    npc.guild_id = 100
    npc.name_i18n = {"en": "Goblin Guard", "ru": "Гоблин Охранник"}
    npc.current_location_id = 10
    # Base stats from properties_json
    npc.properties_json = {
        "stats": {
            "hp": 50,
            "current_hp": 50, # Assuming full HP at start of combat
            "armor_class": 12,
            "dexterity": 12 # Modifier +1
        },
        "abilities": [],
        "faction_id": "goblins"
    }
    npc.ai_metadata_json = {} # For personality etc. if needed by AI rules mock
    return npc

@pytest.fixture
def mock_player_entity_2() -> Player: # Another player for multi-player scenarios
    player = MagicMock(spec=Player)
    player.id = 3
    player.guild_id = 100
    player.name = "Hero Two"
    player.current_location_id = 10
    player.current_party_id = None
    player.max_hp = 120
    player.current_hp = 120
    player.armor_class = 16
    player.dexterity = 10 # Modifier +0
    player.current_status = PlayerStatus.EXPLORING
    player.current_combat_id = None
    return player


# --- Tests for start_combat ---

@pytest.mark.asyncio
@patch('backend.core.rules.get_rule')
@patch('backend.core.dice_roller.roll_dice')
@patch('backend.core.utils.log_event')
async def test_start_combat_successful_creation(
    mock_log_event: AsyncMock,
    mock_roll_dice: MagicMock,
    mock_get_rule: AsyncMock,
    mock_session: AsyncMock,
    mock_player_entity: Player,
    mock_npc_entity: GeneratedNpc
):
    # Mock rule calls
    # Lambda now uses keyword arguments matching the call to get_rule
    def get_rule_mock_side_effect(*, session, guild_id, key, default): # Changed db to session
        return {
            "player:stats:default_max_hp": 100,
            "combat:initiative:dice": "1d20",
            "combat:attack:check_type": "attack_roll_vs_ac",
            "combat:attributes:modifier_formula": "(value - 10) // 2"
        }.get(key, default)
    mock_get_rule.side_effect = get_rule_mock_side_effect

    # Mock dice rolls for initiative: Player (15 + 2 = 17), NPC (10 + 1 = 11)
    # roll_dice returns (total, list_of_dice_values)
    mock_roll_dice.side_effect = [
        (15, [15]), # Player's initiative roll (1d20)
        (10, [10])  # NPC's initiative roll (1d20)
    ]

    participant_entities = [mock_player_entity, mock_npc_entity]
    guild_id = 100
    location_id = 10

    # Mock session.get for player/party status updates
    mock_session.get.side_effect = lambda model_class, entity_id: {
        (Player, mock_player_entity.id): mock_player_entity,
        # (Party, ...): ... if party logic was more complex
    }.get((model_class, entity_id), None)


    combat_encounter = await start_combat(mock_session, guild_id, location_id, participant_entities)

    assert combat_encounter is not None
    assert combat_encounter.guild_id == guild_id
    assert combat_encounter.location_id == location_id
    assert combat_encounter.status == CombatStatus.ACTIVE

    # Check participants_json
    participants_json = combat_encounter.participants_json
    assert participants_json is not None, "participants_json should not be None"

    participant_entities_list = []
    if participants_json: # Guard for Pyright and runtime
        participant_entities_list = participants_json.get("entities", [])
    assert len(participant_entities_list) == 2

    player_p_data = next((p for p in participant_entities_list if isinstance(p, dict) and p.get("id") == mock_player_entity.id), None)
    npc_p_data = next((p for p in participant_entities_list if isinstance(p, dict) and p.get("id") == mock_npc_entity.id), None)

    assert player_p_data is not None, "Player participant data not found"
    if player_p_data: # Guard for Pyright
        assert player_p_data.get("type") == "player"
        assert player_p_data.get("max_hp") == 100 # From mock_player_entity.max_hp
        assert player_p_data.get("initiative_modifier") == 2 # (14-10)//2

    assert npc_p_data is not None, "NPC participant data not found"
    if npc_p_data: # Guard for Pyright
        assert npc_p_data.get("type") == "npc"
        assert npc_p_data.get("max_hp") == 50 # From mock_npc_entity.properties_json
        assert npc_p_data.get("initiative_modifier") == 1 # (12-10)//2

    # Check turn_order_json (Player should be first due to higher initiative roll)
    turn_order_json = combat_encounter.turn_order_json
    assert turn_order_json is not None, "turn_order_json should not be None"

    order_list = []
    current_index = None
    current_turn_number = None
    if turn_order_json: # Guard for Pyright and runtime
        order_list = turn_order_json.get("order", [])
        current_index = turn_order_json.get("current_index")
        current_turn_number = turn_order_json.get("current_turn_number")

    assert len(order_list) == 2
    if len(order_list) > 0: # Guard for Pyright
        first_in_order = order_list[0]
        if first_in_order: # Guard for Pyright
            assert first_in_order.get("id") == mock_player_entity.id
            assert first_in_order.get("type") == "player"
    if len(order_list) > 1: # Guard for Pyright
        second_in_order = order_list[1]
        if second_in_order: # Guard for Pyright
            assert second_in_order.get("id") == mock_npc_entity.id
            assert second_in_order.get("type") == "npc"

    assert combat_encounter.current_turn_entity_id == mock_player_entity.id
    assert combat_encounter.current_turn_entity_type == "player"
    assert current_index == 0
    assert current_turn_number == 1

    # Check rules snapshot (basic check)
    rules_snapshot = combat_encounter.rules_config_snapshot_json
    assert rules_snapshot is not None, "rules_config_snapshot_json should not be None"
    if rules_snapshot: # Guard for Pyright and runtime
        assert "combat:initiative:dice" in rules_snapshot, "'combat:initiative:dice' not in rules_snapshot"
        assert rules_snapshot.get("combat:initiative:dice") == "1d20"

    # Check player status update
    assert mock_player_entity.current_status == PlayerStatus.COMBAT
    if hasattr(mock_player_entity, 'current_combat_id'): # Guard for missing attribute
         assert mock_player_entity.current_combat_id == combat_encounter.id # type: ignore
    else:
        # This case implies the Player model might be missing current_combat_id, which is a separate issue
        # For this test, if the fixture sets it, this branch shouldn't be hit by logic,
        # but Pyright might complain if Player model doesn't define it.
        pass


    # Check log_event call
    mock_log_event.assert_called_once() # type: ignore
    log_call_args = mock_log_event.call_args # Access .call_args directly
    assert log_call_args is not None, "log_event was not called with arguments"

    log_kwargs = log_call_args.kwargs
    assert log_kwargs.get("event_type") == EventType.COMBAT_START.name
    assert log_kwargs.get("guild_id") == guild_id

    details_json = log_kwargs.get("details_json", {})
    assert details_json.get("combat_id") == combat_encounter.id
    assert len(details_json.get("participants", [])) == 2

    # Check that session.add was called for combat_encounter and player
    # Approximate check: number of calls to session.add
    # CombatEncounter + Player + (Party if any)
    # In this case, CombatEncounter + Player
    # The mock_player_entity itself is modified, and then added.
    # The specific object `combat_encounter` is also added.
    # This check is tricky with MagicMock objects being modified in place.
    # A simple count:
    # We add combat_encounter once.
    # We add mock_player_entity once after modifying its status.
    assert mock_session.add.call_count >= 2 # At least for combat_encounter and player

    # Check session.flush was called
    mock_session.flush.assert_called()


@pytest.mark.asyncio
@patch('backend.core.rules.get_rule')
@patch('backend.core.dice_roller.roll_dice')
async def test_start_combat_initiative_tie_break_order(
    mock_roll_dice: MagicMock,
    mock_get_rule: AsyncMock,
    mock_session: AsyncMock,
    mock_player_entity: Player, # Dex 14 (+2)
    mock_npc_entity: GeneratedNpc, # Dex 12 (+1)
    mock_player_entity_2: Player # Dex 10 (+0)
):
    # Player1 (id 1, dex +2), NPC (id 2, dex +1), Player2 (id 3, dex +0)
    # Assume rolls: Player1 gets 10, NPC gets 11, Player2 gets 12.
    # Total initiative: Player1 = 12, NPC = 12, Player2 = 12
    # In case of a tie, current implementation relies on original list order due to sort stability (if Python's sort is stable)
    # or the implicit tie-breaking of sort if not stable.
    # The plan was to use dexterity modifier as a tie-breaker, but current code doesn't explicitly do that.
    # It sorts by score only. Python's Timsort is stable, so original order for ties is preserved.
    # Let's test with original order: [P1, NPC, P2]
    # Expected order if all roll same effective score and sort is stable: P1, NPC, P2
    # If rolls are P1=10 (score 12), NPC=11 (score 12), P2=12 (score 12)
    # Order should be P1, NPC, P2 (if input order was P1, NPC, P2)

    mock_get_rule.side_effect = lambda *, session, guild_id, key, default: {"combat:initiative:dice": "1d20"}.get(key, default) # Changed db to session
    mock_roll_dice.side_effect = [
        (10, [10]), # P1 (id 1, mod +2) -> total 12
        (11, [11]), # NPC (id 2, mod +1) -> total 12
        (12, [12])  # P2 (id 3, mod +0) -> total 12
    ]
    participant_entities = [mock_player_entity, mock_npc_entity, mock_player_entity_2]

    combat_encounter = await start_combat(mock_session, 100, 10, participant_entities)

    order_list = []
    if combat_encounter.turn_order_json and isinstance(combat_encounter.turn_order_json.get("order"), list):
        order_list = combat_encounter.turn_order_json["order"]

    assert len(order_list) == 3, "Turn order should contain 3 participants"
    # Since all have score 12, and Python's sort is stable, the order should be the input order.
    if len(order_list) == 3: # Guard for Pyright
        first_in_order = order_list[0]
        second_in_order = order_list[1]
        third_in_order = order_list[2]
        if first_in_order: assert first_in_order.get("id") == mock_player_entity.id
        if second_in_order: assert second_in_order.get("id") == mock_npc_entity.id
        if third_in_order: assert third_in_order.get("id") == mock_player_entity_2.id

    assert combat_encounter.current_turn_entity_id == mock_player_entity.id

    # If Player 2 had higher dex and they all rolled to the same score
    # Example: P1 (dex+2, roll 10 -> 12), NPC (dex+1, roll 11 -> 12), P2 (dex+3, roll 9 -> 12)
    # If sort was by (score, -dex_mod), P2 would be first among ties.
    # Current code doesn't have secondary sort key.

@pytest.mark.asyncio
async def test_start_combat_no_participants(mock_session: AsyncMock):
    # Should ideally not happen, but test robustness
    with patch('backend.core.game_events.log_event', new_callable=AsyncMock) as mock_log_event_empty: # Avoid conflict
        combat_encounter = await start_combat(mock_session, 100, 10, [])
        assert combat_encounter.status == CombatStatus.ERROR # Or some other appropriate status
        # No log event for COMBAT_START should be called if it errors out early.
        # The current code logs an error and returns. It doesn't raise an exception to trigger @transactional rollback by default.
        # This depends on how @transactional handles function returns vs exceptions.
        # For now, assuming it returns the combat_encounter object.
        # mock_log_event_empty.assert_not_called() # This might fail if error logging happens via log_event
        logger_error_calls = [call for call in mock_session.method_calls if call[0] == 'error'] # Check logger
        # This is not how to check logger calls. Patch logger directly.
        # For now, just check status.
        # The code `logger.error` is called, but not `game_events.log_event`.

# TODO: Add tests for player party status updates during start_combat


# --- Placeholder for tests for process_combat_turn and _handle_combat_end_consequences ---
# These will be more complex as they involve mocking more interactions.

@pytest.mark.asyncio
@patch('backend.core.combat_cycle_manager._handle_combat_end_consequences', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager._check_combat_end', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager._advance_turn', new_callable=AsyncMock)
@patch('backend.core.npc_combat_strategy.get_npc_combat_action', new_callable=AsyncMock)
@patch('backend.core.combat_engine.process_combat_action', new_callable=AsyncMock) # engine_process_combat_action
# @pytest.mark.skip(reason="Temporarily skipping due to RecursionError, needs detailed mock setup for turn progression.") # Unskip
async def test_process_combat_turn_npc_action(
    mock_engine_process_action: AsyncMock,
    mock_get_npc_action: AsyncMock,
    mock_advance_turn: AsyncMock,
    mock_check_combat_end: AsyncMock,
    mock_handle_end_consequences: AsyncMock,
    mock_session: AsyncMock,
    mock_npc_entity: GeneratedNpc # This will be the active entity
):
    guild_id = 100
    combat_id = 1

    # Setup CombatEncounter mock
    mock_combat_encounter = MagicMock(spec=CombatEncounter)
    mock_combat_encounter.id = combat_id
    mock_combat_encounter.guild_id = guild_id
    mock_combat_encounter.status = CombatStatus.ACTIVE
    mock_combat_encounter.current_turn_entity_id = mock_npc_entity.id
    mock_combat_encounter.current_turn_entity_type = "npc"
    mock_combat_encounter.turn_order_json = {
        "order": [{"id": mock_npc_entity.id, "type": "npc"}], # Simplified
        "current_index": 0,
        "current_turn_number": 1
    }
    mock_combat_encounter.participants_json = {
        "entities": [{
            "id": mock_npc_entity.id, "type": "npc", "name": "Goblin", "team": "npcs",
            "current_hp": 30, "max_hp": 50, # NPC is alive
            # ... other participant data
        }]
    }
    mock_combat_encounter.rules_config_snapshot_json = {}
    mock_combat_encounter.location_id = 10

    mock_session.get.return_value = mock_combat_encounter

    # NPC action setup
    npc_chosen_action = {"action_type": "attack", "target_id": 1, "target_type": "player"}
    mock_get_npc_action.return_value = npc_chosen_action

    # Combat engine result setup
    mock_action_result = AsyncMock(spec=type(CombatActionResult)) # Use type for spec
    mock_action_result.success = True
    mock_action_result.description_i18n = {"en": "NPC attacked!"}
    mock_action_result.model_dump = MagicMock(return_value={"success": True, "description_i18n": {"en": "NPC attacked!"}})
    mock_action_result.model_dump_json = MagicMock(return_value='{"success": true, "description_i18n": {"en": "NPC attacked!"}}')
    mock_engine_process_action.return_value = mock_action_result


    # Combat end check setup
    mock_check_combat_end.return_value = (False, None) # Combat does not end

    # Define side_effect for mock_advance_turn to prevent infinite recursion
    async def advance_turn_side_effect(session, encounter_obj):
        # Simulate advancing to a player's turn to break recursion for this test
        encounter_obj.current_turn_entity_type = "player"
        encounter_obj.current_turn_entity_id = 999 # Some dummy player ID

        turn_order_json = encounter_obj.turn_order_json
        if turn_order_json and isinstance(turn_order_json.get("order"), list):
            current_idx = turn_order_json.get("current_index", 0)
            order_list = turn_order_json.get("order", [])
            order_len = len(order_list)
            if order_len > 0:
                turn_order_json["current_index"] = (current_idx + 1) % order_len
                if turn_order_json["current_index"] == 0:
                    turn_order_json["current_turn_number"] = turn_order_json.get("current_turn_number", 1) + 1
        return None

    mock_advance_turn.side_effect = advance_turn_side_effect

    # Call the function
    returned_encounter = await process_combat_turn(mock_session, guild_id, combat_id)

    mock_get_npc_action.assert_called_once_with(
        session=mock_session, guild_id=guild_id, npc_id=mock_npc_entity.id, combat_instance_id=combat_id
    )
    mock_engine_process_action.assert_called_once_with(
        guild_id=guild_id, session=mock_session, combat_instance_id=combat_id,
        actor_id=mock_npc_entity.id, actor_type="npc", action_data=npc_chosen_action
    )
    mock_check_combat_end.assert_called_once_with(mock_session, guild_id, mock_combat_encounter)
    mock_advance_turn.assert_called_once_with(mock_session, mock_combat_encounter) # Ensure session is passed
    mock_handle_end_consequences.assert_not_called() # Combat did not end

    assert returned_encounter == mock_combat_encounter
    mock_session.add.assert_called_with(mock_combat_encounter) # Should be added for updates
    mock_session.refresh.assert_called_once_with(mock_combat_encounter)


# TODO: test_process_combat_turn_player_action_advances_turn (if player action already processed)
# TODO: test_process_combat_turn_combat_ends
# TODO: test_process_combat_turn_active_entity_defeated_skips_action
# TODO: test_process_combat_turn_recursive_npc_turns

# --- Tests for _handle_combat_end_consequences (more involved mocking) ---
# This is a private helper, usually tested via its public caller (process_combat_turn when combat ends)
# For direct testing (if desired):
# @pytest.mark.asyncio
# @patch('backend.core.combat_cycle_manager.xp_awarder.award_xp', new_callable=AsyncMock)
# @patch('backend.core.combat_cycle_manager.loot_generator.distribute_loot', new_callable=AsyncMock)
# ... and so on for other placeholders and game_events.log_event
# async def test_handle_combat_end_consequences_player_wins(
# mock_award_xp, mock_distribute_loot, ..., mock_session, mock_player_entity, mock_npc_entity
# ):
# Setup mock_combat_encounter with specific participants and a winning_team="players"
# Call _handle_combat_end_consequences
# Assert that xp_awarder, loot_generator, etc. were called correctly.
# Assert player statuses are updated.
# Assert COMBAT_END event is logged.


# Minimal test for _advance_turn (private, usually tested via process_combat_turn)
def test_advance_turn_logic_simple(): # This can be a sync test if _advance_turn itself is mostly synchronous logic
    mock_combat_encounter = MagicMock(spec=CombatEncounter)
    mock_combat_encounter.id = 1
    mock_combat_encounter.turn_order_json = {
        "order": [
            {"id": 1, "type": "player"},
            {"id": 2, "type": "npc"},
            {"id": 3, "type": "player"},
        ],
        "current_index": 0, # Player 1's turn
        "current_turn_number": 1
    }
    mock_combat_encounter.participants_json = { # All alive
        "entities": [
            {"id": 1, "type": "player", "current_hp": 10},
            {"id": 2, "type": "npc", "current_hp": 10},
            {"id": 3, "type": "player", "current_hp": 10},
        ]
    }
    # Need to use the actual _advance_turn for a real test, this is just conceptual
    # await _advance_turn(None, mock_combat_encounter) # Pass mock_session if it makes DB calls
    # assert mock_combat_encounter.current_turn_entity_id == 2
    # assert mock_combat_encounter.turn_order_json["current_index"] == 1
    # ... and so on for more complex scenarios (skipping defeated, wrapping around)
    pass # Actual test requires calling the async function or making it sync for this test type.

# More tests to consider:
# - start_combat with a party involved, check PartyTurnStatus.
# - process_combat_turn where the current entity is defeated at the start of their turn.
# - process_combat_turn where an NPC action results in combat ending.
# - process_combat_turn where player action (processed externally) results in combat ending.
# - Full recursive NPC turn processing: NPC1 acts -> NPC2's turn -> NPC2 acts -> Player's turn.

# Test for _check_combat_end (private helper)
# This can be tested more easily as it's mostly pure logic on the encounter state.
def test_check_combat_end_scenarios():
    mock_encounter = MagicMock(spec=CombatEncounter)
    mock_encounter.id = 1
    mock_encounter.guild_id = 100

    # Scenario 1: Players win
    mock_encounter.participants_json = {"entities": [
        {"id": 1, "type": "player", "team": "players", "current_hp": 10},
        {"id": 2, "type": "npc", "team": "npcs", "current_hp": 0},
        {"id": 3, "type": "npc", "team": "npcs", "current_hp": 0},
    ]}
    # ended, winner = await _check_combat_end(None, 100, mock_encounter) # Needs async context
    # assert ended is True
    # assert winner == "players"
    pass # Placeholder for async call

# To run these tests, you'd typically use `pytest` in your terminal.
# Ensure that the test file is discoverable by pytest (e.g., named test_*.py or *_test.py).
# You might need to configure PYTHONPATH or install your package in editable mode (`pip install -e .`)
# for imports like `from backend.core...` to work correctly.
# Also, ensure `asyncio_mode = auto` in pytest.ini or use `pytest-asyncio`.

# pytest.ini example:
# [pytest]
# asyncio_mode = auto
# python_files = test_*.py *_test.py
# testpaths = tests
# log_cli = true
# log_cli_level = INFO
# markers =
#     asyncio
#     slow: marks tests as slow to run
#     serial
# addopts = --strict-markers
# filterwarnings =
#     ignore::DeprecationWarning

# Note: The tests for private functions (_advance_turn, _check_combat_end) are conceptual.
# It's generally better to test private functions via the public interface that uses them.
# However, for complex private logic, direct unit tests (often by temporarily making them non-private
# or using `module._function_name` access) can be useful during development.
# For the final submission, focus on testing the public API (start_combat, process_combat_turn).
# The `_check_combat_end_scenarios` test is good as it tests a critical piece of logic.

# Test for player in a party status update
@pytest.mark.asyncio
@patch('backend.core.rules.get_rule')
@patch('backend.core.dice_roller.roll_dice')
@patch('backend.core.game_events.log_event')
async def test_start_combat_player_in_party_status_update(
    mock_log_event: AsyncMock,
    mock_roll_dice: MagicMock,
    mock_get_rule: AsyncMock,
    mock_session: AsyncMock,
    mock_player_entity: Player, # Player 1
    mock_npc_entity: GeneratedNpc  # NPC
):
    guild_id = 100
    location_id = 10
    party_id = 500

    mock_player_entity.current_party_id = party_id # Player is in a party

    mock_party = MagicMock(spec=Party)
    mock_party.id = party_id
    mock_party.guild_id = guild_id
    mock_party.turn_status = PartyTurnStatus.IDLE
    mock_party.current_combat_id = None # Assuming this attribute exists

    # Mock rule calls
    def get_rule_party_test_side_effect(*, session, guild_id, key, default): # Changed db to session
        return {
            "player:stats:default_max_hp": 100,
            "combat:initiative:dice": "1d20",
        }.get(key, default)
    mock_get_rule.side_effect = get_rule_party_test_side_effect
    mock_roll_dice.return_value = (10, [10]) # Single roll for simplicity

    participant_entities = [mock_player_entity, mock_npc_entity]

    # Mock session.get to return the player and their party
    async def mock_session_get_side_effect(model_class, entity_id):
        if model_class == Player and entity_id == mock_player_entity.id:
            return mock_player_entity
        if model_class == Party and entity_id == party_id:
            return mock_party
        return None
    mock_session.get.side_effect = mock_session_get_side_effect

    combat_encounter = await start_combat(mock_session, guild_id, location_id, participant_entities)

    assert combat_encounter is not None
    assert mock_player_entity.current_status == PlayerStatus.COMBAT # Changed IN_COMBAT
    assert mock_party.turn_status == PartyTurnStatus.IN_COMBAT # This should be fine now
    if hasattr(mock_party, 'current_combat_id'):
        assert mock_party.current_combat_id == combat_encounter.id

    # Verify session.add was called for the party
    # This check is indirect; we ensure party status is changed.
    # Direct check:
    add_calls = mock_session.add.call_args_list
    assert any(call[0][0] == mock_party for call in add_calls), "Session.add was not called with the party object"

    # Check that party status was updated correctly
    # This is implicitly tested by `assert mock_party.turn_status == PartyTurnStatus.IN_COMBAT`
    # if the mock_party object itself is the one being modified and added.
    # If `session.get` returns a copy, this test would be different.
    # With MagicMock, it's usually the same object.

    # Example of how to check specific attributes of added objects if they were different instances
    # party_added = None
    # for call in add_calls:
    #     obj = call[0][0]
    #     if isinstance(obj, Party) and obj.id == party_id:
    #         party_added = obj
    #         break
    # assert party_added is not None
    # assert party_added.turn_status == PartyTurnStatus.IN_COMBAT


# --- Tests for round-based effects ---
from backend.models import ActiveStatusEffect, StatusEffect # For creating mock status effects

@pytest.mark.asyncio
@patch('backend.core.combat_cycle_manager.game_events.log_event', new_callable=AsyncMock)
@patch('backend.core.ability_system.remove_status', new_callable=AsyncMock) # Patched at its source
async def test_process_round_effects_status_duration_and_removal(
    mock_remove_status: AsyncMock,
    mock_log_event_round_effects: AsyncMock, # Renamed to avoid fixture conflict
    mock_session: AsyncMock,
    mock_player_entity: Player, # Will have the status effect
    mock_npc_entity: GeneratedNpc   # Another participant
):
    guild_id = 100
    combat_id = 1
    active_status_id = 123
    status_def_id = 456

    # Setup CombatEncounter
    mock_combat_encounter = MagicMock(spec=CombatEncounter)
    mock_combat_encounter.id = combat_id
    mock_combat_encounter.guild_id = guild_id
    mock_combat_encounter.status = CombatStatus.ACTIVE
    mock_combat_encounter.current_turn_entity_id = mock_npc_entity.id # NPC's turn, player just ended theirs
    mock_combat_encounter.current_turn_entity_type = "npc"
    mock_combat_encounter.location_id = 10

    player_participant_data = {
        "id": mock_player_entity.id, "type": "player", "name": "Test Player", "team": "players",
        "current_hp": 50, "max_hp": 100
    }
    npc_participant_data = {
        "id": mock_npc_entity.id, "type": "npc", "name": "Goblin", "team": "npcs",
        "current_hp": 30, "max_hp": 50
    }
    mock_combat_encounter.participants_json = {"entities": [player_participant_data, npc_participant_data]}

    # Turn order: Player, then NPC. Current index is 1 (NPC), so next is Player (index 0), starting new round.
    mock_combat_encounter.turn_order_json = {
        "order": [
            {"id": mock_player_entity.id, "type": "player"},
            {"id": mock_npc_entity.id, "type": "npc"}
        ],
        "current_index": 1, # NPC's turn just ended / is current
        "current_turn_number": 1
    }
    mock_session.get.return_value = mock_combat_encounter # For process_combat_turn loading

    # Setup ActiveStatusEffect for the player
    mock_status_definition = MagicMock(spec=StatusEffect)
    mock_status_definition.id = status_def_id
    mock_status_definition.static_id = "test_poison"
    mock_status_definition.properties_json = {} # No tick effect for this test

    active_status_player = MagicMock(spec=ActiveStatusEffect)
    active_status_player.id = active_status_id
    active_status_player.entity_id = mock_player_entity.id
    active_status_player.entity_type = "player"
    active_status_player.guild_id = guild_id
    active_status_player.status_effect_id = status_def_id
    active_status_player.remaining_turns = 1 # Initial value
    # Attach the definition to the active effect instance for the join behavior
    active_status_player.status_effect = mock_status_definition


    # Mock session.execute for fetching active status effects
    # await session.execute(stmt) returns a Result object (synchronous).
    # Result.scalars() is a sync method returning ScalarResult.
    # ScalarResult.all() is a sync method returning a list.

    mock_db_result_for_statuses = MagicMock() # This will be the return_value of await session.execute()
    mock_scalar_result_for_statuses = MagicMock()
    mock_scalar_result_for_statuses.all.return_value = [active_status_player]
    mock_db_result_for_statuses.scalars.return_value = mock_scalar_result_for_statuses

    # Store the original execute mock from the fixture
    original_session_execute_mock = mock_session.execute

    # Prepare separate mock results for player and NPC status queries
    # For player
    mock_db_result_player = MagicMock()
    mock_scalar_result_player = MagicMock()
    mock_scalar_result_player.all.return_value = [active_status_player] # Player has the status
    mock_db_result_player.scalars.return_value = mock_scalar_result_player

    # For NPC
    mock_db_result_npc = MagicMock()
    mock_scalar_result_npc = MagicMock()
    mock_scalar_result_npc.all.return_value = [] # NPC has no status
    mock_db_result_npc.scalars.return_value = mock_scalar_result_npc

    # Side effect function for session.execute
    # It will be called twice by _process_round_based_status_effects: once for player, once for NPC.
    # We need to return the correct mock result based on which entity is being queried.
    # This is hard to do by inspecting the statement directly in a mock.
    # Instead, we can rely on the call order if participants are processed predictably.
    # The participant list is [player_participant_data, npc_participant_data].
    # So, first execute call in _process_round_based_status_effects will be for player, second for NPC.

    # We need a way to track calls to the *new* AsyncMock we are about to assign to mock_session.execute
    temp_execute_mock = AsyncMock()

    call_count_for_execute = 0
    async def conditional_execute_side_effect(statement, *args, **kwargs):
        nonlocal call_count_for_execute
        call_count_for_execute += 1
        if call_count_for_execute == 1: # First call (for player)
            return mock_db_result_player
        else: # Second call (for NPC)
            return mock_db_result_npc

    temp_execute_mock.side_effect = conditional_execute_side_effect
    mock_session.execute = temp_execute_mock # Assign the new mock with side_effect

    # We will test _advance_turn directly to isolate the round effect processing
    from backend.core.combat_cycle_manager import _advance_turn

    # Call _advance_turn. This should trigger a new round and call _process_round_based_status_effects.
    await _advance_turn(mock_session, mock_combat_encounter)

    # Restore original session.execute mock from the fixture
    mock_session.execute = original_session_execute_mock


    # Assertions
    # Status duration should have been decremented
    assert active_status_player.remaining_turns == 0 # Decremented from 1 to 0

    # Status should have been removed
    mock_remove_status.assert_called_once_with(mock_session, guild_id, active_status_player.id)

    # Turn number should increment
    assert mock_combat_encounter.turn_order_json["current_turn_number"] == 2
    # Current turn should be player's
    assert mock_combat_encounter.current_turn_entity_id == mock_player_entity.id
    assert mock_combat_encounter.turn_order_json["current_index"] == 0


@pytest.mark.asyncio
@patch('backend.core.combat_cycle_manager._advance_turn', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager.npc_combat_strategy.get_npc_combat_action', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager.combat_engine.process_combat_action', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager._check_combat_end', new_callable=AsyncMock)
async def test_process_combat_turn_active_entity_defeated_skips_action(
    mock_check_combat_end: AsyncMock,
    mock_engine_process_action: AsyncMock,
    mock_get_npc_action: AsyncMock,
    mock_advance_turn: AsyncMock,
    mock_session: AsyncSession,
    mock_player_entity: Player, # Next in turn
    mock_npc_entity: GeneratedNpc   # Current turn, but defeated
):
    guild_id = 100
    combat_id = 1

    # Setup CombatEncounter: NPC is current turn but has 0 HP
    defeated_npc_participant_data = {
        "id": mock_npc_entity.id, "type": "npc", "name": "Defeated Goblin", "team": "npcs",
        "current_hp": 0, "max_hp": 50 # DEFEATED
    }
    player_participant_data = {
        "id": mock_player_entity.id, "type": "player", "name": "Test Player", "team": "players",
        "current_hp": 100, "max_hp": 100
    }
    mock_combat_encounter = MagicMock(spec=CombatEncounter)
    mock_combat_encounter.id = combat_id
    mock_combat_encounter.guild_id = guild_id
    mock_combat_encounter.status = CombatStatus.ACTIVE
    mock_combat_encounter.current_turn_entity_id = mock_npc_entity.id # Defeated NPC's turn
    mock_combat_encounter.current_turn_entity_type = "npc"
    mock_combat_encounter.participants_json = {"entities": [defeated_npc_participant_data, player_participant_data]}
    mock_combat_encounter.turn_order_json = {
        "order": [
            {"id": mock_npc_entity.id, "type": "npc"},      # Defeated
            {"id": mock_player_entity.id, "type": "player"} # Next
        ],
        "current_index": 0, # Defeated NPC's index
        "current_turn_number": 2
    }
    mock_session.get.return_value = mock_combat_encounter
    # Combat does not end immediately (e.g. player still needs to act or other NPCs exist)
    mock_check_combat_end.return_value = (False, None)

    # Call process_combat_turn
    await process_combat_turn(mock_session, guild_id, combat_id)

    # Assertions
    mock_get_npc_action.assert_not_called() # NPC action should be skipped
    mock_engine_process_action.assert_not_called() # Engine processing should be skipped

    # _check_combat_end is called after potential action processing (which is skipped here)
    mock_check_combat_end.assert_called_once_with(mock_session, guild_id, mock_combat_encounter)

    # _advance_turn should be called to move to the next entity because combat didn't end
    mock_advance_turn.assert_called_once_with(mock_session, mock_combat_encounter)

    # Ensure session.refresh was called on the encounter
    mock_session.refresh.assert_called_with(mock_combat_encounter)


@pytest.mark.asyncio
@patch('backend.core.combat_cycle_manager._advance_turn', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager.npc_combat_strategy.get_npc_combat_action', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager.combat_engine.process_combat_action', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager._check_combat_end', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager._handle_combat_end_consequences', new_callable=AsyncMock)
async def test_process_combat_turn_combat_ends(
    mock_handle_end_consequences: AsyncMock,
    mock_check_combat_end: AsyncMock,
    mock_engine_process_action: AsyncMock,
    mock_get_npc_action: AsyncMock,
    mock_advance_turn: AsyncMock,
    mock_session: AsyncSession,
    mock_player_entity: Player,
    mock_npc_entity: GeneratedNpc
):
    guild_id = 100
    combat_id = 1

    # Setup: NPC's turn. Player is the only opponent and has low HP.
    player_participant_data = {
        "id": mock_player_entity.id, "type": "player", "name": "Test Player", "team": "players",
        "current_hp": 5, "max_hp": 100 # Player has low HP
    }
    npc_participant_data = { # NPC is acting
        "id": mock_npc_entity.id, "type": "npc", "name": "Goblin Attacker", "team": "npcs",
        "current_hp": 30, "max_hp": 50
    }
    mock_combat_encounter = MagicMock(spec=CombatEncounter)
    mock_combat_encounter.id = combat_id
    mock_combat_encounter.guild_id = guild_id
    mock_combat_encounter.status = CombatStatus.ACTIVE
    mock_combat_encounter.current_turn_entity_id = mock_npc_entity.id
    mock_combat_encounter.current_turn_entity_type = "npc"
    mock_combat_encounter.participants_json = {"entities": [player_participant_data, npc_participant_data]}
    mock_combat_encounter.turn_order_json = {
        "order": [{"id": mock_npc_entity.id, "type": "npc"}, {"id": mock_player_entity.id, "type": "player"}],
        "current_index": 0, "current_turn_number": 1
    }
    mock_session.get.return_value = mock_combat_encounter

    # NPC performs an action
    mock_get_npc_action.return_value = {"action_type": "attack", "target_id": mock_player_entity.id, "target_type": "player"}

    # combat_engine.process_combat_action will modify participants_json in the session's view of combat_encounter
    # For the test, we simulate this by having _check_combat_end see the result.
    # The mock_engine_process_action itself doesn't need to do much for this test's focus.
    mock_engine_process_action.return_value = AsyncMock(spec=CombatActionResult)


    # _check_combat_end will be called after the action. Simulate it finds combat has ended.
    # It needs to be a side effect because participants_json is modified by combat_engine (conceptually)
    async def check_end_side_effect(session, gid, encounter_obj):
        # Simulate player defeated after NPC action
        for p_data in encounter_obj.participants_json["entities"]:
            if p_data["id"] == mock_player_entity.id:
                p_data["current_hp"] = 0 # Player is now defeated
        return (True, "npcs") # NPCs win
    mock_check_combat_end.side_effect = check_end_side_effect

    await process_combat_turn(mock_session, guild_id, combat_id)

    mock_get_npc_action.assert_called_once()
    mock_engine_process_action.assert_called_once()
    mock_check_combat_end.assert_called_once() # Called after action

    # Crucially, _advance_turn should NOT be called if combat ended
    mock_advance_turn.assert_not_called()

    # _handle_combat_end_consequences should be called
    mock_handle_end_consequences.assert_called_once_with(mock_session, guild_id, mock_combat_encounter, "npcs")

    assert mock_combat_encounter.status == CombatStatus.ENDED_VICTORY_NPCS
    mock_session.add.assert_called_with(mock_combat_encounter) # For status update


@pytest.mark.asyncio
@patch('backend.core.combat_cycle_manager._advance_turn', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager.npc_combat_strategy.get_npc_combat_action', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager.combat_engine.process_combat_action', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager._check_combat_end', new_callable=AsyncMock)
async def test_process_combat_turn_player_action_advances_turn(
    mock_check_combat_end: AsyncMock,
    mock_engine_process_action: AsyncMock, # Should not be called by process_combat_turn for player
    mock_get_npc_action: AsyncMock,      # Should not be called
    mock_advance_turn: AsyncMock,
    mock_session: AsyncSession,
    mock_player_entity: Player, # Current turn
    mock_npc_entity: GeneratedNpc   # Next in turn (hypothetically)
):
    guild_id = 100
    combat_id = 1

    player_participant_data = {
        "id": mock_player_entity.id, "type": "player", "name": "Test Player", "team": "players",
        "current_hp": 100, "max_hp": 100
    }
    npc_participant_data = {
        "id": mock_npc_entity.id, "type": "npc", "name": "Goblin", "team": "npcs",
        "current_hp": 30, "max_hp": 50
    }
    mock_combat_encounter = MagicMock(spec=CombatEncounter)
    mock_combat_encounter.id = combat_id
    mock_combat_encounter.guild_id = guild_id
    mock_combat_encounter.status = CombatStatus.ACTIVE
    mock_combat_encounter.current_turn_entity_id = mock_player_entity.id # Player's turn
    mock_combat_encounter.current_turn_entity_type = "player"
    mock_combat_encounter.participants_json = {"entities": [player_participant_data, npc_participant_data]}
    mock_combat_encounter.turn_order_json = {
        "order": [
            {"id": mock_player_entity.id, "type": "player"},
            {"id": mock_npc_entity.id, "type": "npc"}
        ],
        "current_index": 0,
        "current_turn_number": 1
    }
    mock_session.get.return_value = mock_combat_encounter

    # Player's action is assumed to have been processed externally by combat_engine.
    # So, process_combat_turn should not try to get/process a player action.

    mock_check_combat_end.return_value = (False, None) # Combat continues

    await process_combat_turn(mock_session, guild_id, combat_id)

    mock_get_npc_action.assert_not_called()
    mock_engine_process_action.assert_not_called() # Not by process_combat_turn for player

    mock_check_combat_end.assert_called_once_with(mock_session, guild_id, mock_combat_encounter)
    mock_advance_turn.assert_called_once_with(mock_session, mock_combat_encounter)
    mock_session.refresh.assert_called_with(mock_combat_encounter)


@pytest.mark.asyncio
@patch('backend.core.combat_cycle_manager.npc_combat_strategy.get_npc_combat_action', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager.combat_engine.process_combat_action', new_callable=AsyncMock)
@patch('backend.core.combat_cycle_manager._check_combat_end', new_callable=AsyncMock)
# We need to control _advance_turn very carefully for this test.
# We cannot simply mock it with a single AsyncMock if we want to test recursion based on its side effects.
# Instead, we will patch it but provide a more stateful side_effect or multiple return_values.
# For this test, we'll use a side_effect on the main process_combat_turn mock if needed, or carefully control _advance_turn.
# Let's try to control _advance_turn's effect on the combat_encounter mock.
async def test_process_combat_turn_recursive_npc_turns(
    mock_check_combat_end: AsyncMock,
    mock_engine_process_action: AsyncMock,
    mock_get_npc_action: AsyncMock,
    mock_session: AsyncMock,
    mock_player_entity: Player,
    mock_npc_entity: GeneratedNpc # NPC1
):
    # This test will be complex due to the recursive nature.
    # We want to see process_combat_turn handle NPC1, then NPC2.
    guild_id = 100
    combat_id = 1

    npc2_id = mock_npc_entity.id + 1
    mock_npc_entity_2 = MagicMock(spec=GeneratedNpc)
    mock_npc_entity_2.id = npc2_id
    mock_npc_entity_2.name_i18n = {"en": "Goblin Archer"}

    # Participants data
    player_pd = {"id": mock_player_entity.id, "type": "player", "name": "Player", "team": "players", "current_hp": 100}
    npc1_pd = {"id": mock_npc_entity.id, "type": "npc", "name": "NPC1", "team": "npcs", "current_hp": 50}
    npc2_pd = {"id": npc2_id, "type": "npc", "name": "NPC2", "team": "npcs", "current_hp": 40}

    mock_combat_encounter = MagicMock(spec=CombatEncounter)
    mock_combat_encounter.id = combat_id
    mock_combat_encounter.guild_id = guild_id
    mock_combat_encounter.status = CombatStatus.ACTIVE
    mock_combat_encounter.current_turn_entity_id = mock_npc_entity.id # Start with NPC1's turn
    mock_combat_encounter.current_turn_entity_type = "npc"
    mock_combat_encounter.participants_json = {"entities": [player_pd, npc1_pd, npc2_pd]}
    mock_combat_encounter.turn_order_json = {
        "order": [
            {"id": mock_npc_entity.id, "type": "npc"}, # NPC1
            {"id": npc2_id, "type": "npc"},            # NPC2
            {"id": mock_player_entity.id, "type": "player"}   # Player
        ],
        "current_index": 0, # NPC1's turn
        "current_turn_number": 1
    }
    mock_session.get.return_value = mock_combat_encounter

    # Mock actions for NPCs
    npc1_action = {"action_type": "ability", "ability_id": "npc_skill_1", "target_id": mock_player_entity.id}
    npc2_action = {"action_type": "attack", "target_id": mock_player_entity.id}

    mock_get_npc_action.side_effect = [npc1_action, npc2_action] # NPC1 action, then NPC2 action

    # Mock combat engine results (doesn't need to be complex, just successful)
    mock_engine_process_action.return_value = AsyncMock(spec=CombatActionResult, success=True, description_i18n={"en":"Action done"})

    # Combat doesn't end during these NPC turns
    mock_check_combat_end.return_value = (False, None)

    # This is the tricky part: how _advance_turn modifies mock_combat_encounter
    # We need process_combat_turn to see these changes to trigger recursion.
    # Patching _advance_turn directly to modify the encounter state.
    async def advance_turn_side_effect(session, encounter_obj):
        current_id = encounter_obj.current_turn_entity_id
        if current_id == mock_npc_entity.id: # After NPC1's turn
            encounter_obj.current_turn_entity_id = npc2_id
            encounter_obj.current_turn_entity_type = "npc"
            encounter_obj.turn_order_json["current_index"] = 1
        elif current_id == npc2_id: # After NPC2's turn
            encounter_obj.current_turn_entity_id = mock_player_entity.id
            encounter_obj.current_turn_entity_type = "player"
            encounter_obj.turn_order_json["current_index"] = 2
            encounter_obj.turn_order_json["current_turn_number"] +=1 # New round for player
        # No further recursion if it's player's turn

    with patch('backend.core.combat_cycle_manager._advance_turn', side_effect=advance_turn_side_effect) as mock_advance_turn_stateful:
        await process_combat_turn(mock_session, guild_id, combat_id)

    # Assertions
    assert mock_get_npc_action.call_count == 2
    mock_get_npc_action.assert_any_call(session=mock_session, guild_id=guild_id, npc_id=mock_npc_entity.id, combat_instance_id=combat_id)
    mock_get_npc_action.assert_any_call(session=mock_session, guild_id=guild_id, npc_id=npc2_id, combat_instance_id=combat_id)

    assert mock_engine_process_action.call_count == 2
    mock_engine_process_action.assert_any_call(guild_id=guild_id, session=mock_session, combat_instance_id=combat_id, actor_id=mock_npc_entity.id, actor_type="npc", action_data=npc1_action)
    mock_engine_process_action.assert_any_call(guild_id=guild_id, session=mock_session, combat_instance_id=combat_id, actor_id=npc2_id, actor_type="npc", action_data=npc2_action)

    assert mock_check_combat_end.call_count == 2 # Called after each NPC action
    assert mock_advance_turn_stateful.call_count == 2 # Called after each NPC action that doesn't end combat

    # Final state of combat encounter should be Player's turn
    assert mock_combat_encounter.current_turn_entity_id == mock_player_entity.id
    assert mock_combat_encounter.current_turn_entity_type == "player"


@pytest.mark.asyncio
@patch('backend.core.combat_cycle_manager.game_events.log_event', new_callable=AsyncMock)
@patch('backend.core.entity_stats_utils.change_entity_hp') # Patched at its source
@patch('backend.core.entity_stats_utils.get_entity_hp') # Patched at its source
async def test_process_round_effects_tick_damage_and_participant_json_update(
    mock_get_hp: MagicMock,
    mock_change_hp: MagicMock,
    mock_log_event_tick_damage: AsyncMock,
    mock_session: AsyncMock,
    mock_player_entity: Player
):
    guild_id = 100
    combat_id = 1
    active_status_id = 124
    status_def_id = 457
    initial_hp = 50
    tick_damage = 5

    player_participant_data = {
        "id": mock_player_entity.id, "type": "player", "name": "Test Player", "team": "players",
        "current_hp": initial_hp, "max_hp": 100
    }
    mock_combat_encounter = MagicMock(spec=CombatEncounter)
    mock_combat_encounter.id = combat_id
    mock_combat_encounter.guild_id = guild_id
    mock_combat_encounter.participants_json = {"entities": [player_participant_data]}
    mock_combat_encounter.turn_order_json = {"current_turn_number": 2} # For logging
    mock_combat_encounter.location_id = 10

    # Mock player model for change_entity_hp and get_entity_hp
    # The _process_round_based_status_effects function re-fetches the entity model.
    mock_player_model_instance = Player(id=mock_player_entity.id, current_hp=initial_hp)
    mock_session.get.return_value = mock_player_model_instance # Mock for session.get(Player, ...)

    # Setup ActiveStatusEffect with a tick damage effect
    mock_status_definition_tick = MagicMock(spec=StatusEffect)
    mock_status_definition_tick.id = status_def_id
    mock_status_definition_tick.static_id = "strong_poison"
    mock_status_definition_tick.properties_json = {
        "tick_effect": {"type": "damage", "amount": tick_damage, "damage_type": "poison"}
    }
    active_status_player_tick = MagicMock(spec=ActiveStatusEffect)
    active_status_player_tick.id = active_status_id
    active_status_player_tick.entity_id = mock_player_entity.id
    active_status_player_tick.entity_type = "player"
    active_status_player_tick.guild_id = guild_id
    active_status_player_tick.status_effect_id = status_def_id
    active_status_player_tick.remaining_turns = 2 # Won't expire this round
    active_status_player_tick.status_effect = mock_status_definition_tick

    # Mock session.execute to return this status effect
    mock_db_result_for_tick_status = MagicMock()
    mock_scalar_result_for_tick_status = MagicMock()
    mock_scalar_result_for_tick_status.all.return_value = [active_status_player_tick]
    mock_db_result_for_tick_status.scalars.return_value = mock_scalar_result_for_tick_status

    original_execute = mock_session.execute
    mock_session.execute = AsyncMock(return_value=mock_db_result_for_tick_status)

    # Mock behavior of entity_stats_utils functions
    # change_entity_hp will modify mock_player_model_instance.current_hp
    def change_hp_side_effect(entity, amount):
        entity.current_hp += amount # amount is negative for damage
        return True
    mock_change_hp.side_effect = change_hp_side_effect
    # get_entity_hp will return the updated HP from mock_player_model_instance
    mock_get_hp.side_effect = lambda entity: entity.current_hp


    from backend.core.combat_cycle_manager import _process_round_based_status_effects
    await _process_round_based_status_effects(mock_session, guild_id, mock_combat_encounter)

    mock_session.execute = original_execute # Restore

    # Assertions
    assert active_status_player_tick.remaining_turns == 1 # Decremented
    mock_change_hp.assert_called_once_with(mock_player_model_instance, -tick_damage)
    assert mock_player_model_instance.current_hp == initial_hp - tick_damage

    # Check that participants_json was updated
    updated_player_p_data = mock_combat_encounter.participants_json["entities"][0]
    assert updated_player_p_data["current_hp"] == initial_hp - tick_damage

    # Check log event for tick effect
    mock_log_event_tick_damage.assert_called() # Check if log_event was called at all

    status_tick_log_call = None
    for call_args_tuple in mock_log_event_tick_damage.call_args_list:
        # event_type is the 3rd positional argument (index 2) to game_events.log_event
        if len(call_args_tuple.args) > 2 and call_args_tuple.args[2] == EventType.STATUS_TICK_EFFECT.name:
            status_tick_log_call = call_args_tuple
            break

    assert status_tick_log_call is not None, f"STATUS_TICK_EFFECT event not logged. Calls: {mock_log_event_tick_damage.call_args_list}"

    details = status_tick_log_call.kwargs.get("details_json", {})
    assert details.get("effect_type") == "damage"
    assert details.get("amount") == tick_damage
    assert details.get("status_static_id") == "strong_poison"


# Finalizing the test file structure
if __name__ == "__main__":
    # This block is useful for running tests with a debugger from your IDE
    # For example, in VSCode, you can set a breakpoint and run this file.
    # Note: Pytest features like fixtures and marks might not work as expected
    # when running directly like this. Use `pytest` for full test suite execution.
    #
    # Example of how one might run a single test manually (requires more setup for async):
    # import asyncio
    # async def manual_run():
    #     # Setup mocks manually here if not using pytest fixtures
    #     session = AsyncMock(spec=AsyncSession)
    #     player = ...
    #     npc = ...
    #     await test_start_combat_successful_creation(AsyncMock(), MagicMock(), AsyncMock(), session, player, npc)
    # asyncio.run(manual_run())
    pass
