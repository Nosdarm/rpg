from sqlalchemy import Column, String, BigInteger
from sqlalchemy.orm import Mapped

from src.models.base import Base
from src.models.mixins import TimestampMixin

class MasterUser(Base, TimestampMixin):
    """
    Модель для хранения информации о пользователях UI (Мастерах),
    которые аутентифицируются через Discord.
    """
    __tablename__ = "master_users"

    id: Mapped[int] = Column(BigInteger, primary_key=True, index=True) # type: ignore
    discord_user_id: Mapped[str] = Column(String, unique=True, index=True, nullable=False) # type: ignore
    discord_username: Mapped[str] = Column(String, nullable=False) # type: ignore
    discord_avatar_url: Mapped[str] = Column(String, nullable=True) # type: ignore
    # Можно добавить другие поля, например, roles_json для UI-специфичных ролей

    def __repr__(self) -> str:
        return f"<MasterUser(id={self.id}, discord_user_id='{self.discord_user_id}', discord_username='{self.discord_username}')>"
