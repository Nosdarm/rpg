# src/core/world_generation.py
import logging
from typing import Optional, Any, Dict, Tuple, List

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_orchestrator import trigger_ai_generation_flow, save_approved_generation, \
    _mock_openai_api_call # Используем мок для AI
from src.core.ai_prompt_builder import prepare_ai_prompt
from src.core.ai_response_parser import parse_and_validate_ai_response, ParsedAiData, ParsedLocationData, \
    CustomValidationError
from src.core.crud.crud_location import location_crud
from src.core.game_events import log_event
from src.models import Location
from src.models.enums import EventType, ModerationStatus
from src.models.pending_generation import PendingGeneration

logger = logging.getLogger(__name__)

async def generate_new_location_via_ai(
    session: AsyncSession,
    guild_id: int,
    generation_params: Optional[Dict[str, Any]] = None,
    # Параметры для контекста prompt_builder, если нужны сверх стандартных
    location_id_context: Optional[int] = None,
    player_id_context: Optional[int] = None,
    party_id_context: Optional[int] = None
) -> Tuple[Optional[Location], Optional[str]]:
    """
    Генерирует новую локацию с использованием AI, сохраняет ее в БД и обновляет связи.
    Возвращает (созданная локация, None) или (None, сообщение об ошибке).
    """
    try:
        # 1. Подготовка промпта для AI
        # Добавляем указание на тип генерируемого контента
        prompt_context_params = generation_params or {}
        prompt_context_params["generation_type"] = "location" # Указываем, что хотим сгенерировать локацию

        # Если location_id_context не передан, prompt_builder может не найти текущую локацию
        # для контекста, но для генерации *новой* локации это может быть нормально.
        # Возможно, понадобится передать сюда ID "стартовой" или "соседней" локации для AI.
        # Пока что используем location_id_context как есть.

        prompt = await prepare_ai_prompt(
            session=session,
            guild_id=guild_id,
            location_id=location_id_context, # ID локации для контекста, не ID новой локации
            player_id=player_id_context,
            party_id=party_id_context,
            # Assuming 'context_params' or similar is the intended parameter name in prepare_ai_prompt
            # For now, trying 'generation_params' as it's a common pattern.
            # If this is still an error, prepare_ai_prompt signature is needed.
            # Based on AGENTS.md, 'custom_instruction' might be part of a general context dict.
            # Safest option without signature: remove or use a very generic name.
            # Let's assume custom_generation_request_params was a typo for generation_params in prepare_ai_prompt
            context_params=prompt_context_params
        )
        logger.debug(f"Generated AI prompt for new location in guild {guild_id}:\n{prompt}")

        # 2. Вызов AI (используем мок)
        # В реальном сценарии здесь будет асинхронный вызов к OpenAI API
        # Мок должен вернуть JSON строку, имитирующую ответ LLM
        # Пример ответа AI для локации:
        # {
        #   "type": "location",
        #   "name_i18n": {"en": "Mystic Cave", "ru": "Мистическая Пещера"},
        #   "descriptions_i18n": {"en": "A dark and damp cave.", "ru": "Темная и сырая пещера."},
        #   "location_type": "CAVE", // Соответствует LocationType enum
        #   "coordinates_json": {"x": 10, "y": 5, "plane": "Overworld"},
        #   "generated_details_json": {"entry_description_i18n": {"en": "A narrow passage leads into darkness.", "ru": "Узкий проход ведет во тьму."}},
        #   "potential_neighbors": [ // Описание потенциальных соседей
        #     {"static_id_or_name": "village_center", "connection_description_i18n": {"en": "a hidden path", "ru": "скрытая тропа"}},
        #     {"new_generated_neighbor_type": "FOREST", "connection_description_i18n": {"en": "a dense thicket", "ru": "густая чаща"}} // Пример, если AI предлагает создать еще соседа
        #   ]
        # }
        # Для MVP мок может быть упрощен.
        mock_ai_response_str = await _mock_openai_api_call(prompt) # Corrected L71: Removed language="en"

        # 3. Парсинг и валидация ответа AI
        # parse_and_validate_ai_response ожидает список сущностей.
        # Если AI возвращает одну локацию, обернем ее в список.
        # Модифицируем мок, чтобы он возвращал список с одной локацией.
        # (Предполагаем, что мок _mock_openai_api_call возвращает строку, которую нужно обернуть в список JSON)
        # В реальном сценарии, LLM должен быть настроен на возврат списка.

        # Для теста, предположим, _mock_openai_api_call возвращает одну локацию как JSON объект (строку)
        # Обернем ее в JSON массив строк, если это необходимо для parse_and_validate_ai_response
        # Однако, parse_and_validate_ai_response уже должен уметь работать с одним объектом, если он является валидной сущностью.
        # Проверим, как parse_and_validate_ai_response обрабатывает одиночный объект типа "location"

        parsed_data_or_error = await parse_and_validate_ai_response(
            raw_ai_output_text=mock_ai_response_str,
            guild_id=guild_id
            # session=session # Corrected L88: Removed session (assuming signature doesn't take it)
        )

        if isinstance(parsed_data_or_error, CustomValidationError):
            error_msg = f"AI response validation failed: {parsed_data_or_error.message} - Details: {parsed_data_or_error.details}"
            logger.error(error_msg)
            return None, error_msg

        parsed_ai_data: ParsedAiData = parsed_data_or_error

        # Ищем сгенерированную локацию в parsed_ai_data
        generated_location_data: Optional[ParsedLocationData] = None
        if parsed_ai_data.generated_entities: # Исправлено entities на generated_entities
            for entity in parsed_ai_data.generated_entities: # Исправлено entities на generated_entities
                if isinstance(entity, ParsedLocationData):
                    generated_location_data = entity
                    break

        if not generated_location_data:
            error_msg = "No valid location data found in AI response."
            logger.error(error_msg)
            return None, error_msg

        # 4. Создание записи Location в БД
        # static_id для генерируемых локаций может быть не нужен или генерироваться уникально
        # Пока оставим его None, БД присвоит автоинкрементный id
        new_location_db = await location_crud.create(
            session,
            obj_in={ # Corrected L114, L116: obj_in_data to obj_in
                "guild_id": guild_id,
                "static_id": None, # Генерируемые локации могут не иметь предопределенного static_id
                "name_i18n": generated_location_data.name_i18n,
                "descriptions_i18n": generated_location_data.descriptions_i18n,
                "type": generated_location_data.location_type,
                "coordinates_json": generated_location_data.coordinates_json or {},
                "neighbor_locations_json": [], # Будет заполнено ниже
                "generated_details_json": generated_location_data.generated_details_json or {},
                "ai_metadata_json": {"prompt": prompt, "raw_response": mock_ai_response_str} # Сохраняем метаданные AI
            }
        )
        await session.flush() # Чтобы получить new_location_db.id

        logger.info(f"New location '{generated_location_data.name_i18n.get('en', 'N/A')}' (ID: {new_location_db.id}) generated by AI for guild {guild_id}.")

        # 5. Обновление связей с соседями (MVP: простая обработка)
        # generated_location_data.potential_neighbors должен быть списком словарей
        # {"static_id_or_name": "some_id", "connection_description_i18n": {...}}
        # Эта логика требует доработки для поиска существующих локаций по static_id/name
        # и обновления их neighbor_locations_json.

        # TODO: Реализовать более сложную логику обновления связей с соседями.
        # На данный момент, просто логируем информацию о потенциальных соседях.
        if generated_location_data.potential_neighbors:
            logger.info(f"Potential neighbors for location ID {new_location_db.id}: {generated_location_data.potential_neighbors}")
            # Здесь должна быть логика поиска этих соседей в БД и обновления new_location_db.neighbor_locations_json
            # и neighbor_locations_json у самих соседей.
            # Например:
            # current_neighbors = []
            # for neighbor_info in generated_location_data.potential_neighbors:
            #    neighbor_static_id = neighbor_info.get("static_id_or_name")
            #    if neighbor_static_id:
            #        existing_neighbor = await location_crud.get_by_static_id(session, guild_id=guild_id, static_id=neighbor_static_id)
            #        if existing_neighbor:
            #            # Добавляем связь к новой локации
            #            current_neighbors.append({
            #                "id": existing_neighbor.id,
            #                "type_i18n": neighbor_info.get("connection_description_i18n", {"en": "a connection", "ru": "связь"})
            #            })
            #            # Обновляем соседа
            #            neighbor_neighbor_list = list(existing_neighbor.neighbor_locations_json or [])
            #            neighbor_neighbor_list.append({
            #                "id": new_location_db.id,
            #                "type_i18n": neighbor_info.get("connection_description_i18n", {"en": "a connection", "ru": "связь"}) # Или инвертированное описание
            #            })
            #            await location_crud.update(session, db_obj=existing_neighbor, obj_in_data={"neighbor_locations_json": neighbor_neighbor_list})
            # if current_neighbors:
            #    await location_crud.update(session, db_obj=new_location_db, obj_in_data={"neighbor_locations_json": current_neighbors})
            # await session.flush()

        # Примерная логика обновления соседей (требует тестирования и доработки)
        if generated_location_data.potential_neighbors and new_location_db:
            new_loc_neighbor_list = []
            for neighbor_info in generated_location_data.potential_neighbors:
                neighbor_static_id = neighbor_info.get("static_id_or_name")
                conn_desc_i18n = neighbor_info.get("connection_description_i18n", {"en": "a path", "ru": "тропа"})
                if neighbor_static_id:
                    existing_neighbor_loc = await location_crud.get_by_static_id(session, guild_id=guild_id, static_id=neighbor_static_id)
                    if existing_neighbor_loc:
                        # Связь от новой локации к существующей
                        new_loc_neighbor_list.append({"id": existing_neighbor_loc.id, "type_i18n": conn_desc_i18n})

                        # Связь от существующей локации к новой
                        # Важно: это изменяет существующую локацию, нужно делать аккуратно
                        await update_location_neighbors(session, existing_neighbor_loc, new_location_db.id, conn_desc_i18n, add_connection=True)
                        logger.info(f"Updated existing neighbor {existing_neighbor_loc.id} to connect to new location {new_location_db.id}")
                    else:
                        logger.warning(f"Potential neighbor with static_id '{neighbor_static_id}' not found for guild {guild_id}.")
                # TODO: Обработка случая, когда AI предлагает создать ЕЩЕ ОДНУ новую локацию-соседа (`new_generated_neighbor_type`)

            if new_loc_neighbor_list:
                new_location_db.neighbor_locations_json = new_loc_neighbor_list
                # session.add(new_location_db) # SQLAlchemy 2.0+ отслеживает изменения
                await session.flush([new_location_db])
                logger.info(f"Updated new location {new_location_db.id} with neighbors: {new_loc_neighbor_list}")


        # 6. Логирование события
        await log_event(
            session=session,
            guild_id=guild_id,
            event_type=EventType.WORLD_EVENT_LOCATION_GENERATED.value, # Corrected L198: Added .value
            details_json={
                "location_id": new_location_db.id if new_location_db else -1, # Handle if new_location_db is None (though unlikely here)
                "name_i18n": new_location_db.name_i18n if new_location_db else {},
                "generated_by": "ai",
                "generation_params": generation_params
            },
            location_id=new_location_db.id
        )

        await session.commit()
        logger.info(f"Successfully generated and saved new AI location ID {new_location_db.id} for guild {guild_id}.")
        return new_location_db, None

    except Exception as e:
        logger.exception(f"Error generating new location via AI for guild {guild_id}: {e}")
        await session.rollback()
        return None, f"An unexpected error occurred during AI location generation: {str(e)}"

