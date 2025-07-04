import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List # Added Dict, Any, List

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.npc_combat_strategy import (
    _get_npc_data, # Not testing directly, assuming CRUD works
    _get_combat_encounter_data, # Not testing directly
    _get_participant_entity, # Could be tested if complex
    _get_relationship_value,
    _get_npc_ai_rules,
    _is_hostile,
    _get_potential_targets,
    _calculate_target_score,
    _select_target,
    _get_available_abilities,
    _simulate_action_outcome,
    _evaluate_action_effectiveness,
    _choose_action,
    _format_action_result,
    get_npc_combat_action
)
from src.models.generated_npc import GeneratedNpc
from src.models.player import Player
from src.models.combat_encounter import CombatEncounter
from src.models.enums import CombatParticipantType as EntityType # Changed to CombatParticipantType

# Pytest fixtures if needed, e.g. for mock session
@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)

@pytest.fixture
def mock_actor_npc() -> GeneratedNpc:
    npc = GeneratedNpc(
        id=1,
        guild_id=100,
        name_i18n={"en": "Goblin Warrior"},
        properties_json={
            "stats": {"hp": 50, "mana": 10, "base_attack_damage": 5},
            "abilities": [
                {
                    "static_id": "strong_hit", "name": "Strong Hit",
                    "cost": {"mana": 5}, "cooldown_turns": 2,
                    "effects": [{"type": "damage", "value": "10"}]
                },
                {
                    "static_id": "quick_stab", "name": "Quick Stab",
                    "cost": {"mana": 2}, "cooldown_turns": 0,
                    "effects": [{"type": "damage", "value": "3"}]
                },
                 {
                    "static_id": "self_heal_low", "name": "Minor Heal",
                    "cost": {"mana": 3}, "cooldown_turns": 3,
                    "effects": [{"type": "heal", "value": "10", "target_scope": "self"}]
                }
            ],
            "faction_id": "goblins"
        },
        ai_metadata_json={"personality": "aggressive"}
    )
    # Mock ORM relationships if GeneratedNpc model expects them (e.g. for Pydantic validation)
    # For this example, assuming direct attribute access or that Pydantic handles missing relationships gracefully for this model.
    return npc

@pytest.fixture
def mock_target_player() -> Player:
    player = Player(
        id=10,
        guild_id=100,
        discord_id=12345,
        name="HeroPlayer",
        current_hp=100 # Set current_hp directly
        # Removed properties_json, defense is not a direct Player model field
    )
    # If tests require other stats like 'defense', they need to be mocked differently,
    # as Player model doesn't have a generic 'properties_json' or 'defense' field.
    # For example, a function that retrieves player defense could be patched.
    return player

@pytest.fixture
def mock_target_npc_hostile() -> GeneratedNpc:
    npc = GeneratedNpc(
        id=2,
        guild_id=100,
        name_i18n={"en": "Bandit"},
        properties_json={
            "stats": {"hp": 40},
            "faction_id": "bandits" # Different faction
        }
    )
    return npc

@pytest.fixture
def mock_target_npc_friendly_faction() -> GeneratedNpc:
    npc = GeneratedNpc(
        id=3,
        guild_id=100,
        name_i18n={"en": "Goblin Shaman"},
        properties_json={
            "stats": {"hp": 30},
            "faction_id": "goblins" # Same faction as actor
        }
    )
    return npc


@pytest.fixture
def mock_combat_encounter(mock_actor_npc: GeneratedNpc, mock_target_player: Player) -> CombatEncounter:
    return CombatEncounter(
        id=1,
        guild_id=100,
        location_id=1,
        participants_json=[
            {"id": mock_actor_npc.id, "type": EntityType.NPC.value, "hp": 50, "resources": {"mana": 10}, "cooldowns": {}},
            {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 80}, # Player target
            {"id": 2, "type": EntityType.NPC.value, "hp": 40}, # Another NPC, potentially hostile
            {"id": 3, "type": EntityType.NPC.value, "hp": 30}, # Another NPC, potentially friendly
            {"id": 4, "type": EntityType.PLAYER.value, "hp": 0}, # Defeated player
        ],
        combat_log_json=[],
        rules_config_snapshot_json={},
            turn_order_json={} # Changed turn_info_json to turn_order_json
    )

