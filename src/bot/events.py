import logging
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

class EventCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("EventCog инициализирован.")

    @commands.Cog.listener()
    async def on_ready(self):
        # Этот on_ready в Cog будет вызван в дополнение к on_ready в BotCore, если он там есть.
        # Обычно основной on_ready оставляют в главном классе бота.
        # Но для демонстрации оставим здесь логирование.
        logger.info(f"EventCog: Бот {self.bot.user.name} готов (из Cog).")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return  # Игнорировать сообщения от самого себя

        # logger.info(f"Сообщение от {message.author} в канале {message.channel}: {message.content}")
        # Обработка команд будет осуществляться через command_prefix, заданный в BotCore.
        # Здесь можно добавить логику, не связанную с командами, если это необходимо.
        # Например, реакции на ключевые слова, сбор статистики и т.д.

        # Важно: если вы хотите, чтобы команды обрабатывались, убедитесь, что
        # `await self.bot.process_commands(message)` вызывается где-то,
        # если вы переопределяете on_message и не вызываете super().on_message.
        # В данном случае, так как мы используем Cog, discord.py сам позаботится об этом.
        pass

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        logger.info(f"Бот был добавлен на сервер: {guild.name} (ID: {guild.id}). Владелец: {guild.owner_id}")
        # Здесь можно добавить логику инициализации для нового сервера,
        # например, создание стандартных каналов, ролей или запись в БД.
        # (согласно задаче 0.1 - просто логирование)

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
