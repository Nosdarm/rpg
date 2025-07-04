"""
Модуль для управления системой опыта, начислением XP и повышением уровней.
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import game_events, rules
from src.models import Player, GuildConfig
from src.models.enums import RelationshipEntityType, EventType
from src.core.crud.crud_player import player_crud
from src.core.crud.crud_party import party_crud

logger = logging.getLogger(__name__)

async def award_xp(
    session: AsyncSession,
    guild_id: int,
    entity_id: int,
    entity_type: RelationshipEntityType,
    xp_to_award: int,
    source_event_type: EventType, # Принимаем Enum
    source_log_id: Optional[int] = None,
) -> list[Player]:
    players_to_update: list[Player] = []
    player_recipients: list[Player] = []

    if entity_type == RelationshipEntityType.PLAYER:
        player = await player_crud.get_by_id_and_guild(session, id=entity_id, guild_id=guild_id)
        if player:
            player_recipients.append(player)
        else:
            logger.warning(f"award_xp: Игрок с ID {entity_id} в гильдии {guild_id} не найден.")
            return []
    elif entity_type == RelationshipEntityType.PARTY:
        party = await party_crud.get(session, id=entity_id, guild_id=guild_id)
        if party and party.players:
            player_recipients.extend(party.players)
        else:
            logger.warning(f"award_xp: Партия с ID {entity_id} в гильдии {guild_id} не найдена или не имеет участников (party.players).")
            return []
    else:
        logger.error(f"award_xp: Неподдерживаемый тип сущности {entity_type} для начисления XP.")
        return []

    if not player_recipients:
        logger.info(f"award_xp: Нет получателей XP для entity_id={entity_id}, entity_type={entity_type}.")
        return []

    xp_per_player = xp_to_award
    if entity_type == RelationshipEntityType.PARTY and len(player_recipients) > 0:
        xp_per_player = xp_to_award // len(player_recipients)

    if xp_per_player <= 0 and xp_to_award > 0:
        if len(player_recipients) > 0 : # Проверка, чтобы избежать деления на ноль, если список пуст (хотя выше есть return)
             logger.warning(f"award_xp: XP на игрока стало {xp_per_player} после деления {xp_to_award} на {len(player_recipients)}. Никто не получит XP, если xp_per_player <= 0.")

    for player_obj in player_recipients:
        if xp_per_player > 0 :
            player_obj.xp += xp_per_player

            await game_events.log_event(
                session=session,
                guild_id=guild_id,
                event_type=EventType.XP_GAINED.name, # Передаем имя Enum
                details_json={
                    "player_id": player_obj.id,
                    "player_name": player_obj.name,
                    "xp_awarded": xp_per_player,
                    "new_total_xp": player_obj.xp,
                    "source_event": source_event_type.name, # Передаем имя Enum
                    "source_log_id": source_log_id,
                },
                entity_ids_json={"player_id": player_obj.id}
            )

            level_up_achieved = await _check_for_level_up(session, guild_id, player_obj)
            if level_up_achieved:
                logger.info(f"Игрок {player_obj.name} (ID: {player_obj.id}) повысил уровень до {player_obj.level} в гильдии {guild_id}.")

            players_to_update.append(player_obj)

    if players_to_update:
        await session.commit()
        for p_obj in players_to_update:
            try:
                await session.refresh(p_obj)
            except Exception as e:
                logger.error(f"Не удалось обновить игрока {p_obj.id} после коммита в award_xp: {e}")

    return players_to_update


async def _check_for_level_up(session: AsyncSession, guild_id: int, player: Player) -> bool:
    level_curve_rules = await rules.get_rule(session, guild_id, "experience_system:level_curve")
    level_up_rewards_rules = await rules.get_rule(session, guild_id, "experience_system:level_up_rewards")

    if not level_curve_rules:
        logger.error(f"_check_for_level_up: Правила 'experience_system:level_curve' не найдены для guild_id={guild_id}.")
        return False
    if not isinstance(level_up_rewards_rules, dict): # Проверяем, что это словарь (может быть None)
        logger.warning(f"_check_for_level_up: Правила 'experience_system:level_up_rewards' не найдены или некорректны для guild_id={guild_id}. Награды не будут начислены.")
        level_up_rewards_rules = {}

    level_upped_once = False

    while True:
        current_level_xp_needed = -1
        if not isinstance(level_curve_rules, list):
            logger.error(f"Правило 'experience_system:level_curve' имеет неверный формат (не список) для guild_id={guild_id}")
            break

        for level_info in level_curve_rules:
            if isinstance(level_info, dict) and level_info.get("current_level") == player.level:
                xp_needed_val = level_info.get("xp_to_reach_next_level")
                if isinstance(xp_needed_val, int) and xp_needed_val > 0 :
                    current_level_xp_needed = xp_needed_val
                else:
                    logger.error(f"Некорректное значение xp_to_reach_next_level ({xp_needed_val}) для уровня {player.level} в guild_id={guild_id}")
                break

        if current_level_xp_needed == -1:
            logger.info(f"Игрок {player.id} (уровень {player.level}) достиг максимального уровня по кривой или правила не найдены для guild_id={guild_id}.")
            break

        if player.xp >= current_level_xp_needed:
            player.level += 1
            player.xp -= current_level_xp_needed
            level_upped_once = True
            logger.info(f"Игрок {player.id} повысил уровень до {player.level}! Остаток XP: {player.xp}.")

            rewards_for_level = level_up_rewards_rules.get(str(player.level), level_up_rewards_rules.get("default", {}))

            if isinstance(rewards_for_level, dict):
                player.unspent_xp += rewards_for_level.get("attribute_points", 0)
            else:
                logger.warning(f"Не найдены или некорректны награды за уровень {player.level} (или default) для guild_id={guild_id}. rewards_for_level: {rewards_for_level}")
                rewards_for_level = {}


            await game_events.log_event(
                session=session,
                guild_id=guild_id,
                event_type=EventType.LEVEL_UP.name, # Передаем имя Enum
                details_json={
                    "player_id": player.id,
                    "player_name": player.name,
                    "new_level": player.level,
                    "rewards_received": rewards_for_level,
                    "current_total_xp": player.xp,
                },
                entity_ids_json={"player_id": player.id}
            )
        else:
            break

    return level_upped_once


async def spend_attribute_points(
    session: AsyncSession,
    player: Player,
    attribute_name: str,
    points_to_spend: int,
    guild_id: int
) -> tuple[bool, str, dict]:
    """
    Позволяет игроку потратить unspent_xp на повышение атрибута.

    Args:
        session: SQLAlchemy AsyncSession.
        player: Объект Player.
        attribute_name: Имя атрибута для повышения (ключ из RuleConfig).
        points_to_spend: Количество очков для траты.
        guild_id: ID гильдии для загрузки правил.

    Returns:
        Кортеж (успех: bool, ключ_сообщения_для_локализации: str, детали_для_форматирования: dict).
    """
    if points_to_spend <= 0:
        return False, "levelup_error_invalid_points_value", {"points": points_to_spend}

    if player.unspent_xp < points_to_spend:
        return False, "levelup_error_not_enough_xp", {"unspent_xp": player.unspent_xp, "requested": points_to_spend}

    attribute_definitions = await rules.get_rule(session, guild_id, "character_attributes:definitions")
    if not isinstance(attribute_definitions, dict) or attribute_name not in attribute_definitions:
        return False, "levelup_error_invalid_attribute", {"attribute_name": attribute_name}

    # Предполагаем, что стоимость повышения = 1 очко за +1 к стату.
    # В будущем можно загружать стоимость из RuleConfig: character_attributes:cost_per_point
    cost_per_stat_point = 1
    total_cost = points_to_spend * cost_per_stat_point

    if player.unspent_xp < total_cost:
        # Эта проверка может быть избыточной, если cost_per_stat_point = 1, но полезна для будущего
        return False, "levelup_error_not_enough_xp_for_cost", {
            "unspent_xp": player.unspent_xp,
            "requested_stats": points_to_spend,
            "total_cost": total_cost,
            "attribute_name": attribute_name
        }

    # Обновляем атрибут игрока
    # Инициализируем player.attributes_json, если это None
    if player.attributes_json is None:
        player.attributes_json = {}

    current_attribute_value = player.attributes_json.get(attribute_name, 0)
    new_attribute_value = current_attribute_value + points_to_spend
    player.attributes_json[attribute_name] = new_attribute_value
    player.unspent_xp -= total_cost

    await game_events.log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.ATTRIBUTE_POINTS_SPENT.name,
        details_json={
            "player_id": player.id,
            "player_name": player.name,
            "attribute_changed": attribute_name,
            "points_spent": total_cost, # фактически потрачено unspent_xp
            "stat_increase": points_to_spend, # на сколько увеличился стат
            "old_value": current_attribute_value,
            "new_value": new_attribute_value,
            "remaining_unspent_xp": player.unspent_xp,
        },
        entity_ids_json={"player_id": player.id}
    )

    # Коммит сессии не делается здесь, он должен управляться вызывающей функцией (например, transactional декоратором команды)
    # await session.commit()
    # await session.refresh(player)


    localized_attribute_name = attribute_name # По умолчанию
    if isinstance(attribute_definitions[attribute_name], dict):
        attr_def = attribute_definitions[attribute_name]
        name_i18n = attr_def.get("name_i18n")
        if isinstance(name_i18n, dict):
            # Язык игрока нужно будет передать или получить здесь для полной локализации имени атрибута
            # Пока используем ключ атрибута или первый доступный язык
            localized_attribute_name = name_i18n.get(player.selected_language or "en", name_i18n.get("en", attribute_name))


    return True, "levelup_success", {
        "attribute_name": localized_attribute_name,
        "new_value": new_attribute_value,
        "remaining_xp": player.unspent_xp,
        "spent_points": total_cost
    }
