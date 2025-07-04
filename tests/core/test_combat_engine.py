import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.combat_engine import (
    _get_combat_rule,
    _calculate_attribute_modifier,
    _get_participant_stat,
    process_combat_action
)
from src.models import Player, GeneratedNpc, CombatEncounter
from src.models.combat_outcomes import CombatActionResult
from src.models.check_results import CheckResult, CheckOutcome, ModifierDetail
from src.models.enums import PlayerStatus, CombatStatus, EventType
from src.core.rules import _rules_cache

# Фикстуры и вспомогательные функции

@pytest.fixture(autouse=True)
def clear_rules_cache_fixture():
    _rules_cache.clear()
    yield
    _rules_cache.clear()

@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)

@pytest.fixture
def mock_player() -> Player:
    player = Player(
        id=1, guild_id=1, discord_id=12345, name="Test Player",
        current_hp=100, level=5, xp=1000, unspent_xp=10, gold=50,
        current_status=PlayerStatus.IDLE, current_location_id=1
    )
    # Для тестов _get_participant_stat, где может потребоваться атрибут напрямую
    setattr(player, 'strength', 16) # Example base stat
    setattr(player, 'dexterity', 12) # Example base stat
    return player

@pytest.fixture
def mock_npc() -> GeneratedNpc:
    return GeneratedNpc(
        id=101, guild_id=1, name_i18n={"en": "Test NPC"},
        description_i18n={"en": "A fearsome test dummy."},
        current_location_id=1,
        properties_json={
            "stats": {
                "current_hp": 50, "max_hp": 50, "strength": 12,
                "dexterity": 14, "armor_class": 13
            }
        }
    )

@pytest.fixture
def mock_combat_encounter(mock_player: Player, mock_npc: GeneratedNpc) -> CombatEncounter:
    return CombatEncounter(
        id=1, guild_id=1, location_id=1, status=CombatStatus.ACTIVE,
        participants_json={
            "entities": [
                {"id": mock_player.id, "type": "player", "current_hp": mock_player.current_hp, "team": "A", "name": mock_player.name, "base_entity_id": mock_player.id},
                {"id": mock_npc.id, "type": "npc", "current_hp": mock_npc.properties_json["stats"]["current_hp"], "team": "B", "name": mock_npc.name_i18n.get("en"), "base_entity_id": mock_npc.id}
            ]
        },
        rules_config_snapshot_json={
            "combat:attack:check_type": "attack_roll_snapshot",
            "combat:attributes:modifier_formula": "(value - 10) // 2"
        }
    )

# Тесты для вспомогательных функций (должны проходить)

@pytest.mark.asyncio
async def test_get_combat_rule_from_snapshot(mock_session: AsyncMock, mock_combat_encounter: CombatEncounter):
    rule_key = "combat:attack:check_type"
    expected_value = "attack_roll_snapshot"
    result = await _get_combat_rule(mock_combat_encounter.rules_config_snapshot_json, mock_session, mock_combat_encounter.guild_id, rule_key, default="default_value")
    assert result == expected_value
    mock_session.execute.assert_not_called()

@pytest.mark.asyncio
async def test_get_combat_rule_from_db(mock_session: AsyncMock, mock_combat_encounter: CombatEncounter):
    rule_key = "combat:attack:damage_formula"
    expected_value = "1d6"
    with patch('src.core.combat_engine.core_get_rule', new_callable=AsyncMock) as mock_core_get_rule:
        mock_core_get_rule.return_value = expected_value
        result = await _get_combat_rule(mock_combat_encounter.rules_config_snapshot_json, mock_session, mock_combat_encounter.guild_id, rule_key, default="default_value")
        assert result == expected_value
        mock_core_get_rule.assert_called_once_with(mock_session, mock_combat_encounter.guild_id, rule_key, default="default_value")

