import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call # Added call
from typing import Optional, List, Dict, Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.trade_system import (
    handle_trade_action,
    _calculate_item_price,
    TradeActionResult,
    TradedItemInfo,
    InventoryViewData,
    _evaluate_formula # Import for direct testing if needed, or assume it works via _calculate_item_price
)
from backend.models import Player, GeneratedNpc, Item, InventoryItem, Relationship, RuleConfig
from backend.models.enums import OwnerEntityType, RelationshipEntityType, EventType

# Mock data structure for an Item
def mock_item_data(id: int, static_id: str, name_en: str, base_value: Optional[int], category_en: Optional[str] = "misc") -> Dict[str, Any]:
    return {
        "id": id,
        "static_id": static_id,
        "name_i18n": {"en": name_en, "ru": f"{name_en}_ru"},
        "description_i18n": {"en": f"Desc {name_en}", "ru": f"Desc {name_en}_ru"},
        "base_value": base_value,
        "item_category_i18n": {"en": category_en, "ru": f"{category_en}_ru"} if category_en else {},
        "is_stackable": True,
        # Add other fields if _calculate_item_price or other logic depends on them
    }

# Mock data for InventoryItem
def mock_inventory_item_data(id: int, item_model: Item, quantity: int, owner_id: int, owner_type: OwnerEntityType, guild_id: int = 1) -> Dict[str, Any]:
    return {
        "id": id,
        "item_id": item_model.id,
        "item": item_model, # Nested Item model
        "quantity": quantity,
        "owner_entity_id": owner_id,
        "owner_entity_type": owner_type,
        "guild_id": guild_id,
        "instance_specific_properties_json": {}
    }

