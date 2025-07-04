# tests/core/test_world_generation.py
import sys
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.world_generation import generate_location, update_location_neighbors
from src.core.ai_response_parser import ParsedLocationData, ParsedAiData, CustomValidationError
from src.models import Location
from src.models.location import LocationType # Исправленный импорт
from src.models.enums import EventType


# pytestmark = pytest.mark.asyncio # Не нужно для каждой функции отдельно, если класс или весь модуль

@pytest.mark.asyncio
async def test_generate_new_location_via_ai_success(
    mock_db_session: AsyncSession, # Фикстура из conftest.py или определенная здесь
    mock_location_crud: MagicMock # Фикстура из conftest.py
):
    guild_id = 1
    context_location_id = 10

    mock_parsed_location_data = ParsedLocationData(
        entity_type="location",
        name_i18n={"en": "Generated Test Location", "ru": "Сген Тест Локация"},
        descriptions_i18n={"en": "A test description", "ru": "Тестовое описание"},
        location_type="FOREST",
        coordinates_json={"x": 1, "y": 1},
        generated_details_json={"detail": "some detail"},
        potential_neighbors=[
            {"static_id_or_name": "neighbor1_static", "connection_description_i18n": {"en": "a path", "ru": "тропа"}}
        ]
    )
    mock_parsed_ai_data = ParsedAiData(
        generated_entities=[mock_parsed_location_data],
        raw_ai_output="mock raw output",
        parsing_metadata={}
    )

    # Мок для создаваемой локации
    created_location_mock = Location(
        id=100,
        guild_id=guild_id,
        name_i18n=mock_parsed_location_data.name_i18n,
        descriptions_i18n=mock_parsed_location_data.descriptions_i18n,
        type=LocationType.FOREST, # Используем Enum
        coordinates_json=mock_parsed_location_data.coordinates_json,
        generated_details_json=mock_parsed_location_data.generated_details_json,
        neighbor_locations_json=[] # Начальное значение
    )
    mock_location_crud.create.return_value = created_location_mock

    # Мок для существующего соседа
    existing_neighbor_mock = Location(id=200, guild_id=guild_id, static_id="neighbor1_static", name_i18n={"en":"Neighbor 1"}, neighbor_locations_json=[])
    mock_location_crud.get_by_static_id.return_value = existing_neighbor_mock
    mock_location_crud.get.return_value = existing_neighbor_mock # Для update_location_neighbors

    with patch("src.core.world_generation.prepare_ai_prompt", new_callable=AsyncMock, return_value="Test Prompt") as mock_prepare_prompt, \
         patch("src.core.world_generation._mock_openai_api_call", new_callable=AsyncMock, return_value='[{"entity_type": "location", ...}]') as mock_ai_call, \
         patch("src.core.world_generation.parse_and_validate_ai_response", new_callable=AsyncMock, return_value=mock_parsed_ai_data) as mock_parse_validate, \
         patch("src.core.world_generation.log_event", new_callable=AsyncMock) as mock_log_event, \
         patch("src.core.world_generation.location_crud", new=mock_location_crud), \
         patch("src.core.world_generation.update_location_neighbors", new_callable=AsyncMock) as mock_update_neighbors:

        location, error = await generate_location(
            session=mock_db_session,
            guild_id=guild_id,
            location_id_context=context_location_id
        )

        assert error is None
        assert location is not None
        assert location.id == 100
        assert location.name_i18n["en"] == "Generated Test Location"

        mock_prepare_prompt.assert_called_once()
        mock_ai_call.assert_called_once()
        mock_parse_validate.assert_called_once()

        mock_location_crud.create.assert_called_once()
        # Проверяем, что update_location_neighbors был вызван для существующего соседа
        mock_update_neighbors.assert_called_once_with(
            mock_db_session, existing_neighbor_mock, created_location_mock.id, {"en": "a path", "ru": "тропа"}, add_connection=True
        )

        mock_log_event.assert_called_once()
        assert mock_log_event.call_args[1]["event_type"] == EventType.WORLD_EVENT_LOCATION_GENERATED.value
        assert mock_log_event.call_args[1]["details_json"]["location_id"] == 100

        commit_mock: AsyncMock = mock_db_session.commit # type: ignore
        commit_mock.assert_called_once()

