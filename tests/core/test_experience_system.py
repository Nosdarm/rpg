import sys
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock # Added MagicMock for casting
from typing import cast # Added cast

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.experience_system import award_xp, _check_for_level_up
from src.models import Player, Party, GuildConfig
from src.models.enums import RelationshipEntityType, EventType, PlayerStatus

# Фикстуры для правил из RuleConfig
@pytest.fixture
def mock_level_curve_rules_fixture():
    return [
        {"current_level": 1, "xp_to_reach_next_level": 100},
        {"current_level": 2, "xp_to_reach_next_level": 200},
        {"current_level": 3, "xp_to_reach_next_level": 300},
        {"current_level": 4, "xp_to_reach_next_level": 400}, # Для определения макс. уровня как 4 (переход на 5)
    ]

@pytest.fixture
def mock_level_up_rewards_rules_fixture():
    return {
        "default": {"attribute_points": 1},
        "2": {"attribute_points": 2, "notification_message_key": "level_2_great_success"},
        "3": {"attribute_points": 1, "skill_points": 1},
        "4": {"attribute_points": 1},
        "5": {"attribute_points": 3}, # Награда для 5-го уровня
    }

@pytest.fixture
def guild_id_fixture() -> int:
    return 123456789

@pytest.fixture
def mock_session_fixture() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    return session

@pytest.fixture
def player_fixture(guild_id_fixture: int) -> Player:
    return Player(
        id=1,
        guild_id=guild_id_fixture,
        discord_id=12345,
        name="Test Player",
        xp=0,
        level=1,
        unspent_xp=0,
        attributes_json={}, # Added default attributes_json
        current_status=PlayerStatus.IDLE
    )

@pytest.fixture
def party_fixture(guild_id_fixture: int, player_fixture: Player) -> Party:
    player_fixture.guild_id = guild_id_fixture
    player2 = Player(id=2, guild_id=guild_id_fixture, discord_id=67890, name="Player Two", xp=50, level=1, unspent_xp=0, current_status=PlayerStatus.IDLE)
    party = Party(
        id=1,
        guild_id=guild_id_fixture,
        name="Test Party",
        leader_player_id=player_fixture.id
    )
    party.players = [player_fixture, player2]
    return party


@pytest.mark.asyncio
@patch('src.core.experience_system.player_crud.get_by_id_and_guild', new_callable=AsyncMock)
@patch('src.core.experience_system.game_events.log_event', new_callable=AsyncMock)
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_award_xp_single_player_no_levelup(
    mock_get_rule: AsyncMock,
    mock_log_event: AsyncMock,
    mock_player_crud_get: AsyncMock,
    mock_session_fixture: AsyncSession,
    player_fixture: Player,
    mock_level_curve_rules_fixture,
    mock_level_up_rewards_rules_fixture,
    guild_id_fixture: int
):
    mock_player_crud_get.return_value = player_fixture
    mock_get_rule.side_effect = [mock_level_curve_rules_fixture, mock_level_up_rewards_rules_fixture]

    xp_to_award = 50
    updated_players = await award_xp(
        mock_session_fixture, guild_id_fixture, player_fixture.id, RelationshipEntityType.PLAYER, xp_to_award, EventType.SYSTEM_EVENT # Используем SYSTEM_EVENT
    )

    assert len(updated_players) == 1
    updated_player = updated_players[0]
    assert updated_player.id == player_fixture.id
    assert updated_player.xp == xp_to_award
    assert updated_player.level == 1
    assert updated_player.unspent_xp == 0

    mock_log_event.assert_any_call(
        session=mock_session_fixture,
        guild_id=guild_id_fixture,
        event_type=EventType.XP_GAINED.name, # Передаем .name
        details_json={
            "player_id": updated_player.id,
            "player_name": updated_player.name,
            "xp_awarded": xp_to_award,
            "new_total_xp": updated_player.xp,
            "source_event": EventType.SYSTEM_EVENT.name, # Используем .name
            "source_log_id": None,
        },
        entity_ids_json={"player_id": updated_player.id}
    )
    cast(AsyncMock, mock_session_fixture.commit).assert_called_once() # type: ignore
    cast(AsyncMock, mock_session_fixture.refresh).assert_called_once_with(updated_player) # type: ignore


