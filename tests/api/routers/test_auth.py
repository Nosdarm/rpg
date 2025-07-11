import pytest
from httpx import AsyncClient, Response, RequestError # httpx импортирован
from fastapi import status, FastAPI, Depends
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
from typing import Optional, List, Dict, Any, Generator
import httpx # Повторный импорт не страшен

from sqlalchemy.ext.asyncio import AsyncSession

from backend.main import app
from backend.core.security import TokenPayload, create_access_token
from backend.models.master_user import MasterUser
from backend.config import settings
from backend.schemas.master_user import MasterUserCreate
from urllib.parse import quote_plus


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_scalars.first.return_value = None
    mock_result.scalars.return_value = mock_scalars
    # db.execute должен возвращать awaitable, который вернет mock_result
    async def _execute(*args, **kwargs):
        return mock_result
    db.execute = AsyncMock(side_effect=_execute) # Исправлено
    return db

@pytest.fixture
def client(mock_db: AsyncMock) -> Generator[TestClient, None, None]:
    from backend.core.database import get_db_session
    app.dependency_overrides[get_db_session] = lambda: mock_db
    yield TestClient(app)
    app.dependency_overrides.clear()

def create_test_jwt(
    master_user_id: str = "1",
    discord_user_id: str = "discord123",
    accessible_guilds: Optional[List[Dict[str, str]]] = "DEFAULT_GUILDS_PLACEHOLDER",
    active_guild_id: Optional[str] = None
) -> str:
    if accessible_guilds == "DEFAULT_GUILDS_PLACEHOLDER":
        final_accessible_guilds = [{"id": "guild1", "name": "Test Guild 1"}]
    else:
        final_accessible_guilds = accessible_guilds

    subject_data = {
        "sub": master_user_id,
        "discord_user_id": discord_user_id,
        "accessible_guilds": final_accessible_guilds,
    }
    if active_guild_id:
        subject_data["active_guild_id"] = active_guild_id

    # Используем settings.SECRET_KEY, предполагая, что он будет установлен для тестов
    # через фикстуру или mocker.patch.object
    if not settings.SECRET_KEY:
        # Этого не должно происходить в тестах, если SECRET_KEY правильно запатчен
        raise ValueError("Test JWT creation failed: settings.SECRET_KEY is not set for test session.")
    return create_access_token(subject_data=subject_data)

# Фикстура для автоматического патчинга SECRET_KEY для всех тестов в этом файле
@pytest.fixture(autouse=True)
def auto_patch_settings_secret_key(mocker):
    # Патчим settings в модуле, где он используется функцией create_access_token
    mocker.patch.object(settings, 'SECRET_KEY', 'default_test_secret_key_for_jwt_in_tests', create=True)
    yield
    # Патч автоматически отменится после теста


@pytest.mark.asyncio
@patch("backend.api.routers.auth.httpx.AsyncClient")
@patch("backend.api.routers.auth.crud_master_user", new_callable=AsyncMock)
@patch("backend.api.routers.auth.settings", new_callable=MagicMock)
async def test_discord_callback_success(
    mock_api_auth_settings: MagicMock, # Переименовал, чтобы не конфликтовать с глобальным settings
    mock_crud_master_user: AsyncMock,
    mock_async_client_constructor: MagicMock,
    client: TestClient,
    mock_db: AsyncMock,
    mocker # mocker уже доступен через autouse фикстуру, но можно и явно
):
    mock_api_auth_settings.DISCORD_CLIENT_ID = "test_client_id"
    mock_api_auth_settings.DISCORD_CLIENT_SECRET = "test_client_secret"
    mock_api_auth_settings.DISCORD_REDIRECT_URI = "http://localhost/callback"
    mock_api_auth_settings.UI_APP_REDIRECT_URL_AFTER_LOGIN = "http://frontend/auth-callback"
    # settings.SECRET_KEY уже должен быть запатчен фикстурой auto_patch_settings_secret_key

    mock_http_client = AsyncMock()
    mock_async_client_constructor.return_value.__aenter__.return_value = mock_http_client
    mock_http_client.post.return_value = Response(
        status.HTTP_200_OK,
        json={"access_token": "discord_access_token", "refresh_token": "discord_refresh_token"},
        request=MagicMock(spec=httpx.Request)
    )
    mock_user_info_response = Response(
        status.HTTP_200_OK,
        json={"id": "discord123", "username": "testuser", "avatar": "avatar_hash"},
        request=MagicMock(spec=httpx.Request)
    )
    mock_guilds_response = Response(
        status.HTTP_200_OK,
        json=[
            {"id": "guild1", "name": "Test Guild 1", "permissions": "8", "owner": False},
            {"id": "guild2", "name": "No Perms Guild", "permissions": "0", "owner": False},
            {"id": "guild3", "name": "Bot Guild", "permissions": "8", "owner": False}
        ],
        request=MagicMock(spec=httpx.Request)
    )
    mock_http_client.get.side_effect = [mock_user_info_response, mock_guilds_response]

    mock_master_user = MasterUser(id=1, discord_user_id="discord123", discord_username="testuser")
    mock_crud_master_user.get_by_discord_id.return_value = None
    mock_crud_master_user.create.return_value = mock_master_user

    async def mock_guild_config_get(model, guild_id_str):
        if model.__name__ == "GuildConfig":
            if guild_id_str == "guild1":
                return MagicMock(id="guild1", name="Test Guild 1 DB")
        return None
    mock_db.get = AsyncMock(side_effect=mock_guild_config_get)

    response = client.get("/api/auth/discord/callback?code=test_auth_code", follow_redirects=False)

    assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT # RedirectResponse по умолчанию 307
    assert "location" in response.headers
    redirect_location = response.headers["location"]
    assert redirect_location.startswith(mock_api_auth_settings.UI_APP_REDIRECT_URL_AFTER_LOGIN)
    assert "?token=" in redirect_location
    mock_crud_master_user.get_by_discord_id.assert_called_once_with(mock_db, discord_user_id="discord123")
    mock_crud_master_user.create.assert_called_once()
    assert mock_http_client.post.call_count == 1
    assert mock_http_client.get.call_count == 2


