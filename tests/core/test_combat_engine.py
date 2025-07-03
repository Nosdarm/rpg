import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock, call
from typing import Any, Dict, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

# Imports from SUT (System Under Test)
from src.core.combat_engine import process_combat_action
from src.models.combat_outcomes import CombatActionResult
from src.models.combat_encounter import CombatEncounter
from src.models.player import Player
from src.models.generated_npc import GeneratedNpc
from src.models.enums import RelationshipEntityType, CombatStatus, EventType
from src.models.check_results import CheckResult, CheckOutcome, ModifierDetail
from src.core.check_resolver import CheckError


# --- Fixtures ---
@pytest_asyncio.fixture
async def mock_session_fixture():
    session = AsyncMock(spec=AsyncSession)
    return session

@pytest.fixture
def player_actor_fixture():
    player = Player(id=1, guild_id=100, name="Hero Player", current_hp=50, level=5)
    return player

@pytest.fixture
def npc_target_fixture():
    npc = GeneratedNpc(
        id=2,
        guild_id=100,
        name_i18n={"en": "Goblin Target"},
        properties_json={
            "stats": {"dexterity": 12, "strength": 10}
        }
    )
    return npc

@pytest.fixture
def combat_encounter_fixture_factory():
    def _factory(player_fixture: Player, npc_fixture: GeneratedNpc, participants_override=None, snapshot_override=None):
        default_player_participant = {
            "id": player_fixture.id, "type": "player", "name": player_fixture.name,
            "current_hp": 50, "strength": 16, "dexterity": 14
        }
        default_npc_participant = {
            "id": npc_fixture.id, "type": "generated_npc", "name": npc_fixture.name_i18n.get("en"),
            "current_hp": 30, "strength": 10, "dexterity": 12
        }
        base_participants_list = [default_player_participant, default_npc_participant]
        if participants_override and isinstance(participants_override, list):
             base_participants_list = participants_override
        final_participants_json = {"entities": base_participants_list}
        if participants_override and "entities" in participants_override:
            final_participants_json = participants_override

        return CombatEncounter(
            id=10, guild_id=player_fixture.guild_id, status=CombatStatus.ACTIVE, location_id=101,
            participants_json=final_participants_json,
            rules_config_snapshot_json=snapshot_override if snapshot_override is not None else {},
            combat_log_json={"entries": []}
        )
    return _factory

async def get_rule_from_map_or_default(
    key_arg: str,
    default_arg: Any,
    rules_map_for_test: Optional[Dict[str, Any]] = None
) -> Any:
    if rules_map_for_test and key_arg in rules_map_for_test:
        return rules_map_for_test[key_arg]
    return default_arg

BASE_DB_RULES = {
    "combat:actions:attack:check_type": "melee_attack_vs_ac",
    "combat:actions:attack:actor_attribute_for_check": "strength",
    "combat:actions:attack:dc_base": 10,
    "combat:actions:attack:dc_target_attribute_for_modifier": "dexterity",
    "combat:attributes:strength:modifier_formula": "(value - 10) // 2",
    "combat:attributes:dexterity:modifier_formula": "(value - 10) // 2",
    "combat:actions:attack:damage_formula": "1d6+@actor_strength_modifier",
    "combat:actions:attack:actor_attribute_for_damage": "strength",
    "combat:critical_hit:threshold:natural": 20,
    "combat:critical_hit:damage_multiplier": 2.0,
    "checks:melee_attack_vs_ac:dice_notation": "1d20",
    "checks:melee_attack_vs_ac:base_attribute": "strength",
    "checks:melee_attack_vs_ac:critical_success_threshold": 20,
    "checks:melee_attack_vs_ac:critical_failure_threshold": 1,
}

