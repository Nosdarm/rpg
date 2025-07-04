import logging
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Any # Added Any

from src.core.database import get_db_session, transactional
from src.core.crud.crud_player import player_crud
from src.core.crud.crud_location import location_crud
from src.models.player import PlayerStatus
from src.bot.events import DEFAULT_STATIC_LOCATIONS # Используем список дефолтных локаций
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

class GeneralCog(commands.Cog, name="General Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("GeneralCog инициализирован.")

    @transactional # Apply transactional to the internal method
    async def _start_command_internal(self, interaction: discord.Interaction, *, session: AsyncSession):
        """Внутренняя логика команды start, работает с сессией."""
        if not interaction.guild_id: # This check might be redundant if called from wrapper that already checks
            await interaction.response.send_message("Эта команда должна использоваться на сервере (внутренняя проверка).", ephemeral=True)
            return

        guild_id = interaction.guild_id
        discord_id = interaction.user.id
        player_name: str = interaction.user.display_name or interaction.user.name or "Adventurer"
        player_locale = str(interaction.locale) if interaction.locale else 'en'

        existing_player = await player_crud.get_by_discord_id(db=session, guild_id=guild_id, discord_id=discord_id)

        if existing_player:
            await interaction.response.send_message(
                f"Привет, {player_name}! Ты уже в игре. Твой персонаж уровня {existing_player.level}.",
                ephemeral=True
            )
            return

        starting_location_id: Optional[int] = None
        starting_location_name: str = "неизвестной локации (пожалуйста, сообщите Мастеру)"
        if DEFAULT_STATIC_LOCATIONS:
            first_default_loc_static_id = DEFAULT_STATIC_LOCATIONS[0].get("static_id")
            if first_default_loc_static_id:
                start_loc = await location_crud.get_by_static_id(db=session, guild_id=guild_id, static_id=first_default_loc_static_id)
                if start_loc:
                    starting_location_id = start_loc.id
                    starting_location_name = start_loc.name_i18n.get(player_locale, start_loc.name_i18n.get('en', first_default_loc_static_id))
                else:
                    logger.warning(f"Не удалось найти стартовую локацию по static_id '{first_default_loc_static_id}' для гильдии {guild_id} при создании игрока {discord_id}.")
            else:
                logger.warning(f"В DEFAULT_STATIC_LOCATIONS первая локация не имеет static_id.")
        else:
            logger.warning(f"Список DEFAULT_STATIC_LOCATIONS пуст для гильдии {guild_id}. Невозможно назначить стартовую локацию для игрока {discord_id}.")

        try:
            new_player = await player_crud.create_with_defaults(
                db=session,
                guild_id=guild_id,
                discord_id=discord_id,
                name=player_name,
                current_location_id=starting_location_id,
                selected_language=player_locale
            )
            new_player.current_status = PlayerStatus.EXPLORING
            session.add(new_player)

            logger.info(f"Новый игрок {player_name} (Discord ID: {discord_id}) создан для гильдии {guild_id} в локации ID {starting_location_id}.")
            await interaction.response.send_message(
                f"Добро пожаловать в игру, {player_name}! Твой персонаж создан и находится в локации: {starting_location_name}. "
                f"Твой язык установлен на {player_locale}. Удачи в приключениях!",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Ошибка при создании игрока {player_name} (Discord ID: {discord_id}) для гильдии {guild_id}: {e}", exc_info=True)
            await interaction.response.send_message("Произошла ошибка при создании твоего персонажа. Пожалуйста, попробуй позже.", ephemeral=True)

    @app_commands.command(name="start", description="Начать игру или проверить существующего персонажа.")
    async def start_command(self, interaction: discord.Interaction):
        """Начинает игру для нового игрока или показывает информацию о существующем (wrapper)."""
        if not interaction.guild_id:
            await interaction.response.send_message("Эту команду можно использовать только на сервере.", ephemeral=True)
            return

        guild_id = interaction.guild_id
        discord_id = interaction.user.id
        # Ensure player_name is always a str, falling back to global name or a default if necessary
        player_name: str = interaction.user.display_name or interaction.user.name or "Adventurer"
        player_locale = str(interaction.locale) if interaction.locale else 'en'

        existing_player = await player_crud.get_by_discord_id(db=session, guild_id=guild_id, discord_id=discord_id)

        if existing_player:
            # TODO: Вывести более подробную информацию об игроке, если он уже существует
            await interaction.response.send_message(
                f"Привет, {player_name}! Ты уже в игре. Твой персонаж уровня {existing_player.level}.",
                ephemeral=True
            )
            return

        # Определение стартовой локации
        starting_location_id: Optional[int] = None
        starting_location_name: str = "неизвестной локации (пожалуйста, сообщите Мастеру)"
        if DEFAULT_STATIC_LOCATIONS:
            # Пытаемся взять первую локацию из списка дефолтных
            # В идеале, это должно быть конфигурируемо или иметь более сложную логику выбора
            first_default_loc_static_id = DEFAULT_STATIC_LOCATIONS[0].get("static_id")
            if first_default_loc_static_id:
                start_loc = await location_crud.get_by_static_id(db=session, guild_id=guild_id, static_id=first_default_loc_static_id)
                if start_loc:
                    starting_location_id = start_loc.id
                    starting_location_name = start_loc.name_i18n.get(player_locale, start_loc.name_i18n.get('en', first_default_loc_static_id))
                else:
                    logger.warning(f"Не удалось найти стартовую локацию по static_id '{first_default_loc_static_id}' для гильдии {guild_id} при создании игрока {discord_id}.")
            else:
                logger.warning(f"В DEFAULT_STATIC_LOCATIONS первая локация не имеет static_id.")
        else:
            logger.warning(f"Список DEFAULT_STATIC_LOCATIONS пуст для гильдии {guild_id}. Невозможно назначить стартовую локацию для игрока {discord_id}.")


        try:
            new_player = await player_crud.create_with_defaults(
                db=session,
                guild_id=guild_id,
                discord_id=discord_id,
                name=player_name,
                current_location_id=starting_location_id,
                selected_language=player_locale
            )
            # Обновляем статус на EXPLORING после создания
            new_player.current_status = PlayerStatus.EXPLORING
            session.add(new_player)
            # session.commit() не нужен здесь, т.к. @transactional сделает это

            logger.info(f"Новый игрок {player_name} (Discord ID: {discord_id}) создан для гильдии {guild_id} в локации ID {starting_location_id}.")
            await interaction.response.send_message(
                f"Добро пожаловать в игру, {player_name}! Твой персонаж создан и находится в локации: {starting_location_name}. "
                f"Твой язык установлен на {player_locale}. Удачи в приключениях!",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Ошибка при создании игрока {player_name} (Discord ID: {discord_id}) для гильдии {guild_id}: {e}", exc_info=True)
            await interaction.response.send_message("Произошла ошибка при создании твоего персонажа. Пожалуйста, попробуй позже.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))
    logger.info("GeneralCog успешно загружен.")