@pytest.mark.asyncio
async def test_calculate_attribute_modifier(mock_session: AsyncMock, mock_combat_encounter: CombatEncounter):
    result_mod_16 = await _calculate_attribute_modifier(16, mock_session, 1, mock_combat_encounter.rules_config_snapshot_json)
    assert result_mod_16 == 3
    result_mod_7 = await _calculate_attribute_modifier(7, mock_session, 1, mock_combat_encounter.rules_config_snapshot_json)
    assert result_mod_7 == -2
    with patch('src.core.combat_engine._get_combat_rule', new_callable=AsyncMock) as mock_get_rule:
        mock_get_rule.return_value = "value // 2"
        result_custom_formula = await _calculate_attribute_modifier(20, mock_session, 1, None)
        assert result_custom_formula == 10
        mock_get_rule.assert_called_once_with(None, mock_session, 1, "combat:attributes:modifier_formula", default="(value - 10) // 2")

@pytest.mark.asyncio
async def test_get_participant_stat_from_override(mock_session: AsyncMock, mock_player: Player, mock_combat_encounter: CombatEncounter):
    participant_data = {"current_hp": 75, "strength": 18}
    hp = await _get_participant_stat(participant_data, mock_player, "current_hp", mock_session, 1, mock_combat_encounter.rules_config_snapshot_json)
    assert hp == 75
    strength_base = await _get_participant_stat(participant_data, mock_player, "strength", mock_session, 1, mock_combat_encounter.rules_config_snapshot_json)
    assert strength_base == 18
    strength_mod = await _get_participant_stat(participant_data, mock_player, "strength_modifier", mock_session, 1, mock_combat_encounter.rules_config_snapshot_json)
    assert strength_mod == 4

@pytest.mark.asyncio
async def test_get_participant_stat_from_player_model(mock_session: AsyncMock, mock_player: Player, mock_combat_encounter: CombatEncounter):
    mock_player.current_hp = 90
    hp = await _get_participant_stat(None, mock_player, "current_hp", mock_session, 1, mock_combat_encounter.rules_config_snapshot_json)
    assert hp == 90
    # Player.strength is set in fixture
    strength_mod = await _get_participant_stat(None, mock_player, "strength_modifier", mock_session, 1, mock_combat_encounter.rules_config_snapshot_json)
    assert strength_mod == 3 # (16 - 10) // 2

@pytest.mark.asyncio
async def test_get_participant_stat_from_npc_model(mock_session: AsyncMock, mock_npc: GeneratedNpc, mock_combat_encounter: CombatEncounter):
    hp = await _get_participant_stat(None, mock_npc, "current_hp", mock_session, 1, mock_combat_encounter.rules_config_snapshot_json)
    assert hp == 50
    strength_mod = await _get_participant_stat(None, mock_npc, "strength_modifier", mock_session, 1, mock_combat_encounter.rules_config_snapshot_json)
    assert strength_mod == 1
    ac = await _get_participant_stat(None, mock_npc, "armor_class", mock_session, 1, mock_combat_encounter.rules_config_snapshot_json)
    assert ac == 13

# Тесты для process_combat_action (пропускаются до реализации)