@pytest.mark.asyncio
async def test_process_attack_action_hit_and_damage(
    mock_session_fixture: AsyncSession, player_actor_fixture: Player, npc_target_fixture: GeneratedNpc, combat_encounter_fixture_factory
):
    combat_encounter = combat_encounter_fixture_factory(player_actor_fixture, npc_target_fixture)
    action_data = {"action_type": "attack", "target_id": npc_target_fixture.id}
    guild_id = player_actor_fixture.guild_id
    mock_check_outcome = CheckOutcome(status="success", description="Hit!")
    mock_hit_check_result = CheckResult(guild_id=guild_id, check_type="melee_attack_vs_ac",
        entity_doing_check_id=player_actor_fixture.id, entity_doing_check_type=RelationshipEntityType.PLAYER.value,
        target_entity_id=npc_target_fixture.id, target_entity_type=RelationshipEntityType.GENERATED_NPC.value,
        difficulty_class=11, dice_notation="1d20", raw_rolls=[10], roll_used=10, total_modifier=3,
        modifier_details=[ModifierDetail(source="base_stat:strength", value=3)], final_value=13, outcome=mock_check_outcome,
        rule_config_snapshot=BASE_DB_RULES, check_context_provided={})

    with patch('src.core.combat_engine.combat_encounter_crud.get', AsyncMock(return_value=combat_encounter)), \
         patch('src.core.combat_engine.player_crud.get_by_id_and_guild', AsyncMock(return_value=player_actor_fixture)), \
         patch('src.core.combat_engine.npc_crud.get_by_id_and_guild', AsyncMock(return_value=npc_target_fixture)), \
         patch('src.core.combat_engine.get_rule', new_callable=AsyncMock) as mock_engine_get_rule, \
         patch('src.core.combat_engine.resolve_check', AsyncMock(return_value=mock_hit_check_result)) as mock_resolve_check, \
         patch('src.core.combat_engine.roll_dice', MagicMock(return_value=(7, [4]))) as mock_damage_dice_roll, \
         patch('src.core.combat_engine.log_event', AsyncMock()) as mock_log_event:

        async def side_effect_for_get_rule(db_s, gid, key, default_val): # Renamed from configured_side_effect for clarity
            return await get_rule_from_map_or_default(key, default_val, rules_map_for_test=BASE_DB_RULES)
        mock_engine_get_rule.side_effect = side_effect_for_get_rule

        result = await process_combat_action(guild_id=guild_id, session=mock_session_fixture, combat_instance_id=combat_encounter.id,
            actor_id=player_actor_fixture.id, actor_type_str=RelationshipEntityType.PLAYER.value, action_data=action_data)

        assert result.success is True
        assert result.damage_dealt == 7
        resolve_check_kwargs = mock_resolve_check.call_args.kwargs
        assert resolve_check_kwargs.get('check_type') == "melee_attack_vs_ac"
        assert resolve_check_kwargs.get('difficulty_dc') == 11
        mock_damage_dice_roll.assert_called_once_with("1d6+3")
        target_data_after = next(p for p in combat_encounter.participants_json["entities"] if p["id"] == npc_target_fixture.id)
        assert target_data_after["current_hp"] == 23
        assert "Hero Player attacks Goblin Target. Hits and deals 7 damage." in result.description_i18n['en']
        mock_log_event.assert_called_once()

