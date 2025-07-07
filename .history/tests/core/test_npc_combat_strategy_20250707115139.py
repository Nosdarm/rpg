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
def mock_combat_encounter(
    mock_actor_npc: GeneratedNpc,
    mock_target_player: Player,
    mock_target_npc_hostile: GeneratedNpc,
    mock_target_npc_friendly_faction: GeneratedNpc
) -> CombatEncounter:
    # Max HP values from individual fixtures or sensible defaults for combat data
    actor_props = mock_actor_npc.properties_json if mock_actor_npc.properties_json is not None else {}
    actor_stats = actor_props.get("stats", {}) if isinstance(actor_props, dict) else {}
    actor_max_hp = actor_stats.get("hp", 50) if isinstance(actor_stats, dict) else 50

    player_max_hp = 100 # As per mock_target_player.current_hp and general assumption

    hostile_npc_props = mock_target_npc_hostile.properties_json if mock_target_npc_hostile.properties_json is not None else {}
    hostile_npc_stats = hostile_npc_props.get("stats", {}) if isinstance(hostile_npc_props, dict) else {}
    hostile_npc_max_hp = hostile_npc_stats.get("hp", 40) if isinstance(hostile_npc_stats, dict) else 40

    friendly_npc_props = mock_target_npc_friendly_faction.properties_json if mock_target_npc_friendly_faction.properties_json is not None else {}
    friendly_npc_stats = friendly_npc_props.get("stats", {}) if isinstance(friendly_npc_props, dict) else {}
    friendly_npc_max_hp = friendly_npc_stats.get("hp", 30) if isinstance(friendly_npc_stats, dict) else 30

    defeated_player_max_hp = 100 # Arbitrary typical max HP for a defeated player

    return CombatEncounter(
        id=1,
        guild_id=100,
        location_id=1,
        participants_json=[
            {"id": mock_actor_npc.id, "type": EntityType.NPC.value, "current_hp": actor_max_hp, "max_hp": actor_max_hp, "resources": {"mana": 10}, "cooldowns": {}},
            {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "current_hp": 80, "max_hp": player_max_hp}, # Player target, current_hp can differ from max_hp
            {"id": mock_target_npc_hostile.id, "type": EntityType.NPC.value, "current_hp": hostile_npc_max_hp, "max_hp": hostile_npc_max_hp},
            {"id": mock_target_npc_friendly_faction.id, "type": EntityType.NPC.value, "current_hp": friendly_npc_max_hp, "max_hp": friendly_npc_max_hp},
            {"id": 4, "type": EntityType.PLAYER.value, "current_hp": 0, "max_hp": defeated_player_max_hp}, # Defeated player
        ],
        combat_log_json=[],
        rules_config_snapshot_json={},
        turn_order_json={}
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

@pytest.fixture
def mock_ai_rules_with_hidden_effects(mock_ai_rules: Dict[str, Any], mock_target_player: Player) -> Dict[str, Any]:
    """Extends mock_ai_rules with a sample hidden relationship effect."""
    # Make a deep copy to avoid modifying the original fixture for other tests
    import copy
    rules = copy.deepcopy(mock_ai_rules)

    rules["parsed_hidden_relationship_combat_effects"] = [
        {
            "rule_data": { # This is what would be loaded from RuleConfig
                "enabled": True, "priority": 100, # High priority
                "hostility_override": {
                    "if_target_matches_relationship": True,
                    "new_hostility_status": "friendly", # Make NPC friendly to target of this secret positive rel
                    "condition_formula": "value > 50" # If secret positive value is > 50
                },
                "target_score_modifier_formula": "value * 0.1", # Corrected: Formula should be for adjustment, not new total
                "action_weight_multipliers": [
                    {"action_category": "attack_strong", "multiplier_formula": "0.1"}, # Drastically reduce strong attacks
                    {"action_category": "attack_basic", "multiplier_formula": "0.5"}, # Reduce basic attacks
                    {"action_category": "ability_non_damaging", "multiplier_formula": "2.0"} # Prefer non-damaging abilities
                ]
            },
            "applies_to_relationship": { # This part is constructed by _get_npc_ai_rules based on actual NPC relationships
                "type": "secret_positive_to_entity", # The type of hidden relationship this rule was found for
                "value": 70, # The value of that relationship
                "target_entity_type": EntityType.PLAYER.value, # Target of the relationship is Player
                "target_entity_id": mock_target_player.id # Specifically this player
            }
        }
    ]
    return rules


# --- Tests for _get_npc_ai_rules ---
@pytest.mark.asyncio
async def test_get_npc_ai_rules_merges_defaults_and_specific_relationship_rules(mock_session, mock_actor_npc, mock_combat_encounter):
    base_npc_rules_from_db = {
        "target_selection": {"priority_order": ["lowest_hp_percentage"]},
        "action_selection": {"offensive_bias": 0.6}
    }
    specific_rel_rules_from_db = {
        "enabled": True,
        "hostility_threshold_modifier_formula": "-(relationship_value / 15)",
        "action_choice": {
            "friendly_positive_threshold": 40,
            "actions_if_friendly": [{"action_type": "attack", "weight_multiplier": 0.1}]
        }
    }
    default_rel_influence_rules_in_code = {
        "enabled": True, "hostility_threshold_modifier_formula": "-(relationship_value / 10)",
        "target_score_modifier_formula": "-(relationship_value * 0.2)",
        "action_choice": {
            "friendly_positive_threshold": 50, "hostile_negative_threshold": -50,
            "actions_if_friendly": [], "actions_if_hostile": []
        }
    }

    async def mock_get_rule_side_effect(session, guild_id, key, default=None): # Changed db to session
        if key == "ai_behavior:npc_default_strategy": return base_npc_rules_from_db
        if key == "relationship_influence:npc_combat:behavior": return specific_rel_rules_from_db
        # For hidden relationship tests, this mock will need to return those rules too
        return default

    with patch('src.core.npc_combat_strategy.get_rule', AsyncMock(side_effect=mock_get_rule_side_effect)):
        # Test without hidden relationships first
        compiled_rules = await _get_npc_ai_rules(mock_session, 100, mock_actor_npc, mock_combat_encounter, actor_hidden_relationships=None)

    assert compiled_rules["target_selection"]["priority_order"] == ["lowest_hp_percentage"]
    # Personality "aggressive" (from mock_actor_npc) adds 0.2 to offensive_bias.
    # Base rule from base_npc_rules_from_db.action_selection.offensive_bias is 0.6.
    # So, expected is 0.6 + 0.2 = 0.8.
    assert compiled_rules["action_selection"]["offensive_bias"] == 0.8
    rel_behavior = compiled_rules["relationship_influence"]["npc_combat"]["behavior"]
    assert rel_behavior["enabled"] is True
    assert rel_behavior["hostility_threshold_modifier_formula"] == "-(relationship_value / 15)"
    assert rel_behavior["action_choice"]["friendly_positive_threshold"] == 40
    assert rel_behavior["action_choice"]["actions_if_friendly"] == [{"action_type": "attack", "weight_multiplier": 0.1}]
    assert rel_behavior["target_score_modifier_formula"] == default_rel_influence_rules_in_code["target_score_modifier_formula"]
    assert rel_behavior["action_choice"]["hostile_negative_threshold"] == default_rel_influence_rules_in_code["action_choice"]["hostile_negative_threshold"]
    assert rel_behavior["action_choice"]["actions_if_hostile"] == default_rel_influence_rules_in_code["action_choice"]["actions_if_hostile"]
    # Check that parsed_hidden_relationship_combat_effects is an empty list when no hidden relationships are passed
    assert compiled_rules.get("parsed_hidden_relationship_combat_effects") == []


@pytest.mark.asyncio
async def test_get_npc_ai_rules_loads_hidden_relationship_effects(mock_session, mock_actor_npc, mock_combat_encounter, mock_target_player):
    from src.models.relationship import Relationship # For creating mock Relationship objects

    hidden_rel_npc_to_player = Relationship(
        id=1, guild_id=100,
        entity1_id=mock_actor_npc.id, entity1_type=EntityType.NPC,
        entity2_id=mock_target_player.id, entity2_type=EntityType.PLAYER,
        relationship_type="secret_positive_to_entity", value=75
    )
    actor_hidden_rels = [hidden_rel_npc_to_player]

    # RuleConfig for this hidden relationship type
    rule_for_hidden_secret_positive = {
        "enabled": True, "priority": 50,
        "target_score_modifier_formula": "value * 0.3", # Example effect
        "hostility_override": {"if_target_matches_relationship": True, "new_hostility_status": "neutral"}
    }

    async def mock_get_rule_side_effect(session, guild_id, key, default=None): # Changed db to session
        if key == "ai_behavior:npc_default_strategy": return {} # Minimal base
        if key == "relationship_influence:npc_combat:behavior": return {} # Minimal standard rel influence
        if key == f"hidden_relationship_effects:npc_combat:{hidden_rel_npc_to_player.relationship_type}":
            return rule_for_hidden_secret_positive
        # Generic rule for "secret_positive_to_entity" (if specific above not found or for broader match)
        if key == "hidden_relationship_effects:npc_combat:secret_positive_to_entity": # Base type
             return {"enabled": True, "priority":10, "target_score_modifier_formula": "value * 0.1"} # A less specific rule
        return default

    with patch('src.core.npc_combat_strategy.get_rule', AsyncMock(side_effect=mock_get_rule_side_effect)):
        # Pass the hidden relationships to _get_npc_ai_rules
        compiled_rules = await _get_npc_ai_rules(
            mock_session, 100, mock_actor_npc, mock_combat_encounter,
            actor_hidden_relationships=actor_hidden_rels
        )

    assert "parsed_hidden_relationship_combat_effects" in compiled_rules
    hidden_effects_list = compiled_rules["parsed_hidden_relationship_combat_effects"]
    assert len(hidden_effects_list) == 1

    effect_entry = hidden_effects_list[0]
    assert isinstance(effect_entry, dict), "Effect entry should be a dictionary"

    rule_data = effect_entry.get("rule_data")
    applies_to_relationship = effect_entry.get("applies_to_relationship")

    assert rule_data == rule_for_hidden_secret_positive # Exact rule should be chosen

    assert isinstance(applies_to_relationship, dict), "applies_to_relationship should be a dictionary"
    if isinstance(applies_to_relationship, dict): # Guard for Pyright
        assert applies_to_relationship.get("type") == "secret_positive_to_entity"
        assert applies_to_relationship.get("value") == 75
        assert applies_to_relationship.get("target_entity_id") == mock_target_player.id
        assert applies_to_relationship.get("target_entity_type") == EntityType.PLAYER.value


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

@pytest.mark.asyncio
async def test_is_hostile_hidden_relationship_override_friendly(
    mock_session, mock_actor_npc, mock_target_player, mock_ai_rules_with_hidden_effects # Use fixture with hidden effects
):
    target_player_combat_info = {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 100}
    # mock_ai_rules_with_hidden_effects has a rule for "secret_positive_to_entity" with value 70
    # and hostility_override to "friendly" if value > 50.
    # This should make the NPC friendly to mock_target_player.

    # _is_hostile first checks standard relationships. Assume none or neutral.
    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=0)): # Neutral standard relationship
        hostile = await _is_hostile(
            mock_session, 100, mock_actor_npc,
            target_player_combat_info, mock_target_player,
            mock_ai_rules_with_hidden_effects # Pass rules with pre-parsed hidden effects
        )
        assert hostile is False # Hidden relationship makes it friendly

