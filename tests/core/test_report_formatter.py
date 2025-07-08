import sys
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Tuple, Any, List

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.report_formatter import format_turn_report, _format_log_entry_with_names_cache, _collect_entity_refs_from_log_entry
from src.models.enums import EventType

# Fixtures

@pytest.fixture
def mock_session() -> AsyncMock:
    """Mock for AsyncSession."""
    return AsyncMock(spec=AsyncSession)

@pytest.fixture
def mock_names_cache_fixture() -> Dict[Tuple[str, int], str]:
    """Basic mock for names cache."""
    return {
        ("player", 1): "TestPlayer", ("player", 2): "Another Player", ("player", 99): "CachedPlayer99",
        ("location", 101): "Old Location", ("location", 102): "New Location",
        ("item", 201): "Magic Sword", ("item", 999): "CachedItem999",
        ("ability", 301): "Fireball", ("ability", 302): "Heal",
        ("status_effect", 401): "Burning", ("status_effect", 402): "Regeneration",
        ("quest", 501): "Main Quest", ("quest", 502): "Side Quest",
        ("npc", 601): "Goblin", ("npc", 602): "Ogre",
    }

@pytest.fixture
def mock_get_rule_fixture():
    """Mock for get_rule function."""
    captured_custom_rules_map_for_fixture = {}

    async def _mock_get_rule(session, guild_id, key, default=None):
        if key in captured_custom_rules_map_for_fixture:
            return captured_custom_rules_map_for_fixture[key]
        return default

    mock_fn = AsyncMock(side_effect=_mock_get_rule)

    def set_custom_map(new_map: dict):
        nonlocal captured_custom_rules_map_for_fixture
        captured_custom_rules_map_for_fixture.clear()
        captured_custom_rules_map_for_fixture.update(new_map)

    mock_fn.set_map_for_test = set_custom_map
    return mock_fn


@pytest.fixture
def mock_get_batch_localized_entity_names_fixture():
    """Mock for get_batch_localized_entity_names."""
    async def _mock_batch_names(session, guild_id, entity_refs, language, fallback_language):
        cache: Dict[Tuple[str, int], str] = {}
        base_names = {
            ("player", 1): "PlayerOne" if language == "en" else "ИгрокОдин",
            ("player", 2): "PlayerTwo" if language == "en" else "ИгрокДва",
            ("location", 101): "Old Town" if language == "en" else "Старый Город",
            ("location", 102): "New City" if language == "en" else "Новый Город",
            ("item", 201): "Sword of Testing" if language == "en" else "Меч Тестирования",
            ("ability", 301): "Test Ability" if language == "en" else "Тестовая Способность",
            ("status_effect", 401): "Tested Status" if language == "en" else "Тестовый Статус",
            ("quest", 501): "Test Quest" if language == "en" else "Тестовый Квест",
            ("npc", 601): "Test NPC" if language == "en" else "Тестовый НИП",
            ("npc", 602): "Another NPC" if language == "en" else "Другой НИП"
        }
        for ref in entity_refs:
            ref_type = ref.get("type")
            ref_id = ref.get("id")
            if ref_type and isinstance(ref_id, int):
                cache[(ref_type.lower(), ref_id)] = base_names.get(
                    (ref_type.lower(), ref_id),
                    f"Unknown {ref_type} {ref_id}" if language == "en" else f"Неизвестный {ref_type} {ref_id}"
                )
        return cache
    return AsyncMock(side_effect=_mock_batch_names)


# Tests for _collect_entity_refs_from_log_entry
def test_collect_refs_player_action_examine():
    log_details = {
        "event_type": EventType.PLAYER_ACTION.value,
        "actor": {"type": "player", "id": 1},
        "action": {"intent": "examine", "entities": [{"name": "Chest"}]}
    }
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs

def test_collect_refs_player_move():
    log_details = {
        "event_type": EventType.MOVEMENT.value,
        "player_id": 1,
        "old_location_id": 101,
        "new_location_id": 102
    }
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs
    assert ("location", 101) in refs
    assert ("location", 102) in refs

def test_collect_refs_item_acquired():
    log_details = { "event_type": EventType.ITEM_ACQUIRED.value, "player_id": 1, "item_id": 201 }
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs; assert ("item", 201) in refs

def test_collect_refs_combat_action():
    log_details = { "event_type": EventType.COMBAT_ACTION.value, "actor": {"type": "player", "id": 1}, "target": {"type": "npc", "id": 601} }
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs; assert ("npc", 601) in refs

def test_collect_refs_ability_used():
    log_details = { "event_type": EventType.ABILITY_USED.value, "actor_entity": {"type": "player", "id": 1}, "ability": {"id": 301}, "targets": [{"entity": {"type": "npc", "id": 601}}]}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs; assert ("ability", 301) in refs; assert ("npc", 601) in refs

def test_collect_refs_status_applied():
    log_details = { "event_type": EventType.STATUS_APPLIED.value, "target_entity": {"type": "player", "id": 1}, "status_effect": {"id": 401}}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs; assert ("status_effect", 401) in refs

def test_collect_refs_level_up():
    log_details = {"event_type": EventType.LEVEL_UP.value, "player_id": 1}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs

def test_collect_refs_xp_gained():
    log_details = {"event_type": EventType.XP_GAINED.value, "player_id": 1}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs

def test_collect_refs_relationship_change():
    log_details = { "event_type": EventType.RELATIONSHIP_CHANGE.value, "entity1": {"type": "player", "id": 1}, "entity2": {"type": "npc", "id": 601}}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs; assert ("npc", 601) in refs

def test_collect_refs_combat_start():
    log_details = { "event_type": EventType.COMBAT_START.value, "location_id": 101, "participant_ids": [{"type": "player", "id": 1}, {"type": "npc", "id": 601}]}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("location", 101) in refs; assert ("player", 1) in refs; assert ("npc", 601) in refs

def test_collect_refs_combat_end():
    log_details = { "event_type": EventType.COMBAT_END.value, "location_id": 101, "survivors": [{"type": "player", "id": 1}]}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("location", 101) in refs; assert ("player", 1) in refs

def test_collect_refs_quest_accepted():
    log_details = { "event_type": EventType.QUEST_ACCEPTED.value, "player_id": 1, "quest_id": 501}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs; assert ("quest", 501) in refs

def test_collect_refs_quest_step_completed():
    log_details = { "event_type": EventType.QUEST_STEP_COMPLETED.value, "player_id": 1, "quest_id": 501}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs; assert ("quest", 501) in refs

