# src/core/map_management.py
import logging
from typing import Optional, Any, Dict, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.core.crud.crud_location import location_crud
from src.core.game_events import log_event
from src.core.world_generation import update_location_neighbors # Импортируем вспомогательную функцию
from src.models import Location
from src.models.enums import EventType

logger = logging.getLogger(__name__)

async def add_location_master(
    session: AsyncSession,
    guild_id: int,
    location_data: Dict[str, Any]
) -> Tuple[Optional[Location], Optional[str]]:
    """
    Создает новую локацию вручную Мастером.
    location_data должен содержать все необходимые поля для модели Location,
    включая static_id, name_i18n, descriptions_i18n, type, и др.
    neighbor_locations_json в location_data будет использован для начальной установки соседей.
    """
    try:
        # Проверка на обязательные поля (пример)
        required_fields = ["static_id", "name_i18n", "descriptions_i18n", "type"]
        for field in required_fields:
            if field not in location_data:
                return None, f"Missing required field in location_data: {field}"

        if not location_data["static_id"]: # static_id не должен быть пустым
             return None, "static_id cannot be empty for manually added locations."

        # Проверка на уникальность static_id в пределах guild_id
        existing_loc_by_static_id = await location_crud.get_by_static_id(
            session, guild_id=guild_id, static_id=location_data["static_id"]
        )
        if existing_loc_by_static_id:
            return None, f"Location with static_id '{location_data['static_id']}' already exists in this guild."

        obj_in_data = {
            "guild_id": guild_id,
            "static_id": location_data["static_id"],
            "name_i18n": location_data["name_i18n"],
            "descriptions_i18n": location_data["descriptions_i18n"],
            "type": location_data["type"], # Должен быть валидным значением из LocationType enum
            "coordinates_json": location_data.get("coordinates_json", {}),
            "neighbor_locations_json": location_data.get("neighbor_locations_json", []), # Начальные соседи
            "generated_details_json": location_data.get("generated_details_json", {}),
            "ai_metadata_json": location_data.get("ai_metadata_json", {"created_by_master": True})
        }

        new_location = await location_crud.create(session, obj_in=obj_in_data) # Corrected: obj_in_data to obj_in
        await session.flush() # Чтобы получить new_location.id

        # Обновление связей у соседей, если они были указаны в neighbor_locations_json
        # Это предполагает, что neighbor_locations_json содержит ID существующих локаций
        if new_location and new_location.neighbor_locations_json:
            for neighbor_data_item in new_location.neighbor_locations_json:
                if isinstance(neighbor_data_item, dict):
                    neighbor_id = neighbor_data_item.get("id")
                    conn_type = neighbor_data_item.get("type_i18n", {"en": "a connection", "ru": "связь"})
                    if neighbor_id: # Make sure neighbor_id is not None if .get could return it
                        try:
                            actual_neighbor_id = int(neighbor_id) # Ensure it's an int
                            neighbor_loc = await location_crud.get(session, id=actual_neighbor_id)
                            if neighbor_loc and neighbor_loc.guild_id == guild_id:
                                await update_location_neighbors(session, neighbor_loc, new_location.id, conn_type, add_connection=True)
                            else:
                                logger.warning(f"Neighbor location ID {actual_neighbor_id} not found or not in guild {guild_id} when adding master location {new_location.id}")
                        except ValueError:
                            logger.warning(f"Invalid neighbor_id format: {neighbor_id} in new_location.neighbor_locations_json for location {new_location.id}")
                else:
                    logger.warning(f"Skipping malformed neighbor_data_item in new_location.neighbor_locations_json for location {new_location.id}: {neighbor_data_item}")

        await log_event(
            session=session,
            guild_id=guild_id,
            event_type=EventType.MASTER_ACTION_LOCATION_ADDED.value, # Corrected: Added .value
            details_json={
                "location_id": new_location.id,
                "static_id": new_location.static_id,
                "name_i18n": new_location.name_i18n
            },
            location_id=new_location.id
        )
        await session.commit()
        logger.info(f"Master added new location '{new_location.static_id}' (ID: {new_location.id}) for guild {guild_id}.")
        return new_location, None
    except Exception as e:
        logger.exception(f"Error adding location by master for guild {guild_id}: {e}")
        await session.rollback() # Rollback в случае любой ошибки во время операций с БД
        return None, f"An unexpected error occurred: {str(e)}"

