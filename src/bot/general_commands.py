import logging
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

class CommandCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("CommandCog инициализирован.")

    @commands.command(name="ping", help="Проверяет задержку ответа бота.")
    async def ping_command(self, ctx: commands.Context):
        """
        Отправляет задержку бота в миллисекундах.
        """
        latency_ms = round(self.bot.latency * 1000)
        logger.info(f"Команда /ping вызвана {ctx.author} на сервере {ctx.guild.name if ctx.guild else 'DM'}. Задержка: {latency_ms}ms")
        await ctx.send(f"Понг! Задержка: {latency_ms}ms")

    # Другие команды будут добавляться сюда

    @commands.command(name="start", help="Начать новое приключение или продолжить существующее.")
    async def start_command(self, ctx: commands.Context):
        """
        Регистрирует игрока в текущей гильдии, если он еще не зарегистрирован,
        и предоставляет информацию о его персонаже.
        """
        if not ctx.guild:
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        guild_id = ctx.guild.id
        discord_id = ctx.author.id
        player_name = ctx.author.display_name # Использовать display_name как имя по умолчанию

        from src.core.database import get_db_session
        from src.core.crud.crud_player import player_crud
        from src.core.crud.crud_location import location_crud
        from src.models.enums import PlayerStatus # Для установки начального статуса

        async with get_db_session() as session:
            try:
                player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=discord_id)

                if player:
                    # Игрок уже существует
                    location_name = "неизвестно"
                    if player.current_location_id:
                        loc = await location_crud.get(session, id=player.current_location_id, guild_id=guild_id)
                        if loc and loc.name_i18n:
                            # Попытка получить язык игрока, если он есть, иначе язык гильдии или 'en'
                            lang = player.selected_language or "en" # Добавить получение языка гильдии позже
                            from src.core.locations_utils import get_localized_text # Corrected import
                            location_name = get_localized_text(loc, "name", lang, "en")

                    await ctx.send(
                        f"{ctx.author.mention}, ты уже в игре! \n"
                        f"Имя: {player.name}\n"
                        f"Уровень: {player.level}\n"
                        f"Золото: {player.gold}\n"
                        f"Текущий статус: {player.current_status.value}\n"
                        f"Текущая локация: {location_name}"
                    )
                else:
                    # Новый игрок
                    # 1. Найти стартовую локацию
                    # Предположим, стартовая локация имеет static_id 'starting_village_square'
                    # Это значение может быть взято из RuleConfig в будущем
                    starting_location_static_id = "starting_village_square"
                    start_loc = await location_crud.get_by_static_id(
                        session, guild_id=guild_id, static_id=starting_location_static_id
                    )

                    if not start_loc:
                        logger.error(f"Стартовая локация '{starting_location_static_id}' не найдена для сервера {guild_id}.")
                        await ctx.send("Не могу начать игру: стартовая локация не настроена для этого сервера. Обратитесь к администратору.")
                        return

                    start_location_id = start_loc.id

                    # 2. Создать игрока
                    # Используем CRUDPlayer.create_with_defaults или напрямую CRUDBase.create
                    # create_with_defaults удобнее, так как он инкапсулирует логику начальных значений

                    # Задаем данные для нового игрока
                    # selected_language можно будет брать из GuildConfig.main_language или RuleConfig
                    new_player_data = {
                        "guild_id": guild_id,
                        "discord_id": discord_id,
                        "name": player_name,
                        "current_location_id": start_location_id,
                        "selected_language": "en", # TODO: get from guild config or player settings
                        "xp": 0,
                        "level": 1,
                        "unspent_xp": 0,
                        "gold": 10, # Стартовое золото
                        "current_status": PlayerStatus.EXPLORING,
                        "collected_actions_json": []
                    }

                    player = await player_crud.create(session, obj_in=new_player_data) # guild_id is part of obj_in

                    logger.info(f"Новый игрок создан: {player_name} (Discord ID: {discord_id}) на сервере {guild_id}.")

                    from src.core.locations_utils import get_localized_text # Corrected import
                    location_name = get_localized_text(start_loc, "name", player.selected_language or "en", "en")

                    await ctx.send(
                        f"Добро пожаловать в мир, {ctx.author.mention}! \n"
                        f"Твой персонаж **{player.name}** (уровень {player.level}) был создан. \n"
                        f"Ты начинаешь в локации: **{location_name}**. \n"
                        f"Удачи в приключениях! Используй команды, чтобы взаимодействовать с миром."
                    )
                # Коммит сессии управляется get_db_session
            except Exception as e:
                logger.error(f"Ошибка при выполнении команды /start для {ctx.author} на сервере {guild_id}: {e}", exc_info=True)
                await ctx.send("Произошла ошибка при обработке твоей команды. Попробуй позже.")
                # Роллбэк сессии управляется get_db_session

async def setup(bot: commands.Bot):
    """Функция для загрузки Cog в бота."""
    await bot.add_cog(CommandCog(bot))
    logger.info("CommandCog успешно загружен и добавлен в бота.")