def test_collect_refs_quest_completed():
    log_details = { "event_type": EventType.QUEST_COMPLETED.value, "player_id": 1, "quest_id": 501}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs; assert ("quest", 501) in refs

def test_collect_refs_dialogue_line(): # Already existed and was correct.
    log_details = {"event_type": EventType.DIALOGUE_LINE.value, "speaker_entity": {"type": "npc", "id": 601}, "line_text": "Hello"}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("npc", 601) in refs

def test_collect_refs_quest_failed(): # Already existed and was correct.
    log_details = {"event_type": EventType.QUEST_FAILED.value, "player_id": 1, "quest_id": 501}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs
    assert ("quest", 501) in refs

# --- New tests for _collect_entity_refs_from_log_entry for added event types ---
def test_collect_refs_npc_action():
    log_details = { "event_type": EventType.NPC_ACTION.value, "actor": {"type": "npc", "id": 602}, "action": {"intent": "patrol"}}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("npc", 602) in refs

def test_collect_refs_item_used():
    log_details = { "event_type": EventType.ITEM_USED.value, "player_id": 1, "item_id": 201, "target": {"type": "npc", "id": 601}}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs
    assert ("item", 201) in refs
    assert ("npc", 601) in refs

def test_collect_refs_item_used_no_target():
    log_details = { "event_type": EventType.ITEM_USED.value, "player_id": 1, "item_id": 201}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs
    assert ("item", 201) in refs
    assert len(refs) == 2

def test_collect_refs_item_dropped():
    log_details = { "event_type": EventType.ITEM_DROPPED.value, "player_id": 1, "item_id": 201}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs
    assert ("item", 201) in refs

def test_collect_refs_dialogue_start():
    log_details = { "event_type": EventType.DIALOGUE_START.value, "player_entity": {"type": "player", "id": 1}, "npc_entity": {"type": "npc", "id": 601}}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs
    assert ("npc", 601) in refs

def test_collect_refs_dialogue_end():
    log_details = { "event_type": EventType.DIALOGUE_END.value, "player_entity": {"type": "player", "id": 1}, "npc_entity": {"type": "npc", "id": 601}}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs
    assert ("npc", 601) in refs

def test_collect_refs_faction_change():
    log_details = { "event_type": EventType.FACTION_CHANGE.value, "entity": {"type": "player", "id": 1}, "faction_id": 701}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs
    assert ("faction", 701) in refs

def test_collect_refs_generic_event_with_ids():
    log_details = { "event_type": EventType.SYSTEM_EVENT.value, "player_id": 1, "npc_id": 602, "location_id": 101, "description": "Something happened"}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert ("player", 1) in refs
    assert ("npc", 602) in refs
    assert ("location", 101) in refs

def test_collect_refs_generic_event_no_ids():
    log_details = { "event_type": EventType.WORLD_STATE_CHANGE.value, "description": "Season changed"}
    refs = _collect_entity_refs_from_log_entry(log_details)
    assert len(refs) == 0

# Tests for _format_log_entry_with_names_cache
@pytest.mark.asyncio
async def test_format_player_action_examine_en_with_terms(mock_session, mock_names_cache_fixture, mock_get_rule_fixture):
    mock_get_rule_fixture.set_map_for_test({
        "terms.actions.examine.verb_en": {"en": "inspects"},
        "terms.actions.examine.sees_en": {"en": "Observations"},
        "terms.results.nothing_special_en": {"en": "it is empty"}
    })
    log_details = {
        "guild_id": 1, "event_type": EventType.PLAYER_ACTION.value,
        "actor": {"type": "player", "id": 1},
        "action": {"intent": "examine", "entities": [{"name": "a Dusty Box"}]},
        "result": {"description": "it is empty"}
    }
    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, "en", mock_names_cache_fixture)
    assert "TestPlayer inspects 'a Dusty Box'. Observations: it is empty" in result

@pytest.mark.asyncio
async def test_format_player_action_examine_ru_default_terms(mock_session, mock_names_cache_fixture, mock_get_rule_fixture):
    log_details = {
        "guild_id": 1, "event_type": EventType.PLAYER_ACTION.value,
        "actor": {"type": "player", "id": 1},
        "action": {"intent": "examine", "entities": [{"name": "Старый сундук"}]},
        "result": {"description": "внутри пыльно"}
    }
    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, "ru", mock_names_cache_fixture)
    assert "TestPlayer осматривает 'Старый сундук'. Вы видите: внутри пыльно" in result

@pytest.mark.asyncio
async def test_format_combat_end_ru_with_terms_and_survivors(mock_session, mock_names_cache_fixture, mock_get_rule_fixture):
    mock_get_rule_fixture.set_map_for_test({
        "terms.combat.outcomes.victory_players_ru": {"ru": "победа игроков"},
        "terms.combat.ended_ru": {"ru": "Схватка в '{location_name}' окончена. Результат: {outcome_readable}."},
        "terms.combat.survivors_ru": {"ru": " Уцелевшие: {survivors_str}."}
    })
    log_details = {
        "guild_id": 1, "event_type": EventType.COMBAT_END.value,
        "location_id": 101, "outcome": "victory_players",
        "survivors": [{"type": "player", "id": 1}, {"type": "npc", "id": 602}]
    }
    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, "ru", mock_names_cache_fixture)
    assert "Схватка в 'Old Location' окончена. Результат: победа игроков. Уцелевшие: TestPlayer, Ogre." in result

# Tests for format_turn_report
@pytest.mark.asyncio
async def test_format_turn_report_empty_logs_integration(mock_session, mock_get_batch_localized_entity_names_fixture):
    # Configure the mock_session for the chain of calls in load_rules_config_for_guild
    mock_executed_statement = AsyncMock()
    mock_scalars_result = AsyncMock()
    mock_scalars_result.all.return_value = []

    mock_session.execute.return_value = mock_executed_statement
    mock_executed_statement.scalars.return_value = mock_scalars_result

    with patch('src.core.report_formatter.get_batch_localized_entity_names', new=mock_get_batch_localized_entity_names_fixture):
        report_en = await format_turn_report(mock_session, 1, [], 1, "en")
        assert "Nothing significant happened this turn." in report_en

        # This block was causing indentation issues. Ensuring it's correctly indented.
        # Corrected indentation for the following lines:
        report_ru = await format_turn_report(mock_session, 1, [], 1, "ru")
        assert "Ничего существенного не произошло за этот ход." in report_ru