@pytest.mark.asyncio
@patch('src.core.experience_system.game_events.log_event', new_callable=AsyncMock)
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_award_xp_single_player_level_up(
    mock_get_rule: AsyncMock,
    mock_log_event: AsyncMock,
    mock_session_fixture: AsyncSession,
    mock_level_curve_rules_fixture,
    mock_level_up_rewards_rules_fixture,
    guild_id_fixture: int
):
    player_for_levelup = Player(id=3, guild_id=guild_id_fixture, discord_id=111, name="Leveled Player", xp=90, level=1, unspent_xp=0, current_status=PlayerStatus.IDLE)

    with patch('src.core.experience_system.player_crud.get_by_id_and_guild', new_callable=AsyncMock, return_value=player_for_levelup) as mock_player_crud_get:
        mock_get_rule.side_effect = [
            mock_level_curve_rules_fixture,
            mock_level_up_rewards_rules_fixture
        ]

        xp_to_award = 20
        updated_players = await award_xp(
            mock_session_fixture, guild_id_fixture, player_for_levelup.id, RelationshipEntityType.PLAYER, xp_to_award, EventType.QUEST_COMPLETED
        )

        assert len(updated_players) == 1
        updated_player = updated_players[0]
        assert updated_player.xp == 10
        assert updated_player.level == 2
        assert updated_player.unspent_xp == mock_level_up_rewards_rules_fixture["2"]["attribute_points"]

    assert cast(AsyncMock, mock_log_event).call_count == 2
    cast(AsyncMock, mock_log_event).assert_any_call(
            session=mock_session_fixture, guild_id=guild_id_fixture, event_type=EventType.XP_GAINED.name, # .name
            details_json={
                "player_id": updated_player.id, "player_name": updated_player.name,
                "xp_awarded": xp_to_award, "new_total_xp": 90 + xp_to_award,
                "source_event": EventType.QUEST_COMPLETED.name, "source_log_id": None, # .name
            },
            entity_ids_json={"player_id": updated_player.id}
        )
    cast(AsyncMock, mock_log_event).assert_any_call(
            session=mock_session_fixture, guild_id=guild_id_fixture, event_type=EventType.LEVEL_UP.name, # .name
            details_json={
                "player_id": updated_player.id, "player_name": updated_player.name,
                "new_level": 2, "rewards_received": mock_level_up_rewards_rules_fixture["2"],
                "current_total_xp": updated_player.xp,
            },
            entity_ids_json={"player_id": updated_player.id}
        )
    cast(AsyncMock, mock_session_fixture.commit).assert_called_once() # type: ignore
    cast(AsyncMock, mock_session_fixture.refresh).assert_called_once_with(updated_player) # type: ignore

