from typing import Optional
from datetime import datetime
from pydantic import BaseModel

# Pydantic схемы для MasterUser

class MasterUserBase(BaseModel):
    """
    Базовая схема для MasterUser, содержит общие поля.
    """
    discord_username: Optional[str] = None
    discord_avatar_url: Optional[str] = None

class MasterUserCreate(MasterUserBase):
    """
    Схема для создания нового MasterUser.
    Требует discord_user_id и discord_username.
    """
    discord_user_id: str
    discord_username: str

class MasterUserUpdate(MasterUserBase):
    """
    Схема для обновления существующего MasterUser.
    Все поля опциональны.
    """
    pass

class MasterUserInDBBase(MasterUserBase):
    """
    Базовая схема для MasterUser, как он хранится в БД.
    Включает поля, которые есть в БД (id, created_at, updated_at).
    """
    id: int
    discord_user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True # Для Pydantic V2 (замена orm_mode)

class MasterUserSchema(MasterUserInDBBase):
    """
    Схема для возврата MasterUser из API.
    Наследует все поля от MasterUserInDBBase.
    """
    pass