# @pytest.mark.skip(reason="process_combat_action not yet implemented with full logic") # Unskip this test
@pytest.mark.asyncio
@patch('src.core.combat_engine.get_entity_by_id', new_callable=AsyncMock)
@patch('src.core.combat_engine.core_check_resolver.resolve_check', new_callable=AsyncMock)
@patch('src.core.combat_engine.core_dice_roller.roll_dice')
@patch('src.core.combat_engine.core_game_events.log_event', new_callable=AsyncMock)
# _get_participant_stat и _calculate_attribute_modifier не мокируются, т.к. их тестируем отдельно,
# а _get_combat_rule мокируется для контроля над правилами в тесте process_combat_action
@patch('src.core.combat_engine._get_combat_rule', new_callable=AsyncMock)
async def test_process_combat_action_attack_hit(
    mock_get_combat_rule: AsyncMock, mock_log_event: AsyncMock, mock_roll_dice: MagicMock,
    mock_resolve_check: AsyncMock, mock_get_entity: AsyncMock, mock_session: AsyncMock,
    mock_player: Player, mock_npc: GeneratedNpc, mock_combat_encounter: CombatEncounter
):
    # --- Arrange ---
    mock_session.get.return_value = mock_combat_encounter
    mock_get_entity.side_effect = [mock_player, mock_npc] # actor, target

    # Настройка _get_combat_rule
    def get_rule_side_effect(snapshot, session, guild_id, key, default=None):
        # Используем snapshot из mock_combat_encounter если есть, иначе эти значения
        rules_map = {
            "combat:attack:check_type": "attack_roll_db", # Отличается от снэпшота для теста
            "combat:attack:attacker_main_attribute": "strength", # Атрибут для расчета модификатора атаки
            "combat:attack:target_defense_attribute": "armor_class", # Атрибут цели для DC
            "combat:attack:damage_formula": "1d8",
            "combat:attack:damage_attribute": "strength", # Атрибут для модификатора урона
            "combat:attributes:modifier_formula": "(value - 10) // 2", # Уже есть в снэпшоте, но может быть переопределен
            "combat:attack:crit_damage_multiplier": 2.0,
            "combat:attack:crit_success_threshold": 20,
            "combat:attack:crit_failure_threshold": 1
        }
        if snapshot and key in snapshot: return snapshot[key]
        return rules_map.get(key, default)
    mock_get_combat_rule.side_effect = get_rule_side_effect

    # Player strength is 16 (mod +3) from fixture
    # NPC armor_class is 13 from fixture

    mock_resolve_check.return_value = CheckResult(
        guild_id=1, check_type="attack_roll_snapshot", # Используется правило из снэпшота
        entity_doing_check_id=mock_player.id, entity_doing_check_type="player",
        target_entity_id=mock_npc.id, target_entity_type="npc", dc=13,
        dice_notation="1d20", raw_rolls=[15], roll_used=15, total_modifier=3, final_value=18, # 18 vs DC 13 -> Hit
        outcome=CheckOutcome(status="success", description="Hit!"),
        modifier_details=[ModifierDetail(source="base_stat:strength", value=3)]
    )
    mock_roll_dice.return_value = (4, [4]) # 1d8 -> результат 4

    action_data = {"action_type": "attack", "target_id": mock_npc.id, "target_type": "npc"}

    # --- Act ---
    result = await process_combat_action(
        guild_id=1, session=mock_session, combat_instance_id=mock_combat_encounter.id,
        actor_id=mock_player.id, actor_type="player", action_data=action_data
    )

    # --- Assert ---
    assert result.success is True
    assert result.damage_dealt == (4 + 3) # Damage (4) + Str_Mod (+3 for Str 16)

    npc_data_after_attack = next(p for p in mock_combat_encounter.participants_json["entities"] if p["id"] == mock_npc.id)
    expected_npc_hp = mock_npc.properties_json["stats"]["current_hp"] - (4 + 3)
    assert npc_data_after_attack["current_hp"] == expected_npc_hp

    mock_log_event.assert_called_once()
    # Проверить детали лога, если нужно

# @pytest.mark.skip(reason="process_combat_action guard clauses not fully implemented in stub") # Unskip
@pytest.mark.asyncio
async def test_process_combat_action_actor_not_found(mock_session: AsyncMock, mock_combat_encounter: CombatEncounter, mock_player: Player):
    mock_session.get.return_value = mock_combat_encounter # Combat encounter exists

    # Patch get_entity_by_id to simulate actor not found
    with patch('src.core.combat_engine.get_entity_by_id', new_callable=AsyncMock) as mock_get_entity:
        mock_get_entity.return_value = None # Actor not found

        action_data = {"action_type": "attack", "target_id": mock_player.id, "target_type": "player"} # Target can be anyone for this test

        result = await process_combat_action(
            guild_id=1,
            session=mock_session,
            combat_instance_id=mock_combat_encounter.id,
            actor_id=999, # Non-existent actor ID
            actor_type="player",
            action_data=action_data
        )
        assert result.success is False
        # The exact message might vary based on implementation, adjust if needed.
        # Based on current implementation: "Actor {actor_type} not found."
        assert "Actor player not found" in result.description_i18n["en"]