# TODO: Добавить API функции для Мастера (add_location, remove_location, connect_locations)
# в src/core/map_management.py, как и планировалось.
# world_generation.py будет сфокусирован на AI-генерации.

async def update_location_neighbors(
    session: AsyncSession,
    location: Location,
    neighbor_id: int,
    connection_type_i18n: Dict[str, str],
    add_connection: bool = True
) -> None:
    """
    Вспомогательная функция для добавления/удаления соседа из neighbor_locations_json локации.
    """
    # Ensure current_neighbors is strictly List[Dict[str, Any]]
    raw_neighbors = location.neighbor_locations_json or []
    current_neighbors: List[Dict[str, Any]] = []
    for item in raw_neighbors:
        if isinstance(item, dict):
            current_neighbors.append(item)
        else:
            # Log or handle malformed item if necessary
            logger.warning(f"Location {location.id} contained a malformed (non-dict) neighbor entry: {item}")

    if add_connection:
        # Проверяем, нет ли уже такой связи
        if not any(n.get("id") == neighbor_id for n in current_neighbors):
            current_neighbors.append({"id": neighbor_id, "type_i18n": connection_type_i18n})
            location.neighbor_locations_json = current_neighbors
            logger.debug(f"Added neighbor {neighbor_id} to location {location.id}")
    else: # remove_connection
        initial_len = len(current_neighbors)
        current_neighbors = [n for n in current_neighbors if n.get("id") != neighbor_id]
        if len(current_neighbors) < initial_len:
            logger.debug(f"Removed neighbor {neighbor_id} from location {location.id}")
        location.neighbor_locations_json = current_neighbors

    # session.add(location) # SQLAlchemy 2.0+ отслеживает изменения автоматически
    await session.flush([location])
