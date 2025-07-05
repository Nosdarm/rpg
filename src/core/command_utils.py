import logging
from typing import List, Optional, Dict, Any, Union # Added Union

import discord
from discord import app_commands as dc_app_commands # Changed import style
from discord.ext import commands as ext_commands

from src.models.command_info import CommandInfo, CommandParameterInfo
# from src.core.localization_utils import get_localized_text # TODO: For localization
# from src.core.rules import get_rule # TODO: For localization context

logger = logging.getLogger(__name__)

def _get_localized_string(
    value: Union[str, dc_app_commands.locale_str, None], # Changed locale_str
    lang_code: Optional[str],
    default_str: Optional[str] = None
) -> Optional[str]:
    """
    Helper to get a localized string from a value that might be a locale_str.
    """
    if value is None:
        return default_str

    # If a Translator was used, the description might already be a plain string
    # or it could still be a locale_str if no translation was found or applied.

    # Check if it behaves like a locale_str (has message_map and message attributes)
    if hasattr(value, 'message_map') and hasattr(value, 'message') and isinstance(getattr(value, 'message_map'), dict):
        message_map = getattr(value, 'message_map')
        if lang_code and lang_code in message_map:
            return message_map[lang_code]
        return getattr(value, 'message') # Default/source string
    elif isinstance(value, str):
        return value

    # Fallback for other types or if it's None after all
    return default_str if default_str is not None else str(value) if value is not None else None


def _extract_parameter_details(
    param: discord.app_commands.Parameter,
    language: Optional[str] = None
) -> CommandParameterInfo:
    """Extracts details from a discord.app_commands.Parameter object."""

    param_type_str = str(param.type.name) # e.g., 'string', 'integer', 'user'

    # Имя параметра обычно не локализуется, но описание может быть LocaleStr
    # param.name is str
    # param.description can be locale_str
    param_description = _get_localized_string(param.description, language)
    if param_description and param_description.strip() == "-": # Handle placeholder descriptions
        param_description = None

    # TODO: Обработать choices, если они есть (param.choices)
    # choices_info = []
    # if param.choices:
    #     for choice in param.choices:
    #         # choice.name can also be locale_str
    #         choice_name = _get_localized_string(choice.name, language, str(choice.name))
    #         choices_info.append({"name": choice_name, "value": choice.value})

    return CommandParameterInfo(
        name=param.name,
        description=param_description,
        type=param_type_str,
        required=param.required,
        # choices=choices_info # TODO: Add to CommandParameterInfo model if needed
    )

def _extract_command_details(
    app_cmd: Union[dc_app_commands.Command, dc_app_commands.Group], # Command or Group
    language: Optional[str] = None, # Target language for descriptions
    base_name: Optional[str] = None
) -> List[CommandInfo]:
    """
    Extracts details from a discord.app_commands.Command or Group object.
    Returns a list because a Group can contain multiple sub-commands.
    """
    extracted_commands: List[CommandInfo] = []

    # Имена команд и групп (app_cmd.name) являются строками и не локализуются через LocaleStr.
    # Они могут быть локализованы на стороне Discord при регистрации, если разработчик бота это сделал.
    # Мы берем то имя, которое есть в объекте команды.
    current_name = app_cmd.name
    if base_name:
        current_qualified_name = f"{base_name} {current_name}"
    else:
        current_qualified_name = current_name

    # Описание команды/группы (app_cmd.description) может быть LocaleStr
    description = _get_localized_string(app_cmd.description, language)
    if description and description.strip() == "-": # Handle placeholder descriptions
        description = None

    if isinstance(app_cmd, dc_app_commands.Command):
        param_infos: List[CommandParameterInfo] = []
        # app_cmd.parameters for Command
        if hasattr(app_cmd, 'parameters') and app_cmd.parameters:
            for param in app_cmd.parameters:
                param_infos.append(_extract_parameter_details(param, language))

        # TODO: Обработка информации о guild_only / nsfw / default_permissions / dm_permission
        # app_cmd.guild_only
        # app_cmd.nsfw
        # app_cmd.default_permissions (может быть сложным для простого представления)
        # app_cmd.dm_permission

        extracted_commands.append(CommandInfo(
            name=current_qualified_name,
            description=description,
            parameters=param_infos
        ))
    elif isinstance(app_cmd, dc_app_commands.Group): # Ensuring this is correct
        # logger.debug(f"Processing command group: {current_qualified_name} with description: {description}")
        # Группа может иметь свое описание, но сама не является исполняемой командой с параметрами в том же смысле.
        # UI может захотеть отобразить описание группы. Пока мы его извлекаем, но не создаем CommandInfo для самой группы.
        # Вместо этого мы рекурсивно обрабатываем ее подкоманды.
        # Если нужно будет показать и саму группу как сущность, нужно будет изменить логику.
        for sub_cmd_or_group in app_cmd.commands: # app_cmd.commands содержит Command или Group
            extracted_commands.extend(
                _extract_command_details(sub_cmd_or_group, language=language, base_name=current_qualified_name)
            )

    return extracted_commands


async def get_bot_commands(
    bot: ext_commands.Bot,
    guild_id: Optional[int] = None, # Пока не используется для выбора команд, но может для языка
    language: Optional[str] = None # Язык для локализации описаний
) -> List[CommandInfo]:
    """
    Retrieves a list of registered application (slash) commands from the bot.

    Args:
        bot: The bot instance.
        guild_id: Optional guild ID for context (e.g., for future language determination from GuildConfig).
        language: Optional language code for localization of descriptions. If None, default strings from
                  LocaleStr objects will be used, or the direct string value if not a LocaleStr.

    Returns:
        A list of CommandInfo objects.
    """
    command_infos: List[CommandInfo] = []

    final_language_code = language
    # logger.debug(f"Using language code for command extraction: {final_language_code}")

    # bot.tree.get_commands() возвращает список AppCommand объектов (Command или Group)
    # It can also return ContextMenuCommand, all are AppCommand subclasses.
    all_app_commands_in_tree: List[dc_app_commands.AppCommand] = bot.tree.get_commands() # type: ignore
    # logger.debug(f"Found {len(all_app_commands_in_tree)} top-level app commands in bot.tree.")

    for app_cmd_candidate in all_app_commands_in_tree:
        if isinstance(app_cmd_candidate, (dc_app_commands.Command, dc_app_commands.Group)):
            command_infos.extend(
                _extract_command_details(app_cmd_candidate, language=final_language_code)
            )
        # else: ContextMenuCommands are ignored for now

    # Сортируем команды по имени для консистентности
    command_infos.sort(key=lambda c: c.name)

    logger.info(f"Extracted {len(command_infos)} command details using language: {final_language_code or 'default/source'}.")
    return command_infos
