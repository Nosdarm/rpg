# tests/core/test_map_management.py
import sys
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.map_management import (
    add_location_master,
    remove_location_master,
    connect_locations_master,
    disconnect_locations_master
)
from src.models import Location
from src.models.location import LocationType # Исправленный импорт
from src.models.enums import EventType

# pytestmark = pytest.mark.asyncio # Если использовать для всего модуля

@pytest.mark.asyncio
async def test_add_location_master_success(
    mock_db_session: AsyncSession,
    mock_location_crud: MagicMock
):
    guild_id = 1
    location_data = {
        "static_id": "test_loc_01",
        "name_i18n": {"en": "Test Location", "ru": "Тестовая Локация"},
        "descriptions_i18n": {"en": "Desc", "ru": "Опис"},
        "type": LocationType.CITY.value, # Используем .value для Enum
        "coordinates_json": {"x": 0, "y": 0},
        "neighbor_locations_json": [{"id": 2, "type_i18n": {"en": "road", "ru": "дорога"}}],
        "generated_details_json": {},
        "ai_metadata_json": {}
    }

    mock_location_crud.get_by_static_id.return_value = None # Локация с таким static_id не существует

    created_loc_mock = Location(id=1, guild_id=guild_id, **location_data)
    mock_location_crud.create.return_value = created_loc_mock

    # Мок для соседа, указанного в neighbor_locations_json
    neighbor_loc_mock = Location(id=2, guild_id=guild_id, name_i18n={"en":"Neighbor"}, neighbor_locations_json=[])
    mock_location_crud.get.return_value = neighbor_loc_mock # Когда update_location_neighbors будет его искать

    with patch("src.core.map_management.log_event", new_callable=AsyncMock) as mock_log_event, \
         patch("src.core.map_management.location_crud", new=mock_location_crud), \
         patch("src.core.map_management.update_location_neighbors", new_callable=AsyncMock) as mock_update_neighbors:

        location, error = await add_location_master(mock_db_session, guild_id, location_data)

        assert error is None
        assert location is not None
        assert location.id == 1
        assert location.static_id == "test_loc_01"

        mock_location_crud.get_by_static_id.assert_called_once_with(mock_db_session, guild_id=guild_id, static_id="test_loc_01")
        mock_location_crud.create.assert_called_once()

        # Проверяем, что update_location_neighbors был вызван для соседа
        mock_update_neighbors.assert_called_once_with(
            mock_db_session, neighbor_loc_mock, created_loc_mock.id, {"en": "road", "ru": "дорога"}, add_connection=True
        )

        mock_log_event.assert_called_once() # type: ignore[attr-defined]
        assert mock_log_event.call_args[1]["event_type"] == EventType.MASTER_ACTION_LOCATION_ADDED.value # type: ignore[attr-defined]
        commit_mock_add: AsyncMock = mock_db_session.commit # type: ignore
        commit_mock_add.assert_called_once()

@pytest.mark.asyncio
async def test_add_location_master_static_id_exists(
    mock_db_session: AsyncSession,
    mock_location_crud: MagicMock
):
    guild_id = 1
    location_data = {"static_id": "existing_loc", "name_i18n": {}, "descriptions_i18n": {}, "type": "CITY"}
    mock_location_crud.get_by_static_id.return_value = Location(id=99, static_id="existing_loc") # Локация уже существует

    with patch("src.core.map_management.location_crud", new=mock_location_crud):
        location, error = await add_location_master(mock_db_session, guild_id, location_data)

    assert location is None
    assert error is not None
    assert "already exists" in error
    # mock_db_session.rollback.assert_called_once() # Ошибка до начала транзакции

@pytest.mark.asyncio
async def test_add_location_master_missing_field(mock_db_session: AsyncSession):
    guild_id = 1
    location_data = {"name_i18n": {}, "descriptions_i18n": {}, "type": "CITY"} # Отсутствует static_id

    location, error = await add_location_master(mock_db_session, guild_id, location_data)
    assert location is None
    assert error is not None
    assert "Missing required field" in error
    # rollback не должен вызываться, т.к. ошибка до DB операций
    rollback_mock_missing_field: AsyncMock = mock_db_session.rollback # type: ignore
    rollback_mock_missing_field.assert_not_called()


@pytest.mark.asyncio
async def test_remove_location_master_success(
    mock_db_session: AsyncSession,
    mock_location_crud: MagicMock
):
    guild_id = 1
    loc_id_to_remove = 10

    # Локация для удаления
    loc_to_remove = Location(
        id=loc_id_to_remove, guild_id=guild_id, static_id="loc_to_remove", name_i18n={"en":"Old Loc"},
        neighbor_locations_json=[{"id": 11, "type_i18n": {}}]
    )
    # Ее сосед
    neighbor_loc = Location(id=11, guild_id=guild_id, name_i18n={"en":"Neighbor"}, neighbor_locations_json=[{"id": loc_id_to_remove, "type_i18n": {}}])

    # Первый get находит удаляемую локацию, второй get находит соседа
    mock_location_crud.get.side_effect = [loc_to_remove, neighbor_loc]
    # mock_location_crud.delete.return_value = True # This was the error
    mock_location_crud.delete = AsyncMock(return_value=loc_to_remove) # Fix: make it async and return the object

    with patch("src.core.map_management.log_event", new_callable=AsyncMock) as mock_log_event, \
         patch("src.core.map_management.location_crud", new=mock_location_crud), \
         patch("src.core.map_management.update_location_neighbors", new_callable=AsyncMock) as mock_update_neighbors:

        success, error = await remove_location_master(mock_db_session, guild_id, loc_id_to_remove)

        assert error is None
        assert success is True

        mock_location_crud.delete.assert_called_once_with(mock_db_session, id=loc_id_to_remove) # type: ignore[attr-defined]
        mock_update_neighbors.assert_called_once_with(mock_db_session, neighbor_loc, loc_id_to_remove, {}, add_connection=False) # type: ignore[attr-defined]

        mock_log_event.assert_called_once() # type: ignore[attr-defined]
        assert mock_log_event.call_args[1]["event_type"] == EventType.MASTER_ACTION_LOCATION_REMOVED.value # type: ignore[attr-defined]
        commit_mock_remove: AsyncMock = mock_db_session.commit # type: ignore
        commit_mock_remove.assert_called_once()

