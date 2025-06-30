import logging
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

        extensions_to_load = [
            'bot.events',  # Имя файла events.py в директории bot
            'bot.commands', # Имя файла commands.py в директории bot (для /ping и /start)
            'bot.commands.party_commands' # Имя файла party_commands.py в директории bot/commands
        ]

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

        logger.info("setup_hook завершен.")

    async def on_ready(self):
        """
        Событие, вызываемое при полной готовности бота.
        Это событие может быть также определено в Cog'е (например, в EventCog).
        discord.py вызовет оба, если они есть.
        """
        logger.info(f'Бот {self.user.name} (ID: {self.user.id}) подключен и готов к работе!')
        logger.info(f'Подключен к {len(self.guilds)} серверам (гильдиям):')
        for guild in self.guilds:
            logger.info(f"- {guild.name} (ID: {guild.id})")
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
