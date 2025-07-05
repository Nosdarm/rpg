import logging
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Any, List # Added Any and List

from src.core.database import get_db_session, transactional
# Duplicated logging, discord, app_commands, commands, Optional, Any, List imports removed for overwrite
# from src.core.database import get_db_session, transactional # Duplicated
from src.core.crud.crud_player import player_crud
from src.core.crud.crud_location import location_crud
from src.core.crud.crud_guild import guild_crud
from src.models.guild import GuildConfig
from src.models.player import PlayerStatus
from src.models.location import LocationType # Needed for _populate_default_locations
from src.core.rules import update_rule_config # For setting default language
from src.bot.events import DEFAULT_STATIC_LOCATIONS # Используем список дефолтных локаций
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.command_utils import get_bot_commands
from src.models.command_info import CommandInfo # CommandParameterInfo might be needed for detailed view

logger = logging.getLogger(__name__)


# Helper methods, similar to those in EventCog, but localized or adapted for GeneralCog
async def _ensure_guild_config_in_command(session: AsyncSession, guild_id: int, guild_name: str) -> GuildConfig:
    """Ensures a GuildConfig record exists for the guild, creates if not. (Adapted for command context)"""
    guild_config = await guild_crud.get(session=session, id=guild_id)
    if not guild_config:
        logger.info(f"Конфигурация для гильдии {guild_name} (ID: {guild_id}) не найдена в команде, создаю новую.")
        guild_config_data = {"id": guild_id, "main_language": 'en', "name": guild_name} # Ensure name is passed
        guild_config = await guild_crud.create(session=session, obj_in=guild_config_data)

        await update_rule_config(
            session=session,
            guild_id=guild_id,
            key="guild_main_language",
            value={"language": "en"}
        )
        logger.info(f"Установлен язык по умолчанию 'en' для гильдии {guild_id} в RuleConfig (из команды).")

        # After creating guild_config, also populate default locations
        await _populate_default_locations_in_command(session=session, guild_id=guild_id)
    else:
        logger.info(f"Найдена конфигурация для гильдии {guild_name} (ID: {guild_id}) (из команды).")
    return guild_config

async def _populate_default_locations_in_command(session: AsyncSession, guild_id: int):
    """Populates default static locations for the guild if they don't exist. (Adapted for command context)"""
    logger.info(f"Заполнение стандартными локациями для гильдии {guild_id} (из команды)...")
    created_count = 0
    for loc_data in DEFAULT_STATIC_LOCATIONS:
        # Ensure loc_data is correctly structured for create_with_guild, especially 'type'
        loc_data_copy = loc_data.copy() # Avoid modifying the original DEFAULT_STATIC_LOCATIONS list
        if isinstance(loc_data_copy.get("type"), str): # Assuming LocationType enum members are passed as strings initially
            try:
                loc_data_copy["type"] = LocationType[loc_data_copy["type"].upper()]
            except KeyError:
                logger.error(f"Invalid LocationType string '{loc_data_copy['type']}' in DEFAULT_STATIC_LOCATIONS for static_id '{loc_data_copy['static_id']}'. Skipping.")
                continue
        elif not isinstance(loc_data_copy.get("type"), LocationType):
             logger.error(f"LocationType for static_id '{loc_data_copy['static_id']}' is not a valid string or LocationType enum. Skipping.")
             continue


        existing_location = await location_crud.get_by_static_id(
            session=session, guild_id=guild_id, static_id=loc_data_copy["static_id"]
        )
        if not existing_location:
            # create_with_guild now expects obj_in to be a Pydantic schema or compatible dict
            # Ensure loc_data_copy is compatible (e.g. static_id, name_i18n, descriptions_i18n, type)
            await location_crud.create_with_guild(session=session, obj_in=loc_data_copy, guild_id=guild_id)
            created_count += 1
            logger.info(f"Создана локация '{loc_data_copy['static_id']}' для гильдии {guild_id} (из команды).")
        else:
            logger.info(f"Локация '{loc_data_copy['static_id']}' уже существует для гильдии {guild_id}, пропуск (из команды).")

    if created_count > 0:
        logger.info(f"Создано {created_count} стандартных локаций для гильдии {guild_id} (из команды).")
    else:
        logger.info(f"Стандартные локации уже существуют или не определены для гильдии {guild_id} (из команды).")