@pytest.mark.asyncio
async def test_calculate_target_score_hidden_relationship_modifier(
    mock_session, mock_actor_npc, mock_target_player, mock_ai_rules_with_hidden_effects, mock_combat_encounter
):
    target_info = {"entity": mock_target_player, "combat_data": {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 80, "max_hp": 100, "threat_generated_towards_actor": 10}}
    metric = "highest_threat_score"

    # Standard relationship influence: target_score_modifier_formula: "-(relationship_value * 0.2)"
    # Hidden relationship influence: target_score_modifier_formula: "current_score + (value * 0.1)"
    # Hidden rel value is 70.
    # Standard rel value (mocked for _get_relationship_value): 0 (neutral)

    # Base threat from damage: 10 * 1.5 (threat_factor) = 15
    # Standard rel mod: -(0 * 0.2) = 0
    # Current score before hidden = 15
    # Hidden rel mod: 15 + (70 * 0.1) = 15 + 7 = 22. So, final score should be 22.

    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=0)): # Neutral standard relationship
        score = await _calculate_target_score(
            mock_session, 100, mock_actor_npc, target_info, metric,
            mock_ai_rules_with_hidden_effects, mock_combat_encounter
        )

    expected_base_threat = 10 * mock_ai_rules_with_hidden_effects["target_selection"]["threat_factors"]["damage_dealt_to_self_factor"] # 10 * 1.5 = 15
    expected_final_score = expected_base_threat + (70 * 0.1) # 15 + 7 = 22
    assert score == pytest.approx(expected_final_score)


