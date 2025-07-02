# tests/core/test_report_formatter.py
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.report_formatter import format_log_entry, format_turn_report
# Assuming EventType enum might be used or its string equivalent
# from src.models.enums import EventType

# Default IDs for mocking
DEFAULT_GUILD_ID = 100
DEFAULT_PLAYER_ID = 1
DEFAULT_LANG = "en"

@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)

# --- Tests for format_log_entry ---

@pytest.mark.asyncio
@patch("src.core.report_formatter.get_localized_entity_name", new_callable=AsyncMock)
async def test_format_log_entry_player_move(
    mock_get_name: AsyncMock,
    mock_session: AsyncSession
):
    log_details = {
        "guild_id": DEFAULT_GUILD_ID,
        "event_type": "PLAYER_MOVE", # Using string as per implementation
        "player_id": DEFAULT_PLAYER_ID,
        "old_location_id": 10,
        "new_location_id": 11
    }

    async def name_side_effect(session, guild_id, entity_type, entity_id, lang, fallback_lang="en"):
        if entity_type == "player" and entity_id == DEFAULT_PLAYER_ID: return "TestPlayer"
        if entity_type == "location" and entity_id == 10: return "Old Tavern"
        if entity_type == "location" and entity_id == 11: return "New Market"
        return f"Unknown_{entity_type}_{entity_id}"
    mock_get_name.side_effect = name_side_effect

    # English
    result_en = await format_log_entry(mock_session, log_details, "en")
    assert result_en == "TestPlayer moved from 'Old Tavern' to 'New Market'."

    # Russian
    result_ru = await format_log_entry(mock_session, log_details, "ru")
    assert result_ru == "TestPlayer переместился из 'Old Tavern' в 'New Market'."

    assert mock_get_name.call_count == 6 # 3 for en, 3 for ru

@pytest.mark.asyncio
@patch("src.core.report_formatter.get_localized_entity_name", new_callable=AsyncMock)
async def test_format_log_entry_player_action_examine(
    mock_get_name: AsyncMock,
    mock_session: AsyncSession
):
    log_details = {
        "guild_id": DEFAULT_GUILD_ID,
        "event_type": "PLAYER_ACTION",
        "actor": {"id": DEFAULT_PLAYER_ID, "type": "player"},
        "action": {"intent": "examine", "entities": [{"name": "Mysterious Chest"}]}, # Target name from NLU
        "result": {"description": "a sturdy oak chest, tightly shut."} # Result from interaction_handler
    }
    mock_get_name.return_value = "Adventurer" # For the player

    # English
    result_en = await format_log_entry(mock_session, log_details, "en")
    assert result_en == "Adventurer examines 'Mysterious Chest'. You see: a sturdy oak chest, tightly shut."
    mock_get_name.assert_called_once_with(mock_session, DEFAULT_GUILD_ID, "player", DEFAULT_PLAYER_ID, "en")

    mock_get_name.reset_mock()
    mock_get_name.return_value = "Авантюрист"
    # Russian
    result_ru = await format_log_entry(mock_session, log_details, "ru")
    assert result_ru == "Авантюрист осматривает 'Mysterious Chest'. Вы видите: a sturdy oak chest, tightly shut." # Desc not localized here
    mock_get_name.assert_called_once_with(mock_session, DEFAULT_GUILD_ID, "player", DEFAULT_PLAYER_ID, "ru")

@pytest.mark.asyncio
@patch("src.core.report_formatter.get_localized_entity_name", new_callable=AsyncMock)
async def test_format_log_entry_item_acquired(
    mock_get_name: AsyncMock,
    mock_session: AsyncSession
):
    log_details = {
        "guild_id": DEFAULT_GUILD_ID,
        "event_type": "ITEM_ACQUIRED",
        "player_id": DEFAULT_PLAYER_ID,
        "item_id": 55,
        "quantity": 2,
        "source": "a dusty chest"
    }
    async def name_side_effect(session, guild_id, entity_type, entity_id, lang, fallback_lang="en"):
        if entity_type == "player": return "Hero"
        if entity_type == "item": return "Gold Coin"
        return "Unknown"
    mock_get_name.side_effect = name_side_effect

    result_en = await format_log_entry(mock_session, log_details, "en")
    assert result_en == "Hero acquired Gold Coin (x2) from a dusty chest."

@pytest.mark.asyncio
@patch("src.core.report_formatter.get_localized_entity_name", new_callable=AsyncMock)
async def test_format_log_entry_combat_action_with_damage(
    mock_get_name: AsyncMock,
    mock_session: AsyncSession
):
    log_details = {
        "guild_id": DEFAULT_GUILD_ID,
        "event_type": "COMBAT_ACTION",
        "actor": {"id": DEFAULT_PLAYER_ID, "type": "player"},
        "target": {"id": 1, "type": "npc"},
        "action_name": "Power Attack",
        "damage": 15
    }
    async def name_side_effect(session, guild_id, entity_type, entity_id, lang, fallback_lang="en"):
        if entity_type == "player" and entity_id == DEFAULT_PLAYER_ID: return "Warrior"
        if entity_type == "npc" and entity_id == 1: return "Goblin"
        return "Unknown"
    mock_get_name.side_effect = name_side_effect

    result_en = await format_log_entry(mock_session, log_details, "en")
    assert result_en == "Warrior uses 'Power Attack' on Goblin, dealing 15 damage."

@pytest.mark.asyncio
async def test_format_log_entry_missing_guild_id(mock_session: AsyncSession):
    log_details = {"event_type": "PLAYER_MOVE"}
    result = await format_log_entry(mock_session, log_details, "en")
    assert "Error: Missing guild information" in result