@pytest.fixture
def mock_ai_rules() -> Dict[str, Any]:
    # A fairly standard set of AI rules for testing
    return {
        "target_selection": {
            "priority_order": ["lowest_hp_percentage", "highest_threat_score"],
            "hostility_rules": {
                "default": "attack_players_and_hostile_npcs",
                "relationship_hostile_threshold": -20,
                "relationship_friendly_threshold": 20,
                "same_faction_is_friendly": True
            },
            "threat_factors": {"damage_dealt_to_self_factor": 1.5, "is_healer_factor": 1.2}
        },
        "action_selection": {
            "offensive_bias": 0.75,
            "abilities_priority": [],
            "resource_thresholds": {"self_hp_below_for_heal_ability": 0.4},
            "ability_base_effectiveness_multiplier": 1.1,
            "status_strategic_value": {"stun": 50, "poison": 20},
            "low_hp_heal_urgency_multiplier": 2.0
        },
        "simulation": { "enabled": False } # Keep simulation off for most basic tests for simplicity
    }

# --- Tests for _get_available_abilities ---
def test_get_available_abilities_all_available(mock_actor_npc, mock_ai_rules):
    actor_combat_data = {"resources": {"mana": 10}, "cooldowns": {}}
    abilities = _get_available_abilities(mock_actor_npc, actor_combat_data, mock_ai_rules)
    assert len(abilities) == 3
    assert abilities[0]["static_id"] == "strong_hit"
    assert abilities[1]["static_id"] == "quick_stab"
    assert abilities[2]["static_id"] == "self_heal_low"


def test_get_available_abilities_not_enough_mana(mock_actor_npc, mock_ai_rules):
    actor_combat_data = {"resources": {"mana": 1}, "cooldowns": {}} # Not enough for any ability
    abilities = _get_available_abilities(mock_actor_npc, actor_combat_data, mock_ai_rules)
    assert len(abilities) == 0

def test_get_available_abilities_one_on_cooldown(mock_actor_npc, mock_ai_rules):
    actor_combat_data = {"resources": {"mana": 10}, "cooldowns": {"strong_hit": 1}}
    abilities = _get_available_abilities(mock_actor_npc, actor_combat_data, mock_ai_rules)
    assert len(abilities) == 2
    assert abilities[0]["static_id"] == "quick_stab"
    assert abilities[1]["static_id"] == "self_heal_low"

def test_get_available_abilities_mana_and_cooldown_mix(mock_actor_npc, mock_ai_rules):
    # Strong hit costs 5 mana, quick stab 2 mana. Heal 3 mana.
    actor_combat_data = {"resources": {"mana": 4}, "cooldowns": {"strong_hit": 1}}
    # Can't use strong_hit (cooldown). Can use quick_stab (2 mana). Can use heal (3 mana).
    abilities = _get_available_abilities(mock_actor_npc, actor_combat_data, mock_ai_rules)
    assert len(abilities) == 2
    available_ids = {a["static_id"] for a in abilities}
    assert "quick_stab" in available_ids
    assert "self_heal_low" in available_ids

# --- Tests for _is_hostile ---
@pytest.mark.asyncio
async def test_is_hostile_player_default_hostile(mock_session, mock_actor_npc, mock_target_player, mock_ai_rules):
    target_player_combat_info = {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 100}

    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=None)):
        hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_player_combat_info, mock_target_player, mock_ai_rules)
        assert hostile is True

@pytest.mark.asyncio
async def test_is_hostile_explicitly_friendly_relationship_player(mock_session, mock_actor_npc, mock_target_player, mock_ai_rules):
    target_player_combat_info = {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 100}
    mock_ai_rules["target_selection"]["hostility_rules"]["relationship_friendly_threshold"] = 20

    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=25)): # Friendly relationship
        hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_player_combat_info, mock_target_player, mock_ai_rules)
        assert hostile is False

@pytest.mark.asyncio
async def test_is_hostile_explicitly_hostile_relationship_npc(mock_session, mock_actor_npc, mock_target_npc_friendly_faction, mock_ai_rules):
    # Even if same faction, a very bad relationship should make them hostile
    target_npc_combat_info = {"id": mock_target_npc_friendly_faction.id, "type": EntityType.NPC.value, "hp": 30}
    mock_ai_rules["target_selection"]["hostility_rules"]["relationship_hostile_threshold"] = -50

    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=-60)): # Hostile relationship
        hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_npc_combat_info, mock_target_npc_friendly_faction, mock_ai_rules)
        assert hostile is True

@pytest.mark.asyncio
async def test_is_hostile_same_faction_npc_friendly_by_default(mock_session, mock_actor_npc, mock_target_npc_friendly_faction, mock_ai_rules):
    target_npc_combat_info = {"id": mock_target_npc_friendly_faction.id, "type": EntityType.NPC.value, "hp": 30}
    mock_ai_rules["target_selection"]["hostility_rules"]["same_faction_is_friendly"] = True

    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=None)): # No specific relationship override
        hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_npc_combat_info, mock_target_npc_friendly_faction, mock_ai_rules)
        assert hostile is False # Same faction, default friendly

