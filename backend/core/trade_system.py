# src/core/trade_system.py
import logging
from typing import Optional, List, Dict, Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Player, GeneratedNpc, Item, InventoryItem
from backend.models.enums import OwnerEntityType # EventType, RelationshipEntityType
from backend.core.crud.crud_player import player_crud
from backend.core.crud.crud_npc import npc_crud
from backend.core.crud.crud_item import item_crud
from backend.core.crud.crud_inventory_item import inventory_item_crud
# from ..rules import get_rule
# from ..relationship_system import update_relationship # Будет позже для изменения отношений
from backend.core.crud.crud_relationship import crud_relationship # Для чтения отношений
from .relationship_system import update_relationship # Task 36 - для изменения отношений
from backend.core.rules import get_rule
from backend.core.utils import log_event
from backend.core.database import transactional
from backend.core.localization_utils import get_localized_text
from backend.models.enums import RelationshipEntityType, EventType, OwnerEntityType # Corrected import


logger = logging.getLogger(__name__)


# Helper function to safely evaluate formulas from rules
# For now, this is a very basic placeholder.
# In a real scenario, use a safe evaluation library like asteval.
def _evaluate_formula(formula_str: str, context: Dict[str, Any]) -> float:
    for key, value in context.items():
        formula_str = formula_str.replace(f"@{key}@", str(value))
    try:
        # WARNING: eval is not safe with arbitrary strings.
        # This should be replaced with a safer evaluation method.
        return float(eval(formula_str, {"__builtins__": {}}, {}))
    except Exception as e:
        logger.error(f"Error evaluating formula '{formula_str}' with context {context}: {e}")
        return 1.0 # Default multiplier on error

class TradedItemInfo(BaseModel):
    item_static_id: Optional[str] = None
    item_db_id: int
    name_i18n: Dict[str, str] = Field(default_factory=dict)
    quantity: int
    price_per_unit: float
    total_price: float

class InventoryViewData(BaseModel):
    item_static_id: Optional[str] = None
    item_db_id: int
    name_i18n: Dict[str, str] = Field(default_factory=dict)
    description_i18n: Dict[str, str] = Field(default_factory=dict)
    quantity_available: int
    # Цена, по которой игрок может купить у NPC (т.е. цена продажи NPC)
    npc_sell_price_per_unit: Optional[float] = None
    # Цена, по которой игрок может продать NPC (т.е. цена покупки NPC)
    npc_buy_price_per_unit: Optional[float] = None


class TradeActionResult(BaseModel):
    success: bool
    message_key: str  # Ключ для локализованного сообщения
    message_params: Dict[str, Any] = Field(default_factory=dict)  # Параметры для форматирования сообщения
    action_type: Literal["view_inventory", "buy", "sell", "error"]

    player_gold_after_trade: Optional[int] = None
    # npc_gold_after_trade: Optional[int] = None # Если NPC отслеживает золото (пока не реализуем)

    item_traded: Optional[TradedItemInfo] = None # Общее поле для купленного/проданного предмета

    # Для action_type == "view_inventory"
    npc_inventory_display: Optional[List[InventoryViewData]] = None # Инвентарь NPC для покупки игроком
    player_inventory_display: Optional[List[InventoryViewData]] = None # Инвентарь игрока для продажи NPC

    error_details: Optional[str] = None  # Для отладки или специфических ошибок