@pytest.mark.asyncio
async def test_process_attack_action_miss(
    mock_session_fixture: AsyncSession, player_actor_fixture: Player, npc_target_fixture: GeneratedNpc, combat_encounter_fixture_factory
):
    combat_encounter = combat_encounter_fixture_factory(player_actor_fixture, npc_target_fixture)
    action_data = {"action_type": "attack", "target_id": npc_target_fixture.id}
    guild_id = player_actor_fixture.guild_id
    mock_check_outcome = CheckOutcome(status="failure", description="Miss!")
    mock_miss_check_result = CheckResult(guild_id=guild_id, check_type="melee_attack_vs_ac",
        entity_doing_check_id=player_actor_fixture.id, entity_doing_check_type=RelationshipEntityType.PLAYER.value,
        target_entity_id=npc_target_fixture.id, target_entity_type=RelationshipEntityType.GENERATED_NPC.value,
        difficulty_class=11, dice_notation="1d20", raw_rolls=[5], roll_used=5, total_modifier=3,
        modifier_details=[ModifierDetail(source="base_stat:strength", value=3)], final_value=8, outcome=mock_check_outcome,
        rule_config_snapshot=BASE_DB_RULES, check_context_provided={})

    with patch('src.core.combat_engine.combat_encounter_crud.get', AsyncMock(return_value=combat_encounter)), \
         patch('src.core.combat_engine.player_crud.get_by_id_and_guild', AsyncMock(return_value=player_actor_fixture)), \
         patch('src.core.combat_engine.npc_crud.get_by_id_and_guild', AsyncMock(return_value=npc_target_fixture)), \
         patch('src.core.combat_engine.get_rule', new_callable=AsyncMock) as mock_engine_get_rule, \
         patch('src.core.combat_engine.resolve_check', AsyncMock(return_value=mock_miss_check_result)), \
         patch('src.core.combat_engine.roll_dice', MagicMock()) as mock_damage_dice_roll, \
         patch('src.core.combat_engine.log_event', AsyncMock()):

        async def side_effect_for_get_rule(db_s, gid, key, default_val):
            return await get_rule_from_map_or_default(key, default_val, rules_map_for_test=BASE_DB_RULES)
        mock_engine_get_rule.side_effect = side_effect_for_get_rule

        result = await process_combat_action(guild_id=guild_id, session=mock_session_fixture, combat_instance_id=combat_encounter.id,
            actor_id=player_actor_fixture.id, actor_type_str=RelationshipEntityType.PLAYER.value, action_data=action_data)
        assert result.success is False
        assert result.damage_dealt is None
        mock_damage_dice_roll.assert_not_called()
        target_data_after = next(p for p in combat_encounter.participants_json["entities"] if p["id"] == npc_target_fixture.id)
        assert target_data_after["current_hp"] == 30
        assert "Hero Player attacks Goblin Target. Misses." in result.description_i18n['en']

@pytest.mark.asyncio
async def test_process_attack_action_critical_hit(
    mock_session_fixture: AsyncSession, player_actor_fixture: Player, npc_target_fixture: GeneratedNpc, combat_encounter_fixture_factory
):
    combat_encounter = combat_encounter_fixture_factory(player_actor_fixture, npc_target_fixture)
    action_data = {"action_type": "attack", "target_id": npc_target_fixture.id}
    guild_id = player_actor_fixture.guild_id
    mock_check_outcome = CheckOutcome(status="critical_success", description="Critical Hit!")
    mock_crit_check_result = CheckResult( guild_id=guild_id, check_type="melee_attack_vs_ac",
        entity_doing_check_id=player_actor_fixture.id, entity_doing_check_type=RelationshipEntityType.PLAYER.value,
        target_entity_id=npc_target_fixture.id, target_entity_type=RelationshipEntityType.GENERATED_NPC.value,
        difficulty_class=11, dice_notation="1d20", raw_rolls=[20], roll_used=20, total_modifier=3,
        modifier_details=[ModifierDetail(source="base_stat:strength", value=3)], final_value=23, outcome=mock_check_outcome,
        rule_config_snapshot=BASE_DB_RULES, check_context_provided={})
    with patch('src.core.combat_engine.combat_encounter_crud.get', AsyncMock(return_value=combat_encounter)), \
         patch('src.core.combat_engine.player_crud.get_by_id_and_guild', AsyncMock(return_value=player_actor_fixture)), \
         patch('src.core.combat_engine.npc_crud.get_by_id_and_guild', AsyncMock(return_value=npc_target_fixture)), \
         patch('src.core.combat_engine.get_rule', new_callable=AsyncMock) as mock_engine_get_rule, \
         patch('src.core.combat_engine.resolve_check', AsyncMock(return_value=mock_crit_check_result)), \
         patch('src.core.combat_engine.roll_dice', MagicMock(return_value=(7, [4]))) as mock_damage_dice_roll, \
         patch('src.core.combat_engine.log_event', AsyncMock()):

        async def side_effect_for_get_rule(db_s, gid, key, default_val):
            return await get_rule_from_map_or_default(key, default_val, rules_map_for_test=BASE_DB_RULES)
        mock_engine_get_rule.side_effect = side_effect_for_get_rule

        result = await process_combat_action(guild_id=guild_id, session=mock_session_fixture, combat_instance_id=combat_encounter.id,
            actor_id=player_actor_fixture.id, actor_type_str=RelationshipEntityType.PLAYER.value, action_data=action_data)
        assert result.success is True
        assert result.damage_dealt == 14
        target_data_after = next(p for p in combat_encounter.participants_json["entities"] if p["id"] == npc_target_fixture.id)
        assert target_data_after["current_hp"] == (30 - 14)
        assert "Hero Player attacks Goblin Target. CRITICAL HIT! Deals 14 damage." in result.description_i18n['en']
        mock_damage_dice_roll.assert_called_once_with("1d6+3")

