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
        "simulation": { "enabled": False }, # Keep simulation off for most basic tests for simplicity
        "relationship_influence": { # Added section for relationship influence rules
            "npc_combat": {
                "behavior": {
                    "enabled": True,
                    "hostility_threshold_modifier_formula": "-(relationship_value / 10)",
                    "target_score_modifier_formula": "-(relationship_value * 0.2)",
                    "action_choice": {
                        "friendly_positive_threshold": 30, # Lowered for easier testing
                        "hostile_negative_threshold": -30, # Lowered for easier testing
                        "actions_if_friendly": [
                            {"action_type": "ability", "ability_static_id": "self_heal_low", "weight_multiplier": 1.5}, # Prefer healing self
                            {"action_type": "attack", "weight_multiplier": 0.5} # Less likely to attack
                        ],
                        "actions_if_hostile": [
                             {"action_type": "ability", "ability_static_id": "strong_hit", "weight_multiplier": 1.5}, # Prefer strong hit
                             {"action_type": "attack", "weight_multiplier": 1.2}
                        ]
                    }
                }
            }
        }
    }

# --- Tests for _get_npc_ai_rules ---
@pytest.mark.asyncio
async def test_get_npc_ai_rules_merges_defaults_and_specific_relationship_rules(mock_session, mock_actor_npc, mock_combat_encounter):
    # Base rules for npc_default_strategy (will be returned by get_rule for this key)
    base_npc_rules_from_db = {
        "target_selection": {"priority_order": ["lowest_hp_percentage"]},
        "action_selection": {"offensive_bias": 0.6}
    }
    # Specific relationship influence rules for the guild (will be returned by get_rule for its key)
    specific_rel_rules_from_db = {
        "enabled": True,
        "hostility_threshold_modifier_formula": "-(relationship_value / 15)", # Override default
        "action_choice": {
            "friendly_positive_threshold": 40, # Override default
            "actions_if_friendly": [{"action_type": "attack", "weight_multiplier": 0.1}] # Override
        }
    }
    # Expected default relationship rules if specific one is not fully defined (used by _get_npc_ai_rules internally)
    default_rel_influence_rules_in_code = {
        "enabled": True,
        "hostility_threshold_modifier_formula": "-(relationship_value / 10)",
        "target_score_modifier_formula": "-(relationship_value * 0.2)",
        "action_choice": {
            "friendly_positive_threshold": 50, # Default internal to _get_npc_ai_rules
            "hostile_negative_threshold": -50, # Default internal to _get_npc_ai_rules
            "actions_if_friendly": [],
            "actions_if_hostile": []
        }
    }

    async def mock_get_rule_side_effect(db, guild_id, key, default=None):
        if key == "ai_behavior:npc_default_strategy":
            return base_npc_rules_from_db
        if key == "relationship_influence:npc_combat:behavior":
            return specific_rel_rules_from_db
        return default

    with patch('src.core.npc_combat_strategy.get_rule', AsyncMock(side_effect=mock_get_rule_side_effect)):
        compiled_rules = await _get_npc_ai_rules(mock_session, 100, mock_actor_npc, mock_combat_encounter)

    # Check base rules are present
    assert compiled_rules["target_selection"]["priority_order"] == ["lowest_hp_percentage"]
    assert compiled_rules["action_selection"]["offensive_bias"] == 0.6

    # Check relationship influence rules
    rel_behavior = compiled_rules["relationship_influence"]["npc_combat"]["behavior"]
    assert rel_behavior["enabled"] is True
    # Check overridden values from specific_rel_rules_from_db
    assert rel_behavior["hostility_threshold_modifier_formula"] == "-(relationship_value / 15)"
    assert rel_behavior["action_choice"]["friendly_positive_threshold"] == 40
    assert rel_behavior["action_choice"]["actions_if_friendly"] == [{"action_type": "attack", "weight_multiplier": 0.1}]
    # Check values that should come from default_rel_influence_rules_in_code because not overridden by specific_rel_rules_from_db
    assert rel_behavior["target_score_modifier_formula"] == default_rel_influence_rules_in_code["target_score_modifier_formula"]
    assert rel_behavior["action_choice"]["hostile_negative_threshold"] == default_rel_influence_rules_in_code["action_choice"]["hostile_negative_threshold"]
    assert rel_behavior["action_choice"]["actions_if_hostile"] == default_rel_influence_rules_in_code["action_choice"]["actions_if_hostile"]


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

