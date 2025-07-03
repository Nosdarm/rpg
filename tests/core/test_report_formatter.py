import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Tuple, Any, List # Added List, Tuple, Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.report_formatter import format_turn_report, _format_log_entry_with_names_cache, _collect_entity_refs_from_log_entry
from src.models.enums import EventType # Для создания тестовых логов

# Фикстуры

@pytest.fixture
def mock_session() -> AsyncMock:
    """Мок для AsyncSession."""
    return AsyncMock(spec=AsyncSession)

@pytest.fixture
def mock_names_cache_fixture() -> Dict[Tuple[str, int], str]: # Renamed to avoid conflict
    """Базовый мок для кеша имен, используемый в некоторых тестах _format_log_entry."""
    return {
        ("player", 1): "TestPlayer", ("player", 2): "Another Player",
        ("location", 101): "Old Location", ("location", 102): "New Location",
        ("item", 201): "Magic Sword",
        ("ability", 301): "Fireball", ("ability", 302): "Heal",
        ("status_effect", 401): "Burning", ("status_effect", 402): "Regeneration",
        ("quest", 501): "Main Quest", ("quest", 502): "Side Quest",
        ("npc", 601): "Goblin", ("npc", 602): "Ogre",
    }

@pytest.fixture
def mock_get_rule_fixture(): # Renamed
    """Мок для функции get_rule. По умолчанию возвращает default."""
    async def _mock_get_rule(session, guild_id, key, default=None):
        # Эта логика позволяет моку быть более гибким в тестах
        # Можно установить 'custom_rules_map' на моке в тесте для имитации разных правил
        if hasattr(_mock_get_rule, 'custom_rules_map') and key in _mock_get_rule.custom_rules_map:
            rule_value = _mock_get_rule.custom_rules_map[key]
            # Если правило это словарь (для i18n), и default тоже словарь (с ключом языка)
            if isinstance(rule_value, dict) and isinstance(default, dict):
                lang_key = list(default.keys())[0] # Предполагаем, что default содержит язык как ключ
                return rule_value.get(lang_key, list(default.values())[0])
            return rule_value # Возвращаем как есть, если не i18n или default не словарь

        # Если default - это словарь, предполагаем i18n и возвращаем его значение для первого ключа
        if isinstance(default, dict):
            return list(default.values())[0]
        return default

    mock_fn = AsyncMock(side_effect=_mock_get_rule)
    mock_fn.custom_rules_map = {} # Можно заполнить в тестах
    return mock_fn


@pytest.fixture
def mock_get_batch_localized_entity_names_fixture(): # Renamed
    """Мок для get_batch_localized_entity_names."""
    async def _mock_batch_names(session, guild_id, entity_refs, language, fallback_language):
        cache: Dict[Tuple[str, int], str] = {}
        # Используем mock_names_cache_fixture для простоты, но можно сделать более сложную логику
        # для имитации разных языков или отсутствующих имен, если нужно.
        # Эта фикстура будет предоставлять "базовые" имена.
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


# Тесты для _collect_entity_refs_from_log_entry
# (оставляем существующие тесты для _collect_entity_refs_from_log_entry, они полезны)
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

# ... (остальные тесты для _collect_entity_refs_from_log_entry остаются как есть) ...
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


# Тесты для _format_log_entry_with_names_cache
@pytest.mark.asyncio
async def test_format_player_action_examine_en_with_terms(mock_session, mock_names_cache_fixture, mock_get_rule_fixture):
    mock_get_rule_fixture.custom_rules_map = {
        "terms.actions.examine.verb_en": {"en": "inspects"},
        "terms.actions.examine.sees_en": {"en": "Observations"},
        "terms.results.nothing_special_en": {"en": "it is empty"}
    }
    log_details = {
        "guild_id": 1, "event_type": EventType.PLAYER_ACTION.value,
        "actor": {"type": "player", "id": 1},
        "action": {"intent": "examine", "entities": [{"name": "a Dusty Box"}]},
        "result": {"description": "it is empty"} # This should match the term for full effect
    }
    # Patch get_rule within the scope of this test using the fixture
    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, "en", mock_names_cache_fixture)
    assert "TestPlayer inspects 'a Dusty Box'. Observations: it is empty" in result