@pytest.mark.asyncio
async def test_is_hostile_different_faction_npc_hostile_by_default(mock_session, mock_actor_npc, mock_target_npc_hostile, mock_ai_rules):
    target_npc_combat_info = {"id": mock_target_npc_hostile.id, "type": EntityType.NPC.value, "hp": 40}

    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=None)):
        hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_npc_combat_info, mock_target_npc_hostile, mock_ai_rules)
        assert hostile is True # Different faction, default rule makes it hostile

# --- Tests for _get_potential_targets ---
@pytest.mark.asyncio
async def test_get_potential_targets_basic(
    mock_session, mock_actor_npc, mock_combat_encounter, mock_ai_rules,
    mock_target_player, mock_target_npc_hostile, mock_target_npc_friendly_faction
):
    # Setup mocks for _get_participant_entity and _is_hostile
    # Target Player (ID 10) - Hostile
    # Target NPC Hostile (ID 2) - Hostile
    # Target NPC Friendly Faction (ID 3) - Friendly (same faction)
    # Defeated Player (ID 4) - Skipped

    async def mock_get_entity_side_effect(session, p_info, guild_id):
        if p_info["id"] == mock_target_player.id: return mock_target_player
        if p_info["id"] == mock_target_npc_hostile.id: return mock_target_npc_hostile
        if p_info["id"] == mock_target_npc_friendly_faction.id: return mock_target_npc_friendly_faction
        if p_info["id"] == 4 : return Player(id=4, guild_id=100, name="Defeated", properties_json={"stats":{"hp":100}}) # Mock for defeated
        return None

    async def mock_is_hostile_side_effect(sess, gid, actor, p_info, p_entity, rules):
        if p_info["id"] == mock_target_player.id: return True # Player is hostile
        if p_info["id"] == mock_target_npc_hostile.id: return True # This NPC is hostile
        if p_info["id"] == mock_target_npc_friendly_faction.id: return False # This NPC is friendly (same faction)
        return False # Default for others

    with patch('src.core.npc_combat_strategy._get_participant_entity', AsyncMock(side_effect=mock_get_entity_side_effect)):
        with patch('src.core.npc_combat_strategy._is_hostile', AsyncMock(side_effect=mock_is_hostile_side_effect)):
            # Extract participants_list from the mock_combat_encounter fixture
            participants_list_for_test = mock_combat_encounter.participants_json # This should be the list
            if isinstance(mock_combat_encounter.participants_json, dict) and "entities" in mock_combat_encounter.participants_json:
                 participants_list_for_test = mock_combat_encounter.participants_json["entities"]


            targets = await _get_potential_targets(
                mock_session, mock_actor_npc, mock_combat_encounter,
                mock_ai_rules, 100, participants_list_for_test
            )

            assert len(targets) == 2
            target_ids = {t["entity"].id for t in targets}
            assert mock_target_player.id in target_ids
            assert mock_target_npc_hostile.id in target_ids
            assert mock_target_npc_friendly_faction.id not in target_ids # Should be filtered out as friendly

            # Check that combat_data is passed along
            player_target_entry = next(t for t in targets if t["entity"].id == mock_target_player.id)
            assert player_target_entry["combat_data"]["hp"] == 80 # HP from combat_encounter.participants_json


# TODO: Add more tests for:
# _calculate_target_score for various metrics
# _select_target with different priority orders and tie-breaking
# _simulate_action_outcome (once less of a placeholder)
# _evaluate_action_effectiveness for different actions and results from simulation
# _choose_action for various scenarios (low HP heal, best offensive, etc.)
# _format_action_result
# get_npc_combat_action (full integration test with mocks for all sub-functions)

