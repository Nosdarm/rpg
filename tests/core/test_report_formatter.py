# tests/core/test_report_formatter.py
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from sqlalchemy.ext.asyncio import AsyncSession

# Updated import: _format_log_entry_with_names_cache instead of format_log_entry
from src.core.report_formatter import _format_log_entry_with_names_cache, format_turn_report
# Assuming EventType enum might be used or its string equivalent
# from src.models.enums import EventType

# Default IDs for mocking
DEFAULT_GUILD_ID = 100
DEFAULT_PLAYER_ID = 1
DEFAULT_LANG = "en"

@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)

# --- Tests for _format_log_entry_with_names_cache ---

@pytest.mark.asyncio
async def test_format_log_entry_cache_player_move(mock_session: AsyncSession): # Removed mock_get_name
    log_details = {
        "guild_id": DEFAULT_GUILD_ID,
        "event_type": "PLAYER_MOVE",
        "player_id": DEFAULT_PLAYER_ID,
        "old_location_id": 10,
        "new_location_id": 11
    }
    names_cache_en = {
        ("player", DEFAULT_PLAYER_ID): "TestPlayer",
        ("location", 10): "Old Tavern",
        ("location", 11): "New Market"
    }
    names_cache_ru = {
        ("player", DEFAULT_PLAYER_ID): "ТестИгрок", # Assuming different names for RU for test clarity
        ("location", 10): "Старая Таверна",
        ("location", 11): "Новый Рынок"
    }

    # English
    result_en = await _format_log_entry_with_names_cache(log_details, "en", names_cache_en)
    assert result_en == "TestPlayer moved from 'Old Tavern' to 'New Market'."

    # Russian
    result_ru = await _format_log_entry_with_names_cache(log_details, "ru", names_cache_ru)
    assert result_ru == "ТестИгрок переместился из 'Старая Таверна' в 'Новый Рынок'."

@pytest.mark.asyncio
async def test_format_log_entry_cache_player_action_examine(mock_session: AsyncSession):
    log_details = {
        "guild_id": DEFAULT_GUILD_ID,
        "event_type": "PLAYER_ACTION",
        "actor": {"id": DEFAULT_PLAYER_ID, "type": "player"},
        "action": {"intent": "examine", "entities": [{"name": "Mysterious Chest"}]},
        "result": {"description": "a sturdy oak chest, tightly shut."}
    }
    names_cache_en = {("player", DEFAULT_PLAYER_ID): "Adventurer"}
    names_cache_ru = {("player", DEFAULT_PLAYER_ID): "Авантюрист"}

    # English
    result_en = await _format_log_entry_with_names_cache(log_details, "en", names_cache_en)
    assert result_en == "Adventurer examines 'Mysterious Chest'. You see: a sturdy oak chest, tightly shut."

    # Russian
    result_ru = await _format_log_entry_with_names_cache(log_details, "ru", names_cache_ru)
    assert result_ru == "Авантюрист осматривает 'Mysterious Chest'. Вы видите: a sturdy oak chest, tightly shut."

@pytest.mark.asyncio
async def test_format_log_entry_cache_item_acquired(mock_session: AsyncSession):
    log_details = {
        "guild_id": DEFAULT_GUILD_ID,
        "event_type": "ITEM_ACQUIRED",
        "player_id": DEFAULT_PLAYER_ID,
        "item_id": 55,
        "quantity": 2,
        "source": "a dusty chest"
    }
    names_cache_en = {
        ("player", DEFAULT_PLAYER_ID): "Hero",
        ("item", 55): "Gold Coin"
    }
    result_en = await _format_log_entry_with_names_cache(log_details, "en", names_cache_en)
    assert result_en == "Hero acquired Gold Coin (x2) from a dusty chest."

@pytest.mark.asyncio
async def test_format_log_entry_cache_combat_action_with_damage(mock_session: AsyncSession):
    log_details = {
        "guild_id": DEFAULT_GUILD_ID,
        "event_type": "COMBAT_ACTION",
        "actor": {"id": DEFAULT_PLAYER_ID, "type": "player"},
        "target": {"id": 1, "type": "npc"},
        "action_name": "Power Attack",
        "damage": 15
    }
    names_cache_en = {
        ("player", DEFAULT_PLAYER_ID): "Warrior",
        ("npc", 1): "Goblin"
    }
    result_en = await _format_log_entry_with_names_cache(log_details, "en", names_cache_en)
    assert result_en == "Warrior uses 'Power Attack' on Goblin, dealing 15 damage."

