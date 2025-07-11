import logging
import discord
from discord.ext import commands
# Импорты для событий и команд будут добавлены на шаге setup_hook
# import bot.events as bot_events # Неправильно, нужно импортировать модуль для load_extension
# import bot.commands as bot_commands # Неправильно

logger = logging.getLogger(__name__)

class BotCore(commands.Bot):
    """
    Основной класс бота, наследуемый от commands.Bot.
    """
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        logger.info("Инициализация BotCore...")
        # Токен загружается и передается в self.start() из main.py

    async def setup_hook(self):
        """
        Асинхронный метод, вызываемый после логина бота, но перед подключением к WebSocket.
        Идеальное место для загрузки расширений (cogs) и других асинхронных настроек.
        """
        logger.info("Выполняется setup_hook...")

        # Загрузка когов
        # Пути к когам указываются относительно корневой директории проекта, если PYTHONPATH настроен,
        # или относительно директории, откуда запускается main.py, используя точки как разделители пакетов.
        # В нашем случае, если main.py в src/, а коги в src/bot/, то путь будет 'bot.events' и 'bot.commands'
        # Project root (parent of 'src') is added to sys.path by main.py.
        # Therefore, we should use 'backend.module.submodule' for clarity and correctness.

        # Загрузка когов из settings.py
        try:
            from backend.config.settings import BOT_COGS
            extensions_to_load = BOT_COGS
            if not extensions_to_load:
                logger.warning("Список BOT_COGS в settings.py пуст. Расширения не будут загружены.")
                return
            logger.info(f"Будут загружены следующие расширения из BOT_COGS: {extensions_to_load}")
        except ImportError:
            logger.error("Не удалось импортировать BOT_COGS из backend.config.settings. Расширения не будут загружены.")
            return
        except AttributeError:
            logger.error("Переменная BOT_COGS не найдена в backend.config.settings. Расширения не будут загружены.")
            return


        for extension in extensions_to_load:
            try:
                await self.load_extension(extension)
                logger.info(f"Расширение '{extension}' успешно загружено.")
            except commands.ExtensionNotFound:
                logger.error(f"Ошибка: Расширение '{extension}' не найдено.")
            except commands.ExtensionAlreadyLoaded:
                logger.warning(f"Расширение '{extension}' уже было загружено.")
            except commands.NoEntryPointError:
                logger.error(f"Ошибка: В расширении '{extension}' отсутствует функция setup().")
            except commands.ExtensionFailed as e:
                logger.error(f"Ошибка при загрузке расширения '{extension}': {e.original}", exc_info=True)
            except Exception as e:
                logger.error(f"Непредвиденная ошибка при загрузке расширения '{extension}': {e}", exc_info=True)

        # Синхронизация команд приложения (слеш-команд) после загрузки всех расширений
        try:
            # Sync all commands globally.
            # For guild-specific commands, you might use: await self.tree.sync(guild=discord.Object(id=YOUR_GUILD_ID))
            # If no guild is specified, commands are synced globally.
            # Sync all commands globally.
            # For guild-specific commands, you might use: await self.tree.sync(guild=discord.Object(id=YOUR_GUILD_ID))
            # If no guild is specified, commands are synced globally.
            logger.info("Attempting to sync application commands globally...")
            synced = await self.tree.sync()
            logger.info(f"Successfully synced {len(synced)} application commands globally.")
            if synced:
                logger.info("Details of globally synced commands:")
                for cmd in synced:
                    command_type = "Unknown"
                    if isinstance(cmd, discord.app_commands.Command):
                        command_type = "Command"
                    elif isinstance(cmd, discord.app_commands.Group):
                        command_type = "Group"
                    logger.info(f"  - Name: {cmd.name}, ID: {cmd.id}, Type: {command_type}, Description: '{cmd.description}', Guild ID: {cmd.guild_id or 'Global'}")
            else:
                logger.info("No application commands were returned from the sync operation.")
        except Exception as e:
            logger.error(f"Ошибка при синхронизации команд приложения: {e}", exc_info=True)

        logger.info("setup_hook завершен.")

    async def on_ready(self):
        """
        Событие, вызываемое при полной готовности бота.
        Это событие может быть также определено в Cog'е (например, в EventCog).
        discord.py вызовет оба, если они есть.
        """
        if self.user: # Add a check for self.user
            logger.info(f'Бот {self.user.name} (ID: {self.user.id}) подключен и готов к работе!')
            logger.info(f'Подключен к {len(self.guilds)} серверам (гильдиям):')
            for guild in self.guilds:
                logger.info(f"- {guild.name} (ID: {guild.id})")
        else:
            logger.error("Bot is ready, but self.user is None. This should not happen.")
        # Если вы хотите синхронизировать команды приложения (слеш-команды) при запуске:
        # try:
        #     synced = await self.tree.sync()
        #     logger.info(f"Синхронизировано {len(synced)} команд приложения.")
        # except Exception as e:
        #     logger.error(f"Ошибка синхронизации команд приложения: {e}")


    # async def on_error(self, event_method, *args, **kwargs):
    #     """Обработчик общих ошибок discord.py."""
    #     logger.error(f"Произошла ошибка в событии discord.py '{event_method}': args={args} kwargs={kwargs}", exc_info=True)


# Запуск бота осуществляется из main.py.
# Функция run_bot больше не нужна здесь, так как логика запуска в main.py.