@pytest.mark.asyncio
async def test_is_hostile_relationship_formula_makes_friendly(mock_session, mock_actor_npc, mock_target_player, mock_ai_rules):
    target_player_combat_info = {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 100}
    # Rule: hostility_threshold_modifier_formula: "-(relationship_value / 10)"
    # Base hostile threshold: -20. Base friendly: 20
    # Relationship value: 50 (very friendly)
    # Hostility bias mod = -(50/10) = -5
    # Final hostile threshold = -20 + (-5) = -25
    # Final friendly threshold = 20 - (-5) = 25
    # Since rel_value (50) >= final_friendly_threshold (25), should be False (not hostile)

    # Ensure the specific formula is in ai_rules for this test
    mock_ai_rules_custom = mock_ai_rules.copy() # Avoid modifying fixture for other tests
    mock_ai_rules_custom["relationship_influence"]["npc_combat"]["behavior"]["hostility_threshold_modifier_formula"] = "-(relationship_value / 10)" # Default from fixture
    mock_ai_rules_custom["target_selection"]["hostility_rules"]["relationship_hostile_threshold"] = -20
    mock_ai_rules_custom["target_selection"]["hostility_rules"]["relationship_friendly_threshold"] = 20


    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=50)):
        hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_player_combat_info, mock_target_player, mock_ai_rules_custom)
        assert hostile is False

@pytest.mark.asyncio
async def test_is_hostile_relationship_formula_makes_hostile(mock_session, mock_actor_npc, mock_target_npc_friendly_faction, mock_ai_rules):
    target_npc_combat_info = {"id": mock_target_npc_friendly_faction.id, "type": EntityType.NPC.value, "hp": 30}
    # Same faction, normally friendly. Relationship value: -50 (very hostile)
    # Hostility bias mod = -(-50/10) = 5
    # Final hostile threshold = -20 + 5 = -15
    # Final friendly threshold = 20 - 5 = 15
    # Since rel_value (-50) <= final_hostile_threshold (-15), should be True (hostile)
    mock_ai_rules_custom = mock_ai_rules.copy()
    mock_ai_rules_custom["relationship_influence"]["npc_combat"]["behavior"]["hostility_threshold_modifier_formula"] = "-(relationship_value / 10)"
    mock_ai_rules_custom["target_selection"]["hostility_rules"]["relationship_hostile_threshold"] = -20
    mock_ai_rules_custom["target_selection"]["hostility_rules"]["relationship_friendly_threshold"] = 20
    mock_ai_rules_custom["target_selection"]["hostility_rules"]["same_faction_is_friendly"] = True


    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=-50)):
        hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_npc_combat_info, mock_target_npc_friendly_faction, mock_ai_rules_custom)
        assert hostile is True