@pytest.mark.asyncio
async def test_format_log_entry_cache_missing_guild_id(mock_session: AsyncSession):
    log_details = {"event_type": "PLAYER_MOVE"} # guild_id is missing
    # names_cache is not strictly needed here as it should error out before using it.
    result = await _format_log_entry_with_names_cache(log_details, "en", {})
    assert "Error: Missing guild information" in result

@pytest.mark.asyncio
async def test_format_log_entry_cache_unknown_event_type(mock_session: AsyncSession):
    log_details = {"guild_id": DEFAULT_GUILD_ID, "event_type": "SUPER_SECRET_EVENT"}
    result_en = await _format_log_entry_with_names_cache(log_details, "en", {})
    assert "Event of type 'SUPER_SECRET_EVENT' occurred." in result_en
    result_ru = await _format_log_entry_with_names_cache(log_details, "ru", {})
    assert "Произошло событие типа 'SUPER_SECRET_EVENT'." in result_ru


# --- Tests for format_turn_report ---

@pytest.mark.asyncio
@patch("src.core.report_formatter._format_log_entry_with_names_cache", new_callable=AsyncMock)
@patch("src.core.report_formatter.get_batch_localized_entity_names", new_callable=AsyncMock)
async def test_format_turn_report_single_entry(
    mock_get_batch_names: AsyncMock,
    mock_format_log_entry_cache: AsyncMock,
    mock_session: AsyncSession
):
    mock_format_log_entry_cache.return_value = "Formatted Event 1"
    mock_get_batch_names.return_value = {("player", DEFAULT_PLAYER_ID): "TestPlayer"} # For header

    log_entries = [{"guild_id": DEFAULT_GUILD_ID, "event_type": "TEST_EVENT_1"}]
    fallback_lang = "en" # Define fallback language for the test call

    result_en = await format_turn_report(mock_session, DEFAULT_GUILD_ID, log_entries, DEFAULT_PLAYER_ID, "en", fallback_lang)
    assert result_en == f"Turn Report for TestPlayer:\nFormatted Event 1"
    # Verify _collect_entity_refs_from_log_entry would be called internally, then get_batch_localized_entity_names
    # Then _format_log_entry_with_names_cache is called with the cache
    mock_get_batch_names.assert_called_once() # Was called to build names_cache
    # The actual log_entries[0] is passed to _format_log_entry_with_names_cache
    mock_format_log_entry_cache.assert_called_once_with(log_entries[0], "en", mock_get_batch_names.return_value)


    mock_format_log_entry_cache.reset_mock() # Corrected mock name
    mock_get_batch_names.reset_mock()
    mock_format_log_entry_cache.return_value = "Отформатированное Событие 1" # Corrected mock name
    mock_get_batch_names.return_value = {("player", DEFAULT_PLAYER_ID): "ТестИгрок"} # For header

    result_ru = await format_turn_report(mock_session, DEFAULT_GUILD_ID, log_entries, DEFAULT_PLAYER_ID, "ru", fallback_lang)
    assert result_ru == f"Отчет по ходу для ТестИгрок:\nОтформатированное Событие 1"
    mock_get_batch_names.assert_called_once()
    mock_format_log_entry_cache.assert_called_once_with(log_entries[0], "ru", mock_get_batch_names.return_value)


@pytest.mark.asyncio
@patch("src.core.report_formatter._format_log_entry_with_names_cache", new_callable=AsyncMock)
@patch("src.core.report_formatter.get_batch_localized_entity_names", new_callable=AsyncMock)
async def test_format_turn_report_multiple_entries(
    mock_get_batch_names: AsyncMock,
    mock_format_log_entry_cache: AsyncMock,
    mock_session: AsyncSession
):
    log_entries = [
        {"guild_id": DEFAULT_GUILD_ID, "event_type": "EVENT_A", "player_id": 1}, # Added player_id for ref collection
        {"guild_id": DEFAULT_GUILD_ID, "event_type": "EVENT_B", "actor": {"id": 2, "type": "npc"}} # Added actor for ref collection
    ]
    mock_format_log_entry_cache.side_effect = ["Formatted A", "Formatted B"]
    # Simulate names_cache for player header and any other entities if needed
    mock_get_batch_names.return_value = {
        ("player", DEFAULT_PLAYER_ID): "TestPlayer", # For header
        ("player", 1): "PlayerA",
        ("npc", 2): "NPC_B"
    }
    fallback_lang = "en"

    result = await format_turn_report(mock_session, DEFAULT_GUILD_ID, log_entries, DEFAULT_PLAYER_ID, "en", fallback_lang)
    assert result == f"Turn Report for PlayerA:\nFormatted A\nFormatted B" # Changed TestPlayer to PlayerA

    # Check that get_batch_localized_entity_names was called once with all refs
    # The exact refs depend on _collect_entity_refs_from_log_entry logic,
    # which is implicitly tested here. We can verify the call count.
    mock_get_batch_names.assert_called_once()
    # We can make the assertion on collected_refs more specific if needed, by inspecting args of mock_get_batch_names

    expected_calls_to_formatter = [
        call(log_entries[0], "en", mock_get_batch_names.return_value),
        call(log_entries[1], "en", mock_get_batch_names.return_value)
    ]
    mock_format_log_entry_cache.assert_has_calls(expected_calls_to_formatter)

