import httpx
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode

from src.config import settings # Импортируем наши настройки
from src.core.database import get_async_session
from src.core.crud import crud_master_user
from src.schemas.master_user import MasterUserCreate # Pydantic схема для создания MasterUser
from src.core.security import create_access_token, TokenPayload # Функция для создания JWT и схема

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
        # "state": "your_random_state_string" # Рекомендуется для предотвращения CSRF
    }
    discord_auth_url = f"https://discord.com/oauth2/authorize?{urlencode(params)}"
    return RedirectResponse(url=discord_auth_url)


@router.get("/discord/callback", summary="Handle Discord OAuth2 callback")
async def discord_callback(code: str, session: AsyncSession = Depends(get_async_session)):
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
            token_response.raise_for_status()  # Вызовет исключение для HTTP ошибок 4xx/5xx
            token_json = token_response.json()
            access_token = token_json.get("access_token")
            # refresh_token = token_json.get("refresh_token") # Можно сохранить для обновления токена
        except httpx.HTTPStatusError as e:
            # Логирование ошибки e.response.text
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Не удалось обменять код на токен Discord: {e.response.text}"
            )
        except Exception as e: # Обработка других ошибок httpx или парсинга JSON
            # Логирование ошибки
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
            # discord_avatar = user_json.get("avatar")
            # discord_email = user_json.get("email") # Если scope 'email' был запрошен
        except httpx.HTTPStatusError as e:
            # Логирование ошибки e.response.text
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Не удалось получить информацию о пользователе Discord: {e.response.text}"
            )
        except Exception as e:
            # Логирование ошибки
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
            master_user = await crud_master_user.create(session, obj_in=master_user_in)

        if not master_user: # Дополнительная проверка, если создание не удалось
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать или получить пользователя MasterUser."
            )

        # Шаг 4 - Генерация JWT
        # 'sub' должен быть ID пользователя в нашей системе (master_user.id)
        # Также добавим discord_user_id для удобства, если он потребуется на клиенте или в других частях системы

        # Получаем и фильтруем гильдии пользователя
        accessible_guilds_list = []
        try:
            guilds_response = await client.get(f"{DISCORD_API_BASE_URL}/users/@me/guilds", headers=auth_headers)
            guilds_response.raise_for_status()
            user_discord_guilds = guilds_response.json()

            from src.models.guild import GuildConfig # Локальный импорт для проверки

            for guild_data in user_discord_guilds:
                permissions = int(guild_data.get("permissions", 0))
                # Проверяем права администратора (0x8) или владельца
                is_admin_or_owner = (permissions & 0x8 == 0x8) or guild_data.get("owner", False)

                if is_admin_or_owner:
                    # Проверяем, есть ли гильдия в нашей GuildConfig
                    # Примечание: guild_data["id"] это строка
                    guild_config_entry = await session.get(GuildConfig, guild_data["id"])
                    if guild_config_entry:
                        accessible_guilds_list.append({
                            "id": guild_data["id"],
                            "name": guild_data["name"],
                            "icon": guild_data.get("icon") # Может быть полезно для UI
                        })
        except httpx.HTTPStatusError as e:
            # Логирование ошибки, но не прерываем процесс из-за ошибки получения гильдий
            # logger.warning(f"Не удалось получить или обработать гильдии от Discord: {e.response.text}")
            pass # Оставляем accessible_guilds_list пустым или частично заполненным
        except Exception as e:
            # logger.error(f"Непредвиденная ошибка при получении гильдий Discord: {str(e)}")
            pass


        jwt_subject_data = {
            "sub": str(master_user.id), # ID пользователя MasterUser
            "discord_user_id": master_user.discord_user_id,
            "accessible_guilds": accessible_guilds_list
            # active_guild_id будет добавлен позже, когда пользователь выберет гильдию
        }
        app_jwt_token = create_access_token(subject_data=jwt_subject_data)

        return {
            "message": "Аутентификация через Discord успешна.",
            "access_token": app_jwt_token, # JWT нашего приложения
            "token_type": "bearer",
            # Можно также вернуть информацию о MasterUser, если это нужно UI
            # "user": MasterUserSchema.from_orm(master_user) # Потребует импорт MasterUserSchema
        }