# --- Tests for _calculate_target_score ---
@pytest.mark.asyncio
async def test_calculate_target_score_relationship_formula_modifies_threat(mock_session, mock_actor_npc, mock_target_player, mock_ai_rules, mock_combat_encounter):
    target_info = {"entity": mock_target_player, "combat_data": {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 80, "max_hp": 100}}
    metric = "highest_threat_score"

    # Base threat factors: damage_dealt_to_self_factor: 1.5
    # target_score_modifier_formula: "-(relationship_value * 0.2)"
    # Relationship value: 50 (friendly with player)
    # Expected adjustment = -(50 * 0.2) = -10

    # Assume base threat (e.g. from damage) is 30
    target_info["combat_data"]["threat_generated_towards_actor"] = 20 # 20 * 1.5 = 30 base threat

    mock_ai_rules_custom = mock_ai_rules.copy()
    mock_ai_rules_custom["relationship_influence"]["npc_combat"]["behavior"]["target_score_modifier_formula"] = "-(relationship_value * 0.2)"


    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=50)):
        score_friendly = await _calculate_target_score(mock_session, 100, mock_actor_npc, target_info, metric, mock_ai_rules_custom, mock_combat_encounter)

    # Relationship value: -50 (hostile with player)
    # Expected adjustment = -(-50 * 0.2) = +10
    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=-50)):
        score_hostile = await _calculate_target_score(mock_session, 100, mock_actor_npc, target_info, metric, mock_ai_rules_custom, mock_combat_encounter)

    base_threat_calculated = 20 * 1.5 # 30
    expected_score_friendly = base_threat_calculated - (50 * 0.2) # 30 - 10 = 20
    expected_score_hostile = base_threat_calculated - (-50 * 0.2) # 30 + 10 = 40

    assert score_friendly == pytest.approx(expected_score_friendly)
    assert score_hostile == pytest.approx(expected_score_hostile)


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

# --- Tests for _choose_action with relationship influence ---
@pytest.mark.asyncio
async def test_choose_action_relationship_friendly_prefers_non_attack_or_heal(
    mock_session, mock_actor_npc, mock_target_player, mock_ai_rules, mock_combat_encounter
):
    actor_combat_data = {"id": mock_actor_npc.id, "type": EntityType.NPC.value, "hp": 30, "max_hp": 50, "resources": {"mana": 10}, "cooldowns": {}} # HP is at 60%
    target_info = {"entity": mock_target_player, "combat_data": {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 80, "max_hp": 100}}

    # AI rules from fixture:
    # "actions_if_friendly": [
    #     {"action_type": "ability", "ability_static_id": "self_heal_low", "weight_multiplier": 1.5},
    #     {"action_type": "attack", "weight_multiplier": 0.5}
    # ]
    # "friendly_positive_threshold": 30

    # Relationship: 50 (friendly)
    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=50)):
        # Mock _evaluate_action_effectiveness to return predictable scores BEFORE relationship weight.
        # Let's say basic attack normally has higher score than self_heal_low.
        async def mock_eval_effectiveness(session, guild_id, actor_npc_eval, actor_data_eval, target_info_eval, action_details, ai_rules_eval):
            if action_details.get("type") == "attack":
                return 10.0 # Base score for attack
            elif action_details.get("ability_props", {}).get("static_id") == "self_heal_low":
                return 8.0  # Base score for self_heal_low
            elif action_details.get("ability_props", {}).get("static_id") == "strong_hit":
                 return 12.0 # Base score for strong_hit
            elif action_details.get("ability_props", {}).get("static_id") == "quick_stab":
                 return 7.0 # Base score for quick_stab
            return 1.0 # Default for other abilities

        with patch('src.core.npc_combat_strategy._evaluate_action_effectiveness', AsyncMock(side_effect=mock_eval_effectiveness)):
            chosen_action = await _choose_action(mock_session, 100, mock_actor_npc, actor_combat_data, target_info, mock_ai_rules, mock_combat_encounter)

    # Expected scores after relationship weight:
    # Attack: 10.0 * 0.5 = 5.0
    # Self_heal_low: 8.0 * 1.5 = 12.0
    # Strong_hit: 12.0 (no friendly rule, so weight 1.0)
    # Quick_stab: 7.0 (no friendly rule, so weight 1.0)
    # Best action should be self_heal_low due to multiplier if actor HP is not too low.
    # Oh, wait, self_heal_low is self-target. Does _choose_action consider target for self-abilities?
    # _evaluate_action_effectiveness takes target_info. For self-heal, this might be less relevant for damage part.
    # The current _choose_action doesn't explicitly differentiate self-target abilities for relationship modification.
    # The rule applies weight to "self_heal_low". Let's assume it will be preferred.

    # Re-evaluating: The heal threshold rule (self_hp_below_for_heal_ability: 0.4)
    # Actor HP is 30/50 = 0.6, which is NOT below 0.4. So, heal might not be prioritized by that logic.
    # The relationship multiplier for 'self_heal_low' is 1.5.
    # Attack score: 10 * 0.5 = 5
    # Heal score: 8 * 1.5 = 12
    # Strong Hit score: 12 (no multiplier)
    # Quick Stab score: 7 (no multiplier)
    # So, 'strong_hit' should be chosen as 12 is its base score and it's higher than weighted heal if heal isn't forced by low HP.
    # The test for `actions_if_friendly` currently has `self_heal_low`.
    # If the NPC is friendly, it should prefer healing itself (or buffing) over attacking the friendly target.
    # Let's adjust the mock scores for _evaluate_action_effectiveness so that heal becomes best.
    # Say, heal base is 9. Attack base is 10. Strong hit base is 8.
    # Heal weighted: 9 * 1.5 = 13.5
    # Attack weighted: 10 * 0.5 = 5
    # Strong Hit: 8
    # Then Heal should be chosen.

    async def mock_eval_effectiveness_v2(session, guild_id, actor_npc_eval, actor_data_eval, target_info_eval, action_details, ai_rules_eval):
        if action_details.get("type") == "attack": return 10.0
        elif action_details.get("ability_props", {}).get("static_id") == "self_heal_low": return 9.0
        elif action_details.get("ability_props", {}).get("static_id") == "strong_hit": return 8.0
        elif action_details.get("ability_props", {}).get("static_id") == "quick_stab": return 7.0
        return 1.0

    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=50)): # Friendly
        with patch('src.core.npc_combat_strategy._evaluate_action_effectiveness', AsyncMock(side_effect=mock_eval_effectiveness_v2)):
            chosen_action = await _choose_action(mock_session, 100, mock_actor_npc, actor_combat_data, target_info, mock_ai_rules, mock_combat_encounter)

    assert chosen_action.get("ability_props", {}).get("static_id") == "self_heal_low"