@pytest.mark.asyncio
async def test_choose_action_hidden_relationship_prefers_non_damaging(
    mock_session, mock_actor_npc, mock_target_player, mock_ai_rules_with_hidden_effects, mock_combat_encounter
):
    actor_combat_data = {"id": mock_actor_npc.id, "type": EntityType.NPC.value, "hp": 50, "max_hp":50, "resources": {"mana": 10}, "cooldowns": {}}
    target_info = {"entity": mock_target_player, "combat_data": {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 80, "max_hp": 100}}

    # mock_ai_rules_with_hidden_effects has:
    # "action_weight_multipliers": [
    #     {"action_category": "attack_strong", "multiplier_formula": "0.1"},
    #     {"action_category": "attack_basic", "multiplier_formula": "0.5"},
    #     {"action_category": "ability_non_damaging", "multiplier_formula": "2.0"}
    # ]
    # And applies to relationship with mock_target_player (value 70)

    # Add a non-damaging ability to mock_actor_npc for this test
    mock_actor_npc.properties_json["abilities"].append(
        {"static_id": "tactical_buff", "name": "Tactical Buff", "cost": {"mana": 1}, "cooldown_turns": 0,
         "effects": [{"type": "buff", "target_scope":"self"}], "category": "ability_non_damaging"} # Added category
    )

    async def mock_eval_effectiveness(session, guild_id, actor_npc_eval, actor_data_eval, target_info_eval, action_details, ai_rules_eval):
        # Base scores: Strong Hit (12), Attack (10), Tactical Buff (8)
        if action_details.get("ability_props", {}).get("static_id") == "strong_hit": return 12.0
        if action_details.get("type") == "attack": return 10.0 # Category: attack_basic
        if action_details.get("ability_props", {}).get("static_id") == "tactical_buff": return 8.0 # Category: ability_non_damaging
        return 1.0

    # Standard relationship is neutral for this test (to isolate hidden effect)
    with patch('src.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=0)):
        with patch('src.core.npc_combat_strategy._evaluate_action_effectiveness', AsyncMock(side_effect=mock_eval_effectiveness)):
            chosen_action = await _choose_action(
                mock_session, 100, mock_actor_npc, actor_combat_data, target_info,
                mock_ai_rules_with_hidden_effects, mock_combat_encounter
            )

    # Expected scores after hidden relationship weight (value=70):
    # Strong Hit (cat: attack_strong): 12.0 * 0.1 = 1.2
    # Attack (cat: attack_basic): 10.0 * 0.5 = 5.0
    # Tactical Buff (cat: ability_non_damaging): 8.0 * 2.0 = 16.0
    # Best should be Tactical Buff.
    assert chosen_action.get("ability_props", {}).get("static_id") == "tactical_buff"

    # Clean up added ability from fixture for other tests
    mock_actor_npc.properties_json["abilities"].pop()


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
            assert player_target_entry["combat_data"]["current_hp"] == 80 # HP from combat_encounter.participants_json


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
            with patch('src.core.npc_combat_strategy.crud_relationship.get_relationships_for_entity', AsyncMock(return_value=[])) as mock_get_relationships:
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
    # Ensure participants_json is treated as a list, which it is from the fixture
    participants_list_for_setup = mock_combat_encounter.participants_json
    if not isinstance(participants_list_for_setup, list): # Should not happen with current fixture
        participants_list_for_setup = []


    for p_data in participants_list_for_setup: # mock_combat_encounter.participants_json:
        # Pyright errors on these lines seem to be misinterpretations.
        # p_data is a dict, so .get() is fine.
        # The __getitem__ error for GeneratedNpc/Player on this line is also likely confusion.
<<<<<<< HEAD
        if p_data.get("id") == mock_actor_npc_defeated_data.id and p_data.get("type") == EntityType.NPC.value: # type: ignore[attr-defined]
=======
        if p_data.get("id") == mock_actor_npc_defeated_data.id and p_data.get("type") == EntityType.NPC.value: # Line 626
>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
            p_data["current_hp"] = 0
            defeated_actor_combat_data = p_data
            break

    assert defeated_actor_combat_data is not None and defeated_actor_combat_data.get("current_hp") == 0

    with patch('src.core.npc_combat_strategy._get_npc_data', AsyncMock(return_value=mock_actor_npc_defeated_data)):
        with patch('src.core.npc_combat_strategy._get_combat_encounter_data', AsyncMock(return_value=mock_combat_encounter)):
            with patch('src.core.npc_combat_strategy.crud_relationship.get_relationships_for_entity', AsyncMock(return_value=[])) as mock_get_relationships:
                action_result = await get_npc_combat_action(
<<<<<<< HEAD
                    mock_session, mock_actor_npc_defeated_data.guild_id, mock_actor_npc_defeated_data.id, mock_combat_encounter.id # type: ignore[attr-defined]
=======
                    mock_session, mock_actor_npc_defeated_data.guild_id, mock_actor_npc_defeated_data.id, mock_combat_encounter.id # Line 632 / 633
>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
                )
                assert action_result == {"action_type": "idle", "reason": "Actor is defeated."}

    # Restore HP for other tests if mock_combat_encounter is shared and modified directly
    if defeated_actor_combat_data:
        actor_max_hp = mock_actor_npc.properties_json.get("stats", {}).get("hp", 50)
        defeated_actor_combat_data["current_hp"] = actor_max_hp # Use current_hp and actual max_hp


@pytest.mark.asyncio
async def test_get_npc_combat_action_no_targets_available(mock_session, mock_actor_npc, mock_combat_encounter, mock_ai_rules):
    with patch('src.core.npc_combat_strategy._get_npc_data', AsyncMock(return_value=mock_actor_npc)):
        with patch('src.core.npc_combat_strategy._get_combat_encounter_data', AsyncMock(return_value=mock_combat_encounter)):
            with patch('src.core.npc_combat_strategy.crud_relationship.get_relationships_for_entity', AsyncMock(return_value=[])) as mock_get_relationships:
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
