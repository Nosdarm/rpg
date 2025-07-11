import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from discord.ext import commands as ext_commands

from backend.core.command_utils import get_bot_commands
from backend.models.command_info import CommandListResponse, CommandInfo # CommandInfo for type hint
# from backend.core.localization_utils import get_guild_language_or_default # Potential
# from backend.core.database import get_session, AsyncSession # Potential

logger = logging.getLogger(__name__)
router = APIRouter()

# Зависимость для получения экземпляра бота
# Это предположение, конкретная реализация может отличаться в проекте
# Например, бот может храниться в request.app.state.bot
async def get_bot_instance(request: Request) -> ext_commands.Bot:
    """
    Dependency to get the bot instance.
    Assumes bot is stored in request.app.state.bot or similar.
    Adjust this based on how the bot instance is made available to FastAPI.
    """
    bot_instance = getattr(request.app.state, 'bot', None)
    if not bot_instance:
        logger.error("Bot instance not found in request.app.state.bot")
        raise HTTPException(status_code=500, detail="Bot instance not available.")
    if not isinstance(bot_instance, ext_commands.Bot):
        logger.error(f"Found instance in request.app.state.bot is not a discord.ext.commands.Bot, it's {type(bot_instance)}")
        raise HTTPException(status_code=500, detail="Retrieved bot instance is of incorrect type.")
    return bot_instance


@router.get(
    "/commands/",
    response_model=CommandListResponse,
    summary="Get Bot Commands",
    description="Retrieves a list of available bot application (slash) commands with their details."
)
async def list_bot_commands(
    request: Request, # Чтобы получить доступ к app.state
    guild_id: Optional[int] = None,
    lang: Optional[str] = None,
    # db_session: AsyncSession = Depends(get_session), # Если язык нужно брать из GuildConfig
    bot: ext_commands.Bot = Depends(get_bot_instance)
) -> CommandListResponse:
    """
    Provides a list of all registered application commands for the bot.

    - **guild_id**: Optional Discord Guild ID. If provided, can be used to determine
                   the language for descriptions if `lang` is not set.
    - **lang**: Optional language code (e.g., 'en', 'ru') to request localized
                information if available. Overrides language detection via guild_id.
    """
    logger.debug(f"API /commands/ called with guild_id: {guild_id}, lang: {lang}")

    final_lang_to_use = lang # Приоритет у явно переданного языка

    # Если lang не указан, и есть guild_id, пытаемся получить язык гильдии.
    # Это потребует доступа к GuildConfig, а значит к сессии БД.
    # Для этого нужно раскомментировать db_session и get_guild_language_or_default
    # from backend.core.database import get_session, AsyncSession
    # from backend.core.localization_utils import get_guild_language_or_default
    # Временно закомментировано, так как get_guild_language_or_default не реализована и требует db_session
    # if not final_lang_to_use and guild_id:
    #     try:
    #         # Предполагается, что у бота есть доступ к db_session_factory или аналогичному механизму
    #         # async with bot.db_session_factory() as session: # Пример
    #         #     final_lang_to_use = await get_guild_language_or_default(session, guild_id)
    #         # logger.info(f"Language for guild {guild_id} determined as: {final_lang_to_use}")
    #         pass # Placeholder for now
    #     except Exception as e:
    #         logger.warning(f"Could not determine language for guild {guild_id}: {e}. Proceeding without specific language.")

    # Если язык все еще не определен, можно использовать язык по умолчанию для бота
    if not final_lang_to_use:
        # Доступ к настройкам бота может быть разным, например, bot.settings.DEFAULT_LANGUAGE
        # Или можно использовать константу из backend.config.settings
        from backend.config.settings import settings
        final_lang_to_use = settings.BOT_LANGUAGE
        logger.debug(f"Using default bot language: {final_lang_to_use}")

    logger.info(f"API /commands/ - effective language for command details: {final_lang_to_use}")

    try:
        commands_list: List[CommandInfo] = await get_bot_commands(
            bot=bot,
            guild_id=guild_id,
            language=final_lang_to_use # Передаем определенный язык
        )

        # language_code в ответе должен быть тем языком, который фактически использовался
        # для получения локализованных строк.
        return CommandListResponse(commands=commands_list, language_code=final_lang_to_use)

    except Exception as e:
        logger.error(f"Error retrieving bot commands: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve bot commands.")

# TODO: Этот роутер нужно будет добавить в основное приложение FastAPI в main.py
# Например: app.include_router(commands_api_router, prefix="/api/v1", tags=["Bot Commands"])