@pytest.mark.asyncio
@patch("src.core.report_formatter.get_batch_localized_entity_names", new_callable=AsyncMock) # Still need to mock this
async def test_format_turn_report_empty_log(mock_get_batch_names: AsyncMock, mock_session: AsyncSession):
    fallback_lang = "en"
    result_en = await format_turn_report(mock_session, DEFAULT_GUILD_ID, [], DEFAULT_PLAYER_ID, "en", fallback_lang)
    assert result_en == "Nothing significant happened this turn."
    mock_get_batch_names.assert_not_called() # Should not be called for empty logs

    result_ru = await format_turn_report(mock_session, DEFAULT_GUILD_ID, [], DEFAULT_PLAYER_ID, "ru", fallback_lang)
    assert result_ru == "За этот ход ничего значительного не произошло."
    mock_get_batch_names.assert_not_called()


@pytest.mark.asyncio
@patch("src.core.report_formatter._format_log_entry_with_names_cache", new_callable=AsyncMock)
@patch("src.core.report_formatter.get_batch_localized_entity_names", new_callable=AsyncMock)
async def test_format_turn_report_injects_guild_id_if_missing_in_entry(
    mock_get_batch_names: AsyncMock,
    mock_format_log_entry_cache: AsyncMock,
    mock_session: AsyncSession
):
    log_entries = [{"event_type": "SOME_EVENT"}] # Missing guild_id
    mock_format_log_entry_cache.return_value = "Formatted Event With Injected GuildID"
    mock_get_batch_names.return_value = {("player", DEFAULT_PLAYER_ID): "TestPlayer"} # For header
    fallback_lang = "en"

    await format_turn_report(mock_session, DEFAULT_GUILD_ID, log_entries, DEFAULT_PLAYER_ID, "en", fallback_lang)

    expected_details_arg = {"event_type": "SOME_EVENT", "guild_id": DEFAULT_GUILD_ID}
    # _collect_entity_refs_from_log_entry will be called with original entry
    # then get_batch_localized_entity_names
    # then _format_log_entry_with_names_cache
    mock_format_log_entry_cache.assert_called_once_with(
        expected_details_arg, "en", mock_get_batch_names.return_value
    )

@pytest.mark.asyncio
@patch("src.core.report_formatter._format_log_entry_with_names_cache", new_callable=AsyncMock)
@patch("src.core.report_formatter.get_batch_localized_entity_names", new_callable=AsyncMock)
async def test_format_turn_report_skips_mismatched_guild_id_entry(
    mock_get_batch_names: AsyncMock,
    mock_format_log_entry_cache: AsyncMock,
    mock_session: AsyncSession
):
    log_entries = [
        {"guild_id": DEFAULT_GUILD_ID, "event_type": "GOOD_EVENT"},
        {"guild_id": 999, "event_type": "BAD_EVENT_WRONG_GUILD"},
        {"guild_id": DEFAULT_GUILD_ID, "event_type": "ANOTHER_GOOD_EVENT"}
    ]
    mock_format_log_entry_cache.side_effect = ["Formatted Good Event 1", "Formatted Good Event 2"]
    mock_get_batch_names.return_value = {("player", DEFAULT_PLAYER_ID): "TestPlayer"} # For header
    fallback_lang = "en"

    result = await format_turn_report(mock_session, DEFAULT_GUILD_ID, log_entries, DEFAULT_PLAYER_ID, "en", fallback_lang)

    assert "Formatted Good Event 1" in result
    assert "Formatted Good Event 2" in result
    assert "BAD_EVENT_WRONG_GUILD" not in result

    assert mock_format_log_entry_cache.call_count == 2
    # _collect_entity_refs_from_log_entry will process all, but get_batch_localized_entity_names
    # will be called with refs from good events.
    # Then _format_log_entry_with_names_cache is called only for good events.
    expected_calls_to_formatter = [
        call(log_entries[0], "en", mock_get_batch_names.return_value),
        call(log_entries[2], "en", mock_get_batch_names.return_value)
    ]
    mock_format_log_entry_cache.assert_has_calls(expected_calls_to_formatter)