@pytest.mark.asyncio
async def test_format_turn_report_with_logs_integration(mock_session, mock_get_rule_fixture, mock_get_batch_localized_entity_names_fixture):
    # Configure the mock_session for the chain of calls in load_rules_config_for_guild
    mock_executed_statement = AsyncMock()
    mock_scalars_result = AsyncMock()
    mock_scalars_result.all.return_value = []

    mock_session.execute.return_value = mock_executed_statement
    mock_executed_statement.scalars.return_value = mock_scalars_result

    # Mock names cache for entities in log_entries
    mock_get_batch_localized_entity_names_fixture.return_value = {
        ("player", 1): "PlayerOne",
        ("location", 101): "Old Town",
        ("location", 102): "New City",
        ("item", 201): "Sword of Testing"
    }

    log_entries = [
        {"guild_id": 1, "event_type": EventType.MOVEMENT.value, "player_id": 1, "old_location_id": 101, "new_location_id": 102},
        {"guild_id": 1, "event_type": EventType.ITEM_ACQUIRED.value, "player_id": 1, "item_id": 201, "source": "a chest"}
    ]
    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture),          patch('src.core.report_formatter.get_batch_localized_entity_names', new=mock_get_batch_localized_entity_names_fixture):
        report_en = await format_turn_report(mock_session, 1, log_entries, 1, "en", "en")

    assert "Turn Report for PlayerOne:" in report_en
    assert "PlayerOne moves from 'Old Town' to 'New City'." in report_en # Changed "moved" to "moves"
    assert "PlayerOne acquired 'Sword of Testing' (x1) from a chest." in report_en # Added quotes around item name

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture),          patch('src.core.report_formatter.get_batch_localized_entity_names', new=mock_get_batch_localized_entity_names_fixture):
        report_ru = await format_turn_report(mock_session, 1, log_entries, 1, "ru", "en")

    assert "Отчет по ходу для ИгрокОдин:" in report_ru
    assert "ИгрокОдин перемещается из 'Старый Город' в 'Новый Город'." in report_ru # Changed "переместился" to "перемещается"
    assert "ИгрокОдин получил(а) 'Меч Тестирования' (x1) из a chest." in report_ru # Added quotes around item name and fixed verb form

# Additional tests for event_types with RuleConfig
@pytest.mark.asyncio
@pytest.mark.parametrize("lang, expected_verb, expected_particle", [
    ("en", "uses ability", "on"),
    ("ru", "использует способность", "на")
])
async def test_format_ability_used_with_terms(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, expected_verb, expected_particle):
    mock_get_rule_fixture.set_map_for_test({
        f"terms.abilities.verb_uses_{lang}": {lang: expected_verb},
        f"terms.abilities.particle_on_{lang}": {lang: expected_particle},
        # Corrected key and ensure mock returns direct string for this specific term
        f"terms.general.nobody_{lang}": "nobody" if lang == "en" else "ни на кого"
    })
    log_details = {
        "guild_id": 1, "event_type": EventType.ABILITY_USED.value,
        "actor_entity": {"type": "player", "id": 1},
        "ability": {"id": 301}, 
        "targets": [], 
        "outcome": {"description": "The air crackles." if lang == "en" else "Воздух трещит."}
    }
    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)

    actor_name = mock_names_cache_fixture[("player", 1)]
    ability_name = mock_names_cache_fixture[("ability", 301)]
    # This is what the SUT's get_term should produce for "terms.general.nobody"
    actual_no_target_str = "nobody" if lang == "en" else "ни на кого"
    outcome_str = "The air crackles." if lang == "en" else "Воздух трещит."

    expected_string = f"{actor_name} {expected_verb} '{ability_name}' {expected_particle} {actual_no_target_str}. {outcome_str}"
    assert result.strip() == expected_string.strip() # Use exact match and strip

# --- Tests for newly added event types ---

@pytest.mark.asyncio
@pytest.mark.parametrize("lang, expected_template_key, default_template, location_name_key, participants_key, expected_participants_str_default", [
    ("en", "terms.combat.starts_involving_en", "Combat starts at '{location_name}' involving: {participants_str}.", ("location",101), [("player",1),("npc",601)], "TestPlayer, Goblin"),
    ("ru", "terms.combat.starts_involving_ru", "Начинается бой в '{location_name}' с участием: {participants_str}.", ("location",101), [("player",1),("npc",601)], "TestPlayer, Goblin"),
    ("en", "terms.combat.starts_involving_en", "Combat starts at '{location_name}' involving: {participants_str}.", ("location",101), [], "unknown participants"),
])
async def test_format_combat_start(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, expected_template_key, default_template, location_name_key, participants_key, expected_participants_str_default):
    mock_get_rule_fixture.set_map_for_test({
        expected_template_key: {lang: default_template},
        f"terms.general.unknown_location_{lang}": {lang: "some place"},
        f"terms.general.unknown_participants_{lang}": {lang: expected_participants_str_default if not participants_key else ""}
    })

    log_details = {
        "guild_id": 1, "event_type": EventType.COMBAT_START.value,
        "location_id": location_name_key[1],
        "participant_ids": [{"type": pt[0], "id": pt[1]} for pt in participants_key]
    }
    
    location_name = mock_names_cache_fixture.get(location_name_key, "some place")
    
    participant_names = [mock_names_cache_fixture.get(pk, f"{pk[0]} {pk[1]}") for pk in participants_key]
    participants_str_rendered = ", ".join(participant_names) if participant_names else expected_participants_str_default
    
    expected_msg = default_template.format(location_name=location_name, participants_str=participants_str_rendered)

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg

# --- Tests for newly added event types in _format_log_entry_with_names_cache ---