class GeneralCog(commands.Cog, name="General Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("GeneralCog инициализирован.")

    @transactional # Apply transactional to the internal method
    async def _start_command_internal(self, interaction: discord.Interaction, *, session: AsyncSession):
        """Внутренняя логика команды start, работает с сессией."""
        # Defer interaction immediately, make it ephemeral so only user sees "thinking..."
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild_id: # This check might be redundant if called from wrapper that already checks
            await interaction.followup.send("Эта команда должна использоваться на сервере (внутренняя проверка).", ephemeral=True)
            return

        guild_id = interaction.guild_id
        discord_id = interaction.user.id
        player_name: str = interaction.user.display_name or interaction.user.name or "Adventurer"
        player_locale = str(interaction.locale) if interaction.locale else 'en'

        # Ensure guild configuration exists before proceeding
        if interaction.guild: # Should always be true due to earlier check
            await _ensure_guild_config_in_command(session=session, guild_id=guild_id, guild_name=interaction.guild.name)
        else: # Should not happen
            logger.error("Guild object is None in _start_command_internal despite initial check.")
            await interaction.response.send_message("Произошла ошибка: информация о сервере отсутствует.", ephemeral=True)
            return

        existing_player = await player_crud.get_by_discord_id(session=session, guild_id=guild_id, discord_id=discord_id)

        if existing_player:
            await interaction.followup.send(
                f"Привет, {player_name}! Ты уже в игре. Твой персонаж уровня {existing_player.level}.",
                ephemeral=True
            )
            return

        starting_location_id: Optional[int] = None
        starting_location_name: str = "неизвестной локации (пожалуйста, сообщите Мастеру)" # Default string
        if DEFAULT_STATIC_LOCATIONS:
            first_default_loc_static_id_optional: Optional[Any] = DEFAULT_STATIC_LOCATIONS[0].get("static_id")
            if isinstance(first_default_loc_static_id_optional, str) and first_default_loc_static_id_optional:
                first_default_loc_static_id: str = first_default_loc_static_id_optional # Now clearly a string
                start_loc = await location_crud.get_by_static_id(session=session, guild_id=guild_id, static_id=first_default_loc_static_id) # FIX: db to session
                if start_loc:
                    starting_location_id = start_loc.id
                    loc_name_i18n = start_loc.name_i18n or {} # Location.name_i18n defaults to {}
                    name_candidate = loc_name_i18n.get(player_locale, loc_name_i18n.get('en', first_default_loc_static_id))
                    # name_candidate is guaranteed to be str because first_default_loc_static_id is str.
                    starting_location_name = name_candidate
                else:
                    logger.warning(f"Не удалось найти стартовую локацию по static_id '{first_default_loc_static_id}' для гильдии {guild_id} при создании игрока {discord_id}.")
            else:
                logger.warning(f"В DEFAULT_STATIC_LOCATIONS первая локация не имеет static_id.")
        else:
            logger.warning(f"Список DEFAULT_STATIC_LOCATIONS пуст для гильдии {guild_id}. Невозможно назначить стартовую локацию для игрока {discord_id}.")

        try:
            new_player = await player_crud.create_with_defaults(
                session=session,
                guild_id=guild_id,
                discord_id=discord_id,
                name=player_name,
                current_location_id=starting_location_id,
                selected_language=player_locale
            )
            new_player.current_status = PlayerStatus.EXPLORING
            session.add(new_player)

            logger.info(f"Новый игрок {player_name} (Discord ID: {discord_id}) создан для гильдии {guild_id} в локации ID {starting_location_id}.")
            await interaction.followup.send(
                f"Добро пожаловать в игру, {player_name}! Твой персонаж создан и находится в локации: {starting_location_name}. "
                f"Твой язык установлен на {player_locale}. Удачи в приключениях!",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Ошибка при создании игрока {player_name} (Discord ID: {discord_id}) для гильдии {guild_id}: {e}", exc_info=True)
            if interaction.is_expired():
                 logger.warning(f"Interaction expired before error message could be sent for player {player_name} (Discord ID: {discord_id}).")
            else:
                await interaction.followup.send("Произошла ошибка при создании твоего персонажа. Пожалуйста, попробуй позже.", ephemeral=True)

    @app_commands.command(name="start", description="Начать игру или проверить существующего персонажа.")
    async def start_command(self, interaction: discord.Interaction):
        """Начинает игру для нового игрока или показывает информацию о существующем (wrapper)."""
        if not interaction.guild_id:
            await interaction.response.send_message("Эту команду можно использовать только на сервере.", ephemeral=True)
            return
        await self._start_command_internal(interaction) # type: ignore

    @app_commands.command(name="ping", description="Проверяет задержку ответа бота.")
    async def ping_command(self, interaction: discord.Interaction):
        # Diagnostic: Try to log immediately and send a direct response
        logger.info(f"--- PING COMMAND REACHED --- User: {interaction.user} (ID: {interaction.user.id}), Guild: {interaction.guild_id}, Channel: {interaction.channel_id}")
        try:
            # Try to respond directly without deferring for this test
            latency_ms = round(self.bot.latency * 1000)
            await interaction.response.send_message(f"Pong! Diagnostic Ping. Latency: {latency_ms}ms", ephemeral=True)
            logger.info(f"--- PING COMMAND: Successfully sent diagnostic response. Latency: {latency_ms}ms ---")
        except Exception as e:
            logger.error(f"--- PING COMMAND ERROR: {e} ---", exc_info=True)

    @app_commands.command(name="help", description="Shows a list of commands or details for a specific command.")
    @app_commands.describe(command_name="The specific command to get help for (e.g., 'ping' or 'party create').")
    async def help_command(self, interaction: discord.Interaction, command_name: Optional[str] = None):
        """
        Provides help information for bot commands.
        Can list all commands or show details for a specific command.
        """
        # THIS IS THE CORRECTED PART - NO DUPLICATE DOCSTRING OR TEXT BEFORE await
        logger.info(f"/help command initiated by {interaction.user} (ID: {interaction.user.id}) in guild {interaction.guild_id} (channel {interaction.channel_id}).")
        logger.debug(f"Received command_name: '{command_name}'")
        await interaction.response.defer(ephemeral=True)

        try:
            # Determine language for command descriptions
            lang_code = str(interaction.locale) if interaction.locale else 'en'
            logger.debug(f"Determined language code for help: {lang_code}")

            all_commands: List[CommandInfo] = await get_bot_commands(
                bot=self.bot,
                language=lang_code
            )
            logger.info(f"Retrieved {len(all_commands)} commands via get_bot_commands.")
            if logger.isEnabledFor(logging.DEBUG) and all_commands: # Avoid logging large list if not in debug
                try:
                    command_names_for_log = [cmd.name for cmd in all_commands]
                    logger.debug(f"Command names retrieved: {command_names_for_log}")
                except Exception as log_ex:
                    logger.debug(f"Could not serialize command names for logging: {log_ex}")

            logger.info("--- HELP: CHECKPOINT 1 --- About to check 'if not all_commands'")
            if not all_commands:
                logger.warning("No commands returned by get_bot_commands. Sending 'no commands found' message.")
                await interaction.followup.send("No commands found or unable to retrieve command list.", ephemeral=True)
                return

            logger.info(f"--- HELP: CHECKPOINT 2 --- About to check 'if command_name' (value: {command_name})")
            if command_name:
                logger.debug(f"Processing specific help for command_name: '{command_name}'")
                # Specific command help
                target_command_name = command_name.lower()
                found_cmd_info: Optional[CommandInfo] = None
                for cmd_info in all_commands:
                    if cmd_info.name.lower() == target_command_name:
                        found_cmd_info = cmd_info
                        break

                if found_cmd_info:
                    logger.info(f"Found specific command info for '{command_name}': Name='{found_cmd_info.name}', Desc='{found_cmd_info.description}', Params={len(found_cmd_info.parameters) if found_cmd_info.parameters else 0}")
                    embed = discord.Embed(
                        title=f"Help for `/{found_cmd_info.name}`",
                        description=found_cmd_info.description or "No description available.",
                        color=discord.Color.green() # Different color for specific help
                    )
                    if found_cmd_info.parameters:
                        param_details = []
                        for param in found_cmd_info.parameters:
                            param_desc = param.description or "No specific description."
                            required_text = "Yes" if param.required else "No"
                            param_details.append(
                                f"**{param.name}** (`{param.type}`)\n"
                                f"Required: {required_text}\n"
                                f"Description: {param_desc}"
                            )
                        embed.add_field(name="Parameters", value="\n\n".join(param_details), inline=False)
                    else:
                        embed.add_field(name="Parameters", value="This command takes no parameters.", inline=False)

                    embed.set_footer(text=f"Language: {lang_code}")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    logger.debug(f"Sent specific help embed for '{command_name}'.")
                else:
                    logger.warning(f"Command `/{command_name}` not found in all_commands. Sending 'not found' message.")
                    await interaction.followup.send(f"Command `/{command_name}` not found. Use `/help` to see all available commands.", ephemeral=True)
            else:
                logger.info("--- HELP: CHECKPOINT 3 --- Entering general help block")
                logger.debug("Processing general help (listing all commands).") # Keep this if log level is DEBUG

                logger.info("--- HELP: Attempting to create general help embed ---") # NEW LOG
                embed = discord.Embed(
                    title="Bot Commands Help",
                    description=f"Here's a list of available commands. Use `/help command_name` for more details on a specific command.\nLanguage: {lang_code}",
                    color=discord.Color.blue()
                )
                embed.set_footer(text=f"Total commands: {len(all_commands)}")
                logger.info(f"--- HELP: Embed created. Title: '{embed.title}', Num All Cmds: {len(all_commands)} ---") # NEW LOG

                command_list_str = []
                current_length = 0
                logger.info("--- HELP: Starting to loop through commands for embed description ---") # NEW LOG
                for i, cmd_info in enumerate(all_commands):
                    desc = cmd_info.description or "No description available."
                    entry = f"**/{cmd_info.name}** - {desc}"
                    logger.debug(f"--- HELP: Processing command for embed: {cmd_info.name} (Entry length: {len(entry)}) ---") # DEBUG LOG
                    if current_length + len(entry) + 2 < 4000: # +2 for \n
                        command_list_str.append(entry)
                        current_length += len(entry) + 2
                    else:
                        command_list_str.append("...") # Indicate truncation
                        logger.warning(f"--- HELP: Help message truncated. Index: {i}, Current Length: {current_length}, Total Commands: {len(all_commands)} ---") # NEW LOG
                        break

                logger.info(f"--- HELP: Finished loop. {len(command_list_str)} entries for embed. Current length: {current_length} ---") # NEW LOG

                if command_list_str:
                    embed.description += "\n\n" + "\n".join(command_list_str)
                    logger.info("--- HELP: Added command list to embed description ---") # NEW LOG
                else:
                    logger.warning("--- HELP: Command list string is empty for general help embed! ---") # NEW LOG
                    embed.description += "\n\nNo commands to display."

                logger.info("--- HELP: Attempting to send general help embed ---") # NEW LOG
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info("--- HELP: Successfully sent general help embed ---") # CHANGED TO INFO

        except Exception as e:
            # Log the error first thing in the except block
            logger.error(f"Error in /help command: {e}", exc_info=True)
            if interaction.is_expired():
                logger.warning("Interaction expired before error message could be sent in /help.")
            else:
                await interaction.followup.send("An error occurred while fetching help information.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))
    logger.info("GeneralCog успешно загружен.")