async def _calculate_item_price(
    session: AsyncSession,
    guild_id: int,
    player: Player, # Передаем загруженного игрока
    npc: GeneratedNpc,   # Передаем загруженного NPC
    item: Item,
    transaction_type: Literal["buy", "sell"] # "buy" = player buys from npc, "sell" = player sells to npc
) -> float:
    """
    Calculates the price of an item for a specific transaction type, player, and NPC,
    considering base value, rules, skills, and relationships.
    """
    base_value = 0.0
    if item.base_value is not None:
        base_value = float(item.base_value)
    else:
        # Try to get base value from RuleConfig: economy:base_item_values:<item_category_or_type_key>
        # This part needs a defined way to get category/type key from item
        # For now, let's assume a fallback if item.base_value is missing
        item_category_key = get_localized_text(item.item_category_i18n, "en", "en").lower().replace(" ", "_") # Simple key example
        category_base_value_rule = await get_rule(
            session, guild_id, f"economy:base_item_values:{item_category_key}"
        )
        if category_base_value_rule and isinstance(category_base_value_rule, dict) and "value" in category_base_value_rule:
            base_value = float(category_base_value_rule["value"])
        else:
            base_value = 1.0 # Default base value if not found anywhere
            logger.warning(f"Item {item.id} (static: {item.static_id}) missing base_value and rule. Defaulting to {base_value}.")

    price = base_value
    price_multiplier = 1.0

    # 1. Trade Skill Modifier (economy:price_modifiers:trade_skill)
    trade_skill_rule = await get_rule(session, guild_id, "economy:price_modifiers:trade_skill")
    if trade_skill_rule and isinstance(trade_skill_rule, dict):
        skill_level = player.attributes_json.get("trade_skill", 0) # Assuming trade_skill is in attributes_json
        context = {"skill_level": skill_level}

        formula = None
        min_mult = None
        max_mult = None

        if transaction_type == "buy": # Player buys from NPC, NPC sells to player -> higher price for player
            formula = trade_skill_rule.get("buy_price_multiplier_formula")
            min_mult = trade_skill_rule.get("min_buy_multiplier") # e.g. 1.1 (player never buys below 110%)
        else: # Player sells to NPC, NPC buys from player -> lower price for player
            formula = trade_skill_rule.get("sell_price_multiplier_formula")
            max_mult = trade_skill_rule.get("max_sell_multiplier") # e.g. 0.9 (player never sells above 90%)

        if formula:
            skill_modifier = _evaluate_formula(formula, context)
            if min_mult is not None and transaction_type == "buy":
                skill_modifier = max(skill_modifier, float(min_mult))
            if max_mult is not None and transaction_type == "sell":
                skill_modifier = min(skill_modifier, float(max_mult))
            price_multiplier *= skill_modifier
            logger.debug(f"Trade skill modifier for player {player.id} (skill {skill_level}) on item {item.id} ({transaction_type}): {skill_modifier}")


    # 2. Relationship Modifier (relationship_influence:trade:price_adjustment)
    # This rule structure might be: {"base_buy_multiplier": 1.0, "base_sell_multiplier": 1.0, "relationship_tiers": [...]}
    # or a direct formula: {"buy_price_adjustment_formula": "1 - (relationship_value * 0.001)", "sell_price_adjustment_formula": "1 + (relationship_value * 0.001)"}
    relationship_trade_rule = await get_rule(session, guild_id, "relationship_influence:trade:price_adjustment")
    if relationship_trade_rule and isinstance(relationship_trade_rule, dict):
        relationship = await crud_relationship.get_relationship_between_entities(
            session=session,
            guild_id=guild_id,
            entity1_id=player.id,
            entity1_type=RelationshipEntityType.PLAYER,
            entity2_id=npc.id,
            entity2_type=RelationshipEntityType.GENERATED_NPC
        )
        relationship_value = relationship.value if relationship else 0

        # Example: tiers based modification (similar to faction_relationship but direct)
        # tiers: [{"relationship_above": 75, "buy_mod": -0.15, "sell_mod": 0.15}, ...]
        if "tiers" in relationship_trade_rule and isinstance(relationship_trade_rule["tiers"], list):
            tier_mod = 0.0
            # Iterate tiers from highest to lowest or use a default
            sorted_tiers = sorted(relationship_trade_rule["tiers"], key=lambda t: t.get("relationship_above", -float('inf')), reverse=True)
            applied_tier = False
            for tier in sorted_tiers:
                if relationship_value >= tier.get("relationship_above", -float('inf')):
                    if transaction_type == "buy":
                        tier_mod = float(tier.get("buy_multiplier_mod", 0.0)) # e.g. -0.1 means 10% cheaper for player
                    else: # sell
                        tier_mod = float(tier.get("sell_multiplier_mod", 0.0)) # e.g. +0.1 means 10% more for player
                    applied_tier = True
                    break
            if not applied_tier and "relationship_default" in relationship_trade_rule["tiers"]: # Check for a default tier
                 default_tier = next((t for t in relationship_trade_rule["tiers"] if t.get("relationship_default")), None)
                 if default_tier:
                    if transaction_type == "buy":
                        tier_mod = float(default_tier.get("buy_multiplier_mod", 0.0))
                    else: # sell
                        tier_mod = float(default_tier.get("sell_multiplier_mod", 0.0))

            relationship_modifier_val = 1.0 + tier_mod # if mod is -0.1, modifier is 0.9
            price_multiplier *= relationship_modifier_val
            logger.debug(f"Relationship tier modifier ({relationship_value}) for player {player.id} with NPC {npc.id} on item {item.id} ({transaction_type}): {relationship_modifier_val}")

        # Example: direct formula based modification
        elif "buy_price_adjustment_formula" in relationship_trade_rule and transaction_type == "buy":
            formula = relationship_trade_rule["buy_price_adjustment_formula"]
            rel_modifier = _evaluate_formula(formula, {"relationship_value": relationship_value})
            price_multiplier *= rel_modifier
            logger.debug(f"Relationship formula modifier ({relationship_value}) for player {player.id} with NPC {npc.id} on item {item.id} (buy): {rel_modifier}")
        elif "sell_price_adjustment_formula" in relationship_trade_rule and transaction_type == "sell":
            formula = relationship_trade_rule["sell_price_adjustment_formula"]
            rel_modifier = _evaluate_formula(formula, {"relationship_value": relationship_value})
            price_multiplier *= rel_modifier
            logger.debug(f"Relationship formula modifier ({relationship_value}) for player {player.id} with NPC {npc.id} on item {item.id} (sell): {rel_modifier}")

    # Apply the total multiplier
    price *= price_multiplier

    # Ensure price is not negative and has a minimum value (e.g., 1, or configurable)
    final_price = max(1.0, round(price, 2)) # Round to 2 decimal places, min price 1.0

    logger.info(f"Calculated price for item {item.id} (static: {item.static_id}) for player {player.id} with NPC {npc.id} ({transaction_type}): "
                f"Base={base_value}, Multiplier={price_multiplier:.4f}, Final={final_price}")

    return final_price