@pytest.mark.asyncio
async def test_generate_new_location_ai_validation_error(mock_db_session: AsyncSession):
    guild_id = 1
    validation_error = CustomValidationError(error_type="TestError", message="AI validation failed")

    with patch("src.core.world_generation.prepare_ai_prompt", new_callable=AsyncMock, return_value="Test Prompt"), \
         patch("src.core.world_generation._mock_openai_api_call", new_callable=AsyncMock, return_value='invalid json'), \
         patch("src.core.world_generation.parse_and_validate_ai_response", new_callable=AsyncMock, return_value=validation_error):

        location, error = await generate_location(
            session=mock_db_session,
            guild_id=guild_id
        )

        assert location is None
        assert error is not None
        assert "AI validation failed" in error
    # mock_db_session.rollback.assert_called_once() # Ошибка до начала транзакции

@pytest.mark.asyncio
async def test_generate_new_location_no_location_data_in_response(mock_db_session: AsyncSession):
    guild_id = 1
    # Ответ парсера не содержит ParsedLocationData
    mock_parsed_ai_data_empty = ParsedAiData(generated_entities=[], raw_ai_output="mock raw output", parsing_metadata={})

    with patch("src.core.world_generation.prepare_ai_prompt", new_callable=AsyncMock, return_value="Test Prompt"), \
         patch("src.core.world_generation._mock_openai_api_call", new_callable=AsyncMock, return_value='[]'), \
         patch("src.core.world_generation.parse_and_validate_ai_response", new_callable=AsyncMock, return_value=mock_parsed_ai_data_empty):

        location, error = await generate_location(
            session=mock_db_session,
            guild_id=guild_id
        )

        assert location is None
        assert error is not None
        assert "No valid location data found" in error
    # mock_db_session.rollback.assert_called_once() # Ошибка до начала транзакции


@pytest.mark.asyncio
async def test_update_location_neighbors_add_connection(mock_db_session: AsyncSession):
    loc1 = Location(id=1, guild_id=1, name_i18n={"en":"Loc1"}, neighbor_locations_json=[])
    neighbor_id = 2
    conn_type = {"en": "a bridge", "ru": "мост"}

    await update_location_neighbors(mock_db_session, loc1, neighbor_id, conn_type, add_connection=True)

    assert loc1.neighbor_locations_json is not None
    assert len(loc1.neighbor_locations_json) == 1
    assert loc1.neighbor_locations_json[0]["id"] == neighbor_id  # type: ignore[literal-required]
    assert loc1.neighbor_locations_json[0]["type_i18n"] == conn_type  # type: ignore[literal-required]
    flush_mock: AsyncMock = mock_db_session.flush # type: ignore
    flush_mock.assert_called_once_with([loc1])

@pytest.mark.asyncio
async def test_update_location_neighbors_remove_connection(mock_db_session: AsyncSession):
    neighbor_id_to_remove = 2
    initial_neighbors = [
        {"id": neighbor_id_to_remove, "type_i18n": {"en": "a bridge"}},
        {"id": 3, "type_i18n": {"en": "a tunnel"}}
    ]
    loc1 = Location(id=1, guild_id=1, name_i18n={"en":"Loc1"}, neighbor_locations_json=initial_neighbors)

    await update_location_neighbors(mock_db_session, loc1, neighbor_id_to_remove, {}, add_connection=False)

    assert loc1.neighbor_locations_json is not None
    assert len(loc1.neighbor_locations_json) == 1
    assert loc1.neighbor_locations_json[0]["id"] == 3  # type: ignore[literal-required]
    flush_mock_remove: AsyncMock = mock_db_session.flush # type: ignore
    flush_mock_remove.assert_called_once_with([loc1])