@pytest.mark.asyncio
@patch("backend.api.routers.auth.settings", new_callable=MagicMock)
async def test_discord_callback_missing_redirect_url_config(
    mock_api_auth_settings: MagicMock, client: TestClient, mock_db: AsyncMock, mocker
):
    mock_api_auth_settings.DISCORD_CLIENT_ID = "test_client_id"
    mock_api_auth_settings.DISCORD_CLIENT_SECRET = "test_client_secret"
    mock_api_auth_settings.DISCORD_REDIRECT_URI = "http://localhost/callback"
    mock_api_auth_settings.UI_APP_REDIRECT_URL_AFTER_LOGIN = None
    # settings.SECRET_KEY уже должен быть запатчен

    with patch("backend.api.routers.auth.httpx.AsyncClient") as mock_async_client_constructor, \
         patch("backend.api.routers.auth.crud_master_user", new_callable=AsyncMock) as mock_crud_master_user:

        mock_http_client = AsyncMock()
        mock_async_client_constructor.return_value.__aenter__.return_value = mock_http_client
        mock_http_client.post.return_value = Response(
            status.HTTP_200_OK,
            json={"access_token": "discord_access_token"},
            request=MagicMock(spec=httpx.Request)
        )
        mock_http_client.get.side_effect = [
            Response(status.HTTP_200_OK, json={"id": "discord123", "username": "testuser", "avatar": "avatar_hash"}, request=MagicMock(spec=httpx.Request)),
            Response(status.HTTP_200_OK, json=[], request=MagicMock(spec=httpx.Request))
        ]
        mock_master_user = MasterUser(id=1, discord_user_id="discord123", discord_username="testuser")
        mock_crud_master_user.get_by_discord_id.return_value = mock_master_user
        response = client.get("/api/auth/discord/callback?code=test_auth_code")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "URL для редиректа после входа не настроен на сервере" in response.json()["detail"]