@transactional
async def handle_trade_action(
    session: AsyncSession,
    guild_id: int,
    player_id: int,
    target_npc_id: int,
    action_type: Literal["view_inventory", "buy", "sell"], # Уточнил Literal
    item_static_id: Optional[str] = None,
    item_db_id: Optional[int] = None, # ID из таблицы Items
    inventory_item_db_id: Optional[int] = None, # ID конкретного InventoryItem (для продажи игроком)
    count: Optional[int] = None,
) -> TradeActionResult:
    """
    Handles trading actions between a player and an NPC.
    - view_inventory: Shows NPC items for player to buy, and player items for player to sell.
    - buy: Player buys an item from NPC. Requires item_static_id (or item_db_id of the base Item) and count.
    - sell: Player sells an item to NPC. Requires inventory_item_db_id (ID of the stack in player's inventory) and count.
    """
    logger.info(
        f"Handling trade action: guild={guild_id}, player={player_id}, npc={target_npc_id}, "
        f"action={action_type}, item_static_id={item_static_id}, item_db_id={item_db_id}, "
        f"inventory_item_db_id={inventory_item_db_id}, count={count}"
    )

    # TODO: Implement actual logic based on the plan
    # 1. Load player and NPC
    # 2. Check if NPC is a trader
    # 3. Implement "view_inventory"
    # 4. Implement price calculation helper
    # 5. Implement "buy" logic
    # 6. Implement "sell" logic
    # 7. Integrate relationship updates
    # 8. Handle errors and feedback

    player = await player_crud.get_by_id_and_guild(session=session, id=player_id, guild_id=guild_id)
    if not player:
        return TradeActionResult(
            success=False,
            message_key="trade_error_player_not_found",
            action_type="error",
            error_details=f"Player with ID {player_id} not found in guild {guild_id}.",
            message_params={"player_id": player_id}
        )

    npc = await npc_crud.get_by_id_and_guild(session=session, id=target_npc_id, guild_id=guild_id)
    if not npc:
        return TradeActionResult(
            success=False,
            message_key="trade_error_npc_not_found",
            action_type="error",
            error_details=f"NPC with ID {target_npc_id} not found in guild {guild_id}.",
            message_params={"npc_id": target_npc_id}
        )

    # player_name_loc извлекается здесь для использования в сообщениях об ошибках и успехах
    # Player model has player.name (str), not player.name_i18n.
    # For localization, player.name would be the primary identifier or the 'en' version.
    player_name_loc = player.name # Use player.name directly as it's a simple string.
                                 # Localization logic would apply if player.name were a key.

    npc_name_loc = get_localized_text(npc.name_i18n, player.selected_language or "en") or f"NPC {npc.id}"

    # Check if NPC is a trader
    is_trader_by_type = False
    if npc.npc_type_i18n:
        for lang_code, type_name in npc.npc_type_i18n.items():
            if type_name and type_name.lower().strip() in ["merchant", "trader", "торговец", "продавец", "лавочник"]:
                is_trader_by_type = True
                break

    is_trader_by_property = npc.properties_json.get("is_trader", False) if npc.properties_json else False

    if not (is_trader_by_type or is_trader_by_property):
        return TradeActionResult(
            success=False,
            message_key="trade_error_npc_not_trader",
            action_type="error",
            error_details=f"NPC {target_npc_id} ({npc_name_loc}) is not a trader.",
            message_params={"npc_name": npc_name_loc}
        )

    # Action-specific logic
    if action_type == "view_inventory":
        logger.info(f"Trade action 'view_inventory': player {player.id} with NPC {npc.id} in guild {guild_id}.")
        npc_inventory_display_list: List[InventoryViewData] = []
        player_inventory_display_list: List[InventoryViewData] = []

        # Get NPC inventory (items player can buy)
        npc_raw_inv_items = await inventory_item_crud.get_inventory_for_owner(
            session=session, guild_id=guild_id, owner_entity_id=npc.id, owner_entity_type=OwnerEntityType.GENERATED_NPC
        )
        logger.debug(f"NPC {npc.id} raw inventory items count: {len(npc_raw_inv_items)}")
        for inv_item_instance in npc_raw_inv_items:
            base_item_model = inv_item_instance.item # Assumes item is loaded via relationship
            if not base_item_model: # Should not happen with proper relationship loading
                logger.warning(f"InventoryItem {inv_item_instance.id} for NPC {npc.id} is missing its base Item. Skipping.")
                continue

            price_for_player_to_buy = await _calculate_item_price(
                session=session, guild_id=guild_id, player=player, npc=npc, item=base_item_model, transaction_type="buy"
            )
            npc_inventory_display_list.append(
                InventoryViewData(
                    item_static_id=base_item_model.static_id,
                    item_db_id=base_item_model.id, # ID of the base Item
                    name_i18n=base_item_model.name_i18n,
                    description_i18n=base_item_model.description_i18n,
                    quantity_available=inv_item_instance.quantity,
                    npc_sell_price_per_unit=price_for_player_to_buy, # Price for player to buy from NPC
                    npc_buy_price_per_unit=None # Not applicable for NPC's items view
                )
            )
        logger.debug(f"Processed {len(npc_inventory_display_list)} items for NPC inventory display.")

        # Get Player inventory (items player can sell to NPC)
        player_raw_inv_items = await inventory_item_crud.get_inventory_for_owner(
            session=session, guild_id=guild_id, owner_entity_id=player.id, owner_entity_type=OwnerEntityType.PLAYER
        )
        logger.debug(f"Player {player.id} raw inventory items count: {len(player_raw_inv_items)}")
        for inv_item_instance in player_raw_inv_items:
            base_item_model = inv_item_instance.item
            if not base_item_model:
                logger.warning(f"InventoryItem {inv_item_instance.id} for Player {player.id} is missing its base Item. Skipping.")
                continue

            price_for_player_to_sell = await _calculate_item_price(
                session=session, guild_id=guild_id, player=player, npc=npc, item=base_item_model, transaction_type="sell"
            )
            player_inventory_display_list.append(
                InventoryViewData(
                    item_static_id=base_item_model.static_id,
                    item_db_id=base_item_model.id, # ID of the base Item
                    name_i18n=base_item_model.name_i18n,
                    description_i18n=base_item_model.description_i18n,
                    quantity_available=inv_item_instance.quantity,
                    npc_sell_price_per_unit=None, # Not applicable for player's items view
                    npc_buy_price_per_unit=price_for_player_to_sell # Price for player to sell to NPC
                )
            )
        logger.debug(f"Processed {len(player_inventory_display_list)} items for player inventory display.")

        # Log the view event
        await log_event(
            session,
            guild_id=guild_id,
            event_type=EventType.TRADE_INITIATED.value, # Or a more specific "VIEW_INVENTORY" if added
            details_json={
                "player_id": player.id,
                "npc_id": npc.id,
                "player_name": player_name_loc,
                "npc_name": npc_name_loc,
                "action": "view_inventory"
            },
            player_id=player.id,
            entity_ids_json={"players": [player.id], "generated_npcs": [npc.id]}
        )

        return TradeActionResult(
            success=True,
            message_key="trade_view_inventory_success",
            action_type="view_inventory",
            npc_inventory_display=npc_inventory_display_list,
            player_inventory_display=player_inventory_display_list,
            player_gold_after_trade=player.gold, # Current gold of the player
            message_params={
                "player_name": player_name_loc,
                "npc_name": npc_name_loc,
                "player_gold": player.gold
            }
        )
    elif action_type == "buy":
        if not (item_static_id or item_db_id) or not count or count <= 0:
            return TradeActionResult(
                success=False,
                message_key="trade_error_buy_invalid_params",
                action_type="error",
                error_details="Missing item identifier or invalid count for buying.",
                message_params={"count": count or 0}
            )

        target_item_model: Optional[Item] = None
        # Предпочтение static_id для покупки у NPC, так как это обычно шаблонный предмет
        if item_static_id:
            target_item_model = await item_crud.get_by_static_id(session, guild_id=guild_id, static_id=item_static_id)
        elif item_db_id: # item_db_id здесь относится к ID из таблицы Item (базовый предмет)
            target_item_model = await item_crud.get(session, id=item_db_id, guild_id=guild_id)

        if not target_item_model:
            return TradeActionResult(
                success=False,
                message_key="trade_error_item_not_found_in_system",
                action_type="error",
                error_details=f"Item with static_id '{item_static_id}' or db_id '{item_db_id}' not found.",
                message_params={"item_identifier": item_static_id or (str(item_db_id) if item_db_id else "N/A")}
            )

        item_name_loc = get_localized_text(target_item_model.name_i18n, player.selected_language or "en") or f"Item {target_item_model.id}"

        # Find item stack in NPC's inventory
        npc_inv_stacks = await inventory_item_crud.get_inventory_for_owner(
            session, guild_id=guild_id, owner_entity_id=npc.id, owner_entity_type=OwnerEntityType.GENERATED_NPC
        )
        npc_item_stack_to_buy: Optional[InventoryItem] = None
        for stack in npc_inv_stacks:
            if stack.item_id == target_item_model.id: # Сравниваем ID базового предмета
                npc_item_stack_to_buy = stack
                break

        if not npc_item_stack_to_buy:
            return TradeActionResult(
                success=False,
                message_key="trade_error_npc_does_not_have_item",
                action_type="error",
                message_params={"npc_name": npc_name_loc, "item_name": item_name_loc}
            )

        if npc_item_stack_to_buy.quantity < count:
            return TradeActionResult(
                success=False,
                message_key="trade_error_npc_not_enough_items",
                action_type="error",
                message_params={
                    "npc_name": npc_name_loc,
                    "item_name": item_name_loc,
                    "requested_count": count,
                    "available_count": npc_item_stack_to_buy.quantity
                }
            )

        price_per_unit = await _calculate_item_price(
            session, guild_id=guild_id, player=player, npc=npc, item=target_item_model, transaction_type="buy"
        )
        total_cost = price_per_unit * count

        if player.gold < total_cost:
            return TradeActionResult(
                success=False,
                message_key="trade_error_player_not_enough_gold",
                action_type="error",
                message_params={
                    "item_name": item_name_loc,
                    "total_cost": f"{total_cost:.2f}",
                    "player_gold": player.gold
                }
            )

        # Perform transaction (already under @transactional)
        player.gold -= int(round(total_cost))

        # Уменьшаем количество у NPC
        await inventory_item_crud.remove_item_from_owner(
            session,
            guild_id=guild_id,
            owner_entity_id=npc.id,
            owner_entity_type=OwnerEntityType.GENERATED_NPC,
            item_id=target_item_model.id,
            quantity=count
        )
        # Добавляем предмет игроку
        await inventory_item_crud.add_item_to_owner(
            session,
            guild_id=guild_id,
            owner_entity_id=player.id,
            owner_entity_type=OwnerEntityType.PLAYER,
            item_id=target_item_model.id,
            quantity=count,
            instance_specific_properties_json=npc_item_stack_to_buy.instance_specific_properties_json # Передаем свойства от NPC
        )

        await session.flush()
        await session.refresh(player)


        # Log event
        log_details = {
            "player_id": player.id,
            "npc_id": npc.id,
            "item_static_id": target_item_model.static_id,
            "item_db_id": target_item_model.id,
            "item_name_i18n": target_item_model.name_i18n,
            "quantity": count,
            "price_per_unit": price_per_unit,
            "total_cost": total_cost,
            "player_gold_before": player.gold + int(round(total_cost)),
            "player_gold_after": player.gold
        }
        logged_event = await log_event(
            session,
            guild_id=guild_id,
            event_type=EventType.TRADE_ITEM_BOUGHT.value,
            details_json=log_details,
            player_id=player.id,
            entity_ids_json={"players": [player.id], "generated_npcs": [npc.id], "items": [target_item_model.id]}
        )

        # Update relationships
        if logged_event and logged_event.id:
            await update_relationship(
                session=session,
                guild_id=guild_id,
                entity_doing_id=player.id,
                entity_doing_type=RelationshipEntityType.PLAYER,
                target_entity_id=npc.id,
                target_entity_type=RelationshipEntityType.GENERATED_NPC,
                event_type="TRADE_ITEM_BOUGHT",
                event_details_log_id=logged_event.id
            )
        else:
            logger.warning(f"Could not log TRADE_ITEM_BOUGHT event for player {player.id}, NPC {npc.id}. Skipping relationship update.")


        traded_item_info = TradedItemInfo(
            item_static_id=target_item_model.static_id,
            item_db_id=target_item_model.id,
            name_i18n=target_item_model.name_i18n,
            quantity=count,
            price_per_unit=price_per_unit,
            total_price=total_cost
        )

        return TradeActionResult(
            success=True,
            message_key="trade_buy_success",
            action_type="buy",
            player_gold_after_trade=player.gold,
            item_traded=traded_item_info,
            message_params={
                "item_name": item_name_loc,
                "count": count,
                "total_cost": f"{total_cost:.2f}",
                "npc_name": npc_name_loc,
                "player_gold": player.gold
            }
        )

    elif action_type == "sell":
        if not inventory_item_db_id or not count or count <= 0: # inventory_item_db_id - это ID из InventoryItem
            return TradeActionResult(
                success=False,
                message_key="trade_error_sell_invalid_params",
                action_type="error",
                error_details="Missing inventory item ID or invalid count for selling.",
                 message_params={"inventory_item_id": inventory_item_db_id or 0, "count": count or 0}
            )

        # Get the specific stack from player's inventory by its own ID
        player_item_stack = await inventory_item_crud.get(session, id=inventory_item_db_id)

        if not player_item_stack or \
           player_item_stack.guild_id != guild_id or \
           player_item_stack.owner_entity_id != player.id or \
           player_item_stack.owner_entity_type != OwnerEntityType.PLAYER:
            return TradeActionResult(
                success=False,
                message_key="trade_error_player_does_not_own_item_stack", # Ключ для "игрок не владеет этим стаком"
                action_type="error",
                message_params={"inventory_item_id": inventory_item_db_id}
            )

        # Ensure the base item is loaded. The relationship InventoryItem.item should ideally be eager/joined loaded.
        base_item: Item
        if not player_item_stack.item:
            # This explicit load is a fallback if relationship wasn't loaded.
            loaded_base_item = await item_crud.get(session, id=player_item_stack.item_id, guild_id=guild_id)
            if not loaded_base_item:
                 # This indicates a data integrity issue if an InventoryItem points to a non-existent Item
                 logger.error(f"Data integrity issue: InventoryItem {player_item_stack.id} points to non-existent Item {player_item_stack.item_id}")
                 return TradeActionResult(success=False, message_key="trade_error_base_item_not_found", action_type="error", message_params={"item_id": player_item_stack.item_id})
            base_item = loaded_base_item
            # player_item_stack.item = base_item # No need to assign back if only reading from base_item
        else:
            base_item = player_item_stack.item

        item_name_loc = get_localized_text(base_item.name_i18n, player.selected_language or "en") or f"Item {base_item.id}"

        if player_item_stack.quantity < count:
            return TradeActionResult(
                success=False,
                message_key="trade_error_player_not_enough_items_to_sell",
                action_type="error",
                message_params={
                    "item_name": item_name_loc,
                    "requested_count": count,
                    "available_count": player_item_stack.quantity
                }
            )

        price_per_unit = await _calculate_item_price(
            session, guild_id=guild_id, player=player, npc=npc, item=base_item, transaction_type="sell"
        )
        total_revenue = price_per_unit * count

        # Perform transaction
        player.gold += int(round(total_revenue))

        # Уменьшаем количество у игрока
        # remove_item_from_owner в crud_inventory_item использует item_id (ID базового Item).
        # Это корректно, т.к. у игрока может быть только один InventoryItem для данного item_id из-за unique constraint.
        await inventory_item_crud.remove_item_from_owner(
            session,
            guild_id=guild_id,
            owner_entity_id=player.id,
            owner_entity_type=OwnerEntityType.PLAYER,
            item_id=base_item.id,
            quantity=count
        )
        # Добавляем предмет NPC
        await inventory_item_crud.add_item_to_owner(
            session,
            guild_id=guild_id,
            owner_entity_id=npc.id,
            owner_entity_type=OwnerEntityType.GENERATED_NPC,
            item_id=base_item.id,
            quantity=count,
            instance_specific_properties_json=player_item_stack.instance_specific_properties_json # Передаем свойства от игрока
        )

        await session.flush()
        await session.refresh(player)

        # Log event
        log_details = {
            "player_id": player.id,
            "npc_id": npc.id,
            "item_static_id": base_item.static_id,
            "item_db_id": base_item.id,
            "item_name_i18n": base_item.name_i18n, # Для полноты
            "quantity": count,
            "price_per_unit": price_per_unit,
            "total_revenue": total_revenue,
            "player_gold_before": player.gold - int(round(total_revenue)),
            "player_gold_after": player.gold
        }
        logged_event = await log_event(
            session,
            guild_id=guild_id,
            event_type=EventType.TRADE_ITEM_SOLD.value,
            details_json=log_details,
            player_id=player.id,
            entity_ids_json={"players": [player.id], "generated_npcs": [npc.id], "items": [base_item.id]}
        )

        # Update relationships
        if logged_event and logged_event.id:
            await update_relationship(
                session=session,
                guild_id=guild_id,
                entity_doing_id=player.id,
                entity_doing_type=RelationshipEntityType.PLAYER,
                target_entity_id=npc.id,
                target_entity_type=RelationshipEntityType.GENERATED_NPC,
                event_type="TRADE_ITEM_SOLD",
                event_details_log_id=logged_event.id
            )
        else:
            logger.warning(f"Could not log TRADE_ITEM_SOLD event for player {player.id}, NPC {npc.id}. Skipping relationship update.")


        traded_item_info = TradedItemInfo(
            item_static_id=base_item.static_id,
            item_db_id=base_item.id,
            name_i18n=base_item.name_i18n,
            quantity=count,
            price_per_unit=price_per_unit,
            total_price=total_revenue
        )

        return TradeActionResult(
            success=True,
            message_key="trade_sell_success",
            action_type="sell",
            player_gold_after_trade=player.gold,
            item_traded=traded_item_info, # Используем общее поле
            message_params={
                "item_name": item_name_loc,
                "count": count,
                "total_revenue": f"{total_revenue:.2f}", # Форматируем
                "npc_name": npc_name_loc,
                "player_gold": player.gold
            }
        )

    return TradeActionResult(
        success=False,
        message_key="trade_error_unknown_action_type",
        action_type="error",
        error_details=f"Unknown action type: {action_type}"
    )

logger.info("Trade system module (trade_system.py) structure created.")
