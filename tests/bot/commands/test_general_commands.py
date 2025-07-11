import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional # Added Optional

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession # Added import
import discord # type: ignore
from discord.ext import commands # Added commands import

from backend.bot.commands.general_commands import GeneralCog
from backend.models.player import Player, PlayerStatus
from backend.models.location import Location, LocationType
from backend.models.guild import GuildConfig # Added import
from backend.bot.events import DEFAULT_STATIC_LOCATIONS # Для мокирования или проверки

# Для удобства мокирования объектов discord.py
class MockGuild:
    def __init__(self, id, name="Test Guild"): # Added name attribute
        self.id = id
        self.name = name # Store the name

class MockUser:
    def __init__(self, id, name, display_name=None, locale_str="en-US"):
        self.id = id
        self.name = name
        self.display_name = display_name or name
        if locale_str:
            mock_locale = MagicMock(spec=discord.Locale)
            mock_locale.__str__ = MagicMock(return_value=locale_str)
            self.locale = mock_locale
        else:
            self.locale = None

# Removed local MockInteraction class, using self._create_mock_interaction with AsyncMock(spec=discord.Interaction) instead.

class TestGeneralCommands(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.bot_mock = AsyncMock(spec=commands.Bot)
        self.cog = GeneralCog(self.bot_mock)

        # Патчим get_db_session, чтобы он возвращал мок сессии
        self.session_mock = AsyncMock()
        self.session_mock = AsyncMock(spec=AsyncSession) # Added spec for better mocking
        self.patcher_get_db_session = patch('backend.bot.commands.general_commands.get_db_session')
        self.mock_get_db_session = self.patcher_get_db_session.start()
        self.mock_get_db_session.return_value.__aenter__.return_value = self.session_mock

        # Настройка mock_session_mock.execute для тестов RuleConfig
        # Это общий мок, который будет использоваться, если тест не переопределит session.execute
        mock_execute_result = AsyncMock() # Мок для результата session.execute
        # scalar_one_or_none должен быть синхронным методом мока результата
        mock_execute_result.scalar_one_or_none = MagicMock(return_value=None) # По умолчанию правило не найдено

        # scalars() должен возвращать объект, у которого all() является синхронным методом
        mock_scalars_result = MagicMock()
        mock_scalars_result.all.return_value = [] # .all() возвращает список
        mock_execute_result.scalars = MagicMock(return_value=mock_scalars_result) # .scalars() возвращает этот мок
        self.session_mock.execute.return_value = mock_execute_result


        # Патчим CRUD операции
        self.patcher_player_crud = patch('backend.bot.commands.general_commands.player_crud', new_callable=AsyncMock)
        self.mock_player_crud = self.patcher_player_crud.start()

        self.patcher_location_crud = patch('backend.bot.commands.general_commands.location_crud', new_callable=AsyncMock)
        self.mock_location_crud = self.patcher_location_crud.start()

        self.patcher_guild_crud = patch('backend.bot.commands.general_commands.guild_crud', new_callable=AsyncMock)
        self.mock_guild_crud = self.patcher_guild_crud.start()

        # Мокируем DEFAULT_STATIC_LOCATIONS, если нужно контролировать его в тестах
        self.patcher_default_locs = patch('backend.bot.commands.general_commands.DEFAULT_STATIC_LOCATIONS', [])
        self.mock_default_locs = self.patcher_default_locs.start()

    def _create_mock_interaction(self, user: MockUser, guild: Optional[MockGuild] = None) -> AsyncMock:
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.user = user
        interaction.guild = guild
        interaction.guild_id = guild.id if guild else None

        # Mock for interaction.response
        interaction.response = AsyncMock(spec=discord.InteractionResponse)
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()

        # Mock for interaction.followup
        interaction.followup = AsyncMock() # Removed spec=discord.Webhook
        interaction.followup.send = AsyncMock()

        if user.locale:
            interaction.locale = user.locale
        else:
            # Default to en-US mock if user.locale is None
            mock_locale_default = MagicMock(spec=discord.Locale)
            # Assuming str(interaction.locale) should yield "en-US" or "en"
            # For consistency with other mocks, let's make it yield "en" if SUT expects simple codes
            mock_locale_default.__str__ = MagicMock(return_value="en") # Or "en-US" if that's more accurate for default
            interaction.locale = mock_locale_default
        return interaction

    def tearDown(self):
        self.patcher_get_db_session.stop()
        self.patcher_player_crud.stop()
        self.patcher_location_crud.stop()
        self.patcher_guild_crud.stop()
        self.patcher_default_locs.stop()

    async def test_start_command_new_player(self):
        mock_user = MockUser(id=123, name="TestUser", display_name="Test User Display", locale_str="ru")
        mock_guild = MockGuild(id=456)
        mock_interaction = self._create_mock_interaction(user=mock_user, guild=mock_guild)

        self.mock_player_crud.get_by_discord_id.return_value = None # Игрок не существует
        # Предполагаем, что конфиг гильдии еще не существует и будет создан
        self.mock_guild_crud.get.return_value = None
        mock_created_guild_config = GuildConfig(id=mock_guild.id, name=mock_guild.name, main_language="ru")
        self.mock_guild_crud.create.return_value = mock_created_guild_config


        mock_start_loc = Location(id=1, guild_id=mock_guild.id, static_id="start", name_i18n={"en": "Start Zone", "ru": "Стартовая Зона"}, descriptions_i18n={}, type=LocationType.TOWN)
        self.mock_location_crud.get_by_static_id.return_value = mock_start_loc
        self.mock_default_locs.append({"static_id": "start"}) # Устанавливаем мок для DEFAULT_STATIC_LOCATIONS

        created_player = Player(id=1, guild_id=mock_guild.id, discord_id=mock_user.id, name=mock_user.display_name, current_location_id=mock_start_loc.id, selected_language="ru", level=1)
        self.mock_player_crud.create_with_defaults.return_value = created_player

        # Вызываем внутренний метод, который принимает session
        await self.cog._start_command_internal(mock_interaction, session=self.session_mock)

        self.mock_player_crud.get_by_discord_id.assert_called_once_with(session=self.session_mock, guild_id=mock_guild.id, discord_id=mock_user.id)
        self.mock_location_crud.get_by_static_id.assert_called_once_with(session=self.session_mock, guild_id=mock_guild.id, static_id="start")
        self.mock_player_crud.create_with_defaults.assert_called_once_with(
            session=self.session_mock, guild_id=mock_guild.id, discord_id=mock_user.id, name=mock_user.display_name,
            current_location_id=mock_start_loc.id, selected_language="ru"
        )
        self.session_mock.add.assert_any_call(created_player) # Игрок должен быть добавлен
        self.assertEqual(self.session_mock.add.call_count, 2) # Ожидаем два вызова add: RuleConfig и Player
        self.assertEqual(created_player.current_status, PlayerStatus.EXPLORING)

        mock_interaction.followup.send.assert_called_once() # Changed from response.send_message
        args, kwargs = mock_interaction.followup.send.call_args # Changed from response.send_message
        self.assertIn(f"Добро пожаловать в игру, {mock_user.display_name}!", args[0])
        self.assertIn(f"Стартовая Зона", args[0]) # Проверка имени локации
        self.assertIn(f"язык установлен на ru", args[0])
        self.assertEqual(kwargs.get("ephemeral"), True)

    async def test_start_command_existing_player(self):
        mock_user = MockUser(id=124, name="ExistingUser")
        mock_guild = MockGuild(id=457, name="Existing Player Guild") # Ensure name is present
        mock_interaction = self._create_mock_interaction(user=mock_user, guild=mock_guild)

        # Explicitly ensure followup.send is AsyncMock for this test
        mock_interaction.followup = AsyncMock(spec=discord.Webhook)
        mock_interaction.followup.send = AsyncMock()

        existing_player = Player(id=2, guild_id=mock_guild.id, discord_id=mock_user.id, name=mock_user.name, level=5)
        self.mock_player_crud.get_by_discord_id.return_value = existing_player

        # Мокируем существующий GuildConfig
        existing_guild_config = GuildConfig(id=mock_guild.id, name=mock_guild.name, main_language="en")
        self.mock_guild_crud.get.return_value = existing_guild_config

        await self.cog._start_command_internal(mock_interaction, session=self.session_mock)

        self.mock_player_crud.get_by_discord_id.assert_called_once_with(session=self.session_mock, guild_id=mock_guild.id, discord_id=mock_user.id)
        self.mock_player_crud.create_with_defaults.assert_not_called()
        mock_interaction.followup.send.assert_called_once_with( # Changed to followup
            f"Привет, {mock_user.name}! Ты уже в игре. Твой персонаж уровня 5.",
            ephemeral=True
        )

    async def test_start_command_no_guild(self):
        mock_user = MockUser(id=125, name="DMUser")
        mock_interaction = self._create_mock_interaction(user=mock_user, guild=None) # No guild

        # The wrapper `start_command` handles the no-guild case before calling internal
        # For app commands, callback is already bound, so cog instance isn't passed first.
        await self.cog.start_command.callback(self.cog, mock_interaction) # type: ignore

        mock_interaction.response.send_message.assert_called_once_with(
            "Эту команду можно использовать только на сервере.", ephemeral=True
        )
        self.mock_player_crud.get_by_discord_id.assert_not_called()

    async def test_start_command_no_default_start_location_found(self):
        mock_user = MockUser(id=126, name="NoLocUser", locale_str="de")
        mock_guild = MockGuild(id=458)
        mock_interaction = self._create_mock_interaction(user=mock_user, guild=mock_guild)

        self.mock_player_crud.get_by_discord_id.return_value = None
        # Предполагаем, что конфиг гильдии еще не существует и будет создан
        self.mock_guild_crud.get.return_value = None
        mock_created_guild_config = GuildConfig(id=mock_guild.id, name=mock_guild.name, main_language="de")
        self.mock_guild_crud.create.return_value = mock_created_guild_config

        self.mock_location_crud.get_by_static_id.return_value = None # Локация не найдена
        self.mock_default_locs.append({"static_id": "non_existent_start"})

        created_player = Player(id=3, guild_id=mock_guild.id, discord_id=mock_user.id, name=mock_user.display_name, current_location_id=None, selected_language="de", level=1)
        self.mock_player_crud.create_with_defaults.return_value = created_player

        await self.cog._start_command_internal(mock_interaction, session=self.session_mock)

        self.mock_player_crud.create_with_defaults.assert_called_once_with(
            session=self.session_mock, guild_id=mock_guild.id, discord_id=mock_user.id, name=mock_user.display_name,
            current_location_id=None, selected_language="de"
        )
        mock_interaction.followup.send.assert_called_once() # Changed to followup
        args, kwargs = mock_interaction.followup.send.call_args # Changed to followup
        self.assertIn("находится в локации: неизвестной локации", args[0])


if __name__ == '__main__':
    unittest.main()
