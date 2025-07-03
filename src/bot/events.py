import logging
import discord
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict, Any

from ..core.database import get_db_session, transactional
from ..core.crud.crud_guild import guild_crud # Assuming guild_crud exists
from ..core.crud.crud_location import location_crud
from ..core.rules import update_rule_config # For setting default language
from ..models.guild import GuildConfig
from ..models.location import Location, LocationType

logger = logging.getLogger(__name__)

# Define default static locations to be created for new guilds
DEFAULT_STATIC_LOCATIONS: List[Dict[str, Any]] = [
    {
        "static_id": "town_square",
        "name_i18n": {"en": "Town Square", "ru": "Городская площадь"},
        "descriptions_i18n": {
            "en": "The bustling center of the town, always full of life.",
            "ru": "Шумный центр города, всегда полный жизни."
        },
        "type": LocationType.TOWN,
        "neighbor_locations_json": [], # Example: [{"target_static_id": "market_street", "connection_type_i18n": {"en": "path", "ru": "тропа"}}]
    },
    {
        "static_id": "old_well",
        "name_i18n": {"en": "Old Well", "ru": "Старый колодец"},
        "descriptions_i18n": {
            "en": "A moss-covered well, rumored to be ancient.",
            "ru": "Покрытый мхом колодец, по слухам, очень древний."
        },
        "type": LocationType.GENERIC,
        "neighbor_locations_json": [],
    },
]

class EventCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("EventCog инициализирован.")

    @commands.Cog.listener()
    async def on_ready(self):
        # Этот on_ready в Cog будет вызван в дополнение к on_ready в BotCore, если он там есть.
        # Обычно основной on_ready оставляют в главном классе бота.
        # Но для демонстрации оставим здесь логирование.
        if self.bot.user: # Add a check for self.bot.user
            logger.info(f"EventCog: Бот {self.bot.user.name} готов (из Cog).")
        else:
            logger.error("EventCog: on_ready called, but self.bot.user is None.")

from ..core.database import get_db_session, transactional
from ..core.crud.crud_player import player_crud
from ..core.nlu_service import parse_player_input
from ..models.player import PlayerStatus
from ..models.actions import ParsedAction