@pytest.mark.asyncio
async def test_format_player_action_examine_ru_default_terms(mock_session, mock_names_cache_fixture, mock_get_rule_fixture):
    # No custom rules, so defaults from _format_log_entry should be used via get_term's default
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
    mock_get_rule_fixture.custom_rules_map = {
        "terms.combat.outcomes.victory_players_ru": {"ru": "победа игроков"},
        "terms.combat.ended_ru": {"ru": "Схватка в '{location_name}' окончена. Результат: {outcome_readable}."},
        "terms.combat.survivors_ru": {"ru": " Уцелевшие: {survivors_str}."}
    }
    log_details = {
        "guild_id": 1, "event_type": EventType.COMBAT_END.value,
        "location_id": 101, "outcome": "victory_players",
        "survivors": [{"type": "player", "id": 1}, {"type": "npc", "id": 602}]
    }
    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, "ru", mock_names_cache_fixture)
    assert "Схватка в 'Old Location' окончена. Результат: победа игроков. Уцелевшие: TestPlayer, Ogre." in result


# Тесты для format_turn_report
@pytest.mark.asyncio
async def test_format_turn_report_empty_logs_integration(mock_session, mock_get_batch_localized_entity_names_fixture):
    # Используем фикстуру для get_batch_localized_entity_names
    with patch('src.core.report_formatter.get_batch_localized_entity_names', new=mock_get_batch_localized_entity_names_fixture):
        report_en = await format_turn_report(mock_session, 1, [], 1, "en")
        assert "Nothing significant happened this turn." in report_en
        report_ru = await format_turn_report(mock_session, 1, [], 1, "ru")
        assert "За этот ход ничего значительного не произошло." in report_ru

@pytest.mark.asyncio
async def test_format_turn_report_with_logs_integration(mock_session, mock_get_rule_fixture, mock_get_batch_localized_entity_names_fixture):
    log_entries = [
        {"guild_id": 1, "event_type": EventType.MOVEMENT.value, "player_id": 1, "old_location_id": 101, "new_location_id": 102}, # Changed to MOVEMENT
        {"guild_id": 1, "event_type": EventType.ITEM_ACQUIRED.value, "player_id": 1, "item_id": 201, "source": "a chest"}
    ]

    # Патчим обе зависимости
    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture), \
         patch('src.core.report_formatter.get_batch_localized_entity_names', new=mock_get_batch_localized_entity_names_fixture):

        report_en = await format_turn_report(mock_session, 1, log_entries, 1, "en", "en")

    assert "Turn Report for PlayerOne:" in report_en
    assert "PlayerOne moved from 'Old Town' to 'New City'." in report_en # Проверяем использование имен из mock_get_batch_localized_entity_names_fixture
    assert "PlayerOne acquired Sword of Testing (x1) from a chest." in report_en

    # Проверка для русского языка
    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture), \
         patch('src.core.report_formatter.get_batch_localized_entity_names', new=mock_get_batch_localized_entity_names_fixture):

        report_ru = await format_turn_report(mock_session, 1, log_entries, 1, "ru", "en")

    assert "Отчет по ходу для ИгрокОдин:" in report_ru
    assert "ИгрокОдин переместился из 'Старый Город' в 'Новый Город'." in report_ru
    assert "ИгрокОдин получает Меч Тестирования (x1) из a chest." in report_ru # "a chest" не было локализовано через get_term в примере


# Дополнительные тесты для различных event_type с проверкой RuleConfig
@pytest.mark.asyncio
@pytest.mark.parametrize("lang, expected_verb, expected_particle", [
    ("en", "uses ability", "on"),
    ("ru", "использует способность", "на")
])
async def test_format_ability_used_with_terms(mock_session, mock_names_cache_fixture, mock_get_rule_fixture, lang, expected_verb, expected_particle):
    mock_get_rule_fixture.custom_rules_map = {
        f"terms.abilities.verb_uses_{lang}": {lang: expected_verb},
        f"terms.abilities.particle_on_{lang}": {lang: expected_particle},
        f"terms.general.no_target_{lang}": {lang: "nobody" if lang == "en" else "ни на кого"}
    }
    log_details = {
        "guild_id": 1, "event_type": EventType.ABILITY_USED.value,
        "actor_entity": {"type": "player", "id": 1},
        "ability": {"id": 301}, # Fireball
        "targets": [], # No specific target
        "outcome": {"description": "The air crackles." if lang == "en" else "Воздух трещит."}
    }
    with patch('src.core.report_formatter.get_rule', new=mock_get_rule_fixture):
        result = await _format_log_entry_with_names_cache(mock_session, log_details, lang, mock_names_cache_fixture)

    actor_name = mock_names_cache_fixture[("player", 1)]
    ability_name = mock_names_cache_fixture[("ability", 301)]
    no_target_str = "nobody" if lang == "en" else "ни на кого"
    outcome_str = "The air crackles." if lang == "en" else "Воздух трещит."

    expected_string = f"{actor_name} {expected_verb} '{ability_name}' {expected_particle} {no_target_str}. {outcome_str}"
    assert expected_string in result