# Example for testing get_npc_combat_action (very high level)
@pytest.mark.asyncio
async def test_get_npc_combat_action_chooses_attack_on_player(
    mock_session, mock_actor_npc, mock_combat_encounter, mock_ai_rules, mock_target_player
):
    # This is a complex test to set up fully, requires mocking many underlying functions.
    # We'll mock the direct dependencies of get_npc_combat_action instead of every small utility.

    # Mock data loading functions
    mock_loaded_npc = mock_actor_npc
    mock_loaded_combat_encounter = mock_combat_encounter

    # Mock actor's combat data from the encounter
    actor_combat_data = next(p for p in mock_loaded_combat_encounter.participants_json if p["id"] == mock_loaded_npc.id and p["type"] == EntityType.NPC.value)

    # Mock results of intermediate steps
    # Target player is the only one hostile and available
    selected_target_info = {
        "entity": mock_target_player,
        "combat_data": next(p for p in mock_loaded_combat_encounter.participants_json if p["id"] == mock_target_player.id)
    }

    # Assume _choose_action decides to use "quick_stab"
    chosen_action_details_from_chooser = {
        "type": "ability",
        "name": "Quick Stab",
        "ability_props": next(a for a in mock_actor_npc.properties_json["abilities"] if a["static_id"] == "quick_stab")
    }

    expected_formatted_action = {
        "action_type": "ability",
        "target_id": mock_target_player.id,
        "target_type": EntityType.PLAYER.value,
        "ability_id": "quick_stab"
    }

    with patch('src.core.npc_combat_strategy._get_npc_data', AsyncMock(return_value=mock_loaded_npc)):
        with patch('src.core.npc_combat_strategy._get_combat_encounter_data', AsyncMock(return_value=mock_loaded_combat_encounter)):
            with patch('src.core.npc_combat_strategy._get_npc_ai_rules', AsyncMock(return_value=mock_ai_rules)):
                # For _get_potential_targets to return our player
                with patch('src.core.npc_combat_strategy._get_potential_targets', AsyncMock(return_value=[selected_target_info])):
                    # For _select_target to pick that player
                    with patch('src.core.npc_combat_strategy._select_target', AsyncMock(return_value=selected_target_info)):
                        # For _choose_action to pick "quick_stab"
                        with patch('src.core.npc_combat_strategy._choose_action', AsyncMock(return_value=chosen_action_details_from_chooser)):
                            # _format_action_result is simple enough not to mock for this high-level test, or can be mocked too
                            # with patch('src.core.npc_combat_strategy._format_action_result', MagicMock(return_value=expected_formatted_action)):

                            action_result = await get_npc_combat_action(
                                mock_session, mock_actor_npc.guild_id, mock_actor_npc.id, mock_combat_encounter.id
                            )
                            assert action_result == expected_formatted_action

@pytest.mark.asyncio
async def test_get_npc_combat_action_actor_defeated(mock_session, mock_actor_npc, mock_combat_encounter):
    mock_actor_npc_defeated_data = mock_actor_npc

    # Modify combat encounter so actor is defeated
    defeated_actor_combat_data = None
    for p_data in mock_combat_encounter.participants_json:
        if p_data["id"] == mock_actor_npc_defeated_data.id and p_data["type"] == EntityType.NPC.value:
            p_data["hp"] = 0
            defeated_actor_combat_data = p_data
            break

    assert defeated_actor_combat_data is not None and defeated_actor_combat_data["hp"] == 0

    with patch('src.core.npc_combat_strategy._get_npc_data', AsyncMock(return_value=mock_actor_npc_defeated_data)):
        with patch('src.core.npc_combat_strategy._get_combat_encounter_data', AsyncMock(return_value=mock_combat_encounter)):
            action_result = await get_npc_combat_action(
                mock_session, mock_actor_npc_defeated_data.guild_id, mock_actor_npc_defeated_data.id, mock_combat_encounter.id
            )
            assert action_result == {"action_type": "idle", "reason": "Actor is defeated."}

    # Restore HP for other tests if mock_combat_encounter is shared and modified directly
    if defeated_actor_combat_data:
        defeated_actor_combat_data["hp"] = mock_actor_npc.properties_json["stats"]["hp"]


@pytest.mark.asyncio
async def test_get_npc_combat_action_no_targets_available(mock_session, mock_actor_npc, mock_combat_encounter, mock_ai_rules):
    with patch('src.core.npc_combat_strategy._get_npc_data', AsyncMock(return_value=mock_actor_npc)):
        with patch('src.core.npc_combat_strategy._get_combat_encounter_data', AsyncMock(return_value=mock_combat_encounter)):
            # The actual participants_list from mock_combat_encounter would be passed to the original _get_potential_targets
            # but since we are mocking _get_potential_targets itself to return [], we don't need to pass the list to the mock.
            # The original call inside get_npc_combat_action would construct it.
            # The important part is that the mock for _get_potential_targets is what's being tested here.
            with patch('src.core.npc_combat_strategy._get_npc_ai_rules', AsyncMock(return_value=mock_ai_rules)):
                # _get_potential_targets is mocked directly, so its signature change doesn't affect this specific mock setup
                with patch('src.core.npc_combat_strategy._get_potential_targets', AsyncMock(return_value=[])) as mock_get_targets:
                    action_result = await get_npc_combat_action(
                        mock_session, mock_actor_npc.guild_id, mock_actor_npc.id, mock_combat_encounter.id
                    )
                    # We can assert that the mocked _get_potential_targets was called correctly
                    # (though its internal logic is bypassed by the mock's return_value=[])
                    mock_get_targets.assert_called_once()
                    # We'd expect it to be called with session, actor_npc, combat_encounter, ai_rules, guild_id, and the list
                    # For this test, the key is that it returns [] and causes the "No targets available" outcome.
                    assert action_result == {"action_type": "idle", "reason": "No targets available."}

# (Add more comprehensive tests for other functions and edge cases)