# @pytest.mark.skip(reason="process_combat_action guard clauses not fully implemented in stub") # Unskip
@pytest.mark.asyncio
async def test_process_combat_action_combat_not_found(mock_session: AsyncMock, mock_player: Player):
    mock_session.get.return_value = None # Combat encounter does not exist

    action_data = {"action_type": "attack", "target_id": mock_player.id, "target_type": "player"}

    result = await process_combat_action(
        guild_id=1,
        session=mock_session,
        combat_instance_id=999, # Non-existent combat ID
        actor_id=mock_player.id,
        actor_type="player",
        action_data=action_data
    )
    assert result.success is False
    # Based on current implementation: "Combat encounter ID not found or does not belong to guild ID."
    assert "Combat encounter ID not found or does not belong to guild ID." in result.description_i18n["en"]


@pytest.mark.asyncio
async def test_process_combat_action_target_not_in_combat(
    mock_session: AsyncMock, mock_player: Player, mock_npc: GeneratedNpc, mock_combat_encounter: CombatEncounter
):
    mock_session.get.return_value = mock_combat_encounter

    # Ensure actor (player) is found, but target (some other NPC not in combat) is not in participants_json
    # For this test, we'll make the target_id one that isn't in mock_combat_encounter.participants_json
    # Let's assume an NPC with id 777 exists in DB but is not part of this combat.

    # Mock get_entity_by_id to return player (actor) and this other NPC (target)
    other_npc_not_in_combat = GeneratedNpc(id=777, guild_id=1, name_i18n={"en": "Other NPC"}, properties_json={"stats":{"current_hp":30}})

    with patch('src.core.combat_engine.get_entity_by_id', new_callable=AsyncMock) as mock_get_entity:
        mock_get_entity.side_effect = [mock_player, other_npc_not_in_combat] # Player (actor), Other NPC (target)

        action_data = {"action_type": "attack", "target_id": other_npc_not_in_combat.id, "target_type": "npc"}

        result = await process_combat_action(
            guild_id=1, session=mock_session, combat_instance_id=mock_combat_encounter.id,
            actor_id=mock_player.id, actor_type="player", action_data=action_data
        )
        assert result.success is False
        assert "Target not found in this combat" in result.description_i18n["en"]

@pytest.mark.asyncio
async def test_process_combat_action_target_already_defeated(
    mock_session: AsyncMock, mock_player: Player, mock_npc: GeneratedNpc, mock_combat_encounter: CombatEncounter
):
    mock_session.get.return_value = mock_combat_encounter

    # Modify npc in participants_json to have 0 HP
    for p_data in mock_combat_encounter.participants_json["entities"]:
        if p_data["id"] == mock_npc.id and p_data["type"] == "npc":
            p_data["current_hp"] = 0
            break

    with patch('src.core.combat_engine.get_entity_by_id', new_callable=AsyncMock) as mock_get_entity:
        mock_get_entity.side_effect = [mock_player, mock_npc]

        action_data = {"action_type": "attack", "target_id": mock_npc.id, "target_type": "npc"}

        result = await process_combat_action(
            guild_id=1, session=mock_session, combat_instance_id=mock_combat_encounter.id,
            actor_id=mock_player.id, actor_type="player", action_data=action_data
        )
        assert result.success is True # Action is "successful" in that it was processed, but target was already down.
        assert "Target is already defeated" in result.description_i18n["en"]
        assert result.damage_dealt is None # No damage dealt