@pytest.mark.asyncio
@patch('src.core.experience_system.party_crud.get', new_callable=AsyncMock)
@patch('src.core.experience_system.game_events.log_event', new_callable=AsyncMock)
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_award_xp_party_equal_split_no_levelup(
    mock_get_rule: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud_get: AsyncMock,
    mock_session_fixture: AsyncSession,
    party_fixture: Party,
    mock_level_curve_rules_fixture,
    mock_level_up_rewards_rules_fixture,
    guild_id_fixture: int
):
    mock_party_crud_get.return_value = party_fixture
    mock_get_rule.side_effect = [
        mock_level_curve_rules_fixture, mock_level_up_rewards_rules_fixture,
        mock_level_curve_rules_fixture, mock_level_up_rewards_rules_fixture
    ]

    # Сбрасываем XP игроков в фикстуре для чистоты теста
    party_fixture.players[0].xp = 0
    party_fixture.players[1].xp = 50 # Оставим как есть для разнообразия
    initial_xp_player1 = party_fixture.players[0].xp
    initial_xp_player2 = party_fixture.players[1].xp


    xp_to_award_party = 100
    updated_players = await award_xp(
        mock_session_fixture, guild_id_fixture, party_fixture.id, RelationshipEntityType.PARTY, xp_to_award_party, EventType.COMBAT_END # Используем COMBAT_END
    )

    assert len(updated_players) == 2
    player1_updated = next(p for p in updated_players if p.id == party_fixture.players[0].id)
    player2_updated = next(p for p in updated_players if p.id == party_fixture.players[1].id)

    # Player 1 (player_fixture): xp 0 -> 50. Level 1. No level up.
    assert player1_updated.xp == initial_xp_player1 + 50
    assert player1_updated.level == 1
    assert player1_updated.unspent_xp == 0

    # Player 2: xp 50 -> 100. Level 1 -> 2 (needs 100 xp). Remaining xp = 0.
    assert player2_updated.xp == 0 # initial_xp_player2 (50) + 50 - 100 (cost of level 1->2)
    assert player2_updated.level == 2
    assert player2_updated.unspent_xp == mock_level_up_rewards_rules_fixture["2"]["attribute_points"]

    # Ожидаем 3 лога: XP_GAINED для player1, XP_GAINED для player2, LEVEL_UP для player2
    assert cast(AsyncMock, mock_log_event).call_count == 3
    cast(AsyncMock, mock_log_event).assert_any_call(
        session=mock_session_fixture, guild_id=guild_id_fixture, event_type=EventType.XP_GAINED.name,
        details_json={
            "player_id": player1_updated.id, "player_name": player1_updated.name,
            "xp_awarded": 50, "new_total_xp": player1_updated.xp,
            "source_event": EventType.COMBAT_END.name, "source_log_id": None # .name
        },
        entity_ids_json={"player_id": player1_updated.id}
    )
    cast(AsyncMock, mock_log_event).assert_any_call(
        session=mock_session_fixture, guild_id=guild_id_fixture, event_type=EventType.XP_GAINED.name, # .name
        details_json={
            "player_id": player2_updated.id, "player_name": player2_updated.name,
            "xp_awarded": 50, "new_total_xp": initial_xp_player2 + 50, # XP до вычета за левелап
            "source_event": EventType.COMBAT_END.name, "source_log_id": None # .name
        },
        entity_ids_json={"player_id": player2_updated.id}
    )
    cast(AsyncMock, mock_log_event).assert_any_call(
        session=mock_session_fixture, guild_id=guild_id_fixture, event_type=EventType.LEVEL_UP.name, # .name
        details_json={
            "player_id": player2_updated.id, "player_name": player2_updated.name,
            "new_level": 2, "rewards_received": mock_level_up_rewards_rules_fixture["2"],
            "current_total_xp": player2_updated.xp, # XP после вычета за левелап
        },
        entity_ids_json={"player_id": player2_updated.id}
    )

    assert cast(AsyncMock, mock_session_fixture.commit).call_count == 1 # type: ignore
    assert cast(AsyncMock, mock_session_fixture.refresh).call_count == 2 # type: ignore
    cast(AsyncMock, mock_session_fixture.refresh).assert_any_call(player1_updated) # type: ignore
    cast(AsyncMock, mock_session_fixture.refresh).assert_any_call(player2_updated) # type: ignore

