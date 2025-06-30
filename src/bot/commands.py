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

async def setup(bot: commands.Bot):
    """Функция для загрузки Cog в бота."""
    await bot.add_cog(CommandCog(bot))
    logger.info("CommandCog успешно загружен и добавлен в бота.")