@pytest.mark.asyncio
async def test_process_attack_rules_from_snapshot(
    mock_session_fixture: AsyncSession, player_actor_fixture: Player, npc_target_fixture: GeneratedNpc, combat_encounter_fixture_factory
):
    snapshot_rules = {
        "combat:actions:attack:check_type": "snapshot_check",
        "combat:actions:attack:actor_attribute_for_check": "dexterity",
        "combat:actions:attack:dc_base": 12,
        "combat:actions:attack:dc_target_attribute_for_modifier": "strength",
        "combat:attributes:dexterity:modifier_formula": "(value - 10) // 2",
        "combat:attributes:strength:modifier_formula": "(value - 10) // 2",
        "combat:actions:attack:damage_formula": "1d4+@actor_dexterity_modifier",
        "combat:actions:attack:actor_attribute_for_damage": "dexterity",
        "combat:critical_hit:threshold:natural": 20,
        "combat:critical_hit:damage_multiplier": 2.0,
    }
    combat_encounter = combat_encounter_fixture_factory(player_actor_fixture, npc_target_fixture, snapshot_override=snapshot_rules)
    action_data = {"action_type": "attack", "target_id": npc_target_fixture.id}
    guild_id = player_actor_fixture.guild_id
    mock_check_outcome = CheckOutcome(status="success", description="Snapshot Hit!")
    mock_hit_check_result_snapshot = CheckResult(guild_id=guild_id, check_type="snapshot_check",
        entity_doing_check_id=player_actor_fixture.id, entity_doing_check_type=RelationshipEntityType.PLAYER.value,
        target_entity_id=npc_target_fixture.id, target_entity_type=RelationshipEntityType.GENERATED_NPC.value,
        difficulty_class=12, dice_notation="1d20", raw_rolls=[15], roll_used=15, total_modifier=2,
        modifier_details=[ModifierDetail(source="base_stat:dexterity", value=2)], final_value=17, outcome=mock_check_outcome,
        rule_config_snapshot=snapshot_rules, check_context_provided={})

    with patch('src.core.combat_engine.combat_encounter_crud.get', AsyncMock(return_value=combat_encounter)), \
         patch('src.core.combat_engine.player_crud.get_by_id_and_guild', AsyncMock(return_value=player_actor_fixture)), \
         patch('src.core.combat_engine.npc_crud.get_by_id_and_guild', AsyncMock(return_value=npc_target_fixture)), \
         patch('src.core.combat_engine.get_rule', new_callable=AsyncMock) as mock_engine_get_rule, \
         patch('src.core.combat_engine.resolve_check', AsyncMock(return_value=mock_hit_check_result_snapshot)) as mock_resolve_check, \
         patch('src.core.combat_engine.roll_dice', MagicMock(return_value=(5, [3]))) as mock_damage_dice_roll, \
         patch('src.core.combat_engine.log_event', AsyncMock()):

        mock_engine_get_rule.side_effect = Exception("src.core.combat_engine.get_rule was called unexpectedly! Snapshot should have been used for action rules.")

        result = await process_combat_action(guild_id=guild_id, session=mock_session_fixture, combat_instance_id=combat_encounter.id,
            actor_id=player_actor_fixture.id, actor_type_str=RelationshipEntityType.PLAYER.value, action_data=action_data)

        assert result.success is True
        assert result.damage_dealt == 5
        call_args_resolve = mock_resolve_check.call_args.kwargs
        assert call_args_resolve['check_type'] == "snapshot_check"
        assert call_args_resolve['difficulty_dc'] == 12
        mock_damage_dice_roll.assert_called_once_with("1d4+2")
        mock_engine_get_rule.assert_not_called()
        assert result.additional_details["combat:actions:attack:check_type"] == "snapshot_check"
        assert result.additional_details["combat:actions:attack:damage_formula"] == "1d4+@actor_dexterity_modifier"