# @pytest.mark.skip(reason="process_combat_action not yet implemented for this scenario or needs more detailed rule setup") # Unskip
@pytest.mark.asyncio
@patch('src.core.combat_engine.get_entity_by_id', new_callable=AsyncMock)
@patch('src.core.combat_engine.core_check_resolver.resolve_check', new_callable=AsyncMock)
@patch('src.core.combat_engine.core_dice_roller.roll_dice')
@patch('src.core.combat_engine.core_game_events.log_event', new_callable=AsyncMock)
@patch('src.core.combat_engine._get_combat_rule', new_callable=AsyncMock)
async def test_process_combat_action_attack_miss(
    mock_get_combat_rule: AsyncMock, mock_log_event: AsyncMock, mock_roll_dice: MagicMock,
    mock_resolve_check: AsyncMock, mock_get_entity: AsyncMock, mock_session: AsyncMock,
    mock_player: Player, mock_npc: GeneratedNpc, mock_combat_encounter: CombatEncounter
):
    # --- Arrange ---
    mock_session.get.return_value = mock_combat_encounter
    mock_get_entity.side_effect = [mock_player, mock_npc]

    def get_rule_side_effect_miss(snapshot, session, guild_id, key, default=None):
        rules_map = {
            "combat:attack:check_type": "attack_roll",
            "combat:attack:attacker_main_attribute": "strength",
            "combat:attack:target_defense_attribute": "armor_class",
             # No damage formula needed for a miss
            "combat:attributes:modifier_formula": "(value - 10) // 2",
        }
        if snapshot and key in snapshot: return snapshot[key]
        return rules_map.get(key, default)
    mock_get_combat_rule.side_effect = get_rule_side_effect_miss

    # Player strength 16 (mod +3), NPC AC 13
    mock_resolve_check.return_value = CheckResult(
        guild_id=1, check_type="attack_roll_snapshot",
        entity_doing_check_id=mock_player.id, entity_doing_check_type="player",
        target_entity_id=mock_npc.id, target_entity_type="npc", dc=13,
        dice_notation="1d20", raw_rolls=[5], roll_used=5, total_modifier=3, final_value=8, # 8 vs DC 13 -> Miss
        outcome=CheckOutcome(status="failure", description="Miss!"),
        modifier_details=[ModifierDetail(source="base_stat:strength", value=3)]
    )

    action_data = {"action_type": "attack", "target_id": mock_npc.id, "target_type": "npc"}

    # --- Act ---
    result = await process_combat_action(
        guild_id=1, session=mock_session, combat_instance_id=mock_combat_encounter.id,
        actor_id=mock_player.id, actor_type="player", action_data=action_data
    )

    # --- Assert ---
    assert result.success is False # Attack missed
    assert result.damage_dealt is None
    assert mock_roll_dice.call_count == 0 # No damage roll on miss

    npc_data_after_attack = next(p for p in mock_combat_encounter.participants_json["entities"] if p["id"] == mock_npc.id)
    assert npc_data_after_attack["current_hp"] == mock_npc.properties_json["stats"]["current_hp"] # HP unchanged

    mock_log_event.assert_called_once()
    assert "misses" in result.description_i18n["en"].lower()