# Helper function for NLU processing to keep on_message clean
# This function will handle fetching the player and updating them.
@transactional
async def process_player_message_for_nlu(bot: commands.Bot, message: discord.Message, *, session: AsyncSession):
    """
    Processes a player's message for NLU, updates player's collected_actions_json.
    Session is injected by @transactional as a keyword argument.
    """
    if not message.guild: # Should not happen if called from on_message with guild check
        return

    guild_id = message.guild.id
    player_discord_id = message.author.id

    player = await player_crud.get_by_discord_id(db=session, guild_id=guild_id, discord_id=player_discord_id)

    if not player:
        # logger.debug(f"Player not found for discord_id {player_discord_id} in guild {guild_id}. NLU skipped.")
        return

    # Define statuses where NLU should be skipped or handled differently
    # For MVP, let's process if player is IDLE or EXPLORING.
    # Other statuses like COMBAT, DIALOGUE, MENU, AWAITING_MODERATION might have their own input handlers
    # or should explicitly not trigger general NLU.
    skippable_statuses = [
        PlayerStatus.COMBAT,
        PlayerStatus.DIALOGUE,
        # PlayerStatus.MENU, # Depends on if menu interaction is text-based
        PlayerStatus.AWAITING_MODERATION,
        PlayerStatus.PROCESSING_ACTION,
        PlayerStatus.DEAD
    ]
    if player.current_status in skippable_statuses:
        logger.debug(f"Player {player.name} (ID: {player.id}) in status {player.current_status.name}. NLU processing skipped for message: '{message.content}'")
        return

    parsed_action: Optional[ParsedAction] = await parse_player_input(
        raw_text=message.content,
        guild_id=guild_id,
        player_id=player_discord_id
    )

    if parsed_action and parsed_action.intent != "unknown_intent": # Only save if intent is known for now
        action_dict = parsed_action.model_dump(mode="json") # Convert Pydantic model to dict

        current_actions = player.collected_actions_json or []
        current_actions.append(action_dict)

        update_data = {"collected_actions_json": current_actions}
        await player_crud.update(db=session, db_obj=player, obj_in=update_data)
        logger.info(f"Saved action for player {player.name} (ID: {player.id}): {parsed_action.intent}")

        try:
            # Optional: React to message to show it was "understood"
            await message.add_reaction("✅") # Checkmark emoji
        except discord.Forbidden:
            logger.warning(f"Missing permissions to add reaction in guild {guild_id}, channel {message.channel.id}")
        except discord.HTTPException as e:
            logger.warning(f"Failed to add reaction: {e}")
    elif parsed_action and parsed_action.intent == "unknown_intent":
        logger.info(f"Intent for player {player.name} (ID: {player.id}) was 'unknown_intent' for message: '{message.content}'. Not saved to collected_actions.")
        # Optionally, react with a question mark for unknown intents
        # try:
        #     await message.add_reaction("❓")
        # except: pass # Ignore reaction errors


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return  # Игнорировать сообщения от самого себя

        if not message.guild: # Ignore DMs for NLU processing for now
            return

        # Standard command processing will still happen due to how Cogs work.
        # This is for additional NLU parsing of non-command messages.

        # Avoid NLU processing for messages that are likely commands
        # This is a simple check; more robust would be to see if it matches bot's command_prefix
        # However, with app commands, prefix check is less relevant for slash commands.
        # This check is more for traditional prefixed commands if they are also supported.
        if message.content.startswith(self.bot.command_prefix if isinstance(self.bot.command_prefix, str) else tuple(self.bot.command_prefix)): # type: ignore
             # logger.debug(f"Message starts with command prefix, NLU skipped: {message.content}")
             return

        # Call the transactional helper function to handle NLU logic
        # We need to pass the bot instance if the helper needs it (e.g., for notifications, not needed here)
        # And the message.
        # The session will be managed by the @transactional decorator on process_player_message_for_nlu
        try:
            # Pass `self.bot` if `process_player_message_for_nlu` needs it.
            # For now, it doesn't, but good practice if it might for e.g. sending messages.
            await process_player_message_for_nlu(self.bot, message) # type: ignore[call-arg]
        except Exception as e:
            logger.error(f"Error during NLU processing in on_message for guild {message.guild.id}: {e}", exc_info=True)


    async def _ensure_guild_config_exists(self, session: AsyncSession, guild_id: int, guild_name: str) -> GuildConfig:
        """Ensures a GuildConfig record exists for the guild, creates if not."""
        guild_config = await guild_crud.get(db=session, id=guild_id)
        if not guild_config:
            logger.info(f"Конфигурация для гильдии {guild_name} (ID: {guild_id}) не найдена, создаю новую.")
            # Ensure guild_crud.create can handle id being passed directly or remove it if it's autogen by DB sequence
            # For now, assuming GuildConfig.id is guild.id and should be set explicitly.
            guild_config_in = GuildConfig(id=guild_id, main_language='en', name=guild_name) # Added name
            guild_config = await guild_crud.create(db=session, obj_in=guild_config_in) # Pass GuildConfig instance

            # Set default main language rule
            await update_rule_config(
                db=session,
                guild_id=guild_id,
                key="guild_main_language",
                value_json={"language": "en"}
            )
            logger.info(f"Установлен язык по умолчанию 'en' для гильдии {guild_id} в RuleConfig.")
        else:
            logger.info(f"Найдена конфигурация для гильдии {guild_name} (ID: {guild_id}).")
        return guild_config

    async def _populate_default_locations(self, session: AsyncSession, guild_id: int):
        """Populates default static locations for the guild if they don't exist."""
        logger.info(f"Заполнение стандартными локациями для гильдии {guild_id}...")
        created_count = 0
        for loc_data in DEFAULT_STATIC_LOCATIONS:
            existing_location = await location_crud.get_by_static_id(
                db=session, guild_id=guild_id, static_id=loc_data["static_id"]
            )
            if not existing_location:
                # Ensure obj_in matches the fields of Location model for creation
                # guild_id will be added by create_with_guild or CRUDBase.create
                await location_crud.create_with_guild(db=session, obj_in=loc_data, guild_id=guild_id)
                created_count += 1
                logger.info(f"Создана локация '{loc_data['static_id']}' для гильдии {guild_id}.")
            else:
                logger.info(f"Локация '{loc_data['static_id']}' уже существует для гильдии {guild_id}, пропуск.")
        if created_count > 0:
            logger.info(f"Создано {created_count} стандартных локаций для гильдии {guild_id}.")
        else:
            logger.info(f"Стандартные локации уже существуют или не определены для гильдии {guild_id}.")

    @commands.Cog.listener()
    @transactional # Ensures the whole on_guild_join logic is one transaction
    async def on_guild_join(self, guild: discord.Guild, *, session: AsyncSession): # session injected by @transactional
        logger.info(f"Бот был добавлен на сервер: {guild.name} (ID: {guild.id}). Владелец: {guild.owner_id}")

        # Ensure GuildConfig and default locations are created
        await self._ensure_guild_config_exists(session=session, guild_id=guild.id, guild_name=guild.name)
        await self._populate_default_locations(session=session, guild_id=guild.id)

        # Попытка найти системный канал или первый текстовый канал для приветственного сообщения
        system_channel = guild.system_channel
        target_channel = None

        if system_channel and system_channel.permissions_for(guild.me).send_messages:
            target_channel = system_channel
        else:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    target_channel = channel
                    logger.info(f"Системный канал не найден или нет прав, выбран первый доступный: {target_channel.name}")
                    break

        if target_channel:
            try:
                await target_channel.send(f"Привет, сервер {guild.name}! Я ваш новый RPG бот. Используйте `/ping` для проверки.")
                logger.info(f"Приветственное сообщение отправлено в канал {target_channel.name} на сервере {guild.name}.")
            except discord.Forbidden:
                logger.warning(f"Нет прав для отправки приветственного сообщения в {target_channel.name} на сервере {guild.name}.")
            except Exception as e:
                logger.error(f"Ошибка при отправке приветственного сообщения на сервер {guild.name}: {e}")
        else:
            logger.warning(f"Не найден подходящий канал для отправки приветственного сообщения на сервере {guild.name}.")


    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        logger.info(f"Бот был удален с сервера: {guild.name} (ID: {guild.id})")
        # Здесь можно добавить логику очистки данных, связанных с этим сервером.
        # (согласно задаче 0.1 - просто логирование)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Обработчик ошибок команд для данного кога."""
        if isinstance(error, commands.CommandNotFound):
            # await ctx.send("Такой команды не существует. Используйте `/help` для списка команд.")
            logger.warning(f"Неизвестная команда: {ctx.message.content} от {ctx.author}")
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Не хватает аргументов для команды. {error.param.name} является обязательным.")
            logger.warning(f"Не хватает аргументов для команды {ctx.command}: {error}")
        elif isinstance(error, commands.CommandInvokeError):
            logger.error(f"Ошибка при выполнении команды {ctx.command}: {error.original}", exc_info=True)
            await ctx.send(f"Произошла ошибка при выполнении команды: {error.original}")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("У вас нет прав для выполнения этой команды.")
            logger.warning(f"Ошибка проверки прав для команды {ctx.command} от {ctx.author}: {error}")
        else:
            logger.error(f"Необработанная ошибка команды {ctx.command}: {error}", exc_info=True)
            await ctx.send("Произошла непредвиденная ошибка при выполнении команды.")

async def setup(bot: commands.Bot):
    """Функция для загрузки Cog в бота."""
    await bot.add_cog(EventCog(bot))
    logger.info("EventCog успешно загружен и добавлен в бота.")