@pytest.mark.asyncio
@patch('src.core.experience_system.game_events.log_event', new_callable=AsyncMock)
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_check_for_level_up_multiple_levels(
    mock_get_rule: AsyncMock,
    mock_log_event: AsyncMock,
    mock_session_fixture: AsyncSession,
    player_fixture: Player,
    mock_level_curve_rules_fixture,
    mock_level_up_rewards_rules_fixture,
    guild_id_fixture: int
):
    mock_get_rule.side_effect = [mock_level_curve_rules_fixture, mock_level_up_rewards_rules_fixture]
    player_fixture.xp = 350 # L1->L2 (100), L2->L3 (200). Total 300. Rem 50. Lvl 3.

    level_up_achieved = await _check_for_level_up(mock_session_fixture, guild_id_fixture, player_fixture)

    assert level_up_achieved is True
    assert player_fixture.level == 3
    assert player_fixture.xp == 50
    assert player_fixture.unspent_xp == mock_level_up_rewards_rules_fixture["2"]["attribute_points"] + \
                                     mock_level_up_rewards_rules_fixture["3"]["attribute_points"]

    assert cast(AsyncMock, mock_log_event).call_count == 2
    cast(AsyncMock, mock_log_event).assert_any_call(
        session=mock_session_fixture, guild_id=guild_id_fixture, event_type=EventType.LEVEL_UP.name, # .name
        details_json={
            "player_id": player_fixture.id, "player_name": player_fixture.name,
            "new_level": 2, "rewards_received": mock_level_up_rewards_rules_fixture["2"],
            "current_total_xp": 250, # XP after L1->L2 (350-100=250)
        },
        entity_ids_json={"player_id": player_fixture.id}
    )
    cast(AsyncMock, mock_log_event).assert_any_call(
        session=mock_session_fixture, guild_id=guild_id_fixture, event_type=EventType.LEVEL_UP.name, # .name
        details_json={
            "player_id": player_fixture.id, "player_name": player_fixture.name,
            "new_level": 3, "rewards_received": mock_level_up_rewards_rules_fixture["3"],
            "current_total_xp": 50, # Final XP after L2->L3 (250-200=50)
        },
        entity_ids_json={"player_id": player_fixture.id}
    )
    cast(AsyncMock, mock_session_fixture.commit).assert_not_called() # type: ignore
    cast(AsyncMock, mock_session_fixture.refresh).assert_not_called() # type: ignore

@pytest.mark.asyncio
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_check_for_level_up_no_rules_found(
    mock_get_rule: AsyncMock,
    mock_session_fixture: AsyncSession,
    player_fixture: Player,
    mock_level_curve_rules_fixture,
    guild_id_fixture: int
):
    # Случай 1: Не найдены правила кривой опыта
    mock_get_rule.return_value = None
    level_up_achieved = await _check_for_level_up(mock_session_fixture, guild_id_fixture, player_fixture)
    assert level_up_achieved is False
    assert player_fixture.level == 1

    # Случай 2: Не найдены правила наград (кривая есть)
    # Сбрасываем состояние игрока
    player_fixture.xp = 150
    player_fixture.level = 1
    player_fixture.unspent_xp = 0
    mock_get_rule.side_effect = [mock_level_curve_rules_fixture, None] # Curve exists, rewards not (вернет {} в функции)

    level_up_achieved = await _check_for_level_up(mock_session_fixture, guild_id_fixture, player_fixture)
    # Уровень должен повыситься, даже если нет правил наград (награды будут пустыми)
    assert level_up_achieved is True
    assert player_fixture.level == 2
    assert player_fixture.xp == 50 # 150 - 100
    assert player_fixture.unspent_xp == 0 # Наград нет

@pytest.mark.asyncio
@patch('src.core.experience_system.player_crud.get_by_id_and_guild', new_callable=AsyncMock)
@patch('src.core.experience_system.game_events.log_event', new_callable=AsyncMock)
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_award_xp_player_not_found(
    mock_get_rule: AsyncMock,
    mock_log_event: AsyncMock,
    mock_player_crud_get: AsyncMock,
    mock_session_fixture: AsyncSession,
    guild_id_fixture: int
):
    mock_player_crud_get.return_value = None
    updated_players = await award_xp(
        mock_session_fixture, guild_id_fixture, 999, RelationshipEntityType.PLAYER, 100, EventType.SYSTEM_EVENT # Используем SYSTEM_EVENT
    )
    assert len(updated_players) == 0
    cast(AsyncMock, mock_log_event).assert_not_called() # type: ignore
    cast(AsyncMock, mock_get_rule).assert_not_called() # type: ignore # mock_get_rule is also an AsyncMock
    cast(AsyncMock, mock_session_fixture.commit).assert_not_called() # type: ignore