def test_set_active_guild_success(client: TestClient):
    token = create_test_jwt(accessible_guilds=[{"id": "guild1", "name": "Guild One"}, {"id": "guild2", "name": "Guild Two"}])
    response = client.post(
        "/api/auth/session/active-guild",
        json={"guild_id": "guild1"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data

def test_set_active_guild_forbidden(client: TestClient):
    token = create_test_jwt(accessible_guilds=[{"id": "guild1", "name": "Guild One"}])
    response = client.post(
        "/api/auth/session/active-guild",
        json={"guild_id": "forbidden_guild"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "Доступ к гильдии forbidden_guild запрещен или гильдия не найдена в списке доступных." in response.json()["detail"]

def test_set_active_guild_no_accessible_guilds_in_token(client: TestClient):
    token = create_test_jwt(accessible_guilds=None)
    response = client.post(
        "/api/auth/session/active-guild",
        json={"guild_id": "any_guild"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "Список доступных гильдий отсутствует в токене." in response.json()["detail"]

def test_set_active_guild_forbidden_empty_list(client: TestClient):
    token = create_test_jwt(accessible_guilds=[])
    response = client.post(
        "/api/auth/session/active-guild",
        json={"guild_id": "any_guild"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "Доступ к гильдии any_guild запрещен или гильдия не найдена в списке доступных." in response.json()["detail"]


def test_logout_success(client: TestClient):
    token = create_test_jwt()
    response = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status.HTTP_204_NO_CONTENT

def test_logout_no_token(client: TestClient):
    response = client.post("/api/auth/logout")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


_test_app_for_dependency = FastAPI()
from backend.core.security import get_current_active_guild_id

@_test_app_for_dependency.get("/test-dependency-active-guild")
async def route_test_active_guild(active_guild_id: str = Depends(get_current_active_guild_id)):
    return {"active_guild_id": active_guild_id}

dependency_test_client = TestClient(_test_app_for_dependency)

def test_get_current_active_guild_id_success():
    token = create_test_jwt(active_guild_id="active_guild_123")
    response = dependency_test_client.get(
        "/test-dependency-active-guild",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"active_guild_id": "active_guild_123"}

def test_get_current_active_guild_id_not_set():
    token = create_test_jwt(active_guild_id=None)
    response = dependency_test_client.get(
        "/test-dependency-active-guild",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Активная гильдия не выбрана" in response.json()["detail"]

def test_get_current_active_guild_id_missing_token():
    response = dependency_test_client.get("/test-dependency-active-guild")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
@patch("backend.api.routers.auth.settings", new_callable=MagicMock)
async def test_discord_login_redirect(mock_api_auth_settings: MagicMock, client: TestClient):
    mock_api_auth_settings.DISCORD_CLIENT_ID = "test_client_id"
    mock_api_auth_settings.DISCORD_REDIRECT_URI = "http://testserver/callback"
    response = client.get("/api/auth/discord", follow_redirects=False)
    assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
    assert "location" in response.headers
    location = response.headers["location"]
    assert "discord.com/oauth2/authorize" in location
    assert f"client_id={mock_api_auth_settings.DISCORD_CLIENT_ID}" in location
    assert f"redirect_uri={quote_plus(mock_api_auth_settings.DISCORD_REDIRECT_URI)}" in location
    assert "response_type=code" in location
    assert "scope=identify+guilds+email" in location

@pytest.mark.asyncio
@patch("backend.api.routers.auth.settings", new_callable=MagicMock)
async def test_discord_login_missing_config(mock_api_auth_settings: MagicMock, client: TestClient):
    mock_api_auth_settings.DISCORD_CLIENT_ID = None
    mock_api_auth_settings.DISCORD_REDIRECT_URI = "http://testserver/callback"
    response = client.get("/api/auth/discord")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Discord OAuth2 Client ID или Redirect URI не настроены" in response.json()["detail"]


def test_get_me_guilds_success(client: TestClient, mock_db: AsyncMock):
    guild_list = [{"id": "g1", "name": "Guild Alpha"}, {"id": "g2", "name": "Guild Beta"}]
    token = create_test_jwt(accessible_guilds=guild_list)
    response = client.get("/api/auth/me/guilds", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == guild_list

def test_get_me_guilds_no_guilds_in_token(client: TestClient, mock_db: AsyncMock):
    token = create_test_jwt(accessible_guilds=None)
    response = client.get("/api/auth/me/guilds", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_get_session_active_guild_success(client: TestClient):
    token = create_test_jwt(active_guild_id="active_g_id")
    response = client.get("/api/auth/session/active-guild", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == "active_g_id"

def test_get_session_active_guild_not_set(client: TestClient):
    token = create_test_jwt(active_guild_id=None)
    response = client.get("/api/auth/session/active-guild", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() is None


@pytest.mark.asyncio
@patch("backend.api.routers.auth.httpx.AsyncClient")
@patch("backend.api.routers.auth.settings", new_callable=MagicMock)
async def test_discord_callback_token_exchange_error(
    mock_api_auth_settings: MagicMock,
    mock_async_client_constructor: MagicMock,
    client: TestClient,
    mock_db: AsyncMock
):
    mock_api_auth_settings.DISCORD_CLIENT_ID = "test_client_id"
    mock_api_auth_settings.DISCORD_CLIENT_SECRET = "test_client_secret"
    mock_api_auth_settings.DISCORD_REDIRECT_URI = "http://localhost/callback"

    mock_http_client = AsyncMock()
    mock_async_client_constructor.return_value.__aenter__.return_value = mock_http_client
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = "http://discord/api/oauth2/token"
    http_error = httpx.HTTPStatusError(
        message="Bad Request",
        request=mock_request,
        response=Response(status.HTTP_400_BAD_REQUEST, json={"error": "invalid_grant"}, request=mock_request)
    )
    mock_http_client.post.side_effect = http_error

    response = client.get("/api/auth/discord/callback?code=invalid_auth_code")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Не удалось обменять код на токен Discord" in response.json()["detail"]
    assert "invalid_grant" in response.json()["detail"]


@pytest.mark.asyncio
@patch("backend.api.routers.auth.httpx.AsyncClient")
@patch("backend.api.routers.auth.settings", new_callable=MagicMock)
async def test_discord_callback_user_info_error(
    mock_api_auth_settings: MagicMock,
    mock_async_client_constructor: MagicMock,
    client: TestClient,
    mock_db: AsyncMock,
    mocker
):
    mock_api_auth_settings.DISCORD_CLIENT_ID = "test_client_id"
    mock_api_auth_settings.DISCORD_CLIENT_SECRET = "test_client_secret"
    mock_api_auth_settings.DISCORD_REDIRECT_URI = "http://localhost/callback"
    # mocker.patch.object(settings, 'SECRET_KEY', 'testsecret_for_user_info_error', create=True) # Для create_access_token

    mock_http_client = AsyncMock()
    mock_async_client_constructor.return_value.__aenter__.return_value = mock_http_client
    mock_http_client.post.return_value = Response(
        status.HTTP_200_OK,
        json={"access_token": "discord_access_token"},
        request=MagicMock(spec=httpx.Request)
    )
    mock_request_user_info = MagicMock(spec=httpx.Request)
    mock_request_user_info.url = "http://discord/api/users/@me"
    user_info_http_error = httpx.HTTPStatusError(
        message="Unauthorized",
        request=mock_request_user_info,
        response=Response(status.HTTP_401_UNAUTHORIZED, json={"message": "401: Unauthorized"}, request=mock_request_user_info)
    )
    mock_http_client.get.side_effect = user_info_http_error

    response = client.get("/api/auth/discord/callback?code=valid_auth_code")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Не удалось получить информацию о пользователе Discord" in response.json()["detail"]
    assert "401: Unauthorized" in response.json()["detail"]


try:
    with open("tests/__init__.py", "x") as f: pass
except FileExistsError:
    pass
try:
    with open("tests/api/__init__.py", "x") as f: pass
except FileExistsError:
    pass
try:
    with open("tests/api/routers/__init__.py", "x") as f: pass
except FileExistsError:
    pass


@pytest.mark.asyncio
@patch("backend.api.routers.auth.httpx.AsyncClient")
@patch("backend.api.routers.auth.crud_master_user", new_callable=AsyncMock)
@patch("backend.api.routers.auth.settings", new_callable=MagicMock)
async def test_discord_callback_master_user_creation_details(
    mock_api_auth_settings: MagicMock,
    mock_crud_master_user: AsyncMock,
    mock_async_client_constructor: MagicMock,
    client: TestClient,
    mock_db: AsyncMock,
    mocker
):
    mock_api_auth_settings.DISCORD_CLIENT_ID = "test_cid"
    mock_api_auth_settings.DISCORD_CLIENT_SECRET = "test_csec"
    mock_api_auth_settings.DISCORD_REDIRECT_URI = "http://localhost/cb"
    mock_api_auth_settings.UI_APP_REDIRECT_URL_AFTER_LOGIN = "http://frontend/cb"
    # settings.SECRET_KEY уже должен быть запатчен фикстурой auto_patch_settings_secret_key

    mock_http_client = AsyncMock()
    mock_async_client_constructor.return_value.__aenter__.return_value = mock_http_client
    mock_http_client.post.return_value = Response(
        200,
        json={"access_token": "dat"},
        request=MagicMock(spec=httpx.Request)
    )
    discord_user_data = {"id": "discord999", "username": "newbie", "avatar": "new_avatar"}
    mock_http_client.get.side_effect = [
        Response(200, json=discord_user_data, request=MagicMock(spec=httpx.Request)),
        Response(200, json=[], request=MagicMock(spec=httpx.Request))
    ]
    mock_crud_master_user.get_by_discord_id.return_value = None
    expected_master_user_create_dict = MasterUserCreate(
        discord_user_id="discord999",
        discord_username="newbie",
        discord_avatar_url=f"https://cdn.discordapp.com/avatars/discord999/new_avatar.png"
    ).model_dump()
    mock_created_user = MasterUser(id=5, **expected_master_user_create_dict)
    mock_crud_master_user.create.return_value = mock_created_user

    client.get("/api/auth/discord/callback?code=new_user_code")
    mock_crud_master_user.create.assert_called_once_with(
        mock_db,
        obj_in=expected_master_user_create_dict
    )
