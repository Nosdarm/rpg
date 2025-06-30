# Этот файл делает директорию 'models' пакетом Python.

# Импортируем Base, чтобы он был доступен при импорте пакета models,
# что удобно для Alembic и других частей приложения.
from .base import Base

# Импортируем все модели, чтобы они были зарегистрированы в metadata Base.
# Это важно для Alembic, чтобы он мог обнаружить модели для создания миграций,
# а также для функций типа Base.metadata.create_all().
from .guild import GuildConfig
from .rule_config import RuleConfig
# from .player import Player # Пример будущей модели
# from .location import Location # Пример будущей модели
# ... и так далее для всех остальных моделей

# Можно также определить __all__ для контроля над тем, что импортируется с `from models import *`
# __all__ = [
#     "Base",
#     "GuildConfig",
#     "RuleConfig",
#     # "Player",
#     # "Location",
# ]

# Логгер для информации о загрузке моделей (опционально)
import logging
logger = logging.getLogger(__name__)
logger.info("Пакет моделей инициализирован. Загружены: Base, GuildConfig, RuleConfig.")
