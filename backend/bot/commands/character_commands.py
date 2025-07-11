import logging
import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import transactional
from backend.core.crud.crud_player import player_crud
from backend.core.experience_system import spend_attribute_points
from backend.core import localization_utils, rules
from backend.models import Player

logger = logging.getLogger(__name__)

class CharacterCog(commands.Cog, name="Character Commands"): # type: ignore[call-arg]
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("CharacterCog инициализирован.")

    @app_commands.command(name="levelup", description="Распределить очки повышения уровня для улучшения атрибутов.")
    @app_commands.describe(
        attribute_name="Название атрибута для улучшения (например, strength, dexterity).",
        points_to_spend="Количество очков, которое вы хотите потратить на этот атрибут."
    )
    async def levelup_command(self, interaction: discord.Interaction, attribute_name: str, points_to_spend: int):
        # Вызываем внутренний метод, к которому применен @transactional
        await self._levelup_internal(interaction, attribute_name, points_to_spend) # type: ignore

    @transactional
    async def _levelup_internal(self, interaction: discord.Interaction, attribute_name: str, points_to_spend: int, *, session: AsyncSession):
        if not interaction.guild_id or not interaction.user:
            await interaction.response.send_message("Эта команда должна использоваться на сервере.", ephemeral=True)
            return

        guild_id = interaction.guild_id
        discord_id = interaction.user.id
        player_locale = str(interaction.locale) if interaction.locale else 'en'

        player = await player_crud.get_by_discord_id(session=session, guild_id=guild_id, discord_id=discord_id) # FIX: db to session

        if not player:
            # TODO: Локализовать это сообщение через RuleConfig
            await interaction.response.send_message(
                "Сначала вам нужно начать игру с помощью команды `/start`.",
                ephemeral=True
            )
            return

        if player.unspent_xp <= 0:
            no_points_message_key = "levelup_error_no_unspent_xp"
            # TODO: Загрузить локализованное сообщение из RuleConfig
            # message_template = await rules.get_rule(session, guild_id, no_points_message_key, default="У вас нет очков для распределения.")
            # formatted_message = message_template
            # Пока используем заглушку:
            formatted_message = localization_utils.get_localized_text(
                {"en": "You have no unspent attribute points to spend.", "ru": "У вас нет нераспределенных очков атрибутов."},
                player_locale
            )
            await interaction.response.send_message(formatted_message, ephemeral=True)
            return

        success, message_key, details = await spend_attribute_points(
            session=session,
            player=player,
            attribute_name=attribute_name.lower(), # Атрибуты обычно в нижнем регистре в ключах
            points_to_spend=points_to_spend,
            guild_id=guild_id
        )

        # Загружаем шаблон сообщения из RuleConfig
        # Если RuleConfig еще не содержит этих ключей, будут использованы значения по умолчанию.
        # Важно, чтобы эти ключи были добавлены в RuleConfig на шаге 6 плана.
        default_messages = {
            "levelup_success": "{attribute_name} повышен до {new_value}. Потрачено очков: {spent_points}. Осталось очков: {remaining_xp}",
            "levelup_error_invalid_points_value": "Количество очков для траты ({points}) должно быть положительным.",
            "levelup_error_not_enough_xp": "Недостаточно очков ({unspent_xp}) для траты {requested} очков.",
            "levelup_error_invalid_attribute": "Атрибут '{attribute_name}' не найден или недоступен для улучшения.",
            "levelup_error_not_enough_xp_for_cost": "Недостаточно очков ({unspent_xp}) для повышения {attribute_name} на {requested_stats} (требуется {total_cost}).",
            "levelup_error_generic": "Произошла ошибка при распределении очков."
        }

        message_template_from_rules = await rules.get_rule(session, guild_id, message_key)

        if message_template_from_rules and isinstance(message_template_from_rules, str):
            final_message_template = message_template_from_rules
        elif isinstance(message_template_from_rules, dict): # Если правило это словарь с i18n текстами
             final_message_template = localization_utils.get_localized_text(message_template_from_rules, player_locale, "en")
             if not final_message_template: # Если и в i18n не нашлось
                 final_message_template = default_messages.get(message_key, "Произошла неизвестная ошибка.")
        else: # Если правило не строка и не словарь, или None
            final_message_template = default_messages.get(message_key, "Произошла неизвестная ошибка.")

        try:
            # Дополняем details стандартными значениями, если они отсутствуют, для безопасного форматирования
            full_details = {
                "attribute_name": details.get("attribute_name", attribute_name),
                "new_value": details.get("new_value", "N/A"),
                "remaining_xp": details.get("remaining_xp", player.unspent_xp), # Обновленное значение
                "spent_points": details.get("spent_points", points_to_spend),
                "points": details.get("points", points_to_spend),
                "unspent_xp": details.get("unspent_xp", player.unspent_xp), # Это может быть старое значение до вызова spend_attribute_points
                "requested": details.get("requested", points_to_spend),
                "requested_stats": details.get("requested_stats", points_to_spend),
                "total_cost": details.get("total_cost", points_to_spend),
            }
            formatted_message = final_message_template.format(**full_details)
        except KeyError as e:
            logger.error(f"Ошибка форматирования сообщения для ключа {message_key}: {e}. Шаблон: '{final_message_template}', Детали: {details}")
            formatted_message = default_messages.get("levelup_error_generic", "Произошла ошибка при форматировании ответа.")


        await interaction.response.send_message(formatted_message, ephemeral=True)

        if success:
            logger.info(f"Игрок {player.name} (ID: {player.id}) успешно потратил {details.get('spent_points')} очков на {details.get('attribute_name', attribute_name)}.")
        else:
            logger.warning(f"Ошибка для игрока {player.name} (ID: {player.id}) при попытке потратить очки: {message_key}, детали: {details}")


async def setup(bot: commands.Bot):
    await bot.add_cog(CharacterCog(bot))
    logger.info("CharacterCog успешно загружен.")