@pytest.mark.asyncio
async def test_process_action_error_combat_not_found(mock_session_fixture: AsyncSession, player_actor_fixture: Player):
    with patch('src.core.combat_engine.combat_encounter_crud.get', AsyncMock(return_value=None)):
        result = await process_combat_action(guild_id=100, session=mock_session_fixture, combat_instance_id=999,
            actor_id=player_actor_fixture.id, actor_type_str=RelationshipEntityType.PLAYER.value,
            action_data={"action_type": "attack", "target_id": 2})
        assert result.success is False
        assert "Combat encounter 999 not found" in result.description_i18n['en']

@pytest.mark.asyncio
async def test_process_action_error_actor_not_in_participants(
    mock_session_fixture: AsyncSession, player_actor_fixture: Player, combat_encounter_fixture_factory, npc_target_fixture
):
    participants_without_actor = {"entities": [
         {"id": npc_target_fixture.id, "type": "generated_npc", "name": "Target", "current_hp": 30, "dexterity": 12}
    ]}
    combat_encounter = combat_encounter_fixture_factory(player_actor_fixture, npc_target_fixture, participants_override=participants_without_actor)
    with patch('src.core.combat_engine.combat_encounter_crud.get', AsyncMock(return_value=combat_encounter)), \
         patch('src.core.combat_engine.player_crud.get_by_id_and_guild', AsyncMock(return_value=player_actor_fixture)):
        result = await process_combat_action(guild_id=100, session=mock_session_fixture, combat_instance_id=combat_encounter.id,
            actor_id=player_actor_fixture.id, actor_type_str=RelationshipEntityType.PLAYER.value,
            action_data={"action_type": "attack", "target_id": npc_target_fixture.id})
        assert result.success is False
        assert "Actor not found in combat" in result.description_i18n['en']

@pytest.mark.asyncio
async def test_process_action_check_resolver_raises_checkerror(
    mock_session_fixture: AsyncSession, player_actor_fixture: Player, npc_target_fixture: GeneratedNpc, combat_encounter_fixture_factory
):
    combat_encounter = combat_encounter_fixture_factory(player_actor_fixture, npc_target_fixture)
    action_data = {"action_type": "attack", "target_id": npc_target_fixture.id}
    guild_id = player_actor_fixture.guild_id
    with patch('src.core.combat_engine.combat_encounter_crud.get', AsyncMock(return_value=combat_encounter)), \
         patch('src.core.combat_engine.player_crud.get_by_id_and_guild', AsyncMock(return_value=player_actor_fixture)), \
         patch('src.core.combat_engine.npc_crud.get_by_id_and_guild', AsyncMock(return_value=npc_target_fixture)), \
         patch('src.core.combat_engine.get_rule', new_callable=AsyncMock) as mock_engine_get_rule, \
         patch('src.core.combat_engine.resolve_check', new_callable=AsyncMock) as mock_resolve_check_obj, \
         patch('src.core.combat_engine.log_event', AsyncMock()):

        async def side_effect_for_get_rule(db_s, gid, key, default_val):
            return await get_rule_from_map_or_default(key, default_val, rules_map_for_test=BASE_DB_RULES)
        mock_engine_get_rule.side_effect = side_effect_for_get_rule

        mock_resolve_check_obj.side_effect = CheckError("Test CheckError from mock")

        result = await process_combat_action(guild_id=guild_id, session=mock_session_fixture, combat_instance_id=combat_encounter.id,
            actor_id=player_actor_fixture.id, actor_type_str=RelationshipEntityType.PLAYER.value, action_data=action_data)
        assert result.success is False
        assert "Error during check: Test CheckError from mock" in result.description_i18n['en']