@pytest.mark.asyncio
@patch('src.core.experience_system.party_crud.get', new_callable=AsyncMock)
@patch('src.core.experience_system.game_events.log_event', new_callable=AsyncMock)
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_award_xp_party_not_found_or_empty(
    mock_get_rule: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud_get: AsyncMock,
    mock_session_fixture: AsyncSession,
    guild_id_fixture: int
):
    mock_party_crud_get.return_value = None
    updated_players = await award_xp(
        mock_session_fixture, guild_id_fixture, 999, RelationshipEntityType.PARTY, 100, EventType.SYSTEM_EVENT # Используем SYSTEM_EVENT
    )
    assert len(updated_players) == 0

    empty_party = Party(id=2, guild_id=guild_id_fixture, name="Empty Party")
    empty_party.players = []
    mock_party_crud_get.return_value = empty_party
    updated_players = await award_xp(
        mock_session_fixture, guild_id_fixture, 2, RelationshipEntityType.PARTY, 100, EventType.SYSTEM_EVENT # Используем SYSTEM_EVENT
    )
    assert len(updated_players) == 0

    cast(AsyncMock, mock_log_event).assert_not_called() # type: ignore
    cast(AsyncMock, mock_get_rule).assert_not_called() # type: ignore # mock_get_rule is also an AsyncMock
    cast(AsyncMock, mock_session_fixture.commit).assert_not_called() # type: ignore

@pytest.mark.asyncio
@patch('src.core.experience_system.game_events.log_event', new_callable=AsyncMock)
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_check_for_level_up_max_level_reached(
    mock_get_rule: AsyncMock,
    mock_log_event: AsyncMock,
    mock_session_fixture: AsyncSession,
    player_fixture: Player,
    mock_level_curve_rules_fixture,
    mock_level_up_rewards_rules_fixture,
    guild_id_fixture: int
):
    # Уровень 5 не определен как current_level в mock_level_curve_rules_fixture, поэтому это максимальный уровень
    player_fixture.level = 5
    player_fixture.xp = 500

    mock_get_rule.side_effect = [mock_level_curve_rules_fixture, mock_level_up_rewards_rules_fixture]

    level_up_achieved = await _check_for_level_up(mock_session_fixture, guild_id_fixture, player_fixture)

    assert level_up_achieved is False
    assert player_fixture.level == 5
    assert player_fixture.xp == 500
    cast(AsyncMock, mock_log_event).assert_not_called() # type: ignore

@pytest.mark.asyncio
@patch('src.core.experience_system.party_crud.get', new_callable=AsyncMock)
@patch('src.core.experience_system.game_events.log_event', new_callable=AsyncMock)
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_award_xp_party_xp_per_player_becomes_zero(
    mock_get_rule: AsyncMock,
    mock_log_event: AsyncMock,
    mock_party_crud_get: AsyncMock,
    mock_session_fixture: AsyncSession,
    party_fixture: Party,
    guild_id_fixture: int
):
    mock_party_crud_get.return_value = party_fixture
    # Правила для _check_for_level_up не должны вызываться, если XP не начислен

    xp_to_award_party = 1
    updated_players = await award_xp(
        mock_session_fixture, guild_id_fixture, party_fixture.id, RelationshipEntityType.PARTY, xp_to_award_party, EventType.COMBAT_END # Используем COMBAT_END
    )

    assert len(updated_players) == 0
    assert cast(AsyncMock, mock_log_event).call_count == 0

    player1 = next(p for p in party_fixture.players if p.id == 1)
    player2 = next(p for p in party_fixture.players if p.id == 2)
    assert player1.xp == 0
    assert player2.xp == 50

    cast(AsyncMock, mock_session_fixture.commit).assert_not_called()


