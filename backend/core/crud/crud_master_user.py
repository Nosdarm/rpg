from typing import Optional, Type, TypeVar
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from typing import Optional, TypeVar # Removed Type, no longer needed here
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.crud_base_definitions import CRUDBase
from backend.models.master_user import MasterUser
from backend.schemas.master_user import MasterUserCreate, MasterUserUpdate # Импортируем Pydantic схемы

# Уточнение типов для CRUDBase, если необходимо, но обычно CRUDBase[ModelType, CreateSchemaType, UpdateSchemaType] достаточно
# ModelType = TypeVar("ModelType", bound=MasterUser)
# CreateSchemaType = TypeVar("CreateSchemaType", bound=MasterUserCreate)
# UpdateSchemaType = TypeVar("UpdateSchemaType", bound=MasterUserUpdate)


class CRUDMasterUser(CRUDBase[MasterUser]): # Corrected: Only ModelType is needed for CRUDBase generic
    async def get_by_discord_id(self, session: AsyncSession, *, discord_user_id: str) -> Optional[MasterUser]:
        """
        Получает пользователя MasterUser по его discord_user_id.
        """
        statement = select(self.model).where(self.model.discord_user_id == discord_user_id)
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    # Можно добавить другие специфичные для MasterUser CRUD методы, если потребуется.
    # Например, поиск по username и т.д.

# Экземпляр CRUD для использования в приложении
crud_master_user = CRUDMasterUser(MasterUser)