# @pytest.mark.skip(reason="process_combat_action not yet implemented for this specific critical hit scenario") # Unskip
@pytest.mark.asyncio
@patch('src.core.combat_engine.get_entity_by_id', new_callable=AsyncMock)
@patch('src.core.combat_engine.core_check_resolver.resolve_check', new_callable=AsyncMock)
@patch('src.core.combat_engine.core_dice_roller.roll_dice')
@patch('src.core.combat_engine.core_game_events.log_event', new_callable=AsyncMock)
@patch('src.core.combat_engine._get_combat_rule', new_callable=AsyncMock)
async def test_process_combat_action_attack_crit_hit(
    mock_get_combat_rule: AsyncMock, mock_log_event: AsyncMock, mock_roll_dice: MagicMock,
    mock_resolve_check: AsyncMock, mock_get_entity: AsyncMock, mock_session: AsyncMock,
    mock_player: Player, mock_npc: GeneratedNpc, mock_combat_encounter: CombatEncounter
):
    # --- Arrange ---
    mock_session.get.return_value = mock_combat_encounter
    mock_get_entity.side_effect = [mock_player, mock_npc] # actor, target
    setattr(mock_player, 'strength', 16) # Str 16 -> Mod +3

    # Настройка _get_combat_rule для крит. удара
    def get_rule_side_effect_crit(snapshot, session, guild_id, key, default=None):
        rules_map = {
            "combat:attack:check_type": "attack_roll_db_crit",
            "combat:attack:attacker_main_attribute": "strength",
            "combat:attack:target_defense_attribute": "armor_class",
            "combat:attack:damage_formula": "1d8", # Базовый урон
            "combat:attack:damage_attribute": "strength",
            "combat:attributes:modifier_formula": "(value - 10) // 2",
            "combat:attack:crit_damage_multiplier": 2.0, # Множитель для default crit effect
            "combat:attack:crit_effect": "multiply_total_damage", # Правило для эффекта крита
            "combat:attack:crit_success_threshold": 20,
            "combat:attack:crit_failure_threshold": 1
        }
        if snapshot and key in snapshot: return snapshot[key] # Snapshot может переопределить
        return rules_map.get(key, default)
    # mock_get_combat_rule.side_effect = get_rule_side_effect_crit # Replaced with more direct mock

    rules_to_mock_values = {
        "combat:attack:check_type": "attack_roll_db_crit",
        "combat:attack:attacker_main_attribute": "strength",
        "combat:attack:target_defense_attribute": "armor_class",
        "combat:attack:damage_formula": "1d8",
        "combat:attack:damage_attribute": "strength",
        "combat:attributes:modifier_formula": "(value - 10) // 2",
        "combat:attack:crit_damage_multiplier": 2.0,
        "combat:attack:crit_effect": "multiply_total_damage", # Test this branch
        "combat:attack:crit_success_threshold": 20,
        "combat:attack:crit_failure_threshold": 1
    }
    def side_effect_func(snapshot, session, guild_id, key, default=None):
        if snapshot and key in snapshot: return snapshot[key]
        return rules_to_mock_values.get(key, default)
    mock_get_combat_rule.side_effect = side_effect_func

    mock_resolve_check.return_value = CheckResult(
        guild_id=1, check_type="attack_roll_db_crit",
        entity_doing_check_id=mock_player.id, entity_doing_check_type="player",
        target_entity_id=mock_npc.id, target_entity_type="npc", dc=13,
        dice_notation="1d20", raw_rolls=[20], roll_used=20, total_modifier=3, final_value=23,
        outcome=CheckOutcome(status="critical_success", description="Critical Hit!"),
        modifier_details=[ModifierDetail(source="base_stat:strength", value=3)]
    )

    mock_roll_dice.return_value = (5, [5]) # Should be called once

    action_data = {"action_type": "attack", "target_id": mock_npc.id, "target_type": "npc"}

    # --- Act ---
    result = await process_combat_action(
        guild_id=1, session=mock_session, combat_instance_id=mock_combat_encounter.id,
        actor_id=mock_player.id, actor_type="player", action_data=action_data
    )

    # --- Assert ---
    assert result.success is True
    # Damage for multiply_total_damage: (base_roll (5) + damage_mod (3)) * crit_multiplier (2.0) = 16
    expected_damage = (5 + 3) * 2
    assert result.damage_dealt == expected_damage
    assert "critically strikes" in result.description_i18n["en"]
    assert result.additional_details["crit_effect"] == "multiply_total_damage"

    npc_data_after_attack = next(p for p in mock_combat_encounter.participants_json["entities"] if p["id"] == mock_npc.id)
    expected_npc_hp = mock_npc.properties_json["stats"]["current_hp"] - expected_damage
    assert npc_data_after_attack["current_hp"] == expected_npc_hp

    mock_log_event.assert_called_once()
    assert mock_roll_dice.call_count == 1 # Expect 1 call for this crit_effect
    delattr(mock_player, 'strength')