async def remove_location_master(
    session: AsyncSession,
    guild_id: int,
    location_id_to_remove: int
) -> Tuple[bool, Optional[str]]:
    """
    Удаляет локацию Мастером. Также обновляет связи у бывших соседей.
    """
    location_to_remove = await location_crud.get(session, id=location_id_to_remove)

    if not location_to_remove:
        # await session.rollback() # Не нужно, если ошибка до начала изменений
        return False, "Location not found."
    if location_to_remove.guild_id != guild_id:
        logger.warning(f"Master from guild {guild_id} attempted to remove location {location_id_to_remove} from another guild {location_to_remove.guild_id}.")
        # await session.rollback() # Не нужно, если ошибка до начала изменений
        return False, "Location not found in this guild."

    try:
        # Сохраняем ID соседей до удаления самой локации
        neighbor_ids_to_update: List[int] = []
        if location_to_remove.neighbor_locations_json:
            for neighbor_info in location_to_remove.neighbor_locations_json:
                if isinstance(neighbor_info, dict) and "id" in neighbor_info:
                    neighbor_ids_to_update.append(neighbor_info["id"])

        removed_static_id = location_to_remove.static_id
        removed_name_i18n = location_to_remove.name_i18n

        # Удаляем локацию
        await location_crud.delete(session, id=location_id_to_remove) # Corrected: remove to delete
        # session.flush() # delete (from CRUDBase) typically doesn't require separate flush before commit

        # Обновляем бывших соседей
        for neighbor_id in neighbor_ids_to_update:
            neighbor_loc = await location_crud.get(session, id=neighbor_id)
            if neighbor_loc and neighbor_loc.guild_id == guild_id:
                # Тип соединения здесь не важен, т.к. мы просто удаляем ссылку
                await update_location_neighbors(session, neighbor_loc, location_id_to_remove, {}, add_connection=False)
            else:
                logger.warning(f"Former neighbor location ID {neighbor_id} not found or not in guild {guild_id} when removing location {location_id_to_remove}")

        await log_event(
            session=session,
            guild_id=guild_id,
            event_type=EventType.MASTER_ACTION_LOCATION_REMOVED.value, # Corrected: Added .value
            details_json={
                "removed_location_id": location_id_to_remove,
                "removed_static_id": removed_static_id,
                "removed_name_i18n": removed_name_i18n
            }
        )
        await session.commit()
        logger.info(f"Master removed location ID {location_id_to_remove} (Static: {removed_static_id}) from guild {guild_id}.")
        return True, None
    except Exception as e:
        logger.exception(f"Error removing location {location_id_to_remove} by master for guild {guild_id}: {e}")
        await session.rollback()
        return False, f"An unexpected error occurred: {str(e)}"

async def connect_locations_master(
    session: AsyncSession,
    guild_id: int,
    loc1_id: int,
    loc2_id: int,
    connection_type_i18n: Dict[str, str]
) -> Tuple[bool, Optional[str]]:
    """
    Соединяет две локации Мастером, обновляя их neighbor_locations_json.
    """
    if loc1_id == loc2_id:
        return False, "Cannot connect a location to itself."
    try:
        loc1 = await location_crud.get(session, id=loc1_id)
        loc2 = await location_crud.get(session, id=loc2_id)

        if not loc1:
            return False, f"Location with ID {loc1_id} not found."
        if loc1.guild_id != guild_id:
            return False, f"Location {loc1_id} not found in this guild."
        if not loc2:
            return False, f"Location with ID {loc2_id} not found."
        if loc2.guild_id != guild_id:
            return False, f"Location {loc2_id} not found in this guild."

        # Соединяем loc1 -> loc2
        await update_location_neighbors(session, loc1, loc2_id, connection_type_i18n, add_connection=True)

        # Соединяем loc2 -> loc1 (симметрично)
        # Можно использовать тот же connection_type_i18n или определить обратный, если нужно
        await update_location_neighbors(session, loc2, loc1_id, connection_type_i18n, add_connection=True)

        await log_event(
            session=session,
            guild_id=guild_id,
            event_type=EventType.MASTER_ACTION_LOCATIONS_CONNECTED.value, # Corrected: Added .value
            details_json={
                "location1_id": loc1_id,
                "location2_id": loc2_id,
                "connection_type_i18n": connection_type_i18n
            }
        )
        await session.commit()
        logger.info(f"Master connected locations {loc1_id} and {loc2_id} in guild {guild_id}.")
        return True, None
    except Exception as e:
        logger.exception(f"Error connecting locations {loc1_id} and {loc2_id} by master for guild {guild_id}: {e}")
        await session.rollback()
        return False, f"An unexpected error occurred: {str(e)}"

async def disconnect_locations_master(
    session: AsyncSession,
    guild_id: int,
    loc1_id: int,
    loc2_id: int
) -> Tuple[bool, Optional[str]]:
    """
    Разъединяет две локации Мастером.
    """
    if loc1_id == loc2_id:
        return False, "Cannot disconnect a location from itself."
    try:
        loc1 = await location_crud.get(session, id=loc1_id)
        loc2 = await location_crud.get(session, id=loc2_id)

        if not loc1:
            return False, f"Location with ID {loc1_id} not found."
        if loc1.guild_id != guild_id:
            return False, f"Location {loc1_id} not found in this guild."
        if not loc2:
            return False, f"Location with ID {loc2_id} not found."
        if loc2.guild_id != guild_id:
            return False, f"Location {loc2_id} not found in this guild."

        # Разъединяем loc1 -> loc2
        await update_location_neighbors(session, loc1, loc2_id, {}, add_connection=False)

        # Разъединяем loc2 -> loc1
        await update_location_neighbors(session, loc2, loc1_id, {}, add_connection=False)

        await log_event(
            session=session,
            guild_id=guild_id,
            event_type=EventType.MASTER_ACTION_LOCATIONS_DISCONNECTED.value, # Corrected: Added .value
            details_json={
                "location1_id": loc1_id,
                "location2_id": loc2_id,
            }
        )
        await session.commit()
        logger.info(f"Master disconnected locations {loc1_id} and {loc2_id} in guild {guild_id}.")
        return True, None
    except Exception as e:
        logger.exception(f"Error disconnecting locations {loc1_id} and {loc2_id} by master for guild {guild_id}: {e}")
        await session.rollback()
        return False, f"An unexpected error occurred: {str(e)}"

logger.info("Map Management module initialized.")

# В src/core/__init__.py нужно будет добавить:
# from . import map_management
# from .map_management import add_location_master, remove_location_master, connect_locations_master, disconnect_locations_master
# и в __all__ добавить эти функции.
