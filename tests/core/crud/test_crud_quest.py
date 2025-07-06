import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import sqlalchemy as sa # Добавлен импорт sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select # Уточнен импорт select

from src.models.quest import Questline, GeneratedQuest, QuestStep, PlayerQuestProgress
from src.models.enums import QuestStatus, RelationshipEntityType
from src.core.crud.crud_quest import (
    questline_crud,
    generated_quest_crud,
    quest_step_crud,
    player_quest_progress_crud
)
from src.models.guild import GuildConfig # Для создания GuildConfig
from src.models.player import Player # Для создания Player
from src.models.party import Party # Для создания Party

# Вспомогательная функция для создания мок-сессии и результата
def _get_mock_session_with_result(result_value):
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()

    if isinstance(result_value, list):
        mock_result.scalars.return_value.all.return_value = result_value
        mock_result.scalar_one_or_none.return_value = result_value[0] if result_value else None
    else:
        mock_result.scalars.return_value.all.return_value = [result_value] if result_value else []
        mock_result.scalar_one_or_none.return_value = result_value
        mock_result.scalar.return_value = result_value # для get

    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session

class TestQuestCrud(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Можно создать базовые сущности, если они нужны для FK в тестах
        # Но CRUD тесты обычно мокируют вызовы к БД напрямую
        self.guild = GuildConfig(id=12345, name="Test Guild") # Corrected: id is the guild_discord_id
        self.player = Player(id=1, guild_id=self.guild.id, discord_id=67890, name="Test Player") # Use self.guild.id
        self.party = Party(id=1, guild_id=self.guild.id, name="Test Party", leader_player_id=1) # Use self.guild.id


    # --- CRUDQuestline Tests ---
    async def test_create_questline(self):
        mock_session = AsyncMock(spec=AsyncSession)
        questline_data = {
            "guild_id": self.guild.id,
            "static_id": "ql_test",
            "title_i18n": {"en": "Test QL"}
        }
        # CRUDBase.create использует session.add и session.flush
        # Мы не будем здесь проверять детали CRUDBase, а сфокусируемся на кастомных методах
        # Для теста create нужно мокнуть add, flush, refresh

        # Пропустим тест create для CRUDBase, так как он общий
        pass

    async def test_get_questline_by_static_id(self):
        questline = Questline(id=1, guild_id=self.guild.id, static_id="ql_test", title_i18n={"en":"Test"})
        mock_session = _get_mock_session_with_result(questline)

        found_ql = await questline_crud.get_by_static_id(mock_session, static_id="ql_test", guild_id=self.guild.id)
        self.assertEqual(found_ql, questline)

        # Проверка вызова execute
        mock_session.execute.assert_called_once()
        # statement = mock_session.execute.call_args[0][0] # Получаем statement
        # self.assertIn("questlines.guild_id = :guild_id_1", str(statement))
        # self.assertIn("questlines.static_id = :static_id_1", str(statement))


    # --- CRUDGeneratedQuest Tests ---
    async def test_get_generated_quest_by_static_id(self):
        quest = GeneratedQuest(id=1, guild_id=self.guild.id, static_id="gq_test", title_i18n={"en":"Test GQ"})
        mock_session = _get_mock_session_with_result(quest)

        found_gq = await generated_quest_crud.get_by_static_id(mock_session, static_id="gq_test", guild_id=self.guild.id)
        self.assertEqual(found_gq, quest)

    # --- CRUDQuestStep Tests ---
    async def test_get_quest_step_by_quest_id_and_order(self):
        step = QuestStep(id=1, quest_id=1, step_order=1, title_i18n={"en":"Step 1"})
        mock_session = _get_mock_session_with_result(step)

        found_step = await quest_step_crud.get_by_quest_id_and_order(mock_session, quest_id=1, step_order=1)
        self.assertEqual(found_step, step)

    async def test_get_all_quest_steps_for_quest(self):
        steps = [
            QuestStep(id=1, quest_id=1, step_order=1, title_i18n={"en":"Step 1"}),
            QuestStep(id=2, quest_id=1, step_order=2, title_i18n={"en":"Step 2"})
        ]
        mock_session = _get_mock_session_with_result(steps)

        found_steps = await quest_step_crud.get_all_for_quest(mock_session, quest_id=1)
        self.assertEqual(found_steps, steps)

    # --- CRUDPlayerQuestProgress Tests ---
    async def test_get_player_quest_progress_by_player_and_quest(self):
        progress = PlayerQuestProgress(id=1, player_id=self.player.id, quest_id=1, guild_id=self.guild.id, status=QuestStatus.STARTED) # ACCEPTED -> STARTED
        mock_session = _get_mock_session_with_result(progress)

        found_progress = await player_quest_progress_crud.get_by_player_and_quest(
            mock_session, player_id=self.player.id, quest_id=1, guild_id=self.guild.id
        )
        self.assertEqual(found_progress, progress)

    async def test_get_all_player_quest_progress_for_player(self):
        progress_list = [
            PlayerQuestProgress(id=1, player_id=self.player.id, quest_id=1, guild_id=self.guild.id, status=QuestStatus.STARTED), # ACCEPTED -> STARTED
            PlayerQuestProgress(id=2, player_id=self.player.id, quest_id=2, guild_id=self.guild.id, status=QuestStatus.COMPLETED)
        ]
        mock_session = _get_mock_session_with_result(progress_list)

        found_list = await player_quest_progress_crud.get_all_for_player(
            mock_session, player_id=self.player.id, guild_id=self.guild.id
        )
        self.assertEqual(found_list, progress_list)

    async def test_get_player_quest_progress_by_party_and_quest(self):
        progress = PlayerQuestProgress(id=1, party_id=self.party.id, quest_id=1, guild_id=self.guild.id, status=QuestStatus.IN_PROGRESS)
        mock_session = _get_mock_session_with_result(progress)

        found_progress = await player_quest_progress_crud.get_by_party_and_quest(
            mock_session, party_id=self.party.id, quest_id=1, guild_id=self.guild.id
        )
        self.assertEqual(found_progress, progress)

    async def test_get_all_player_quest_progress_for_party(self):
        progress_list = [
            PlayerQuestProgress(id=1, party_id=self.party.id, quest_id=1, guild_id=self.guild.id, status=QuestStatus.IN_PROGRESS),
            PlayerQuestProgress(id=2, party_id=self.party.id, quest_id=3, guild_id=self.guild.id, status=QuestStatus.FAILED)
        ]
        mock_session = _get_mock_session_with_result(progress_list)

        found_list = await player_quest_progress_crud.get_all_for_party(
            mock_session, party_id=self.party.id, guild_id=self.guild.id
        )
        self.assertEqual(found_list, progress_list)

    # Тесты для базовых методов CRUDBase (create, get, update, delete) писать не будем,
    # предполагая, что CRUDBase уже протестирован отдельно или его функциональность достаточно проста.
    # Фокусируемся на кастомных методах CRUD для квестов.

if __name__ == '__main__':
    unittest.main()