@pytest.mark.asyncio
async def test_update_location_neighbors_add_existing_does_not_duplicate(mock_db_session: AsyncSession):
    existing_neighbor_id = 2
    conn_type = {"en": "a bridge", "ru": "мост"}
    initial_neighbors = [{"id": existing_neighbor_id, "type_i18n": conn_type}]
    loc1 = Location(id=1, guild_id=1, name_i18n={"en":"Loc1"}, neighbor_locations_json=initial_neighbors)

    # Попытка добавить того же соседа
    await update_location_neighbors(mock_db_session, loc1, existing_neighbor_id, conn_type, add_connection=True)

    assert loc1.neighbor_locations_json is not None
    assert len(loc1.neighbor_locations_json) == 1 # Длина не должна измениться
    assert loc1.neighbor_locations_json[0]["id"] == existing_neighbor_id  # type: ignore[literal-required]
    # flush должен быть вызван, так как объект передается в него, даже если список не изменился
    # Однако, если бы мы проверяли session.add(loc1), то он не должен был бы быть вызван, если объект не dirty.
    # Но flush([loc1]) будет вызван в любом случае нашей функцией.
    flush_mock_duplicate: AsyncMock = mock_db_session.flush # type: ignore
    flush_mock_duplicate.assert_called_once_with([loc1])

@pytest.mark.asyncio
async def test_generate_new_location_potential_neighbor_not_found(
    mock_db_session: AsyncSession,
    mock_location_crud: MagicMock
):
    guild_id = 1
    mock_parsed_location_data = ParsedLocationData(
        entity_type="location",
        name_i18n={"en": "Test Loc"}, descriptions_i18n={"en": "Desc"}, location_type="PLAINS",
        potential_neighbors=[{"static_id_or_name": "non_existent_neighbor", "connection_description_i18n": {"en": "a track"}}]
    )
    mock_parsed_ai_data = ParsedAiData(generated_entities=[mock_parsed_location_data], raw_ai_output="", parsing_metadata={})
    created_location_mock = Location(id=101, guild_id=guild_id, name_i18n=mock_parsed_location_data.name_i18n, neighbor_locations_json=[])

    mock_location_crud.create.return_value = created_location_mock
    mock_location_crud.get_by_static_id.return_value = None # Сосед не найден

    with patch("src.core.world_generation.prepare_ai_prompt", new_callable=AsyncMock, return_value="Prompt"), \
         patch("src.core.world_generation._mock_openai_api_call", new_callable=AsyncMock, return_value='[{}]'), \
         patch("src.core.world_generation.parse_and_validate_ai_response", new_callable=AsyncMock, return_value=mock_parsed_ai_data), \
         patch("src.core.world_generation.log_event", new_callable=AsyncMock), \
         patch("src.core.world_generation.location_crud", new=mock_location_crud), \
         patch("src.core.world_generation.update_location_neighbors", new_callable=AsyncMock) as mock_update_neighbors:

        location, error = await generate_location(mock_db_session, guild_id)

        assert error is None
        assert location is not None
        assert location.id == 101
        assert not location.neighbor_locations_json # Список соседей должен остаться пустым

        update_neighbors_mock_typed: AsyncMock = mock_update_neighbors # type: ignore
        update_neighbors_mock_typed.assert_not_called() # Не должен вызываться, если сосед не найден

        commit_mock_no_neighbor: AsyncMock = mock_db_session.commit # type: ignore
        commit_mock_no_neighbor.assert_called_once()

# TODO: Тесты для обработки `new_generated_neighbor_type` в `potential_neighbors`,
# когда AI предлагает создать еще одного соседа. Это более сложный сценарий,
# возможно, требующий рекурсивного вызова или отдельного механизма.
# Для текущего MVP это выходит за рамки.

# Фикстуры, если они не в conftest.py
# @pytest.fixture
# async def mock_db_session() -> AsyncMock:
#     session = AsyncMock(spec=AsyncSession)
#     session.commit = AsyncMock()
#     session.rollback = AsyncMock()
#     session.flush = AsyncMock()
#     return session

# @pytest.fixture
# def mock_location_crud() -> MagicMock:
#     crud = MagicMock()
#     crud.create = AsyncMock()
#     crud.get_by_static_id = AsyncMock()
#     crud.get = AsyncMock()
#     crud.update = AsyncMock()
#     return crud
