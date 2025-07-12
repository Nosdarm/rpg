import httpx
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode

from pydantic import BaseModel
from typing import Optional

from backend.config import settings
from backend.core.database import get_db_session
from backend.core.crud import crud_master_user
from backend.schemas.master_user import MasterUserCreate
from backend.core.security import create_access_token, TokenPayload, get_current_token_payload

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)

DISCORD_API_BASE_URL = "https://discord.com/api/v10" # Используем API v10

@router.get("/discord", summary="Redirect to Discord OAuth2 authorization")
async def discord_login():
    """
    Перенаправляет пользователя на страницу авторизации Discord.
    """
    if not settings.DISCORD_CLIENT_ID or not settings.DISCORD_REDIRECT_URI:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Discord OAuth2 Client ID или Redirect URI не настроены на сервере."
        )

    params = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "redirect_uri": settings.DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds email",  # Запрашиваем identify, guilds и email (email опционально)
        # "state": "your_random_state_string"
    }
    discord_auth_url = f"https://discord.com/oauth2/authorize?{urlencode(params)}"
    return RedirectResponse(url=discord_auth_url)


@router.get("/discord/callback", summary="Handle Discord OAuth2 callback")
async def discord_callback(code: str, session: AsyncSession = Depends(get_db_session)):
    """
    Обрабатывает коллбэк от Discord после авторизации пользователя.
    Обменивает авторизационный код на access token, получает информацию о пользователе
    и генерирует JWT для сессии UI.
    """
    if not settings.DISCORD_CLIENT_ID or not settings.DISCORD_CLIENT_SECRET or not settings.DISCORD_REDIRECT_URI:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Discord OAuth2 конфигурация не завершена на сервере."
        )

    token_url = f"{DISCORD_API_BASE_URL}/oauth2/token"
    token_data = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "client_secret": settings.DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.DISCORD_REDIRECT_URI,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    async with httpx.AsyncClient() as client:
        try:
            token_response = await client.post(token_url, data=token_data, headers=headers)
            token_response.raise_for_status()
            token_json = token_response.json()
            access_token = token_json.get("access_token")
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Не удалось обменять код на токен Discord: {e.response.text}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Внутренняя ошибка при обмене токена Discord: {str(e)}"
            )

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Discord не вернул access_token."
            )

        # Получение информации о пользователе Discord
        user_info_url = f"{DISCORD_API_BASE_URL}/users/@me"
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        try:
            user_response = await client.get(user_info_url, headers=auth_headers)
            user_response.raise_for_status()
            user_json = user_response.json()
            discord_user_id = user_json.get("id")
            discord_username = user_json.get("username")
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Не удалось получить информацию о пользователе Discord: {e.response.text}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Внутренняя ошибка при получении информации о пользователе Discord: {str(e)}"
            )

        if not discord_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не удалось получить Discord User ID."
            )

        # Шаг 3 - Найти или создать MasterUser в БД
        master_user = await crud_master_user.get_by_discord_id(session, discord_user_id=discord_user_id)
        if not master_user:
            discord_avatar_code = user_json.get("avatar")
            avatar_url = None
            if discord_avatar_code:
                avatar_url = f"https://cdn.discordapp.com/avatars/{discord_user_id}/{discord_avatar_code}.png"

            master_user_in = MasterUserCreate(
                discord_user_id=discord_user_id,
                discord_username=discord_username,
                discord_avatar_url=avatar_url
            )
            # Convert Pydantic model to dict before passing to CRUD
            master_user = await crud_master_user.create(session, obj_in=master_user_in.model_dump())

        if not master_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать или получить пользователя MasterUser."
            )

        accessible_guilds_list = []
        try:
            guilds_response = await client.get(f"{DISCORD_API_BASE_URL}/users/@me/guilds", headers=auth_headers)
            guilds_response.raise_for_status()
            user_discord_guilds = guilds_response.json()

            from backend.models.guild import GuildConfig

            for guild_data in user_discord_guilds:
                permissions = int(guild_data.get("permissions", 0))
                is_admin_or_owner = (permissions & 0x8 == 0x8) or guild_data.get("owner", False)

                if is_admin_or_owner:
                    guild_config_entry = await session.get(GuildConfig, guild_data["id"])
                    if guild_config_entry:
                        accessible_guilds_list.append({
                            "id": guild_data["id"],
                            "name": guild_data["name"],
                            "icon": guild_data.get("icon")
                        })
        except httpx.HTTPStatusError:
            pass
        except Exception:
            pass


        jwt_subject_data = {
            "sub": str(master_user.id),
            "discord_user_id": master_user.discord_user_id,
            "accessible_guilds": accessible_guilds_list
        }
        app_jwt_token = create_access_token(subject_data=jwt_subject_data)

        if not settings.UI_APP_REDIRECT_URL_AFTER_LOGIN:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="URL для редиректа после входа не настроен на сервере."
            )

        redirect_url_with_token = f"{settings.UI_APP_REDIRECT_URL_AFTER_LOGIN}?token={app_jwt_token}"

        return RedirectResponse(url=redirect_url_with_token)


@router.get("/me/guilds", summary="Get accessible guilds for the authenticated user")
async def get_my_guilds(
    token_payload: TokenPayload = Depends(get_current_token_payload), # Защищаем эндпоинт
):
    """
    Возвращает список доступных гильдий для пользователя из JWT.
    """
    if token_payload.accessible_guilds is not None:
        return token_payload.accessible_guilds
    else:
        return []


class ActiveGuildRequest(BaseModel):
    guild_id: str

@router.post("/session/active-guild", summary="Set the active guild for the current session")
async def set_active_guild(
    request_data: ActiveGuildRequest,
    token_payload: TokenPayload = Depends(get_current_token_payload) # Защищаем и получаем текущий payload
):
    """
    Устанавливает активную гильдию для сессии пользователя.
    Обновляет JWT, добавляя/изменяя active_guild_id.
    Возвращает новый JWT.
    """
    requested_guild_id = request_data.guild_id

    if token_payload.accessible_guilds is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Список доступных гильдий отсутствует в токене. Попробуйте перелогиниться."
        )

    is_accessible = False
    if isinstance(token_payload.accessible_guilds, list):
        for guild in token_payload.accessible_guilds:
            if guild.get("id") == requested_guild_id:
                is_accessible = True
                break

    if not is_accessible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Доступ к гильдии {requested_guild_id} запрещен или гильдия не найдена в списке доступных."
        )

    new_jwt_subject_data = token_payload.model_dump()
    new_jwt_subject_data["active_guild_id"] = requested_guild_id
    new_access_token = create_access_token(subject_data=new_jwt_subject_data)

    return {
        "message": f"Активная гильдия установлена на {request_data.guild_id}",
        "access_token": new_access_token,
        "token_type": "bearer"
    }

@router.get("/session/active-guild", summary="Get the active guild for the current session", response_model=Optional[str])
async def get_active_guild(
    token_payload: TokenPayload = Depends(get_current_token_payload) # Защищаем и получаем payload
):
    """
    Возвращает ID активной гильдии из JWT текущей сессии.
    Возвращает null, если активная гильдия не установлена.
    """
    return token_payload.active_guild_id


@router.post("/logout", summary="Logout user", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    token_payload: TokenPayload = Depends(get_current_token_payload)
):
    """
    Logs out the current user.
    In a stateless JWT setup, this endpoint primarily serves as a signal for the client
    to discard the JWT. No server-side token invalidation is performed.
    """
    return None
