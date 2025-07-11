import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.npc_combat_strategy import (
    _get_npc_ai_rules, _is_hostile, _get_potential_targets,
    _calculate_target_score, _get_available_abilities, _choose_action,
    get_npc_combat_action
)
from backend.models.generated_npc import GeneratedNpc
from backend.models.player import Player
from backend.models.combat_encounter import CombatEncounter
from backend.models.enums import CombatParticipantType as EntityType
from backend.models.relationship import Relationship

class TestNPCCombatStrategy:

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def mock_actor_npc(self) -> GeneratedNpc:
        npc = GeneratedNpc(
            id=1, guild_id=100, name_i18n={"en": "Goblin Warrior"},
            properties_json={
                "stats": {"hp": 50, "mana": 10, "base_attack_damage": 5},
                "abilities": [
                    {"static_id": "strong_hit", "name": "Strong Hit", "cost": {"mana": 5}, "cooldown_turns": 2, "effects": [{"type": "damage", "value": "10"}]},
                    {"static_id": "quick_stab", "name": "Quick Stab", "cost": {"mana": 2}, "cooldown_turns": 0, "effects": [{"type": "damage", "value": "3"}]},
                    {"static_id": "self_heal_low", "name": "Minor Heal", "cost": {"mana": 3}, "cooldown_turns": 3, "effects": [{"type": "heal", "value": "10", "target_scope": "self"}]}
                ], "faction_id": "goblins"
            }, ai_metadata_json={"personality": "aggressive"}
        )
        return npc

    @pytest.fixture
    def mock_target_player(self) -> Player:
        player = Player(id=10, guild_id=100, discord_id=12345, name="HeroPlayer", current_hp=100)
        return player

    @pytest.fixture
    def mock_target_npc_hostile(self) -> GeneratedNpc:
        npc = GeneratedNpc(id=2, guild_id=100, name_i18n={"en": "Bandit"}, properties_json={"stats": {"hp": 40}, "faction_id": "bandits"})
        return npc

    @pytest.fixture
    def mock_target_npc_friendly_faction(self) -> GeneratedNpc:
        npc = GeneratedNpc(id=3, guild_id=100, name_i18n={"en": "Goblin Shaman"}, properties_json={"stats": {"hp": 30}, "faction_id": "goblins"})
        return npc

    @pytest.fixture
    def mock_combat_encounter(self, mock_actor_npc: GeneratedNpc, mock_target_player: Player, mock_target_npc_hostile: GeneratedNpc, mock_target_npc_friendly_faction: GeneratedNpc) -> CombatEncounter:
        actor_props = mock_actor_npc.properties_json if mock_actor_npc.properties_json is not None else {}
        actor_stats = actor_props.get("stats", {}) if isinstance(actor_props, dict) else {}
        actor_max_hp = actor_stats.get("hp", 50) if isinstance(actor_stats, dict) else 50
        player_max_hp = 100
        hostile_npc_props = mock_target_npc_hostile.properties_json if mock_target_npc_hostile.properties_json is not None else {}
        hostile_npc_stats = hostile_npc_props.get("stats", {}) if isinstance(hostile_npc_props, dict) else {}
        hostile_npc_max_hp = hostile_npc_stats.get("hp", 40) if isinstance(hostile_npc_stats, dict) else 40
        friendly_npc_props = mock_target_npc_friendly_faction.properties_json if mock_target_npc_friendly_faction.properties_json is not None else {}
        friendly_npc_stats = friendly_npc_props.get("stats", {}) if isinstance(friendly_npc_props, dict) else {}
        friendly_npc_max_hp = friendly_npc_stats.get("hp", 30) if isinstance(friendly_npc_stats, dict) else 30
        defeated_player_max_hp = 100
        return CombatEncounter(
            id=1, guild_id=100, location_id=1,
            participants_json=[
                {"id": mock_actor_npc.id, "type": EntityType.NPC.value, "current_hp": actor_max_hp, "max_hp": actor_max_hp, "resources": {"mana": 10}, "cooldowns": {}},
                {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "current_hp": 80, "max_hp": player_max_hp},
                {"id": mock_target_npc_hostile.id, "type": EntityType.NPC.value, "current_hp": hostile_npc_max_hp, "max_hp": hostile_npc_max_hp},
                {"id": mock_target_npc_friendly_faction.id, "type": EntityType.NPC.value, "current_hp": friendly_npc_max_hp, "max_hp": friendly_npc_max_hp},
                {"id": 4, "type": EntityType.PLAYER.value, "current_hp": 0, "max_hp": defeated_player_max_hp},
            ], combat_log_json=[], rules_config_snapshot_json={}, turn_order_json={}
        )

    @pytest.fixture
    def mock_ai_rules(self) -> Dict[str, Any]:
        return {
            "target_selection": { "priority_order": ["lowest_hp_percentage", "highest_threat_score"], "hostility_rules": { "default": "attack_players_and_hostile_npcs", "relationship_hostile_threshold": -20, "relationship_friendly_threshold": 20, "same_faction_is_friendly": True }, "threat_factors": {"damage_dealt_to_self_factor": 1.5, "is_healer_factor": 1.2} },
            "action_selection": { "offensive_bias": 0.75, "abilities_priority": [], "resource_thresholds": {"self_hp_below_for_heal_ability": 0.4}, "ability_base_effectiveness_multiplier": 1.1, "status_strategic_value": {"stun": 50, "poison": 20}, "low_hp_heal_urgency_multiplier": 2.0 },
            "simulation": { "enabled": False },
            "relationship_influence": { "npc_combat": { "behavior": { "enabled": True, "hostility_threshold_modifier_formula": "-(relationship_value / 10)", "target_score_modifier_formula": "-(relationship_value * 0.2)", "action_choice": { "friendly_positive_threshold": 30, "hostile_negative_threshold": -30, "actions_if_friendly": [ {"action_type": "ability", "ability_static_id": "self_heal_low", "weight_multiplier": 1.5}, {"action_type": "attack", "weight_multiplier": 0.5} ], "actions_if_hostile": [ {"action_type": "ability", "ability_static_id": "strong_hit", "weight_multiplier": 1.5}, {"action_type": "attack", "weight_multiplier": 1.2} ] } } } }
        }

    @pytest.fixture
    def mock_ai_rules_with_hidden_effects(self, mock_ai_rules: Dict[str, Any], mock_target_player: Player) -> Dict[str, Any]:
        import copy
        rules = copy.deepcopy(mock_ai_rules)
        rules["parsed_hidden_relationship_combat_effects"] = [
            { "rule_data": { "enabled": True, "priority": 100, "hostility_override": { "if_target_matches_relationship": True, "new_hostility_status": "friendly", "condition_formula": "value > 50" }, "target_score_modifier_formula": "value * 0.1", "action_weight_multipliers": [ {"action_category": "attack_strong", "multiplier_formula": "0.1"}, {"action_category": "attack_basic", "multiplier_formula": "0.5"}, {"action_category": "ability_non_damaging", "multiplier_formula": "2.0"} ] }, "applies_to_relationship": { "type": "secret_positive_to_entity", "value": 70, "target_entity_type": EntityType.PLAYER.value, "target_entity_id": mock_target_player.id } }
        ]
        return rules

    @pytest.mark.asyncio
    async def test_get_npc_ai_rules_merges_defaults_and_specific_relationship_rules(self, mock_session, mock_actor_npc, mock_combat_encounter):
        base_npc_rules_from_db = { "target_selection": {"priority_order": ["lowest_hp_percentage"]}, "action_selection": {"offensive_bias": 0.6} }
        specific_rel_rules_from_db = { "enabled": True, "hostility_threshold_modifier_formula": "-(relationship_value / 15)", "action_choice": { "friendly_positive_threshold": 40, "actions_if_friendly": [{"action_type": "attack", "weight_multiplier": 0.1}] } }
        default_rel_influence_rules_in_code = { "enabled": True, "hostility_threshold_modifier_formula": "-(relationship_value / 10)", "target_score_modifier_formula": "-(relationship_value * 0.2)", "action_choice": { "friendly_positive_threshold": 50, "hostile_negative_threshold": -50, "actions_if_friendly": [], "actions_if_hostile": [] } }
        async def mock_get_rule_side_effect(session, guild_id, key, default=None):
            if key == "ai_behavior:npc_default_strategy": return base_npc_rules_from_db
            if key == "relationship_influence:npc_combat:behavior": return specific_rel_rules_from_db
            return default
        with patch('backend.core.npc_combat_strategy.get_rule', AsyncMock(side_effect=mock_get_rule_side_effect)):
            compiled_rules = await _get_npc_ai_rules(mock_session, 100, mock_actor_npc, mock_combat_encounter, actor_hidden_relationships=None)
        assert compiled_rules["target_selection"]["priority_order"] == ["lowest_hp_percentage"]
        assert compiled_rules["action_selection"]["offensive_bias"] == 0.8
        rel_behavior = compiled_rules["relationship_influence"]["npc_combat"]["behavior"]
        assert rel_behavior["enabled"] is True
        assert rel_behavior["hostility_threshold_modifier_formula"] == "-(relationship_value / 15)"
        assert rel_behavior["action_choice"]["friendly_positive_threshold"] == 40
        assert rel_behavior["action_choice"]["actions_if_friendly"] == [{"action_type": "attack", "weight_multiplier": 0.1}]
        assert rel_behavior["target_score_modifier_formula"] == default_rel_influence_rules_in_code["target_score_modifier_formula"]
        assert rel_behavior["action_choice"]["hostile_negative_threshold"] == default_rel_influence_rules_in_code["action_choice"]["hostile_negative_threshold"]
        assert rel_behavior["action_choice"]["actions_if_hostile"] == default_rel_influence_rules_in_code["action_choice"]["actions_if_hostile"]
        assert compiled_rules.get("parsed_hidden_relationship_combat_effects") == []

    @pytest.mark.asyncio
    async def test_get_npc_ai_rules_loads_hidden_relationship_effects(self, mock_session, mock_actor_npc, mock_combat_encounter, mock_target_player):
        hidden_rel_npc_to_player = Relationship(id=1, guild_id=100, entity1_id=mock_actor_npc.id, entity1_type=EntityType.NPC, entity2_id=mock_target_player.id, entity2_type=EntityType.PLAYER, relationship_type="secret_positive_to_entity", value=75)
        actor_hidden_rels = [hidden_rel_npc_to_player]
        rule_for_hidden_secret_positive = { "enabled": True, "priority": 50, "target_score_modifier_formula": "value * 0.3", "hostility_override": {"if_target_matches_relationship": True, "new_hostility_status": "neutral"} }
        async def mock_get_rule_side_effect(session, guild_id, key, default=None):
            if key == "ai_behavior:npc_default_strategy": return {}
            if key == "relationship_influence:npc_combat:behavior": return {}
            if key == f"hidden_relationship_effects:npc_combat:{hidden_rel_npc_to_player.relationship_type}": return rule_for_hidden_secret_positive
            if key == "hidden_relationship_effects:npc_combat:secret_positive_to_entity": return {"enabled": True, "priority":10, "target_score_modifier_formula": "value * 0.1"}
            return default
        with patch('backend.core.npc_combat_strategy.get_rule', AsyncMock(side_effect=mock_get_rule_side_effect)):
            compiled_rules = await _get_npc_ai_rules(mock_session, 100, mock_actor_npc, mock_combat_encounter, actor_hidden_relationships=actor_hidden_rels)
        assert "parsed_hidden_relationship_combat_effects" in compiled_rules
        hidden_effects_list = compiled_rules["parsed_hidden_relationship_combat_effects"]
        assert len(hidden_effects_list) == 1
        effect_entry = hidden_effects_list[0]
        assert isinstance(effect_entry, dict)
        rule_data = effect_entry.get("rule_data")
        applies_to_relationship = effect_entry.get("applies_to_relationship")
        assert rule_data == rule_for_hidden_secret_positive
        assert isinstance(applies_to_relationship, dict)
        if isinstance(applies_to_relationship, dict):
            assert applies_to_relationship.get("type") == "secret_positive_to_entity"
            assert applies_to_relationship.get("value") == 75
            assert applies_to_relationship.get("target_entity_id") == mock_target_player.id
            assert applies_to_relationship.get("target_entity_type") == EntityType.PLAYER.value

    def test_get_available_abilities_all_available(self, mock_actor_npc, mock_ai_rules):
        actor_combat_data = {"resources": {"mana": 10}, "cooldowns": {}}
        abilities = _get_available_abilities(mock_actor_npc, actor_combat_data, mock_ai_rules)
        assert len(abilities) == 3
        assert abilities[0]["static_id"] == "strong_hit"
        assert abilities[1]["static_id"] == "quick_stab"
        assert abilities[2]["static_id"] == "self_heal_low"

    def test_get_available_abilities_not_enough_mana(self, mock_actor_npc, mock_ai_rules):
        actor_combat_data = {"resources": {"mana": 1}, "cooldowns": {}}
        abilities = _get_available_abilities(mock_actor_npc, actor_combat_data, mock_ai_rules)
        assert len(abilities) == 0

    def test_get_available_abilities_one_on_cooldown(self, mock_actor_npc, mock_ai_rules):
        actor_combat_data = {"resources": {"mana": 10}, "cooldowns": {"strong_hit": 1}}
        abilities = _get_available_abilities(mock_actor_npc, actor_combat_data, mock_ai_rules)
        assert len(abilities) == 2
        assert abilities[0]["static_id"] == "quick_stab"
        assert abilities[1]["static_id"] == "self_heal_low"

    def test_get_available_abilities_mana_and_cooldown_mix(self, mock_actor_npc, mock_ai_rules):
        actor_combat_data = {"resources": {"mana": 4}, "cooldowns": {"strong_hit": 1}}
        abilities = _get_available_abilities(mock_actor_npc, actor_combat_data, mock_ai_rules)
        assert len(abilities) == 2
        available_ids = {a["static_id"] for a in abilities}
        assert "quick_stab" in available_ids
        assert "self_heal_low" in available_ids

    @pytest.mark.asyncio
    async def test_is_hostile_player_default_hostile(self, mock_session, mock_actor_npc, mock_target_player, mock_ai_rules):
        target_player_combat_info = {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 100}
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=None)):
            hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_player_combat_info, mock_target_player, mock_ai_rules)
            assert hostile is True

    @pytest.mark.asyncio
    async def test_is_hostile_explicitly_friendly_relationship_player(self, mock_session, mock_actor_npc, mock_target_player, mock_ai_rules):
        target_player_combat_info = {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 100}
        mock_ai_rules["target_selection"]["hostility_rules"]["relationship_friendly_threshold"] = 20
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=25)):
            hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_player_combat_info, mock_target_player, mock_ai_rules)
            assert hostile is False

    @pytest.mark.asyncio
    async def test_is_hostile_explicitly_hostile_relationship_npc(self, mock_session, mock_actor_npc, mock_target_npc_friendly_faction, mock_ai_rules):
        target_npc_combat_info = {"id": mock_target_npc_friendly_faction.id, "type": EntityType.NPC.value, "hp": 30}
        mock_ai_rules["target_selection"]["hostility_rules"]["relationship_hostile_threshold"] = -50
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=-60)):
            hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_npc_combat_info, mock_target_npc_friendly_faction, mock_ai_rules)
            assert hostile is True

    @pytest.mark.asyncio
    async def test_is_hostile_same_faction_npc_friendly_by_default(self, mock_session, mock_actor_npc, mock_target_npc_friendly_faction, mock_ai_rules):
        target_npc_combat_info = {"id": mock_target_npc_friendly_faction.id, "type": EntityType.NPC.value, "hp": 30}
        mock_ai_rules["target_selection"]["hostility_rules"]["same_faction_is_friendly"] = True
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=None)):
            hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_npc_combat_info, mock_target_npc_friendly_faction, mock_ai_rules)
            assert hostile is False

    @pytest.mark.asyncio
    async def test_is_hostile_different_faction_npc_hostile_by_default(self, mock_session, mock_actor_npc, mock_target_npc_hostile, mock_ai_rules):
        target_npc_combat_info = {"id": mock_target_npc_hostile.id, "type": EntityType.NPC.value, "hp": 40}
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=None)):
            hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_npc_combat_info, mock_target_npc_hostile, mock_ai_rules)
            assert hostile is True

    @pytest.mark.asyncio
    async def test_is_hostile_relationship_formula_makes_friendly(self, mock_session, mock_actor_npc, mock_target_player, mock_ai_rules):
        target_player_combat_info = {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 100}
        mock_ai_rules_custom = mock_ai_rules.copy()
        mock_ai_rules_custom["relationship_influence"]["npc_combat"]["behavior"]["hostility_threshold_modifier_formula"] = "-(relationship_value / 10)"
        mock_ai_rules_custom["target_selection"]["hostility_rules"]["relationship_hostile_threshold"] = -20
        mock_ai_rules_custom["target_selection"]["hostility_rules"]["relationship_friendly_threshold"] = 20
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=50)):
            hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_player_combat_info, mock_target_player, mock_ai_rules_custom)
            assert hostile is False

    @pytest.mark.asyncio
    async def test_is_hostile_relationship_formula_makes_hostile(self, mock_session, mock_actor_npc, mock_target_npc_friendly_faction, mock_ai_rules):
        target_npc_combat_info = {"id": mock_target_npc_friendly_faction.id, "type": EntityType.NPC.value, "hp": 30}
        mock_ai_rules_custom = mock_ai_rules.copy()
        mock_ai_rules_custom["relationship_influence"]["npc_combat"]["behavior"]["hostility_threshold_modifier_formula"] = "-(relationship_value / 10)"
        mock_ai_rules_custom["target_selection"]["hostility_rules"]["relationship_hostile_threshold"] = -20
        mock_ai_rules_custom["target_selection"]["hostility_rules"]["relationship_friendly_threshold"] = 20
        mock_ai_rules_custom["target_selection"]["hostility_rules"]["same_faction_is_friendly"] = True
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=-50)):
            hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_npc_combat_info, mock_target_npc_friendly_faction, mock_ai_rules_custom)
            assert hostile is True

    @pytest.mark.asyncio
    async def test_calculate_target_score_relationship_formula_modifies_threat(self, mock_session, mock_actor_npc, mock_target_player, mock_ai_rules, mock_combat_encounter):
        target_info = {"entity": mock_target_player, "combat_data": {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 80, "max_hp": 100}}
        metric = "highest_threat_score"
        target_info["combat_data"]["threat_generated_towards_actor"] = 20
        mock_ai_rules_custom = mock_ai_rules.copy()
        mock_ai_rules_custom["relationship_influence"]["npc_combat"]["behavior"]["target_score_modifier_formula"] = "-(relationship_value * 0.2)"
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=50)):
            score_friendly = await _calculate_target_score(mock_session, 100, mock_actor_npc, target_info, metric, mock_ai_rules_custom, mock_combat_encounter)
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=-50)):
            score_hostile = await _calculate_target_score(mock_session, 100, mock_actor_npc, target_info, metric, mock_ai_rules_custom, mock_combat_encounter)
        base_threat_calculated = 20 * 1.5
        expected_score_friendly = base_threat_calculated - (50 * 0.2)
        expected_score_hostile = base_threat_calculated - (-50 * 0.2)
        assert score_friendly == pytest.approx(expected_score_friendly)
        assert score_hostile == pytest.approx(expected_score_hostile)

    @pytest.mark.asyncio
    async def test_is_hostile_hidden_relationship_override_friendly(self, mock_session, mock_actor_npc, mock_target_player, mock_ai_rules_with_hidden_effects ):
        target_player_combat_info = {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 100}
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=0)):
            hostile = await _is_hostile(mock_session, 100, mock_actor_npc, target_player_combat_info, mock_target_player, mock_ai_rules_with_hidden_effects )
            assert hostile is False

    @pytest.mark.asyncio
    async def test_calculate_target_score_hidden_relationship_modifier(self, mock_session, mock_actor_npc, mock_target_player, mock_ai_rules_with_hidden_effects, mock_combat_encounter):
        target_info = {"entity": mock_target_player, "combat_data": {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 80, "max_hp": 100, "threat_generated_towards_actor": 10}}
        metric = "highest_threat_score"
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=0)):
            score = await _calculate_target_score(mock_session, 100, mock_actor_npc, target_info, metric, mock_ai_rules_with_hidden_effects, mock_combat_encounter)
        expected_base_threat = 10 * mock_ai_rules_with_hidden_effects["target_selection"]["threat_factors"]["damage_dealt_to_self_factor"]
        expected_final_score = expected_base_threat + (70 * 0.1)
        assert score == pytest.approx(expected_final_score)

    @pytest.mark.asyncio
    async def test_choose_action_hidden_relationship_prefers_non_damaging(self, mock_session, mock_actor_npc, mock_target_player, mock_ai_rules_with_hidden_effects, mock_combat_encounter):
        actor_combat_data = {"id": mock_actor_npc.id, "type": EntityType.NPC.value, "hp": 50, "max_hp":50, "resources": {"mana": 10}, "cooldowns": {}}
        target_info = {"entity": mock_target_player, "combat_data": {"id": mock_target_player.id, "type": EntityType.PLAYER.value, "hp": 80, "max_hp": 100}}
        mock_actor_npc.properties_json["abilities"].append( {"static_id": "tactical_buff", "name": "Tactical Buff", "cost": {"mana": 1}, "cooldown_turns": 0, "effects": [{"type": "buff", "target_scope":"self"}], "category": "ability_non_damaging"} )
        async def mock_eval_effectiveness(session, guild_id, actor_npc_eval, actor_data_eval, target_info_eval, action_details, ai_rules_eval):
            if action_details.get("ability_props", {}).get("static_id") == "strong_hit": return 12.0
            if action_details.get("type") == "attack": return 10.0
            if action_details.get("ability_props", {}).get("static_id") == "tactical_buff": return 8.0
            return 1.0
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=0)):
            with patch('backend.core.npc_combat_strategy._evaluate_action_effectiveness', AsyncMock(side_effect=mock_eval_effectiveness)):
                chosen_action = await _choose_action( mock_session, 100, mock_actor_npc, actor_combat_data, target_info, mock_ai_rules_with_hidden_effects, mock_combat_encounter)
        assert chosen_action.get("ability_props", {}).get("static_id") == "tactical_buff"
        mock_actor_npc.properties_json["abilities"].pop()

    @pytest.mark.asyncio
    async def test_get_potential_targets_basic(self, mock_session, mock_actor_npc, mock_combat_encounter, mock_ai_rules, mock_target_player, mock_target_npc_hostile, mock_target_npc_friendly_faction ):
        async def mock_get_entity_side_effect(session, p_info_dict: Dict[str, Any], guild_id): # Renamed and typed p_info
            if p_info_dict.get("id") == mock_target_player.id: return mock_target_player
            if p_info_dict.get("id") == mock_target_npc_hostile.id: return mock_target_npc_hostile
            if p_info_dict.get("id") == mock_target_npc_friendly_faction.id: return mock_target_npc_friendly_faction
            if p_info_dict.get("id") == 4 : return Player(id=4, guild_id=100, name="Defeated", properties_json={"stats":{"hp":100}})
            return None
        async def mock_is_hostile_side_effect(sess, gid, actor, p_info_dict: Dict[str, Any], p_entity, rules): # Renamed and typed p_info
            if p_info_dict.get("id") == mock_target_player.id: return True
            if p_info_dict.get("id") == mock_target_npc_hostile.id: return True
            if p_info_dict.get("id") == mock_target_npc_friendly_faction.id: return False
            return False
        with patch('backend.core.npc_combat_strategy._get_participant_entity', AsyncMock(side_effect=mock_get_entity_side_effect)):
            with patch('backend.core.npc_combat_strategy._is_hostile', AsyncMock(side_effect=mock_is_hostile_side_effect)):
                participants_list_for_test = mock_combat_encounter.participants_json
                # Ensure participants_list_for_test is a list before passing
                if not isinstance(participants_list_for_test, list):
                    participants_list_for_test = []

                targets = await _get_potential_targets( mock_session, mock_actor_npc, mock_combat_encounter, mock_ai_rules, 100, participants_list_for_test )
                assert len(targets) == 2
                # Corrected: t["entity"] is an object, access its id attribute
                target_ids = {t["entity"].id for t in targets}
                assert mock_target_player.id in target_ids
                assert mock_target_npc_hostile.id in target_ids
                assert mock_target_npc_friendly_faction.id not in target_ids
                # Corrected: t["entity"] is an object
                player_target_entry = next(t for t in targets if t["entity"].id == mock_target_player.id)
                assert player_target_entry["combat_data"]["current_hp"] == 80

    @pytest.mark.asyncio
    async def test_get_npc_combat_action_chooses_attack_on_player(self, mock_session, mock_actor_npc, mock_combat_encounter, mock_ai_rules, mock_target_player ):
        mock_loaded_npc = mock_actor_npc
        mock_loaded_combat_encounter = mock_combat_encounter
        participants_list = mock_loaded_combat_encounter.participants_json
        if not isinstance(participants_list, list): participants_list = []
        actor_combat_data = next((p for p in participants_list if p.get("id") == mock_loaded_npc.id and p.get("type") == EntityType.NPC.value), None)
        assert actor_combat_data is not None
        target_player_combat_data = next((p for p in participants_list if p.get("id") == mock_target_player.id), None)
        assert target_player_combat_data is not None
        selected_target_info = { "entity": mock_target_player, "combat_data": target_player_combat_data }
        actor_properties = mock_actor_npc.properties_json
        actor_abilities = actor_properties.get("abilities") if isinstance(actor_properties, dict) and isinstance(actor_properties.get("abilities"), list) else []
        quick_stab_ability_props = next((a for a in actor_abilities if isinstance(a, dict) and a.get("static_id") == "quick_stab"), None)
        assert quick_stab_ability_props is not None
        chosen_action_details_from_chooser = { "type": "ability", "name": "Quick Stab", "ability_props": quick_stab_ability_props }
        expected_formatted_action = { "action_type": "ability", "target_id": mock_target_player.id, "target_type": EntityType.PLAYER.value, "ability_id": "quick_stab" }
        with patch('backend.core.npc_combat_strategy._get_npc_data', AsyncMock(return_value=mock_loaded_npc)):
            with patch('backend.core.npc_combat_strategy._get_combat_encounter_data', AsyncMock(return_value=mock_loaded_combat_encounter)):
                with patch('backend.core.npc_combat_strategy.crud_relationship.get_relationships_for_entity', AsyncMock(return_value=[])):
                    with patch('backend.core.npc_combat_strategy._get_npc_ai_rules', AsyncMock(return_value=mock_ai_rules)):
                        with patch('backend.core.npc_combat_strategy._get_potential_targets', AsyncMock(return_value=[selected_target_info])):
                            with patch('backend.core.npc_combat_strategy._select_target', AsyncMock(return_value=selected_target_info)):
                                with patch('backend.core.npc_combat_strategy._choose_action', AsyncMock(return_value=chosen_action_details_from_chooser)):
                                    action_result = await get_npc_combat_action( mock_session, mock_actor_npc.guild_id if mock_actor_npc.guild_id is not None else -1, mock_actor_npc.id if mock_actor_npc.id is not None else -1, mock_combat_encounter.id if mock_combat_encounter.id is not None else -1 )
                                    assert mock_target_player.id is not None
                                    assert action_result.get("action_type") == expected_formatted_action.get("action_type")
                                    assert action_result.get("target_id") == expected_formatted_action.get("target_id")
                                    assert action_result.get("target_type") == expected_formatted_action.get("target_type")
                                    assert action_result.get("ability_id") == expected_formatted_action.get("ability_id")

    @pytest.mark.asyncio
    async def test_get_npc_combat_action_actor_defeated(self, mock_session, mock_actor_npc, mock_combat_encounter):
        mock_actor_npc_defeated_data = mock_actor_npc
        defeated_actor_combat_data = None
        participants_list_for_setup = mock_combat_encounter.participants_json
        if not isinstance(participants_list_for_setup, list): participants_list_for_setup = []
        for p_data in participants_list_for_setup:
            if isinstance(p_data, dict) and p_data.get("id") == getattr(mock_actor_npc_defeated_data, 'id', -1) and p_data.get("type") == EntityType.NPC.value:
                p_data["current_hp"] = 0
                defeated_actor_combat_data = p_data
                break
        assert defeated_actor_combat_data is not None and defeated_actor_combat_data.get("current_hp") == 0
        with patch('backend.core.npc_combat_strategy._get_npc_data', AsyncMock(return_value=mock_actor_npc_defeated_data)):
            with patch('backend.core.npc_combat_strategy._get_combat_encounter_data', AsyncMock(return_value=mock_combat_encounter)):
                with patch('backend.core.npc_combat_strategy.crud_relationship.get_relationships_for_entity', AsyncMock(return_value=[])):
                    action_result = await get_npc_combat_action( mock_session, mock_actor_npc_defeated_data.guild_id if mock_actor_npc_defeated_data.guild_id is not None else -1, mock_actor_npc_defeated_data.id if mock_actor_npc_defeated_data.id is not None else -1, mock_combat_encounter.id if mock_combat_encounter.id is not None else -1 )
                    assert action_result == {"action_type": "idle", "reason": "Actor is defeated."}
        if defeated_actor_combat_data:
            actor_properties = mock_actor_npc.properties_json
            actor_max_hp = actor_properties.get("stats", {}).get("hp", 50) if isinstance(actor_properties, dict) else 50
            defeated_actor_combat_data["current_hp"] = actor_max_hp

    @pytest.mark.asyncio
    async def test_get_npc_combat_action_no_targets_available(self, mock_session, mock_actor_npc, mock_combat_encounter, mock_ai_rules):
        with patch('backend.core.npc_combat_strategy._get_npc_data', AsyncMock(return_value=mock_actor_npc)):
            with patch('backend.core.npc_combat_strategy._get_combat_encounter_data', AsyncMock(return_value=mock_combat_encounter)):
                with patch('backend.core.npc_combat_strategy.crud_relationship.get_relationships_for_entity', AsyncMock(return_value=[])):
                    with patch('backend.core.npc_combat_strategy._get_npc_ai_rules', AsyncMock(return_value=mock_ai_rules)):
                        with patch('backend.core.npc_combat_strategy._get_potential_targets', AsyncMock(return_value=[])) as mock_get_targets:
                            action_result = await get_npc_combat_action( mock_session, mock_actor_npc.guild_id if mock_actor_npc.guild_id is not None else -1, mock_actor_npc.id if mock_actor_npc.id is not None else -1, mock_combat_encounter.id if mock_combat_encounter.id is not None else -1 )
                            mock_get_targets.assert_called_once()
                            assert action_result == {"action_type": "idle", "reason": "No targets available."}

    @pytest.mark.asyncio
    async def test_choose_action_relationship_friendly_prefers_non_attack_or_heal(self, mock_session, mock_actor_npc, mock_target_player, mock_ai_rules, mock_combat_encounter ):
        actor_combat_data = {"id": mock_actor_npc.id if mock_actor_npc.id is not None else -1, "type": EntityType.NPC.value, "hp": 30, "max_hp": 50, "resources": {"mana": 10}, "cooldowns": {}}
        target_info_combat_data = {"id": mock_target_player.id if mock_target_player.id is not None else -1, "type": EntityType.PLAYER.value, "hp": 80, "max_hp": 100}
        target_info = {"entity": mock_target_player, "combat_data": target_info_combat_data }
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=50)):
            async def mock_eval_effectiveness_v2(session, guild_id, actor_npc_eval, actor_data_eval, target_info_eval, action_details, ai_rules_eval):
                if action_details.get("type") == "attack": return 10.0
                elif action_details.get("ability_props", {}).get("static_id") == "self_heal_low": return 9.0
                elif action_details.get("ability_props", {}).get("static_id") == "strong_hit": return 8.0
                elif action_details.get("ability_props", {}).get("static_id") == "quick_stab": return 7.0
                return 1.0
            with patch('backend.core.npc_combat_strategy._evaluate_action_effectiveness', AsyncMock(side_effect=mock_eval_effectiveness_v2)):
                chosen_action = await _choose_action(mock_session, 100, mock_actor_npc, actor_combat_data, target_info, mock_ai_rules, mock_combat_encounter)
        assert chosen_action.get("ability_props", {}).get("static_id") == "self_heal_low"

    @pytest.mark.asyncio
    async def test_choose_action_relationship_hostile_prefers_strong_attack(self, mock_session, mock_actor_npc, mock_target_player, mock_ai_rules, mock_combat_encounter ):
        actor_combat_data = {"id": mock_actor_npc.id if mock_actor_npc.id is not None else -1, "type": EntityType.NPC.value, "hp": 50, "max_hp":50, "resources": {"mana": 10}, "cooldowns": {}}
        target_info_combat_data = {"id": mock_target_player.id if mock_target_player.id is not None else -1, "type": EntityType.PLAYER.value, "hp": 80, "max_hp": 100}
        target_info = {"entity": mock_target_player, "combat_data": target_info_combat_data}
        with patch('backend.core.npc_combat_strategy._get_relationship_value', AsyncMock(return_value=-50)):
            async def mock_eval_effectiveness(session, guild_id, actor_npc_eval, actor_data_eval, target_info_eval, action_details, ai_rules_eval):
                if action_details.get("ability_props", {}).get("static_id") == "strong_hit": return 10.0
                if action_details.get("type") == "attack": return 9.0
                if action_details.get("ability_props", {}).get("static_id") == "quick_stab": return 8.0
                if action_details.get("ability_props", {}).get("static_id") == "self_heal_low": return 7.0
                return 1.0
            with patch('backend.core.npc_combat_strategy._evaluate_action_effectiveness', AsyncMock(side_effect=mock_eval_effectiveness)):
                chosen_action = await _choose_action(mock_session, 100, mock_actor_npc, actor_combat_data, target_info, mock_ai_rules, mock_combat_encounter)
        assert chosen_action.get("ability_props", {}).get("static_id") == "strong_hit"