@pytest.mark.asyncio
@patch('src.core.combat_engine.get_entity_by_id', new_callable=AsyncMock)
@patch('src.core.combat_engine.core_check_resolver.resolve_check', new_callable=AsyncMock)
@patch('src.core.combat_engine.core_dice_roller.roll_dice') # Not expected to be called for crit fail outcome if no damage
@patch('src.core.combat_engine.core_game_events.log_event', new_callable=AsyncMock)
@patch('src.core.combat_engine._get_combat_rule', new_callable=AsyncMock)
async def test_process_combat_action_attack_crit_fail(
    mock_get_combat_rule: AsyncMock, mock_log_event: AsyncMock, mock_roll_dice: MagicMock,
    mock_resolve_check: AsyncMock, mock_get_entity: AsyncMock, mock_session: AsyncMock,
    mock_player: Player, mock_npc: GeneratedNpc, mock_combat_encounter: CombatEncounter
):
    # --- Arrange ---
    mock_session.get.return_value = mock_combat_encounter
    mock_get_entity.side_effect = [mock_player, mock_npc]
    setattr(mock_player, 'strength', 16)

    rules_to_mock_values = {
        "combat:attack:check_type": "attack_roll_crit_fail",
        "combat:attack:attacker_main_attribute": "strength",
        "combat:attack:target_defense_attribute": "armor_class",
        "combat:attributes:modifier_formula": "(value - 10) // 2",
        "combat:attack:crit_failure_threshold": 1 # Standard crit fail on 1
    }
    def side_effect_func(snapshot, session, guild_id, key, default=None):
        if snapshot and key in snapshot: return snapshot[key]
        return rules_to_mock_values.get(key, default)
    mock_get_combat_rule.side_effect = side_effect_func

    mock_resolve_check.return_value = CheckResult(
        guild_id=1, check_type="attack_roll_crit_fail",
        entity_doing_check_id=mock_player.id, entity_doing_check_type="player",
        target_entity_id=mock_npc.id, target_entity_type="npc", dc=13,
        dice_notation="1d20", raw_rolls=[1], roll_used=1, total_modifier=3, final_value=4,
        outcome=CheckOutcome(status="critical_failure", description="Critical Failure!"),
        modifier_details=[ModifierDetail(source="base_stat:strength", value=3)]
    )

    action_data = {"action_type": "attack", "target_id": mock_npc.id, "target_type": "npc"}

    # --- Act ---
    result = await process_combat_action(
        guild_id=1, session=mock_session, combat_instance_id=mock_combat_encounter.id,
        actor_id=mock_player.id, actor_type="player", action_data=action_data
    )

    # --- Assert ---
    assert result.success is False # Attack critically failed
    assert result.damage_dealt is None
    assert "critically fails" in result.description_i18n["en"]
    mock_roll_dice.assert_not_called() # No damage roll on critical failure

    npc_data_after_attack = next(p for p in mock_combat_encounter.participants_json["entities"] if p["id"] == mock_npc.id)
    assert npc_data_after_attack["current_hp"] == mock_npc.properties_json["stats"]["current_hp"] # HP unchanged

    mock_log_event.assert_called_once()
    delattr(mock_player, 'strength')


@pytest.mark.asyncio
async def test_process_combat_action_unknown_action( # Removed mock_get_entity from params
    mock_session: AsyncMock, mock_player: Player, mock_combat_encounter: CombatEncounter
):
    # --- Arrange ---
    mock_session.get.return_value = mock_combat_encounter
    # mock_get_entity is already a fixture, but we need to ensure it's patched if process_combat_action uses it before unknown action check
    # For this test, we assume actor is found if the function gets that far.
    # Let's refine this by patching it specifically for this test if needed, or ensure actor loading happens before action type check.
    # Based on current implementation, actor is loaded before action type check.
    with patch('src.core.combat_engine.get_entity_by_id', new_callable=AsyncMock) as patched_get_entity:
        patched_get_entity.return_value = mock_player # Actor is found

        action_data = {"action_type": "dance", "target_id": mock_player.id, "target_type": "player"}

        # --- Act ---
        result = await process_combat_action(
            guild_id=1, session=mock_session, combat_instance_id=mock_combat_encounter.id,
            actor_id=mock_player.id, actor_type="player", action_data=action_data
        )

        # --- Assert ---
        assert result.success is False
        assert "Action type 'dance' is not recognized" in result.description_i18n["en"]
        # No log event should be created for an unrecognized action that doesn't change game state
        # However, the current implementation logs *after* action processing.
        # For an unknown action, it returns early. So, log_event should NOT be called.
        # This requires a patch for log_event for this specific test.
        # For now, let's assume no log_event if it returns early.
        # If log_event is called unconditionally at the end, this test would need adjustment or the code would.
        # The current code returns early, so log_event is not called.
        # Let's add a patch for log_event to be sure it's not called.
        with patch('src.core.combat_engine.core_game_events.log_event', new_callable=AsyncMock) as mock_log_event_unknown:
            result_rerun = await process_combat_action( # Rerun with log_event patched
                guild_id=1, session=mock_session, combat_instance_id=mock_combat_encounter.id,
                actor_id=mock_player.id, actor_type="player", action_data=action_data
            )
            assert result_rerun.success is False # Re-assert from rerun
            assert "Action type 'dance' is not recognized" in result_rerun.description_i18n["en"]
            mock_log_event_unknown.assert_not_called()