@pytest.mark.asyncio
async def test_remove_location_master_not_found(
    mock_db_session: AsyncSession,
    mock_location_crud: MagicMock
):
    guild_id = 1
    loc_id_to_remove = 999
    mock_location_crud.get.return_value = None # Локация не найдена

    with patch("src.core.map_management.location_crud", new=mock_location_crud):
        success, error = await remove_location_master(mock_db_session, guild_id, loc_id_to_remove)

    assert success is False
    assert error == "Location not found."
    # mock_db_session.rollback.assert_called_once() # Ошибка до начала транзакции


@pytest.mark.asyncio
async def test_connect_locations_master_success(
    mock_db_session: AsyncSession,
    mock_location_crud: MagicMock
):
    guild_id=1
    loc1_id=1
    loc2_id=2
    conn_type = {"en": "a bridge"}

    loc1 = Location(id=loc1_id, guild_id=guild_id, name_i18n={"en":"Loc1"}, neighbor_locations_json=[])
    loc2 = Location(id=loc2_id, guild_id=guild_id, name_i18n={"en":"Loc2"}, neighbor_locations_json=[])
    mock_location_crud.get.side_effect = [loc1, loc2]

    with patch("src.core.map_management.log_event", new_callable=AsyncMock) as mock_log_event, \
         patch("src.core.map_management.location_crud", new=mock_location_crud), \
         patch("src.core.map_management.update_location_neighbors", new_callable=AsyncMock) as mock_update_neighbors:

        success, error = await connect_locations_master(mock_db_session, guild_id, loc1_id, loc2_id, conn_type)

        assert error is None
        assert success is True

        assert mock_update_neighbors.call_count == 2
        mock_update_neighbors.assert_any_call(mock_db_session, loc1, loc2_id, conn_type, add_connection=True)
        mock_update_neighbors.assert_any_call(mock_db_session, loc1, loc2_id, conn_type, add_connection=True) # type: ignore[attr-defined]
        mock_update_neighbors.assert_any_call(mock_db_session, loc2, loc1_id, conn_type, add_connection=True) # type: ignore[attr-defined]

        mock_log_event.assert_called_once() # type: ignore[attr-defined]
        assert mock_log_event.call_args[1]["event_type"] == EventType.MASTER_ACTION_LOCATIONS_CONNECTED.value # type: ignore[attr-defined]
        commit_mock_connect: AsyncMock = mock_db_session.commit # type: ignore
        commit_mock_connect.assert_called_once()

@pytest.mark.asyncio
async def test_disconnect_locations_master_success(
    mock_db_session: AsyncSession,
    mock_location_crud: MagicMock
):
    guild_id=1
    loc1_id=1
    loc2_id=2

    loc1 = Location(id=loc1_id, guild_id=guild_id, name_i18n={"en":"Loc1"}, neighbor_locations_json=[{"id":loc2_id}])
    loc2 = Location(id=loc2_id, guild_id=guild_id, name_i18n={"en":"Loc2"}, neighbor_locations_json=[{"id":loc1_id}])
    mock_location_crud.get.side_effect = [loc1, loc2]

    with patch("src.core.map_management.log_event", new_callable=AsyncMock) as mock_log_event, \
         patch("src.core.map_management.location_crud", new=mock_location_crud), \
         patch("src.core.map_management.update_location_neighbors", new_callable=AsyncMock) as mock_update_neighbors:

        success, error = await disconnect_locations_master(mock_db_session, guild_id, loc1_id, loc2_id)

        assert error is None
        assert success is True

        assert mock_update_neighbors.call_count == 2
        mock_update_neighbors.assert_any_call(mock_db_session, loc1, loc2_id, {}, add_connection=False)
        mock_update_neighbors.assert_any_call(mock_db_session, loc1, loc2_id, {}, add_connection=False) # type: ignore[attr-defined]
        mock_update_neighbors.assert_any_call(mock_db_session, loc2, loc1_id, {}, add_connection=False) # type: ignore[attr-defined]

        mock_log_event.assert_called_once() # type: ignore[attr-defined]
        assert mock_log_event.call_args[1]["event_type"] == EventType.MASTER_ACTION_LOCATIONS_DISCONNECTED.value # type: ignore[attr-defined]
        commit_mock_disconnect: AsyncMock = mock_db_session.commit # type: ignore
        commit_mock_disconnect.assert_called_once()

# Фикстуры, если они не в conftest.py
# @pytest.fixture
# async def mock_db_session() -> AsyncMock:
#     session = AsyncMock(spec=AsyncSession)
#     session.commit = AsyncMock()
#     session.rollback = AsyncMock()
#     session.flush = AsyncMock() # Добавлено для update_location_neighbors
#     return session

# @pytest.fixture
# def mock_location_crud() -> MagicMock:
#     crud = MagicMock()
#     crud.create = AsyncMock()
#     crud.get_by_static_id = AsyncMock()
#     crud.get = AsyncMock()
#     crud.update = AsyncMock()
#     crud.remove = AsyncMock(return_value=True) # Пример возвращаемого значения
#     return crud