class TestTradeSystem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1
        self.player_id = 10
        self.npc_id = 20

        # Mock Player
        self.mock_player = Player(
            id=self.player_id,
            guild_id=self.guild_id,
            name="TestPlayer",
            gold=1000,
            attributes_json={"trade_skill": 5}, # Example trade skill
            selected_language="en"
        )
        # Mock NPC
        self.mock_npc = GeneratedNpc(
            id=self.npc_id,
            guild_id=self.guild_id,
            name_i18n={"en": "TestTrader", "ru": "ТестТорговец"},
            npc_type_i18n={"en": "Merchant"}, # Mark as trader
            properties_json={"is_trader": True}
        )

        # Mock Items
        self.item_sword = Item(**mock_item_data(id=1, static_id="common_sword", name_en="Sword", base_value=50, category_en="weapon"))
        self.item_potion = Item(**mock_item_data(id=2, static_id="healing_potion", name_en="Potion", base_value=10, category_en="consumable"))
        self.item_gem_no_base_value = Item(**mock_item_data(id=3, static_id="ruby_gem", name_en="Ruby", base_value=None, category_en="gem"))


        # --- Patches ---
        self.patch_player_crud = patch('backend.core.trade_system.player_crud', AsyncMock())
        self.mock_player_crud = self.patch_player_crud.start()
        self.mock_player_crud.get_by_id_and_guild.return_value = self.mock_player

        self.patch_npc_crud = patch('backend.core.trade_system.npc_crud', AsyncMock())
        self.mock_npc_crud = self.patch_npc_crud.start()
        self.mock_npc_crud.get_by_id_and_guild.return_value = self.mock_npc

        self.patch_item_crud = patch('backend.core.trade_system.item_crud', AsyncMock())
        self.mock_item_crud = self.patch_item_crud.start()
        # Setup item_crud.get and get_by_static_id to return our mock items
        item_map = {self.item_sword.id: self.item_sword, self.item_potion.id: self.item_potion, self.item_gem_no_base_value.id: self.item_gem_no_base_value}
        static_item_map = {i.static_id: i for i in item_map.values() if i.static_id}

        async def mock_item_get(session, id, guild_id):
            return item_map.get(id)
        async def mock_item_get_by_static_id(session, guild_id, static_id):
            return static_item_map.get(static_id)

        self.mock_item_crud.get = AsyncMock(side_effect=mock_item_get)
        self.mock_item_crud.get_by_static_id = AsyncMock(side_effect=mock_item_get_by_static_id)


        self.patch_inventory_item_crud = patch('backend.core.trade_system.inventory_item_crud', AsyncMock())
        self.mock_inventory_item_crud = self.patch_inventory_item_crud.start()
        # Mock methods for inventory_item_crud as needed by tests, e.g., get_inventory_for_owner, add_item_to_owner, remove_item_from_owner
        self.mock_inventory_item_crud.get_inventory_for_owner.return_value = [] # Default empty
        self.mock_inventory_item_crud.add_item_to_owner = AsyncMock(return_value=MagicMock(spec=InventoryItem))
        self.mock_inventory_item_crud.remove_item_from_owner = AsyncMock(return_value=None) # Or returns updated item
        self.mock_inventory_item_crud.get = AsyncMock(return_value=None) # For fetching specific InventoryItem by ID

        self.patch_get_rule = patch('backend.core.trade_system.get_rule', AsyncMock())
        self.mock_get_rule = self.patch_get_rule.start()
        self.mock_get_rule.return_value = None # Default no rule

        self.patch_crud_relationship = patch('backend.core.trade_system.crud_relationship', AsyncMock())
        self.mock_crud_relationship = self.patch_crud_relationship.start()
        self.mock_crud_relationship.get_relationship_between_entities.return_value = None # Default no relationship

        self.patch_log_event = patch('backend.core.trade_system.log_event', AsyncMock())
        self.mock_log_event = self.patch_log_event.start()
        self.mock_log_event.return_value = MagicMock(id=12345) # Mocked StoryLog entry with an ID

        self.patch_update_relationship = patch('backend.core.trade_system.update_relationship', AsyncMock())
        self.mock_update_relationship = self.patch_update_relationship.start()

        self.patch_evaluate_formula = patch('backend.core.trade_system._evaluate_formula', MagicMock())
        self.mock_evaluate_formula = self.patch_evaluate_formula.start()
        self.mock_evaluate_formula.return_value = 1.0 # Default no modification from formula

    async def asyncTearDown(self):
        self.patch_player_crud.stop()
        self.patch_npc_crud.stop()
        self.patch_item_crud.stop()
        self.patch_inventory_item_crud.stop()
        self.patch_get_rule.stop()
        self.patch_crud_relationship.stop()
        self.patch_log_event.stop()
        self.patch_update_relationship.stop()
        self.patch_evaluate_formula.stop()

    # --- Tests for _calculate_item_price ---

    async def test_calculate_price_base_value_only(self):
        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_sword, "buy")
        self.assertEqual(price, 50.0) # Base value of sword
        price_sell = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_sword, "sell")
        self.assertEqual(price_sell, 50.0) # Base value, multiplier is 1.0 by default from _evaluate_formula mock

    async def test_calculate_price_item_no_base_value_uses_rule_or_default(self):
        # Scenario 1: Rule exists for category
        self.mock_get_rule.side_effect = lambda session, guild_id, key: {"value": 200.0} if key == "economy:base_item_values:gem" else None
        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_gem_no_base_value, "buy")
        self.assertEqual(price, 200.0)

        # Scenario 2: No rule, should use default 1.0
        self.mock_get_rule.side_effect = None # Reset side_effect
        self.mock_get_rule.return_value = None
        price_default = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_gem_no_base_value, "buy")
        self.assertEqual(price_default, 1.0)

    async def test_calculate_price_trade_skill_modifier_buy(self):
        self.mock_player.attributes_json = {"trade_skill": 10}
        trade_skill_rule = {
            "buy_price_multiplier_formula": "1.5 - (@skill_level@ * 0.02)", # 1.5 - 0.2 = 1.3
            "min_buy_multiplier": 1.1
        }
        self.mock_get_rule.side_effect = lambda session, guild_id, key: trade_skill_rule if key == "economy:price_modifiers:trade_skill" else None
        self.mock_evaluate_formula.side_effect = lambda formula_str, context: 1.5 - (context["skill_level"] * 0.02)

        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_sword, "buy")
        self.assertAlmostEqual(price, 50.0 * 1.3) # 65.0

    async def test_calculate_price_trade_skill_modifier_sell(self):
        self.mock_player.attributes_json = {"trade_skill": 10}
        trade_skill_rule = {
            "sell_price_multiplier_formula": "0.5 + (@skill_level@ * 0.02)", # 0.5 + 0.2 = 0.7
            "max_sell_multiplier": 0.9
        }
        self.mock_get_rule.side_effect = lambda session, guild_id, key: trade_skill_rule if key == "economy:price_modifiers:trade_skill" else None
        self.mock_evaluate_formula.side_effect = lambda formula_str, context: 0.5 + (context["skill_level"] * 0.02)

        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_sword, "sell")
        self.assertAlmostEqual(price, 50.0 * 0.7) # 35.0

    async def test_calculate_price_relationship_modifier_tiers_buy(self):
        mock_relationship = Relationship(value=80) # Friendly
        self.mock_crud_relationship.get_relationship_between_entities.return_value = mock_relationship

        relationship_trade_rule = {
            "tiers": [
                {"relationship_above": 75, "buy_multiplier_mod": -0.10}, # 10% cheaper for player
                {"relationship_above": 0, "buy_multiplier_mod": 0.0},
            ]
        }
        self.mock_get_rule.side_effect = lambda session, guild_id, key: relationship_trade_rule if key == "relationship_influence:trade:price_adjustment" else None

        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_sword, "buy")
        self.assertAlmostEqual(price, 50.0 * 0.9) # 45.0

    async def test_calculate_price_relationship_modifier_formula_sell(self):
        mock_relationship = Relationship(value=-50) # Unfriendly
        self.mock_crud_relationship.get_relationship_between_entities.return_value = mock_relationship

        relationship_trade_rule = {
             "sell_price_adjustment_formula": "1.0 + (@relationship_value@ * 0.001)" # 1.0 + (-50 * 0.001) = 1.0 - 0.05 = 0.95
        }
        self.mock_get_rule.side_effect = lambda session, guild_id, key: relationship_trade_rule if key == "relationship_influence:trade:price_adjustment" else None
        self.mock_evaluate_formula.side_effect = lambda formula_str, context: 1.0 + (context["relationship_value"] * 0.001)

        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_sword, "sell")
        self.assertAlmostEqual(price, 50.0 * 0.95) # 47.5

    async def test_calculate_price_relationship_modifier_tiers_sell_high_relation(self):
        mock_relationship = Relationship(value=80) # Friendly
        self.mock_crud_relationship.get_relationship_between_entities.return_value = mock_relationship
        relationship_trade_rule = {
            "tiers": [
                {"relationship_above": 75, "sell_multiplier_mod": 0.15}, # Player sells for 15% more
                {"relationship_above": 0, "sell_multiplier_mod": 0.0},
            ]
        }
        self.mock_get_rule.side_effect = lambda session, guild_id, key: relationship_trade_rule if key == "relationship_influence:trade:price_adjustment" else None
        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_sword, "sell")
        self.assertAlmostEqual(price, 50.0 * 1.15) # 57.5

    async def test_calculate_price_relationship_modifier_tiers_neutral_no_default(self):
        mock_relationship = Relationship(value=10) # Neutral-ish
        self.mock_crud_relationship.get_relationship_between_entities.return_value = mock_relationship
        relationship_trade_rule = {
            "tiers": [ # No tier for 10, and no default
                {"relationship_above": 75, "buy_multiplier_mod": -0.10},
                {"relationship_above": 25, "buy_multiplier_mod": -0.05},
            ]
        }
        self.mock_get_rule.side_effect = lambda session, guild_id, key: relationship_trade_rule if key == "relationship_influence:trade:price_adjustment" else None
        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_sword, "buy")
        self.assertAlmostEqual(price, 50.0) # Should be base price as no relationship modifier applies

    async def test_calculate_price_relationship_modifier_tiers_use_default_tier(self):
        mock_relationship = Relationship(value=-10) # Negative, but no specific tier for it
        self.mock_crud_relationship.get_relationship_between_entities.return_value = mock_relationship
        relationship_trade_rule = {
            "tiers": [
                {"relationship_above": 75, "buy_multiplier_mod": -0.10},
                {"relationship_default": True, "buy_multiplier_mod": 0.05}, # Default makes it 5% more expensive
            ]
        }
        self.mock_get_rule.side_effect = lambda session, guild_id, key: relationship_trade_rule if key == "relationship_influence:trade:price_adjustment" else None
        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_sword, "buy")
        self.assertAlmostEqual(price, 50.0 * 1.05) # 52.5

    async def test_calculate_price_no_relationship_rule_defined(self):
        self.mock_crud_relationship.get_relationship_between_entities.return_value = Relationship(value=100)
        self.mock_get_rule.side_effect = lambda session, guild_id, key: None # No rule for relationship_influence:trade:price_adjustment
        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_sword, "buy")
        self.assertAlmostEqual(price, 50.0) # Should be base price

    async def test_calculate_price_relationship_rule_invalid_structure(self):
        self.mock_crud_relationship.get_relationship_between_entities.return_value = Relationship(value=100)
        # Rule exists but is malformed (e.g., not a dict, or missing 'tiers' and formulas)
        self.mock_get_rule.side_effect = lambda session, guild_id, key: {"bad_structure": True} if key == "relationship_influence:trade:price_adjustment" else None
        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_sword, "buy")
        self.assertAlmostEqual(price, 50.0) # Should default to base price without erroring out, multiplier remains 1.0

    async def test_calculate_price_relationship_modifier_formula_buy_positive_relation(self):
        mock_relationship = Relationship(value=50) # Positive relationship
        self.mock_crud_relationship.get_relationship_between_entities.return_value = mock_relationship
        relationship_trade_rule = {
             "buy_price_adjustment_formula": "1.0 - (@relationship_value@ * 0.002)" # 1.0 - (50 * 0.002) = 1.0 - 0.1 = 0.9
        }
        self.mock_get_rule.side_effect = lambda session, guild_id, key: relationship_trade_rule if key == "relationship_influence:trade:price_adjustment" else None
        self.mock_evaluate_formula.side_effect = lambda formula_str, context: 1.0 - (context["relationship_value"] * 0.002)
        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, self.item_sword, "buy")
        self.assertAlmostEqual(price, 50.0 * 0.9) # 45.0

    async def test_calculate_price_min_price_applied(self):
        very_cheap_item = Item(**mock_item_data(id=100, static_id="dirt_pile", name_en="Dirt", base_value=1))
        # Make multipliers very low
        self.mock_evaluate_formula.return_value = 0.01 # This will result in 1 * 0.01 = 0.01, so min price 1.0 should apply
        price = await _calculate_item_price(self.mock_session, self.guild_id, self.mock_player, self.mock_npc, very_cheap_item, "sell")
        self.assertEqual(price, 1.0) # Min price is 1.0

    # --- Tests for handle_trade_action ---

    # VIEW INVENTORY
    async def test_view_inventory_success(self):
        # Setup NPC inventory
        npc_inv_item1 = InventoryItem(**mock_inventory_item_data(id=101, item_model=self.item_sword, quantity=2, owner_id=self.npc_id, owner_type=OwnerEntityType.GENERATED_NPC))
        self.mock_inventory_item_crud.get_inventory_for_owner.side_effect = [
            [npc_inv_item1], # NPC's inventory
            []               # Player's inventory (empty for this test of viewing NPC)
        ]
        # Mock price calculation for this test - assume _calculate_item_price is tested separately
        # For view_inventory, _calculate_item_price is called for NPC items (buy for player) and Player items (sell for player)
        with patch('backend.core.trade_system._calculate_item_price', new_callable=AsyncMock) as mock_calc_price:
            mock_calc_price.side_effect = [60.0] # Price for sword (player buys from NPC)

            result = await handle_trade_action(self.mock_session, self.guild_id, self.player_id, self.npc_id, "view_inventory")

            self.assertTrue(result.success)
            self.assertEqual(result.action_type, "view_inventory")
            self.assertEqual(result.message_key, "trade_view_inventory_success")

            self.assertIsNotNone(result.npc_inventory_display)
            assert result.npc_inventory_display is not None # For pyright
            self.assertEqual(len(result.npc_inventory_display), 1)
            self.assertEqual(result.npc_inventory_display[0].item_db_id, self.item_sword.id)
            self.assertEqual(result.npc_inventory_display[0].quantity_available, 2)
            self.assertEqual(result.npc_inventory_display[0].npc_sell_price_per_unit, 60.0) # Player buys at 60

            self.assertIsNotNone(result.player_inventory_display)
            assert result.player_inventory_display is not None # For pyright
            self.assertEqual(len(result.player_inventory_display), 0)

            mock_calc_price.assert_called_once_with(
                session=self.mock_session, guild_id=self.guild_id, player=self.mock_player, npc=self.mock_npc, item=self.item_sword, transaction_type="buy"
            )

    async def test_view_inventory_npc_not_trader(self):
        self.mock_npc.npc_type_i18n = {"en": "Guard"} # Not a merchant
        self.mock_npc.properties_json = {"is_trader": False}
        result = await handle_trade_action(self.mock_session, self.guild_id, self.player_id, self.npc_id, "view_inventory")
        self.assertFalse(result.success)
        self.assertEqual(result.message_key, "trade_error_npc_not_trader")

    # BUY ACTION
    async def test_buy_item_success(self):
        self.mock_player.gold = 200
        npc_sword_stack = InventoryItem(**mock_inventory_item_data(id=101, item_model=self.item_sword, quantity=5, owner_id=self.npc_id, owner_type=OwnerEntityType.GENERATED_NPC))
        self.mock_inventory_item_crud.get_inventory_for_owner.return_value = [npc_sword_stack] # NPC has swords

        with patch('backend.core.trade_system._calculate_item_price', AsyncMock(return_value=60.0)) as mock_calc_price: # Player buys sword at 60
            result = await handle_trade_action(
                self.mock_session, self.guild_id, self.player_id, self.npc_id,
                action_type="buy", item_static_id=self.item_sword.static_id, count=2
            )

        self.assertTrue(result.success)
        self.assertEqual(result.message_key, "trade_buy_success")
        self.assertEqual(self.mock_player.gold, 200 - (60 * 2)) # 200 - 120 = 80

        self.mock_inventory_item_crud.remove_item_from_owner.assert_called_once_with(
            self.mock_session, guild_id=self.guild_id, owner_entity_id=self.npc_id, owner_entity_type=OwnerEntityType.GENERATED_NPC, item_id=self.item_sword.id, quantity=2
        )
        self.mock_inventory_item_crud.add_item_to_owner.assert_called_once_with(
            self.mock_session, guild_id=self.guild_id, owner_entity_id=self.player_id, owner_entity_type=OwnerEntityType.PLAYER, item_id=self.item_sword.id, quantity=2, instance_specific_properties_json={}
        )
        self.mock_log_event.assert_called_once()
        self.assertEqual(self.mock_log_event.call_args[1]['event_type'], EventType.TRADE_ITEM_BOUGHT.value)
        self.mock_update_relationship.assert_called_once()
        self.assertEqual(self.mock_update_relationship.call_args[1]['event_type'], "TRADE_ITEM_BOUGHT")

    async def test_buy_item_not_enough_gold(self):
        self.mock_player.gold = 50 # Not enough for a sword at 60
        npc_sword_stack = InventoryItem(**mock_inventory_item_data(id=101, item_model=self.item_sword, quantity=1, owner_id=self.npc_id, owner_type=OwnerEntityType.GENERATED_NPC))
        self.mock_inventory_item_crud.get_inventory_for_owner.return_value = [npc_sword_stack]

        with patch('backend.core.trade_system._calculate_item_price', AsyncMock(return_value=60.0)):
            result = await handle_trade_action(
                self.mock_session, self.guild_id, self.player_id, self.npc_id,
                action_type="buy", item_static_id=self.item_sword.static_id, count=1
            )
        self.assertFalse(result.success)
        self.assertEqual(result.message_key, "trade_error_player_not_enough_gold")
        self.assertEqual(self.mock_player.gold, 50) # Gold unchanged

    async def test_buy_item_npc_not_enough_items(self):
        self.mock_player.gold = 200
        npc_sword_stack = InventoryItem(**mock_inventory_item_data(id=101, item_model=self.item_sword, quantity=1, owner_id=self.npc_id, owner_type=OwnerEntityType.GENERATED_NPC))
        self.mock_inventory_item_crud.get_inventory_for_owner.return_value = [npc_sword_stack]

        with patch('backend.core.trade_system._calculate_item_price', AsyncMock(return_value=60.0)):
             result = await handle_trade_action(
                self.mock_session, self.guild_id, self.player_id, self.npc_id,
                action_type="buy", item_static_id=self.item_sword.static_id, count=2 # Request 2, NPC has 1
            )
        self.assertFalse(result.success)
        self.assertEqual(result.message_key, "trade_error_npc_not_enough_items")
        self.assertEqual(self.mock_player.gold, 200) # Gold unchanged


    # SELL ACTION
    async def test_sell_item_success(self):
        self.mock_player.gold = 100
        player_potion_stack = InventoryItem(**mock_inventory_item_data(id=201, item_model=self.item_potion, quantity=5, owner_id=self.player_id, owner_type=OwnerEntityType.PLAYER))
        self.mock_inventory_item_crud.get.return_value = player_potion_stack # Mock fetching the stack by ID

        with patch('backend.core.trade_system._calculate_item_price', AsyncMock(return_value=5.0)) as mock_calc_price: # Player sells potion at 5
            result = await handle_trade_action(
                self.mock_session, self.guild_id, self.player_id, self.npc_id,
                action_type="sell", inventory_item_db_id=player_potion_stack.id, count=3
            )

        self.assertTrue(result.success)
        self.assertEqual(result.message_key, "trade_sell_success")
        self.assertEqual(self.mock_player.gold, 100 + (5 * 3)) # 100 + 15 = 115

        self.mock_inventory_item_crud.remove_item_from_owner.assert_called_once_with(
            self.mock_session, guild_id=self.guild_id, owner_entity_id=self.player_id, owner_entity_type=OwnerEntityType.PLAYER, item_id=self.item_potion.id, quantity=3
        )
        self.mock_inventory_item_crud.add_item_to_owner.assert_called_once_with(
            self.mock_session, guild_id=self.guild_id, owner_entity_id=self.npc_id, owner_entity_type=OwnerEntityType.GENERATED_NPC, item_id=self.item_potion.id, quantity=3, instance_specific_properties_json={}
        )
        self.mock_log_event.assert_called_once()
        self.assertEqual(self.mock_log_event.call_args[1]['event_type'], EventType.TRADE_ITEM_SOLD.value)
        self.mock_update_relationship.assert_called_once()
        self.assertEqual(self.mock_update_relationship.call_args[1]['event_type'], "TRADE_ITEM_SOLD")

    async def test_sell_item_player_not_enough_items(self):
        self.mock_player.gold = 100
        player_potion_stack = InventoryItem(**mock_inventory_item_data(id=201, item_model=self.item_potion, quantity=2, owner_id=self.player_id, owner_type=OwnerEntityType.PLAYER))
        self.mock_inventory_item_crud.get.return_value = player_potion_stack

        with patch('backend.core.trade_system._calculate_item_price', AsyncMock(return_value=5.0)):
            result = await handle_trade_action(
                self.mock_session, self.guild_id, self.player_id, self.npc_id,
                action_type="sell", inventory_item_db_id=player_potion_stack.id, count=3 # Request 3, player has 2
            )
        self.assertFalse(result.success)
        self.assertEqual(result.message_key, "trade_error_player_not_enough_items_to_sell")
        self.assertEqual(self.mock_player.gold, 100) # Gold unchanged

    async def test_sell_item_player_does_not_own_stack(self):
        self.mock_inventory_item_crud.get.return_value = None # Player doesn't own this stack ID
        result = await handle_trade_action(
            self.mock_session, self.guild_id, self.player_id, self.npc_id,
            action_type="sell", inventory_item_db_id=999, count=1
        )
        self.assertFalse(result.success)
        self.assertEqual(result.message_key, "trade_error_player_does_not_own_item_stack")

if __name__ == '__main__':
    unittest.main()

# To run these tests:
# python -m unittest tests.core.test_trade_system
# (Ensure __init__.py files are present in tests and tests/core for discovery)
# Or from the root directory:
# python -m unittest discover -s tests -p "test_trade_system.py"
# Or using pytest if configured:
# pytest tests/core/test_trade_system.py