@router.get("/me/guilds", summary="Get accessible guilds for the authenticated user (TEMPORARY IMPLEMENTATION)")
async def get_my_guilds(
    token_payload: TokenPayload = Depends(get_current_token_payload), # Защищаем эндпоинт
    session: AsyncSession = Depends(get_async_session) # Для доступа к GuildConfig
):
    """
    ВРЕМЕННАЯ РЕАЛИЗАЦИЯ: Возвращает ВСЕ гильдии из GuildConfig.
    Это НЕБЕЗОПАСНО для продакшена. Фильтрация по правам пользователя Discord
    должна быть реализована после обновления логики callback'а для сохранения
    Discord Access Token или списка доступных гильдий в JWT.
    """
    # Импорты здесь, чтобы избежать проблем с загрузкой моделей/crud на уровне модуля до инициализации всего
    from src.core.crud.crud_guild import guild_crud # Используем существующий crud_guild
    from src.models.guild import GuildConfig # Используем существующую модель GuildConfig
    # from src.schemas.guild import GuildSchema # Если бы возвращали полную схему

    db_guild_configs = await guild_crud.get_multi(session, limit=1000)

    guilds_for_ui = []
    for gc in db_guild_configs:
        # Предполагаем, что GuildConfig.id это discord_guild_id (строка)
        # и у GuildConfig есть поле name (опциональное)
        guilds_for_ui.append({"id": str(gc.id), "name": gc.name if gc.name else f"Guild {gc.id}"})

    # В идеале, здесь должен быть логгер, предупреждающий о временной реализации.
    # logger.warning("Endpoint /me/guilds is using a temporary, insecure implementation.")
    # return guilds_for_ui # Старая временная реализация

    # Новая реализация: читаем из JWT
    if token_payload.accessible_guilds is not None:
        # logger.info(f"Returning {len(token_payload.accessible_guilds)} guilds from JWT for user {token_payload.sub}")
        return token_payload.accessible_guilds
    else:
        # Это может произойти, если токен был сгенерирован до добавления accessible_guilds (маловероятно после обновления callback)
        # или если при получении гильдий от Discord произошла ошибка и список остался пустым/None.
        # logger.info(f"No accessible_guilds found in JWT payload for user {token_payload.sub}.")
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

    Примечание: UI должен будет проверить, что пользователь действительно имеет доступ
    к этому guild_id, используя список из /me/guilds (или данные, полученные от Discord).
    Бэкенд здесь доверяет, что UI передает корректный guild_id из доступных пользователю.
    Для большей безопасности, бэкенд мог бы также проверять доступ, если бы хранил
    список доступных гильдий из JWT (после обновления callback'а).
    """

    # Создаем новый payload на основе старого, но с обновленным active_guild_id
    new_jwt_subject_data = {
        "sub": token_payload.sub,
        "discord_user_id": token_payload.discord_user_id,
        "active_guild_id": request_data.guild_id
    }

    # Время жизни нового токена можно оставить таким же, как у стандартных токенов,
    # или сделать его короче/длиннее по необходимости. Используем стандартное.
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


# TODO: Модифицировать /discord/callback для получения, фильтрации и сохранения списка гильдий в JWT.
# TODO: После обновления callback, обновить /me/guilds для чтения списка из JWT.
# TODO: Рассмотреть проверку доступа к guild_id в POST /session/active-guild после обновления callback.

# --- Напоминание для будущих API эндпоинтов для UI ---
# Все API эндпоинты, создаваемые для взаимодействия с UI и работы с RPG данными (например,
# для управления игроками, предметами, квестами и т.д.), должны:
# 1. Быть защищены JWT: использовать зависимость `get_current_token_payload` или `get_current_master_user`
#    из `src.core.security`.
# 2. Извлекать `active_guild_id` из `token_payload.active_guild_id`.
# 3. Если `active_guild_id` отсутствует (равен None), возвращать ошибку 400 Bad Request,
#    указывающую на необходимость сначала выбрать активную гильдию через эндпоинт
#    POST /api/auth/session/active-guild.
# 4. Передавать этот `active_guild_id` во все вызовы CRUD-операций и сервисных функций,
#    которые требуют `guild_id` для корректной фильтрации данных по гильдии.
#
# Пример такой проверки в защищенном эндпоинте:
#
# from fastapi import HTTPException, status
# from src.core.security import TokenPayload, get_current_token_payload
#
# @router.get("/some-rpg-data")
# async def get_rpg_data(token_payload: TokenPayload = Depends(get_current_token_payload)):
#     if not token_payload.active_guild_id:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Активная гильдия не выбрана. Пожалуйста, выберите гильдию через POST /api/auth/session/active-guild."
#         )
#     active_guild_id = token_payload.active_guild_id
#     # ... дальнейшая логика с использованием active_guild_id ...
#     return {"data_for_guild": active_guild_id}
# --- Конец напоминания ---

# TODO: В src/main.py нужно будет добавить этот router:
# from src.api.routers import auth as auth_router
# app.include_router(auth_router.router)
# Также убедиться, что FastAPI приложение `app` создается и настраивается в src/main.py
# и что `uvicorn` запускает именно этот `app` из `src.main`.
# Пример src/main.py, если его нет:
"""
from fastapi import FastAPI, Depends # Добавлен Depends
from src.api.routers import auth as auth_router # Пример
from src.core.security import get_current_master_user, TokenPayload # Для тестового эндпоинта
from src.models.master_user import MasterUser # Для тестового эндпоинта
from src.schemas.master_user import MasterUserSchema # Для тестового эндпоинта
# from src.core.database import init_db # Если есть функция инициализации БД

app = FastAPI(title="RPG Bot Backend API")

# app.on_event("startup")
# async def on_startup():
#     await init_db() # Пример инициализации БД

app.include_router(auth_router.router)

# Простой эндпоинт для проверки работы API
@app.get("/")
async def read_root():
    return {"message": "Welcome to the RPG Bot Backend API"}

# Пример защищенного эндпоинта
@app.get("/api/users/me", response_model=MasterUserSchema, tags=["Users"])
async def read_users_me(current_user: MasterUser = Depends(get_current_master_user)):
    return current_user

@app.get("/api/test-active-guild", tags=["Users"])
async def test_active_guild(token_payload: TokenPayload = Depends(get_current_token_payload)):
    if not token_payload.active_guild_id:
        raise HTTPException(status_code=400, detail="No active guild selected")
    return {"active_guild_id": token_payload.active_guild_id, "user_id": token_payload.sub}


# Для запуска: uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
"""
# Импортируем BaseModel для ActiveGuildRequest, если он еще не импортирован глобально
from pydantic import BaseModel
from typing import Optional # Для response_model в get_active_guild
from src.core.security import get_current_token_payload # Убедимся, что он импортирован для Depends
