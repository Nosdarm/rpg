# Этот файл делает директорию 'models' пакетом Python.

# Импортируем Base, чтобы он был доступен при импорте пакета models,
# что удобно для Alembic и других частей приложения.
from .base import Base

# Импортируем все модели, чтобы они были зарегистрированы в metadata Base.
# Это важно для Alembic, чтобы он мог обнаружить модели для создания миграций,
# а также для функций типа Base.metadata.create_all().
from .guild import GuildConfig
from .rule_config import RuleConfig
from .location import Location, LocationType # Import Location model and Enum
from .enums import PlayerStatus, PartyTurnStatus, OwnerEntityType, EventType, RelationshipEntityType # Import game specific Enums
from .player import Player # Import Player model
from .party import Party # Import Party model
from .generated_npc import GeneratedNpc # Import GeneratedNpc model
from .generated_faction import GeneratedFaction # Import GeneratedFaction model
from .item import Item # Import Item model
from .inventory_item import InventoryItem # Import InventoryItem model
from .story_log import StoryLog # Import StoryLog model
from .relationship import Relationship # Import Relationship model
from .player_npc_memory import PlayerNpcMemory # Import PlayerNpcMemory model
from .ability import Ability # Import Ability model
from .skill import Skill # Import Skill model
from .status_effect import StatusEffect, ActiveStatusEffect # Import StatusEffect models
from .quest import Questline, GeneratedQuest, QuestStep, PlayerQuestProgress # Import Quest models
from .mobile_group import MobileGroup # Import MobileGroup model
from .crafting_recipe import CraftingRecipe # Import CraftingRecipe model
# ... и так далее для всех остальных моделей

# Можно также определить __all__ для контроля над тем, что импортируется с `from models import *`
# __all__ = [
#     "Base",
#     "GuildConfig",
#     "RuleConfig",
#     "Location",
#     "LocationType",
#     "PlayerStatus",
#     "PartyTurnStatus",
#     "OwnerEntityType",
#     "EventType",
#     "RelationshipEntityType",
#     "QuestStatus", # Enum
#     "Player",
#     "Party",
#     "GeneratedNpc",
#     "GeneratedFaction",
#     "Item",
#     "InventoryItem",
#     "StoryLog",
#     "Relationship",
#     "PlayerNpcMemory",
#     "Ability",
#     "Skill",
#     "StatusEffect",
#     "ActiveStatusEffect",
#     "Questline",
#     "GeneratedQuest",
#     "QuestStep",
#     "PlayerQuestProgress",
#     "MobileGroup",
#     "CraftingRecipe",
# ]

# Логгер для информации о загрузке моделей (опционально)
import logging
logger = logging.getLogger(__name__)
# Обновляем список загруженных моделей в логгере
from .enums import QuestStatus # Ensure QuestStatus is explicitly mentioned if not covered by * from enums
logger.info(
    "Пакет моделей инициализирован. Загружены: Base, GuildConfig, RuleConfig, Location, LocationType, "
    "PlayerStatus, PartyTurnStatus, OwnerEntityType, EventType, RelationshipEntityType, QuestStatus, Player, Party, "
    "GeneratedNpc, GeneratedFaction, Item, InventoryItem, StoryLog, Relationship, PlayerNpcMemory, Ability, Skill, "
    "StatusEffect, ActiveStatusEffect, Questline, GeneratedQuest, QuestStep, PlayerQuestProgress, MobileGroup, "
    "CraftingRecipe."
)