@pytest.mark.asyncio
async def test_format_log_entry_unknown_event_type(mock_session: AsyncSession):
    log_details = {"guild_id": DEFAULT_GUILD_ID, "event_type": "SUPER_SECRET_EVENT"}
    result = await format_log_entry(mock_session, log_details, "en")
    assert "Event of type 'SUPER_SECRET_EVENT' occurred." in result
    result_ru = await format_log_entry(mock_session, log_details, "ru")
    assert "Произошло событие типа 'SUPER_SECRET_EVENT'." in result_ru


# --- Tests for format_turn_report ---

@pytest.mark.asyncio
@patch("src.core.report_formatter.format_log_entry", new_callable=AsyncMock)
async def test_format_turn_report_single_entry(
    mock_format_log_entry: AsyncMock,
    mock_session: AsyncSession
):
    mock_format_log_entry.return_value = "Formatted Event 1"
    log_entries = [{"guild_id": DEFAULT_GUILD_ID, "event_type": "TEST_EVENT_1"}]

    result_en = await format_turn_report(mock_session, DEFAULT_GUILD_ID, log_entries, DEFAULT_PLAYER_ID, "en")
    assert result_en == f"Turn Report for Player {DEFAULT_PLAYER_ID}:\nFormatted Event 1"
    mock_format_log_entry.assert_called_once_with(mock_session, log_entries[0], "en")

    mock_format_log_entry.reset_mock()
    mock_format_log_entry.return_value = "Отформатированное Событие 1"
    result_ru = await format_turn_report(mock_session, DEFAULT_GUILD_ID, log_entries, DEFAULT_PLAYER_ID, "ru")
    assert result_ru == f"Отчет по ходу для игрока {DEFAULT_PLAYER_ID}:\nОтформатированное Событие 1"
    mock_format_log_entry.assert_called_once_with(mock_session, log_entries[0], "ru")


@pytest.mark.asyncio
@patch("src.core.report_formatter.format_log_entry", new_callable=AsyncMock)
async def test_format_turn_report_multiple_entries(
    mock_format_log_entry: AsyncMock,
    mock_session: AsyncSession
):
    log_entries = [
        {"guild_id": DEFAULT_GUILD_ID, "event_type": "EVENT_A"},
        {"guild_id": DEFAULT_GUILD_ID, "event_type": "EVENT_B"}
    ]
    mock_format_log_entry.side_effect = ["Formatted A", "Formatted B"]

    result = await format_turn_report(mock_session, DEFAULT_GUILD_ID, log_entries, DEFAULT_PLAYER_ID, "en")
    assert result == f"Turn Report for Player {DEFAULT_PLAYER_ID}:\nFormatted A\nFormatted B"

    expected_calls = [
        call(mock_session, log_entries[0], "en"),
        call(mock_session, log_entries[1], "en")
    ]
    mock_format_log_entry.assert_has_calls(expected_calls)

@pytest.mark.asyncio
async def test_format_turn_report_empty_log(mock_session: AsyncSession):
    result_en = await format_turn_report(mock_session, DEFAULT_GUILD_ID, [], DEFAULT_PLAYER_ID, "en")
    assert result_en == "Nothing significant happened this turn."

    result_ru = await format_turn_report(mock_session, DEFAULT_GUILD_ID, [], DEFAULT_PLAYER_ID, "ru")
    assert result_ru == "За этот ход ничего значительного не произошло."

@pytest.mark.asyncio
@patch("src.core.report_formatter.format_log_entry", new_callable=AsyncMock)
async def test_format_turn_report_injects_guild_id_if_missing_in_entry(
    mock_format_log_entry: AsyncMock,
    mock_session: AsyncSession
):
    # Log entry details_json is missing guild_id
    log_entries = [{"event_type": "SOME_EVENT"}]
    mock_format_log_entry.return_value = "Formatted Event With Injected GuildID"

    await format_turn_report(mock_session, DEFAULT_GUILD_ID, log_entries, DEFAULT_PLAYER_ID, "en")

    # Verify that format_log_entry was called with the guild_id injected
    expected_details_arg = {"event_type": "SOME_EVENT", "guild_id": DEFAULT_GUILD_ID}
    mock_format_log_entry.assert_called_once_with(mock_session, expected_details_arg, "en")

@pytest.mark.asyncio
@patch("src.core.report_formatter.format_log_entry", new_callable=AsyncMock)
async def test_format_turn_report_skips_mismatched_guild_id_entry(
    mock_format_log_entry: AsyncMock,
    mock_session: AsyncSession
):
    log_entries = [
        {"guild_id": DEFAULT_GUILD_ID, "event_type": "GOOD_EVENT"},
        {"guild_id": 999, "event_type": "BAD_EVENT_WRONG_GUILD"}, # Mismatched guild_id
        {"guild_id": DEFAULT_GUILD_ID, "event_type": "ANOTHER_GOOD_EVENT"}
    ]

    # format_log_entry should only be called for good events
    mock_format_log_entry.side_effect = ["Formatted Good Event 1", "Formatted Good Event 2"]

    result = await format_turn_report(mock_session, DEFAULT_GUILD_ID, log_entries, DEFAULT_PLAYER_ID, "en")

    assert "Formatted Good Event 1" in result
    assert "Formatted Good Event 2" in result
    assert "BAD_EVENT_WRONG_GUILD" not in result # Check it didn't use the fallback for the bad one

    assert mock_format_log_entry.call_count == 2
    expected_calls = [
        call(mock_session, log_entries[0], "en"),
        call(mock_session, log_entries[2], "en")
    ]
    mock_format_log_entry.assert_has_calls(expected_calls)

