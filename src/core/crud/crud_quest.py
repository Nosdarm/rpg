from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.crud_base_definitions import CRUDBase
from src.models.quest import GeneratedQuest, QuestStep, PlayerQuestProgress, Questline # Import all quest related models

# CRUD for GeneratedQuest
class CRUDGeneratedQuest(CRUDBase[GeneratedQuest]):
    async def get_by_static_id(
        self, db: AsyncSession, *, static_id: str, guild_id: int
    ) -> Optional[GeneratedQuest]:
        statement = select(self.model).where(
            self.model.guild_id == guild_id,
            self.model.static_id == static_id
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

generated_quest_crud = CRUDGeneratedQuest(GeneratedQuest)

# CRUD for QuestStep
class CRUDQuestStep(CRUDBase[QuestStep]):
    async def get_by_quest_id_and_order(
        self, db: AsyncSession, *, quest_id: int, step_order: int
    ) -> Optional[QuestStep]:
        statement = select(self.model).where(
            self.model.quest_id == quest_id,
            self.model.step_order == step_order
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_all_for_quest(
        self, db: AsyncSession, *, quest_id: int
    ) -> Sequence[QuestStep]:
        statement = select(self.model).where(self.model.quest_id == quest_id).order_by(self.model.step_order)
        result = await db.execute(statement)
        return result.scalars().all()

quest_step_crud = CRUDQuestStep(QuestStep)

# CRUD for PlayerQuestProgress
class CRUDPlayerQuestProgress(CRUDBase[PlayerQuestProgress]):
    async def get_by_player_and_quest(
        self, db: AsyncSession, *, player_id: int, quest_id: int, guild_id: int
    ) -> Optional[PlayerQuestProgress]:
        statement = select(self.model).where(
            self.model.player_id == player_id,
            self.model.quest_id == quest_id,
            self.model.guild_id == guild_id
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_all_for_player(
        self, db: AsyncSession, *, player_id: int, guild_id: int
    ) -> Sequence[PlayerQuestProgress]:
        statement = select(self.model).where(
            self.model.player_id == player_id,
            self.model.guild_id == guild_id
        )
        result = await db.execute(statement)
        return result.scalars().all()

player_quest_progress_crud = CRUDPlayerQuestProgress(PlayerQuestProgress)

# CRUD for Questline
class CRUDQuestline(CRUDBase[Questline]):
    async def get_by_static_id(
        self, db: AsyncSession, *, static_id: str, guild_id: int
    ) -> Optional[Questline]:
        statement = select(self.model).where(
            self.model.guild_id == guild_id,
            self.model.static_id == static_id
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

questline_crud = CRUDQuestline(Questline)