@pytest.mark.asyncio
async def test_choose_action_relationship_hostile_prefers_strong_attack(
    mock_session, mock_actor_npc, mock_target_player, mock_ai_rules, mock_combat_encounter
):
    actor_combat_data = {"id": mock_actor_npc.id, "type": EntityType.NPC.value, "hp": 50, "max_hp":50, "resources": {"mana": 10}, "cooldowns": {}}
    target_info = {"entity": mock_target_player, "combat_data": {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 80, "max_hp": 100}}

    # AI rules from fixture:
    # "actions_if_hostile": [
    #     {"action_type": "ability", "ability_static_id": "strong_hit", "weight_multiplier": 1.5},
    #     {"action_type": "attack", "weight_multiplier": 1.2}
    # ]
    # "hostile_negative_threshold": -30

    # Relationship: -50 (hostile)
    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=-50)):
        async def mock_eval_effectiveness(session, guild_id, actor_npc_eval, actor_data_eval, target_info_eval, action_details, ai_rules_eval):
            # Base scores: Strong Hit (10), Attack (9), Quick Stab (8), Heal (7)
            if action_details.get("ability_props", {}).get("static_id") == "strong_hit": return 10.0
            if action_details.get("type") == "attack": return 9.0
            if action_details.get("ability_props", {}).get("static_id") == "quick_stab": return 8.0
            if action_details.get("ability_props", {}).get("static_id") == "self_heal_low": return 7.0
            return 1.0

        with patch('src.core.npc_combat_strategy._evaluate_action_effectiveness', AsyncMock(side_effect=mock_eval_effectiveness)):
            chosen_action = await _choose_action(mock_session, 100, mock_actor_npc, actor_combat_data, target_info, mock_ai_rules, mock_combat_encounter)

    # Expected scores after relationship weight:
    # Strong Hit: 10.0 * 1.5 = 15.0
    # Attack: 9.0 * 1.2 = 10.8
    # Quick Stab: 8.0 (no hostile rule, so weight 1.0)
    # Heal: 7.0 (no hostile rule, so weight 1.0)
    # Best action should be "strong_hit".
    assert chosen_action.get("ability_props", {}).get("static_id") == "strong_hit"


# (Add more comprehensive tests for other functions and edge cases)