# --- Тесты для spend_attribute_points ---

@pytest.fixture
def mock_attribute_definitions_fixture():
    return {
        "strength": {"name_i18n": {"en": "Strength", "ru": "Сила"}},
        "dexterity": {"name_i18n": {"en": "Dexterity", "ru": "Ловкость"}},
    }

@pytest.mark.asyncio
@patch('src.core.experience_system.game_events.log_event', new_callable=AsyncMock)
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_spend_attribute_points_success(
    mock_get_rule: AsyncMock,
    mock_log_event: AsyncMock,
    mock_session_fixture: AsyncSession,
    player_fixture: Player,
    mock_attribute_definitions_fixture,
    guild_id_fixture: int
):
    from src.core.experience_system import spend_attribute_points # Локальный импорт
    player_fixture.unspent_xp = 5
    player_fixture.attributes_json = {"strength": 10}
    player_fixture.selected_language = "en"

    mock_get_rule.return_value = mock_attribute_definitions_fixture

    success, msg_key, details = await spend_attribute_points(
        mock_session_fixture, player_fixture, "strength", 3, guild_id_fixture
    )

    assert success is True
    assert msg_key == "levelup_success"
    assert details["attribute_name"] == "Strength" # Локализованное имя
    assert details["new_value"] == 13
    assert details["remaining_xp"] == 2
    assert details["spent_points"] == 3

    assert player_fixture.unspent_xp == 2
    assert player_fixture.attributes_json["strength"] == 13

    mock_log_event.assert_called_once_with(
        session=mock_session_fixture,
        guild_id=guild_id_fixture,
        event_type=EventType.ATTRIBUTE_POINTS_SPENT.name,
        details_json={
            "player_id": player_fixture.id,
            "player_name": player_fixture.name,
            "attribute_changed": "strength",
            "points_spent": 3,
            "stat_increase": 3,
            "old_value": 10,
            "new_value": 13,
            "remaining_unspent_xp": 2,
        },
        entity_ids_json={"player_id": player_fixture.id}
    ) # type: ignore
    # session.commit() и session.refresh() не должны вызываться внутри spend_attribute_points
    cast(AsyncMock, mock_session_fixture.commit).assert_not_called() # type: ignore
    cast(AsyncMock, mock_session_fixture.refresh).assert_not_called() # type: ignore


@pytest.mark.asyncio
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_spend_attribute_points_not_enough_xp(
    mock_get_rule: AsyncMock,
    mock_session_fixture: AsyncSession,
    player_fixture: Player,
    mock_attribute_definitions_fixture,
    guild_id_fixture: int
):
    from src.core.experience_system import spend_attribute_points # Локальный импорт
    player_fixture.unspent_xp = 2
    player_fixture.attributes_json = {"strength": 10}
    mock_get_rule.return_value = mock_attribute_definitions_fixture

    success, msg_key, details = await spend_attribute_points(
        mock_session_fixture, player_fixture, "strength", 3, guild_id_fixture
    )

    assert success is False
    assert msg_key == "levelup_error_not_enough_xp"
    assert details["unspent_xp"] == 2
    assert details["requested"] == 3
    assert player_fixture.unspent_xp == 2 # Не изменилось
    assert player_fixture.attributes_json["strength"] == 10 # Не изменилось