@pytest.mark.asyncio
@pytest.mark.parametrize("lang, actor_key, action_intent, target_name_str, result_message, expected_verb_key_suffix, default_verb_format_param, default_preposition_param", [
    ("en", ("npc", 601), "attack", "PlayerOne", "deals 10 damage", ".verb_npc", "performs '{action_intent}'", "on"),
    ("ru", ("npc", 602), "guard", "the treasure", "successfully", ".verb_npc", "совершает '{action_intent}'", "над"),
    ("en", ("npc", 601), "special_move", "themselves", "", ".verb_npc", "performs '{action_intent}'", "on"),
])
async def test_format_npc_action(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, actor_key, action_intent, target_name_str, result_message, expected_verb_key_suffix, default_verb_format_param, default_preposition_param):
    verb_key = f"terms.actions.{action_intent}{expected_verb_key_suffix}_{lang}"
    # Term for the verb itself (without preposition)
    verb_term_value = default_verb_format_param.format(action_intent=action_intent)

    # Term for the preposition (the SUT will try preposition_npc then preposition)
    preposition_key_npc = f"terms.actions.{action_intent}.preposition_npc_{lang}"
    # preposition_key_general = f"terms.actions.{action_intent}.preposition_{lang}" # Not directly used in this test's setup logic but SUT might try it

    term_map_setup = {
        verb_key: {lang: verb_term_value},
        f"terms.general.an_npc_{lang}": {lang: "An NPC" if lang == "en" else "НИП"},
        # Ensure the mock_get_rule returns the default_preposition_param for the key the SUT will query
        preposition_key_npc: {lang: default_preposition_param},
    }
    mock_get_rule_fixture.set_map_for_test(term_map_setup)

    log_details = {
        "guild_id": 1, "event_type": EventType.NPC_ACTION.value,
        "actor": {"type": actor_key[0], "id": actor_key[1]},
        "action": {"intent": action_intent, "entities": [{"name": target_name_str}]},
        "result": {"message": result_message}
    }

    actor_name = mock_names_cache_fixture.get(actor_key, "An NPC" if lang == "en" else "НИП")

    # Expected message construction based on how the SUT will build it:
    # Actor Verb Preposition 'Target'. Result.
    expected_msg = f"{actor_name} {verb_term_value}"
    if target_name_str: # The SUT adds preposition only if target_name_str exists
        expected_msg += f" {default_preposition_param} '{target_name_str}'"
    expected_msg += "." # SUT adds a period

    if result_message:
        expected_msg += f" {result_message}"
    expected_msg = expected_msg.strip() # Final strip to handle potential leading/trailing spaces from logic

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg

# --- Tests for Combat Action with CheckResult details ---
@pytest.mark.asyncio
@pytest.mark.parametrize("lang, damage, roll, total_mod, final_val, dc, rel_desc, rel_val", [
    ("en", 10, 15, 2, 17, 16, "Friendly (Formula)", 2),
    ("ru", 5, 8, -1, 7, 10, "Враждебность (Порог)", -1),
    ("en", 0, 5, 0, 5, 10, None, None), # Miss, no specific relationship bonus shown in this test case
])
async def test_format_combat_action_with_check_result_and_relationship_details(
    mock_session, mock_names_cache_fixture, mock_get_rule_fixture,
    lang, damage, roll, total_mod, final_val, dc, rel_desc, rel_val
):
    actor_key = ("player", 1)
    target_key = ("npc", 601)
    action_name = "Slash" if lang == "en" else "Рубящий удар"

    # Setup terms for the test
    term_map = {
        f"terms.combat.uses_{lang}": {"en": "uses", "ru": "использует"}[lang],
        f"terms.combat.on_{lang}": {"en": "on", "ru": "против"}[lang],
        f"terms.combat.dealing_damage_{lang}": {"en": "dealing", "ru": "нанося"}[lang],
        f"terms.general.damage_{lang}": {"en": "damage", "ru": "урона"}[lang],
        f"terms.checks.roll_{lang}": {"en": "Roll", "ru": "Бросок"}[lang],
        f"terms.checks.modifier_{lang}": {"en": "Mod", "ru": "Мод."}[lang],
        f"terms.checks.total_{lang}": {"en": "Total", "ru": "Итог"}[lang],
        f"terms.checks.vs_dc_{lang}": {"en": "vs DC", "ru": "против СЛ"}[lang],
        f"terms.checks.bonuses_penalties_{lang}": {"en": "Bonuses/Penalties", "ru": "Бонусы/Штрафы"}[lang],
    }
    mock_get_rule_fixture.set_map_for_test(term_map)

    check_result_details_dict = {
        "roll_used": roll, "total_modifier": total_mod, "final_value": final_val, "difficulty_class": dc,
        "modifier_details": []
    }
    if rel_desc and rel_val is not None:
        check_result_details_dict["modifier_details"].append(
            {"description": rel_desc, "value": rel_val, "source": "relationship:some_pattern"}
        )

    # Add a generic modifier for more coverage
    check_result_details_dict["modifier_details"].append(
        {"description": "Base Stat", "value": total_mod - (rel_val or 0), "source":"base_stat:strength"}
    )


    log_details = {
        "guild_id": 1, "event_type": EventType.COMBAT_ACTION.value,
        "actor": {"type": actor_key[0], "id": actor_key[1]},
        "target": {"type": target_key[0], "id": target_key[1]},
        "action_name": action_name,
        "damage": damage if damage > 0 else None, # None if 0 damage
        "check_result": check_result_details_dict
    }

    # Expected base message part
    actor_name = mock_names_cache_fixture[actor_key]
    target_name = mock_names_cache_fixture[target_key]
    uses_term = term_map[f"terms.combat.uses_{lang}"]
    on_term = term_map[f"terms.combat.on_{lang}"]

    expected_base_msg = f"{actor_name} {uses_term} '{action_name}' {on_term} {target_name}"
    if damage > 0:
        dealing_term = term_map[f"terms.combat.dealing_damage_{lang}"]
        damage_term_val = term_map[f"terms.general.damage_{lang}"]
        expected_base_msg += f", {dealing_term} {damage} {damage_term_val}."
    else:
        expected_base_msg += "."

    # Expected check details part
    term_roll_val = term_map[f"terms.checks.roll_{lang}"]
    term_mod_val = term_map[f"terms.checks.modifier_{lang}"]
    term_total_val = term_map[f"terms.checks.total_{lang}"]
    term_vs_dc_val = term_map[f"terms.checks.vs_dc_{lang}"]
    expected_check_str = f" ({term_roll_val}: {roll}, {term_mod_val}: {total_mod}, {term_total_val}: {final_val} {term_vs_dc_val}: {dc})"

    mod_descs_rendered = []
    if rel_desc and rel_val is not None:
        mod_descs_rendered.append(f"{rel_desc} ({'+' if rel_val >=0 else ''}{rel_val})")

    # Add the generic modifier to rendered list
    generic_mod_val = total_mod - (rel_val or 0)
    mod_descs_rendered.append(f"Base Stat ({'+' if generic_mod_val >=0 else ''}{generic_mod_val})")

    if mod_descs_rendered:
        term_bonuses_penalties_val = term_map[f"terms.checks.bonuses_penalties_{lang}"]
        expected_check_str += f" [{term_bonuses_penalties_val}: {'; '.join(mod_descs_rendered)}]"

    final_expected_msg = expected_base_msg + expected_check_str

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)

    assert result == final_expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, player_key, item_key, target_info, outcome_desc, uses_term_default, on_term_default", [
    ("en", ("player", 1), ("item", 201), {"type": "npc", "id": 601}, "It glows faintly.", "uses", "on"),
    ("ru", ("player", 2), ("item", 999), None, "Предмет исчезает.", "использует", "на"),
    ("en", ("player", 1), ("item", 201), {"type": "location", "id": 101}, "", "uses", "on"),
])
async def test_format_item_used(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, player_key, item_key, target_info, outcome_desc, uses_term_default, on_term_default):
    term_map = {
        f"terms.items.uses_{lang}": {lang: uses_term_default},
        f"terms.general.someone_{lang}": {lang: "Someone" if lang == "en" else "Некто"},
        f"terms.general.an_item_{lang}": {lang: "an item" if lang == "en" else "предмет"},
    }
    if target_info:
        term_map[f"terms.items.on_{lang}"] = {lang: on_term_default}

    mock_get_rule_fixture.set_map_for_test(term_map)

    log_details = {
        "guild_id": 1, "event_type": EventType.ITEM_USED.value,
        "player_id": player_key[1], "item_id": item_key[1],
        "outcome_description": outcome_desc
    }
    if target_info:
        log_details["target"] = target_info

    player_name = mock_names_cache_fixture.get(player_key, "Someone" if lang == "en" else "Некто")
    item_name = mock_names_cache_fixture.get(item_key, "an item" if lang == "en" else "предмет")

    target_str_rendered = ""
    if target_info:
        target_name_rendered = mock_names_cache_fixture.get(
            (target_info["type"], target_info["id"]),
            f"[{target_info['type'].capitalize()} ID: {target_info['id']} (Cached?)]"
        )
        target_str_rendered = f" {on_term_default} '{target_name_rendered}'"

    expected_msg = f"{player_name} {uses_term_default} '{item_name}'{target_str_rendered}."
    if outcome_desc:
        expected_msg += f" {outcome_desc}"
    expected_msg = expected_msg.strip()

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, player_key, item_key, quantity, drops_term_default", [
    ("en", ("player", 1), ("item", 201), 1, "drops"),
    ("ru", ("player", 2), ("item", 999), 5, "выбрасывает"),
])
async def test_format_item_dropped(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, player_key, item_key, quantity, drops_term_default):
    mock_get_rule_fixture.set_map_for_test({
        f"terms.items.drops_{lang}": {lang: drops_term_default},
        f"terms.general.someone_{lang}": {lang: "Someone" if lang == "en" else "Некто"},
        f"terms.general.an_item_{lang}": {lang: "an item" if lang == "en" else "предмет"},
    })

    log_details = {
        "guild_id": 1, "event_type": EventType.ITEM_DROPPED.value,
        "player_id": player_key[1], "item_id": item_key[1], "quantity": quantity
    }

    player_name = mock_names_cache_fixture.get(player_key, "Someone" if lang == "en" else "Некто")
    item_name = mock_names_cache_fixture.get(item_key, "an item" if lang == "en" else "предмет")
    expected_msg = f"{player_name} {drops_term_default} '{item_name}' (x{quantity})."

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, player_key, npc_key, template_default", [
    ("en", ("player", 1), ("npc", 601), "{player_name} starts a conversation with {npc_name}."),
    ("ru", ("player", 2), ("npc", 602), "{player_name} начинает разговор с {npc_name}."),
])
async def test_format_dialogue_start(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, player_key, npc_key, template_default):
    mock_get_rule_fixture.set_map_for_test({
        f"terms.dialogue.starts_conversation_with_{lang}": {lang: template_default},
        f"terms.general.someone_{lang}": {lang: "Someone" if lang == "en" else "Некто"},
        f"terms.general.an_npc_{lang}": {lang: "An NPC" if lang == "en" else "НИП"},
    })
    log_details = {
        "guild_id": 1, "event_type": EventType.DIALOGUE_START.value,
        "player_entity": {"type": player_key[0], "id": player_key[1]},
        "npc_entity": {"type": npc_key[0], "id": npc_key[1]}
    }
    player_name = mock_names_cache_fixture.get(player_key, "Someone" if lang == "en" else "Некто")
    npc_name = mock_names_cache_fixture.get(npc_key, "An NPC" if lang == "en" else "НИП")
    expected_msg = template_default.format(player_name=player_name, npc_name=npc_name)

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, player_key, npc_key, template_default", [
    ("en", ("player", 1), ("npc", 601), "{player_name} ends the conversation with {npc_name}."),
    ("ru", ("player", 2), ("npc", 602), "{player_name} заканчивает разговор с {npc_name}."),
])
async def test_format_dialogue_end(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, player_key, npc_key, template_default):
    mock_get_rule_fixture.set_map_for_test({
        f"terms.dialogue.ends_conversation_with_{lang}": {lang: template_default},
        # Add other general fallbacks if needed by get_name_from_cache for this test
    })
    log_details = {
        "guild_id": 1, "event_type": EventType.DIALOGUE_END.value,
        "player_entity": {"type": player_key[0], "id": player_key[1]},
        "npc_entity": {"type": npc_key[0], "id": npc_key[1]}
    }
    player_name = mock_names_cache_fixture[player_key] # Assume player is always in cache for these tests
    npc_name = mock_names_cache_fixture[npc_key]       # Assume NPC is always in cache
    expected_msg = template_default.format(player_name=player_name, npc_name=npc_name)

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, entity_key, faction_key, old_s, new_s, reason", [
    ("en", ("player", 1), ("faction", 701), "Neutral", "Friendly", "Helped them"),
    ("ru", ("party", 11), ("faction", 702), "Враждебность", "Нейтралитет", None),
])
async def test_format_faction_change(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, entity_key, faction_key, old_s, new_s, reason):
    # Add faction to names_cache_fixture for the test
    mock_names_cache_fixture[("faction", 701)] = "The Protectors" if lang == "en" else "Защитники"
    mock_names_cache_fixture[("faction", 702)] = "Shadow Syndicate" if lang == "en" else "Теневой Синдикат"
    if entity_key[0] == "party": # Add party to cache if used
         mock_names_cache_fixture[entity_key] = "The Avengers" if lang == "en" else "Мстители"


    term_map = {
        f"terms.factions.reputation_of_{lang}": {lang: "Reputation of" if lang == "en" else "Репутация"},
        f"terms.factions.with_faction_{lang}": {lang: "with" if lang == "en" else "с"},
        f"terms.factions.changed_from_{lang}": {lang: "changed from" if lang == "en" else "изменилась с"},
        f"terms.factions.to_standing_{lang}": {lang: "to" if lang == "en" else "на"},
        f"terms.general.an_entity_{lang}": {lang: "An entity" if lang == "en" else "Сущность"},
        f"terms.factions.a_faction_{lang}": {lang: "a faction" if lang == "en" else "фракцией"},
    }
    if reason:
        term_map[f"terms.general.reason_{lang}"] = {lang: "Reason" if lang == "en" else "Причина"}

    mock_get_rule_fixture.set_map_for_test(term_map)

    log_details = {
        "guild_id": 1, "event_type": EventType.FACTION_CHANGE.value,
        "entity": {"type": entity_key[0], "id": entity_key[1]},
        "faction_id": faction_key[1], "old_standing": old_s, "new_standing": new_s,
    }
    if reason:
        log_details["reason"] = reason

    entity_name = mock_names_cache_fixture.get(entity_key, "An entity" if lang == "en" else "Сущность")
    faction_name = mock_names_cache_fixture.get(faction_key, "a faction" if lang == "en" else "фракцией")

    reputation_of_fmt = "Reputation of" if lang == "en" else "Репутация"
    with_faction_fmt = "with" if lang == "en" else "с"
    changed_from_fmt = "changed from" if lang == "en" else "изменилась с"
    to_standing_fmt = "to" if lang == "en" else "на"

    expected_msg_base = f"{reputation_of_fmt} {entity_name} {with_faction_fmt} {faction_name} {changed_from_fmt} {old_s} {to_standing_fmt} {new_s}."
    if reason:
        reason_term_fmt = "Reason" if lang == "en" else "Причина"
        expected_msg_base += f" ({reason_term_fmt}: {reason})"

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg_base


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, event_type_enum, details, expected_prefix, expected_content_part", [
    ("en", EventType.SYSTEM_EVENT, {"description": "Weather changed to sunny."}, "[System Event]:", "Weather changed to sunny."),
    ("ru", EventType.WORLD_STATE_CHANGE, {"change": "season is now winter"}, "[World State Change]:", "change: season is now winter"),
    ("en", EventType.MASTER_COMMAND, {"command_name": "teleport", "target_player_id": 1}, "[Master Command]:", "command_name: teleport"),
    ("ru", EventType.ERROR_EVENT, {"error_message": "Failed to load module X."}, "[Error Event]:", "error_message: Failed to load module X."),
    ("en", EventType.AI_GENERATION_TRIGGERED, {"context": "new_npc_for_tavern"}, "[Ai Generation Triggered]:", "context: new_npc_for_tavern"),
    ("ru", EventType.TRADE_INITIATED, {"player_id": 1, "npc_id": 601}, "[Trade Initiated]:", "player_id: 1; npc_id: 601"),
])
async def test_format_generic_events(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, event_type_enum, details, expected_prefix, expected_content_part):
    log_details = {"guild_id": 1, "event_type": event_type_enum.value, **details}

    # No specific terms needed for generic formatter, it uses event_type and details_json keys
    mock_get_rule_fixture.set_map_for_test({})

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)

    assert result.startswith(expected_prefix)
    assert expected_content_part in result


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, speaker_key, line_text", [
    ("en", ("player", 1), "Hello world!"),
    ("ru", ("npc", 601), "Привет, мир!"),
    ("en", ("player", 99), "No speaker in cache."), 
])
async def test_format_dialogue_line(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, speaker_key, line_text):
    mock_get_rule_fixture.set_map_for_test({
        f"terms.general.someone_{lang}": {lang: "SomeoneViaTerm" if lang == "en" else "НектоЧерезТермин"}
    })
    
    log_details = {
        "guild_id": 1, "event_type": EventType.DIALOGUE_LINE.value,
        "speaker_entity": {"type": speaker_key[0], "id": speaker_key[1]},
        "line_text": line_text
    }
    
    sut_default_prefix = speaker_key[0].capitalize()
    sut_placeholder_if_not_in_cache = f"[{sut_default_prefix} ID: {speaker_key[1]} (Cached?)]"
    # Correctly expect the placeholder if the speaker is not in the primary cache
    speaker_name = mock_names_cache_fixture.get(speaker_key) 
    if speaker_name is None: # Check if it was found in the cache
        if speaker_key[1] == 99 : # Specific case for player 99 not being in cache
             speaker_name = sut_placeholder_if_not_in_cache
        else: # Other un-cached speakers might use a term or a simpler placeholder
             speaker_name = "Someone" if lang == "en" else "Некто" # Fallback if not player 99 and not in cache

    expected_msg = f'{speaker_name}: "{line_text}"' # Added quotes around line_text


    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, template_key, default_template, target_key, status_key", [
    ("en", "terms.statuses.effect_ended_on_en", "'{status_name}' effect has ended on {target_name}.", ("player", 1), ("status_effect", 401)),
    ("ru", "terms.statuses.effect_ended_on_ru", "Эффект '{status_name}' закончился для {target_name}.", ("npc", 601), ("status_effect", 402)),
])
async def test_format_status_removed(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, template_key, default_template, target_key, status_key):
    mock_get_rule_fixture.set_map_for_test({
        template_key: {lang: default_template},
        f"terms.general.someone_{lang}": {lang: "Someone" if lang == "en" else "Некто"}, 
        f"terms.statuses.a_status_effect_{lang}": {lang: "a status effect" if lang == "en" else "эффект состояния"}
    })
    log_details = {
        "guild_id": 1, "event_type": EventType.STATUS_REMOVED.value,
        "target_entity": {"type": target_key[0], "id": target_key[1]},
        "status_effect": {"id": status_key[1]}
    }
    target_name = mock_names_cache_fixture.get(target_key, "Someone" if lang == "en" else "Некто")
    status_name = mock_names_cache_fixture.get(status_key, "a status effect" if lang == "en" else "эффект состояния")
    expected_msg = default_template.format(status_name=status_name, target_name=target_name)

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, reason, template_key_suffix, default_template_format, player_key, quest_key", [
    ("en", "ran out of time", "with_reason", "{player_name} has failed the quest '{quest_name}' due to: {reason}.", ("player",1), ("quest",501)),
    ("ru", "кончилось время", "with_reason", "{player_name} провалил(а) задание '{quest_name}' по причине: {reason}.", ("player",1), ("quest",501)),
    ("en", None, "simple", "{player_name} has failed the quest '{quest_name}'.", ("player",1), ("quest",501)),
    ("ru", None, "simple", "{player_name} провалил(а) задание '{quest_name}'.", ("player",1), ("quest",501)),
])
async def test_format_quest_failed(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, reason, template_key_suffix, default_template_format, player_key, quest_key):
    template_key = f"terms.quests.failed_{template_key_suffix}_{lang}"
    mock_get_rule_fixture.set_map_for_test({
        template_key: {lang: default_template_format},
        f"terms.general.someone_{lang}": {lang: "Someone" if lang == "en" else "Некто"},
        f"terms.quests.a_quest_{lang}": {lang: "a quest" if lang == "en" else "задание"}
    })
    
    log_details = {
        "guild_id": 1, "event_type": EventType.QUEST_FAILED.value,
        "player_id": player_key[1], "quest_id": quest_key[1]
    }
    if reason:
        log_details["reason"] = reason

    player_name = mock_names_cache_fixture.get(player_key, "Someone" if lang == "en" else "Некто")
    quest_name = mock_names_cache_fixture.get(quest_key, "a quest" if lang == "en" else "задание")
    
    if reason:
        expected_msg = default_template_format.format(player_name=player_name, quest_name=quest_name, reason=reason)
    else:
        expected_msg = default_template_format.format(player_name=player_name, quest_name=quest_name)

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, template_key, default_template, player_key, quest_key", [
    ("en", "terms.quests.accepted_en", "{player_name} has accepted the quest: '{quest_name}'.", ("player",1), ("quest",501)),
    ("ru", "terms.quests.accepted_ru", "{player_name} принял(а) задание: '{quest_name}'.", ("player",1), ("quest",501)),
])
async def test_format_quest_accepted(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, template_key, default_template, player_key, quest_key):
    mock_get_rule_fixture.set_map_for_test({template_key: {lang: default_template}})
    log_details = {
        "guild_id": 1, "event_type": EventType.QUEST_ACCEPTED.value,
        "player_id": player_key[1], "quest_id": quest_key[1]
    }
    player_name = mock_names_cache_fixture[player_key]
    quest_name = mock_names_cache_fixture[quest_key]
    expected_msg = default_template.format(player_name=player_name, quest_name=quest_name)

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, step_details, template_key_suffix, default_template_format", [
    ("en", "Retrieve the amulet", "detailed", "{player_name} completed a step in '{quest_name}': {step_details}."),
    ("ru", "Добудьте амулет", "detailed", "{player_name} выполнил(а) этап в задании '{quest_name}': {step_details}."),
    ("en", None, "simple", "{player_name} completed a step in the quest '{quest_name}'."),
    ("ru", None, "simple", "{player_name} выполнил(а) этап в задании '{quest_name}'."),
])
async def test_format_quest_step_completed(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, step_details, template_key_suffix, default_template_format):
    template_key = f"terms.quests.step_completed_{template_key_suffix}_{lang}"
    mock_get_rule_fixture.set_map_for_test({template_key: {lang: default_template_format}})
    
    player_key = ("player", 1)
    quest_key = ("quest", 501)
    log_details = {
        "guild_id": 1, "event_type": EventType.QUEST_STEP_COMPLETED.value,
        "player_id": player_key[1], "quest_id": quest_key[1],
    }
    if step_details:
        log_details["step_details"] = step_details

    player_name = mock_names_cache_fixture[player_key]
    quest_name = mock_names_cache_fixture[quest_key]
    
    if step_details:
        expected_msg = default_template_format.format(player_name=player_name, quest_name=quest_name, step_details=step_details)
    else:
        expected_msg = default_template_format.format(player_name=player_name, quest_name=quest_name)

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, template_key, default_template, player_key, quest_key", [
    ("en", "terms.quests.completed_en", "{player_name} has completed the quest: '{quest_name}'!", ("player",1), ("quest",501)),
    ("ru", "terms.quests.completed_ru", "{player_name} завершил(а) задание: '{quest_name}'!", ("player",1), ("quest",501)),
])
async def test_format_quest_completed(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, template_key, default_template, player_key, quest_key):
    mock_get_rule_fixture.set_map_for_test({template_key: {lang: default_template}})
    log_details = {
        "guild_id": 1, "event_type": EventType.QUEST_COMPLETED.value,
        "player_id": player_key[1], "quest_id": quest_key[1]
    }
    player_name = mock_names_cache_fixture[player_key]
    quest_name = mock_names_cache_fixture[quest_key]
    expected_msg = default_template.format(player_name=player_name, quest_name=quest_name)

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, new_level, template_key, default_template", [
    ("en", 5, "terms.character.level_up_en", "{player_name} has reached level {level_str}!"),
    ("ru", 5, "terms.character.level_up_ru", "{player_name} достиг(ла) уровня {level_str}!"),
    ("en", None, "terms.character.level_up_en", "{player_name} has reached level {level_str}!"), 
])
async def test_format_level_up(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, new_level, template_key, default_template):
    player_key = ("player", 1)
    mock_get_rule_fixture.set_map_for_test({
        template_key: {lang: default_template},
        f"terms.character.unknown_level_{lang}": {lang: "a new level" if lang == "en" else "новый уровень"}
    })
    log_details = {
        "guild_id": 1, "event_type": EventType.LEVEL_UP.value,
        "player_id": player_key[1], "new_level": new_level
    }
    player_name = mock_names_cache_fixture[player_key]
    level_str = str(new_level) if new_level is not None else ("a new level" if lang == "en" else "новый уровень")
    
    expected_msg = default_template.format(player_name=player_name, level_str=level_str)

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, amount, source, template_key_suffix, default_template_format", [
    ("en", 100, "defeating a goblin", "with_source", "{player_name} gained {amount_str} {xp_term} {source_str}."),
    ("ru", 100, "победа над гоблином", "with_source", "{player_name} получил(а) {amount_str} {xp_term} {source_str}."),
    ("en", 50, None, "simple", "{player_name} gained {amount_str} {xp_term}."),
    ("ru", 50, None, "simple", "{player_name} получил(а) {amount_str} {xp_term}."),
    ("en", None, "a mysterious event", "with_source", "{player_name} gained {amount_str} {xp_term} {source_str}."),
])
async def test_format_xp_gained(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, amount, source, template_key_suffix, default_template_format):
    player_key = ("player", 1)
    template_key = f"terms.character.xp_gained_{template_key_suffix}_{lang}"
    
    term_map = {
        template_key: {lang: default_template_format},
        f"terms.character.xp_{lang}": {lang: "XP" if lang == "en" else "опыта"},
        f"terms.character.some_xp_{lang}": {lang: "some" if lang == "en" else "немного"}
    }
    if source:
        term_map[f"terms.character.from_source_{lang}"] = {lang: "from {source}" if lang == "en" else "из {source}"}

    mock_get_rule_fixture.set_map_for_test(term_map)

    log_details = {
        "guild_id": 1, "event_type": EventType.XP_GAINED.value,
        "player_id": player_key[1], "amount": amount
    }
    if source:
        log_details["source"] = source

    player_name = mock_names_cache_fixture[player_key]
    amount_str = str(amount) if amount is not None else ("some" if lang == "en" else "немного")
    xp_term = "XP" if lang == "en" else "опыта"
    
    if source:
        source_term_template = "from {source}" if lang == "en" else "из {source}"
        source_str_rendered = source_term_template.format(source=source)
        expected_msg = default_template_format.format(player_name=player_name, amount_str=amount_str, xp_term=xp_term, source_str=source_str_rendered)
    else:
        expected_msg = default_template_format.format(player_name=player_name, amount_str=amount_str, xp_term=xp_term)

    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, new_value, reason, e1_key, e2_key", [
    ("en", 50, "completed a task", ("player", 1), ("npc", 601)),
    ("ru", -20, "оскорбление", ("npc", 601), ("player", 2)),
    ("en", 0, None, ("player", 1), ("player", 2)), 
    ("ru", None, "таинственное событие", ("quest", 501), ("location", 101)), 
])
async def test_format_relationship_change(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, new_value, reason, e1_key, e2_key):
    term_map = {
        f"terms.relationships.relation_between_{lang}": {lang: "Relationship between {e1_name} and {e2_name}" if lang == "en" else "Отношения между {e1_name} и {e2_name}"},
        f"terms.relationships.is_now_{lang}": {lang: "is now {value_str}" if lang == "en" else "теперь {value_str}"},
        f"terms.relationships.an_unknown_level_{lang}": {lang: "an unknown level" if lang == "en" else "неизвестного уровня"},
        f"terms.general.one_entity_{lang}": {lang: "One entity", "ru": "Одна сущность"}, 
        f"terms.general.another_entity_{lang}": {lang: "another entity", "ru": "другой сущностью"}, 
    }
    if reason:
        term_map[f"terms.relationships.due_to_reason_{lang}"] = {lang: "due to: {change_reason}" if lang == "en" else "по причине: {change_reason}"}
    
    mock_get_rule_fixture.set_map_for_test(term_map)

    log_details = {
        "guild_id": 1, "event_type": EventType.RELATIONSHIP_CHANGE.value,
        "entity1": {"type": e1_key[0], "id": e1_key[1]},
        "entity2": {"type": e2_key[0], "id": e2_key[1]},
        "new_value": new_value
    }
    if reason:
        log_details["change_reason"] = reason

    e1_name = mock_names_cache_fixture.get(e1_key, "One entity" if lang=="en" else "Одна сущность")
    e2_name = mock_names_cache_fixture.get(e2_key, "another entity" if lang=="en" else "другой сущностью")
    value_str = str(new_value) if new_value is not None else ("an unknown level" if lang == "en" else "неизвестного уровня")

    relation_between_fmt = "Relationship between {e1_name} and {e2_name}" if lang == "en" else "Отношения между {e1_name} и {e2_name}"
    is_now_fmt = "is now {value_str}" if lang == "en" else "теперь {value_str}"
    
    expected_msg = f"{relation_between_fmt.format(e1_name=e1_name, e2_name=e2_name)} {is_now_fmt.format(value_str=value_str)}"
    if reason:
        due_to_reason_fmt = "due to: {change_reason}" if lang == "en" else "по причине: {change_reason}"
        expected_msg += f" ({due_to_reason_fmt.format(change_reason=reason)})."
    else:
        expected_msg += "."
        
    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("lang, duration, source_info, target_key, status_key", [
    ("en", 3, {"type": "ability", "id": 301}, ("player", 1), ("status_effect", 401)), 
    ("ru", None, {"name": "Ловушка с ядом"}, ("npc", 601), ("status_effect", 402)), 
    ("en", 5, None, ("player", 2), ("status_effect", 401)), 
    ("ru", 2, {"type": "item", "id": 999}, ("npc", 602), ("status_effect", 402)), 
])
async def test_format_status_applied(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, duration, source_info, target_key, status_key):
    term_map = {
        f"terms.statuses.is_now_affected_by_{lang}": {lang: "is now affected by" if lang == "en" else "теперь под действием"},
        f"terms.statuses.a_status_effect_{lang}": {lang: "a status effect" if lang == "en" else "эффект состояния"},
        f"terms.general.someone_{lang}": {lang: "Someone", "ru": "Некто"},
    }
    if duration:
        term_map[f"terms.statuses.for_duration_{lang}"] = {lang: "for {duration_turns} turns" if lang == "en" else "на {duration_turns} ходов"}
    if source_info:
        term_map[f"terms.statuses.from_source_{lang}"] = {lang: "from" if lang == "en" else "от"}
        if not (source_info.get("id") and source_info.get("type")) and not source_info.get("name"):
             term_map[f"terms.statuses.an_unknown_source_{lang}"] = {lang: "an unknown source" if lang == "en" else "неизвестного источника"}

    mock_get_rule_fixture.set_map_for_test(term_map)

    log_details = {
        "guild_id": 1, "event_type": EventType.STATUS_APPLIED.value,
        "target_entity": {"type": target_key[0], "id": target_key[1]},
        "status_effect": {"id": status_key[1]},
    }
    if duration is not None:
        log_details["duration_turns"] = duration
    if source_info:
        log_details["source_entity"] = source_info

    target_name = mock_names_cache_fixture.get(target_key, "Someone" if lang=="en" else "Некто")
    status_name = mock_names_cache_fixture.get(status_key, "a status effect" if lang=="en" else "эффект состояния")

    msg_parts = [target_name]
    is_now_affected_by = "is now affected by" if lang == "en" else "теперь под действием"
    msg_parts.extend([is_now_affected_by, f"'{status_name}'"])

    if duration is not None:
        for_duration_fmt = "for {duration_turns} turns" if lang == "en" else "на {duration_turns} ходов"
        msg_parts.append(for_duration_fmt.format(duration_turns=duration))

    if source_info:
        from_source_term = "from" if lang == "en" else "от"
        msg_parts.append(from_source_term)
        source_id = source_info.get("id")
        source_type = source_info.get("type")
        source_name_direct = source_info.get("name")
        
        source_display_name_val = ""
        if source_id and source_type:
            sut_source_placeholder = f"[{str(source_type).capitalize()} ID: {source_id} (Cached?)]"
            source_display_name_val = mock_names_cache_fixture.get((str(source_type).lower(), source_id), sut_source_placeholder)
            msg_parts.append(f"'{source_display_name_val}'")
        elif source_name_direct:
            msg_parts.append(f"'{source_name_direct}'")
        else:
            msg_parts.append("an unknown source" if lang == "en" else "неизвестного источника")
            
    msg_parts.append(".")
    expected_msg = " ".join(msg_parts)
        
    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)
    assert result == expected_msg