@pytest.mark.asyncio
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_spend_attribute_points_invalid_attribute(
    mock_get_rule: AsyncMock,
    mock_session_fixture: AsyncSession,
    player_fixture: Player,
    mock_attribute_definitions_fixture,
    guild_id_fixture: int
):
    from src.core.experience_system import spend_attribute_points # Локальный импорт
    player_fixture.unspent_xp = 5
    mock_get_rule.return_value = mock_attribute_definitions_fixture # "wisdom" не определен

    success, msg_key, details = await spend_attribute_points(
        mock_session_fixture, player_fixture, "wisdom", 1, guild_id_fixture
    )

    assert success is False
    assert msg_key == "levelup_error_invalid_attribute"
    assert details["attribute_name"] == "wisdom"
    assert player_fixture.unspent_xp == 5 # Не изменилось

@pytest.mark.asyncio
async def test_spend_attribute_points_invalid_points_value(
    mock_session_fixture: AsyncSession,
    player_fixture: Player,
    guild_id_fixture: int
):
    from src.core.experience_system import spend_attribute_points # Локальный импорт
    player_fixture.unspent_xp = 5

    success, msg_key, details = await spend_attribute_points(
        mock_session_fixture, player_fixture, "strength", 0, guild_id_fixture
    )
    assert success is False
    assert msg_key == "levelup_error_invalid_points_value"
    assert details["points"] == 0

    success, msg_key, details = await spend_attribute_points(
        mock_session_fixture, player_fixture, "strength", -1, guild_id_fixture
    )
    assert success is False
    assert msg_key == "levelup_error_invalid_points_value"
    assert details["points"] == -1

@pytest.mark.asyncio
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_spend_attribute_points_new_attribute(
    mock_get_rule: AsyncMock,
    mock_session_fixture: AsyncSession,
    player_fixture: Player,
    mock_attribute_definitions_fixture,
    guild_id_fixture: int
):
    from src.core.experience_system import spend_attribute_points # Локальный импорт
    player_fixture.unspent_xp = 5
    player_fixture.attributes_json = {} # Атрибутов еще нет
    player_fixture.selected_language = "ru"
    mock_get_rule.return_value = mock_attribute_definitions_fixture

    success, msg_key, details = await spend_attribute_points(
        mock_session_fixture, player_fixture, "dexterity", 2, guild_id_fixture
    )

    assert success is True
    assert msg_key == "levelup_success"
    assert details["attribute_name"] == "Ловкость" # Локализованное имя
    assert details["new_value"] == 2
    assert details["remaining_xp"] == 3
    assert player_fixture.unspent_xp == 3
    assert player_fixture.attributes_json["dexterity"] == 2


@pytest.mark.asyncio
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_spend_attribute_points_attribute_definitions_not_dict(
    mock_get_rule: AsyncMock,
    mock_session_fixture: AsyncSession,
    player_fixture: Player,
    guild_id_fixture: int
):
    from src.core.experience_system import spend_attribute_points # Локальный импорт
    player_fixture.unspent_xp = 5
    mock_get_rule.return_value = "not_a_dict" # Некорректные правила

    success, msg_key, details = await spend_attribute_points(
        mock_session_fixture, player_fixture, "strength", 1, guild_id_fixture
    )

    assert success is False
    assert msg_key == "levelup_error_invalid_attribute"
    assert details["attribute_name"] == "strength"
    assert player_fixture.unspent_xp == 5

@pytest.mark.asyncio
@patch('src.core.experience_system.rules.get_rule', new_callable=AsyncMock)
async def test_spend_attribute_points_no_attribute_definitions_rule(
    mock_get_rule: AsyncMock,
    mock_session_fixture: AsyncSession,
    player_fixture: Player,
    guild_id_fixture: int
):
    from src.core.experience_system import spend_attribute_points # Локальный импорт
    player_fixture.unspent_xp = 5
    mock_get_rule.return_value = None # Правило не найдено

    success, msg_key, details = await spend_attribute_points(
        mock_session_fixture, player_fixture, "strength", 1, guild_id_fixture
    )

    assert success is False
    assert msg_key == "levelup_error_invalid_attribute"
    assert details["attribute_name"] == "strength"
    assert player_fixture.unspent_xp == 5
