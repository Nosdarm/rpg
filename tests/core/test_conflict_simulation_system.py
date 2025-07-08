import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from typing import List, Dict, Any, Optional, Tuple # Added Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Player, GeneratedNpc, PendingConflict, Item, InventoryItem # Added Item, InventoryItem
from src.models.actions import ParsedAction, ActionEntity
from src.models.enums import RelationshipEntityType, ConflictStatus
from src.core.conflict_simulation_system import simulate_conflict_detection, _extract_primary_target_signature, SimulatedActionActor

# Helper function to create ParsedAction instances easily
from typing import List, Dict, Any, Optional # Ensure Optional is imported

# ... other imports ...

# Helper function to create ParsedAction instances easily
def create_parsed_action(
    raw_text: str,
    intent: str,
    entities: Optional[list[ActionEntity]] = None, # Corrected type hint
    guild_id: int = 1,
    player_id: int = 1 # Discord ID
) -> ParsedAction:
    if entities is None:
        entities = []
    return ParsedAction(
        raw_text=raw_text,
        intent=intent,
        entities=entities,
        guild_id=guild_id,
        player_id=player_id
    )

class TestExtractPrimaryTargetSignature(unittest.TestCase):
    def test_attack_npc_id(self):
        action = create_parsed_action("attack goblin", "attack", [ActionEntity(type="target_npc_id", value="123")])
        self.assertEqual(_extract_primary_target_signature(action), "npc:123")

    def test_attack_player_id(self):
        action = create_parsed_action("attack player", "attack", [ActionEntity(type="target_player_id", value="456")])
        self.assertEqual(_extract_primary_target_signature(action), "player:456")

    def test_trade_target_npc_name(self):
        action = create_parsed_action("trade with Elara", "trade_view_inventory", [ActionEntity(type="target_npc_name", value="Elara")])
        self.assertEqual(_extract_primary_target_signature(action), "npc_name:elara")

    def test_interact_item_static_id(self):
        # This case might be ambiguous, 'interact' usually for world objects, 'use' for items.
        # However, if NLU produces it, the signature extractor should handle it.
        # Let's assume 'interact' with an item implies 'use' or 'examine' for signature purposes.
        # The current _extract_primary_target_signature for 'interact' prioritizes objects.
        # If an item_static_id is the only entity, it might fall to the generic named_entity.
        # Let's test the current behavior.
        action = create_parsed_action("interact magic scroll", "interact", [ActionEntity(type="item_static_id", value="scroll_of_fire")])
        # Based on current logic: 'interact' does not directly look for item_static_id in its primary block.
        # It will fall through to the generic_target fallback if only one entity.
        # Based on current logic for "interact", it prioritizes obj_static, obj_name.
        # If only item_static_id is present, it falls to generic_target.
        self.assertEqual(_extract_primary_target_signature(action), "generic_target:item_static_id:scroll_of_fire")

    def test_interact_location_object_static_id(self):
        action = create_parsed_action("pull lever", "interact", [ActionEntity(type="target_object_static_id", value="lever_main_gate")])
        self.assertEqual(_extract_primary_target_signature(action), "obj_static:lever_main_gate")

    def test_interact_location_object_name(self):
        action = create_parsed_action("pull the rusty lever", "interact", [ActionEntity(type="target_object_name", value="Rusty Lever")])
        self.assertEqual(_extract_primary_target_signature(action), "obj_name:rusty lever")

    def test_examine_item_id_priority(self):
        action = create_parsed_action("examine potion", "examine", [
            ActionEntity(type="item_name", value="Healing Potion"),
            ActionEntity(type="target_item_id", value="item_inst_123")
        ])
        self.assertEqual(_extract_primary_target_signature(action), "item_instance:item_inst_123")

    def test_examine_object_name(self):
        action = create_parsed_action("examine statue", "examine", [ActionEntity(type="target_object_name", value="Old Statue")])
        self.assertEqual(_extract_primary_target_signature(action), "obj_name:old statue")

    def test_examine_npc_static_id(self):
        # Assuming NLU might provide npc_static_id for examine, though target_npc_id is more common for direct interaction
        # Let's add a hypothetical entity type for this test if needed, or use target_npc_id
        action = create_parsed_action("examine guard", "examine", [ActionEntity(type="target_npc_id", value="guard_001")])
        self.assertEqual(_extract_primary_target_signature(action), "npc:guard_001")

    def test_go_to_sublocation_static_id(self):
        action = create_parsed_action("go to the kitchen", "go_to", [ActionEntity(type="target_sublocation_static_id", value="kitchen_01")])
        self.assertEqual(_extract_primary_target_signature(action), "subloc_static:kitchen_01")

    def test_go_to_sublocation_name(self):
        action = create_parsed_action("go to the armory", "go_to", [ActionEntity(type="target_sublocation_name", value="The Armory")])
        self.assertEqual(_extract_primary_target_signature(action), "subloc_name:the armory")

    def test_go_to_point_name(self):
        action = create_parsed_action("go to the fireplace", "go_to", [ActionEntity(type="target_point_name", value="Fireplace")])
        self.assertEqual(_extract_primary_target_signature(action), "point_name:fireplace")

    def test_take_item_instance_id(self):
        action = create_parsed_action("take sword", "take", [ActionEntity(type="target_item_id", value="777")])
        self.assertEqual(_extract_primary_target_signature(action), "item_instance:777")

    def test_take_item_static_id(self):
        action = create_parsed_action("take potion", "take", [ActionEntity(type="item_static_id", value="potion_healing")])
        self.assertEqual(_extract_primary_target_signature(action), "item_static:potion_healing")

    def test_drop_item_name(self):
        action = create_parsed_action("drop rock", "drop", [ActionEntity(type="item_name", value="heavy rock")])
        self.assertEqual(_extract_primary_target_signature(action), "item_name:heavy rock")

    def test_use_item_on_self_by_static_id(self):
        action = create_parsed_action("use potion", "use", [ActionEntity(type="item_static_id", value="potion_greater_healing")])
        self.assertEqual(_extract_primary_target_signature(action), "use_on_self:item_static:potion_greater_healing")

    def test_use_item_on_self_by_item_id(self):
        action = create_parsed_action("use my potion", "use", [ActionEntity(type="target_item_id", value="888")])
        self.assertEqual(_extract_primary_target_signature(action), "use_on_self:item_instance:888")

    def test_use_item_on_npc_by_static_id(self):
        action = create_parsed_action("use potion on goblin", "use", [
            ActionEntity(type="item_static_id", value="potion_harming"),
            ActionEntity(type="target_npc_id", value="g1")
        ])
        self.assertEqual(_extract_primary_target_signature(action), "use:item_static:potion_harming@target:npc:g1")

    def test_use_item_on_player_by_item_id(self):
        action = create_parsed_action("use scroll on P2", "use", [
            ActionEntity(type="target_item_id", value="s99"),
            ActionEntity(type="target_player_id", value="p2")
        ])
        self.assertEqual(_extract_primary_target_signature(action), "use:item_instance:s99@target:player:p2")

    def test_use_skill_on_self(self):
        action = create_parsed_action("use power strike", "use", [ActionEntity(type="skill_name", value="power_strike")])
        self.assertEqual(_extract_primary_target_signature(action), "use_on_self:skill:power_strike")

    def test_use_skill_on_target_npc(self):
        action = create_parsed_action("use fireball on orc", "use", [
            ActionEntity(type="skill_name", value="fireball"),
            ActionEntity(type="target_npc_id", value="orc_boss")
        ])
        self.assertEqual(_extract_primary_target_signature(action), "use:skill:fireball@target:npc:orc_boss")

    def test_use_object_static_id(self):
        action = create_parsed_action("use lever", "use", [ActionEntity(type="target_object_static_id", value="lever_01")])
        self.assertEqual(_extract_primary_target_signature(action), "use_obj_static:lever_01") # Expectation is correct

    def test_use_object_name(self):
        action = create_parsed_action("use the big red button", "use", [ActionEntity(type="target_object_name", value="Big Red Button")])
        self.assertEqual(_extract_primary_target_signature(action), "use_obj_name:big red button") # Expectation is correct

    def test_use_priority_item_over_object(self):
        action = create_parsed_action("use potion", "use", [
            ActionEntity(type="item_static_id", value="potion_healing"), # Item
            ActionEntity(type="target_object_name", value="Old Chest")    # Object also present
        ])
        # Item use (on self by default) should take priority
        self.assertEqual(_extract_primary_target_signature(action), "use_on_self:item_static:potion_healing")

    def test_use_priority_skill_over_object(self):
        action = create_parsed_action("use heal skill", "use", [
            ActionEntity(type="skill_name", value="minor_heal"),       # Skill
            ActionEntity(type="target_object_static_id", value="altar") # Object also present
        ])
        # Skill use (on self by default) should take priority over world object
        self.assertEqual(_extract_primary_target_signature(action), "use_on_self:skill:minor_heal")

    def test_use_priority_item_over_skill_over_object(self):
        action = create_parsed_action("use something", "use", [
            ActionEntity(type="item_static_id", value="super_potion"),    # Item
            ActionEntity(type="skill_name", value="mega_spell"),         # Skill
            ActionEntity(type="target_object_name", value="ancient_orb") # Object
        ])
        # Item use (on self by default) should take top priority
        self.assertEqual(_extract_primary_target_signature(action), "use_on_self:item_static:super_potion")

    def test_move_location_static_id(self):
        action = create_parsed_action("go to tavern", "move", [ActionEntity(type="location_static_id", value="tavern_01")])
        self.assertEqual(_extract_primary_target_signature(action), "location_static:tavern_01")

    def test_move_direction(self):
        action = create_parsed_action("go north", "move", [ActionEntity(type="direction", value="North")])
        self.assertEqual(_extract_primary_target_signature(action), "direction:north")

    def test_no_entities(self):
        action = create_parsed_action("look around", "look", [])
        self.assertIsNone(_extract_primary_target_signature(action))

    def test_single_generic_entity_for_examine_object(self): # Examine object by name falls to generic
        action = create_parsed_action("examine stone", "examine", [ActionEntity(type="target_object_name", value="Mysterious Stone")])
        self.assertEqual(_extract_primary_target_signature(action), "obj_name:mysterious stone")

    def test_single_generic_entity_for_examine_item(self): # Examine item by name
        action = create_parsed_action("examine sword", "examine", [ActionEntity(type="item_name", value="Long Sword")])
        self.assertEqual(_extract_primary_target_signature(action), "item_name:long sword")

    def test_irrelevant_single_entity(self):
        action = create_parsed_action("walk carefully", "move", [ActionEntity(type="manner", value="carefully")])
        self.assertIsNone(_extract_primary_target_signature(action)) # 'manner' is not a target type


# ... другие импорты ...
from src.core.conflict_simulation_system import (
    DEFAULT_RULES_SAME_INTENT_SAME_TARGET_CFG,
    DEFAULT_RULES_CONFLICTING_INTENT_PAIRS_CFG
)

class TestSimulateConflictDetection(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)

        self.mock_player_crud_get = patch('src.core.crud.player_crud.get', new_callable=AsyncMock).start()
        self.mock_npc_crud_get = patch('src.core.crud.npc_crud.get', new_callable=AsyncMock).start()

        # Мокируем get_rule, используемый внутри conflict_simulation_system
        self.mock_get_rule = patch('src.core.conflict_simulation_system.get_rule', new_callable=AsyncMock).start()

        # Настройка поведения по умолчанию для mock_get_rule
        # Он будет возвращать дефолтные правила, если не указано иное в конкретном тесте
        async def get_rule_side_effect(session, guild_id, key, default_value=None):
            # Использование default_value из вызова get_rule, если он предоставлен, иначе наши DEFAULT_..._CFG
            effective_default = default_value
            if key == "conflict_simulation:rules_same_intent_same_target":
                if effective_default is None: effective_default = DEFAULT_RULES_SAME_INTENT_SAME_TARGET_CFG
                return effective_default
            if key == "conflict_simulation:rules_conflicting_intent_pairs":
                if effective_default is None: effective_default = DEFAULT_RULES_CONFLICTING_INTENT_PAIRS_CFG
                return effective_default
            if key == "conflict_simulation:enable_use_self_vs_take_check":
                if effective_default is None: effective_default = {"enabled": True}
                return effective_default
            return default_value # Общий случай, вернет None если default_value не был передан в get_rule

        self.mock_get_rule.side_effect = get_rule_side_effect

        self.addCleanup(patch.stopall)

        self.player1 = Player(id=1, guild_id=1, discord_id=101, name="P1", collected_actions_json=[])
        self.player2 = Player(id=2, guild_id=1, discord_id=102, name="P2", collected_actions_json=[])
        self.player3 = Player(id=3, guild_id=1, discord_id=103, name="P3", collected_actions_json=[])
        self.npc1 = GeneratedNpc(id=1, guild_id=1, static_id="npc_goblin_1", name_i18n={"en": "Goblin"}, description_i18n={}, properties_json={})
        self.item_potion_s = Item(id=1, guild_id=1, static_id="potion_healing_s", name_i18n={"en":"Small Potion"}, description_i18n={}, item_type_i18n={"en":"Potion"})
        self.item_potion_m_inst = InventoryItem(id=101, guild_id=1, owner_entity_id=1, owner_entity_type=RelationshipEntityType.PLAYER, item_id=2, quantity=1)


    async def test_no_actions_no_conflicts(self):
        result = await simulate_conflict_detection(self.mock_session, 1, [])
        self.assertEqual(result, [])

    async def test_single_action_no_conflicts(self):
        self.mock_player_crud_get.return_value = self.player1
        actions_data = [{"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("attack", "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()}]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(result, [])

    async def test_two_actions_different_targets_no_conflict(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("attack npc1", "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("interact lever", "interact", [ActionEntity(type="target_object_static_id", value="lever1")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(result, [])

    async def test_two_actions_same_target_non_conflicting_intents(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        # Example: 'examine' and 'look' on the same target are not defined as conflicting.
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("examine npc1", "examine", [ActionEntity(type="target_npc_id", value="1")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("talk to npc1", "talk", [ActionEntity(type="target_npc_id", value="1")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(result, [], "Examine and Talk on same target should not conflict by default")

    async def test_conflict_two_attacks_on_same_npc(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        self.mock_npc_crud_get.return_value = self.npc1 # Assume target_npc_id "1" maps to this

        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("attack goblin", "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("smash goblin", "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(len(result), 1)
        conflict = result[0]
        self.assertEqual(conflict.status, ConflictStatus.SIMULATED_INTERNAL_CONFLICT)
        self.assertTrue(conflict.conflict_type.startswith("sim_multi_attack_on_npc_1"))
        self.assertEqual(len(conflict.involved_entities_json), 2)
        self.assertEqual(conflict.resolution_details_json, {"target_signature": "npc:1"})


    async def test_conflict_two_takes_for_same_item_static_id(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("take potion", "take", [ActionEntity(type="item_static_id", value="potion_healing_s")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("grab potion", "take", [ActionEntity(type="item_static_id", value="potion_healing_s")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(len(result), 1)
        conflict = result[0]
        self.assertTrue(conflict.conflict_type.startswith("sim_item_take_contention_on_item_static_potion_healing_s"))
        self.assertEqual(len(conflict.involved_entities_json), 2)
        self.assertEqual(conflict.resolution_details_json, {"target_signature": "item_static:potion_healing_s"})

    async def test_conflict_take_vs_use_on_same_item_instance(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("take my potion", "take", [ActionEntity(type="target_item_id", value="101")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("use my potion", "use", [ActionEntity(type="target_item_id", value="101")]).model_dump()} # use on self
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(len(result), 1)
        conflict = result[0]
        # This is caught by Rule 3 (_check_use_self_vs_take_conflicts)
        self.assertTrue(conflict.conflict_type.startswith("sim_item_use_self_vs_take_item_instance_101"))
        self.assertEqual(len(conflict.involved_entities_json), 2)
        self.assertEqual(conflict.resolution_details_json, {"item_signature": "item_instance:101"})


    async def test_conflict_use_on_self_vs_take_same_item_static_id(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("use potion", "use", [ActionEntity(type="item_static_id", value="potion_healing_s")]).model_dump()}, # use_on_self
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("take potion", "take", [ActionEntity(type="item_static_id", value="potion_healing_s")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(len(result), 1)
        conflict = result[0]
        # This specific conflict (use_on_self vs take) is handled by a separate block
        self.assertTrue(conflict.conflict_type.startswith("sim_item_use_self_vs_take_item_static_potion_healing_s"))
        self.assertEqual(conflict.resolution_details_json, {"item_signature": "item_static:potion_healing_s"})

    async def test_no_conflict_use_on_self_vs_attack_unrelated(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        self.mock_npc_crud_get.return_value = self.npc1
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("use potion", "use", [ActionEntity(type="item_static_id", value="potion_healing_s")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("attack goblin", "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(result, [])

    async def test_involved_entities_json_structure_and_conflict_type(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        action1_text = "P1 attacks goblin"
        action2_text = "P2 also attacks goblin"
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action(action1_text, "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action(action2_text, "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(len(result), 1)
        conflict = result[0]
        self.assertTrue(conflict.conflict_type == "sim_multi_attack_on_npc_1")
        self.assertEqual(len(conflict.involved_entities_json), 2)

        p1_action_details = next(item for item in conflict.involved_entities_json if item["entity_id"] == 1)
        p2_action_details = next(item for item in conflict.involved_entities_json if item["entity_id"] == 2)

        self.assertEqual(p1_action_details["entity_type"], "player")
        self.assertEqual(p1_action_details["action_intent"], "attack")
        self.assertEqual(p1_action_details["action_text"], action1_text)
        self.assertTrue(isinstance(p1_action_details["action_entities"], list))
        self.assertEqual(p1_action_details["action_entities"][0]["type"], "target_npc_id")
        self.assertEqual(p1_action_details["action_entities"][0]["value"], "1")

        self.assertEqual(p2_action_details["entity_type"], "player")
        self.assertEqual(p2_action_details["action_intent"], "attack")
        self.assertEqual(p2_action_details["action_text"], action2_text)

    async def test_conflict_three_exclusive_actions_same_target(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2, self.player3]
        # Redefine EXCLUSIVE_INTENTS locally for this test if it was removed/changed in the main code
        # For this test, assume attack, interact, take are exclusive on the same target.
        # The current code handles multi-attack separately.
        # Let's test take vs interact on same target.
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("take artifact", "take", [ActionEntity(type="item_static_id", value="artifact_xyz")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("use artifact", "use", [ActionEntity(type="item_static_id", value="artifact_xyz")]).model_dump()},
            {"actor_id": 3, "actor_type": "player", "parsed_action": create_parsed_action("examine artifact", "examine", [ActionEntity(type="item_static_id", value="artifact_xyz")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(len(result), 1)
        conflict = result[0]
        self.assertEqual(conflict.status, ConflictStatus.SIMULATED_INTERNAL_CONFLICT)
        # This should be caught by Rule 3 (use_on_self vs take)
        self.assertTrue(conflict.conflict_type.startswith("sim_item_use_self_vs_take_item_static_artifact_xyz"))
        self.assertEqual(len(conflict.involved_entities_json), 2) # P1 (take) and P2 (use on self)
        involved_ids = {e["entity_id"] for e in conflict.involved_entities_json}
        self.assertIn(1, involved_ids) # P1
        self.assertIn(2, involved_ids) # P2
        self.assertNotIn(3, involved_ids) # P3 (examine) should not be part of this specific conflict
        # Check details from Rule 3
        self.assertEqual(conflict.resolution_details_json, {"item_signature": "item_static:artifact_xyz"})


    async def test_no_target_signature_actions_no_conflict(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("look around", "look", []).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("think", "think", []).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(result, [])

    async def test_mixed_targeted_and_non_targeted_actions(self):
        # P1 attacks NPC1, P2 looks around, P3 attacks NPC1
        self.mock_player_crud_get.side_effect = [self.player1, self.player2, self.player3]
        self.mock_npc_crud_get.return_value = self.npc1
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("attack goblin", "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("look around", "look", []).model_dump()},
            {"actor_id": 3, "actor_type": "player", "parsed_action": create_parsed_action("charge goblin", "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(len(result), 1)
        conflict = result[0]
        self.assertTrue(conflict.conflict_type.startswith("sim_multi_attack_on_npc_1"))
        self.assertEqual(len(conflict.involved_entities_json), 2) # Only p1 and p3
        ids_in_conflict = {entry["entity_id"] for entry in conflict.involved_entities_json}
        self.assertIn(1, ids_in_conflict)
        self.assertIn(3, ids_in_conflict)
        self.assertNotIn(2, ids_in_conflict)

    async def test_conflict_two_uses_on_same_object_static_id(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("use lever", "use", [ActionEntity(type="target_object_static_id", value="gate_lever")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("activate lever", "use", [ActionEntity(type="target_object_static_id", value="gate_lever")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(len(result), 1)
        conflict = result[0]
        # Based on EXCLUSIVE_OBJECT_MANIPULATION rule
        self.assertTrue(conflict.conflict_type.startswith("sim_exclusive_object_manipulation_on_use_for_use_obj_static_gate_lever"))
        self.assertEqual(len(conflict.involved_entities_json), 2)
        self.assertEqual(conflict.resolution_details_json["target_signature"], "use_obj_static:gate_lever")
        self.assertEqual(conflict.resolution_details_json["category"], "EXCLUSIVE_OBJECT_MANIPULATION")
        self.assertEqual(conflict.resolution_details_json["conflicting_intent"], "use")

    async def test_conflict_interact_vs_use_on_same_object_name(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("interact with shrine", "interact", [ActionEntity(type="target_object_name", value="Mystic Shrine")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("use shrine", "use", [ActionEntity(type="target_object_name", value="Mystic Shrine")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        # With current signature logic:
        # P1: interact with Mystic Shrine -> target_sig = "obj_name:mystic shrine"
        # P2: use Mystic Shrine          -> target_sig = "use_obj_name:mystic shrine"
        # These are different signatures. The actions will be in different groups.
        # Rule 1 (_apply_same_intent_conflict_rules) processes groups with >1 action. These groups have 1.
        # Rule 2 (_apply_conflicting_intent_pairs_rules) processes groups with >1 action. These groups have 1.
        # Rule 3 (_check_use_self_vs_take_conflicts) is not relevant.
        # Therefore, 0 conflicts are expected.
        self.assertEqual(len(result), 0, "Interact and Use on the same object (name) should not conflict if signatures differ ('obj_name:...' vs 'use_obj_name:...') and no specific cross-signature rule exists for this pair.")


class TestConflictRuleApplication(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guild_id = 1
        self.player1_sim_actor = SimulatedActionActor(guild_id=self.guild_id, player=Player(id=1, name="P1", guild_id=self.guild_id), parsed_action=create_parsed_action("",""))
        self.player2_sim_actor = SimulatedActionActor(guild_id=self.guild_id, player=Player(id=2, name="P2", guild_id=self.guild_id), parsed_action=create_parsed_action("",""))
        self.player3_sim_actor = SimulatedActionActor(guild_id=self.guild_id, player=Player(id=3, name="P3", guild_id=self.guild_id), parsed_action=create_parsed_action("",""))

        # Import the functions to be tested (they are not async, so direct import is fine)
        from src.core.conflict_simulation_system import (
            _apply_same_intent_conflict_rules,
            _apply_conflicting_intent_pairs_rules,
            _check_use_self_vs_take_conflicts,
            _extract_primary_target_signature as _epfs # Alias for easier use
        )
        self._apply_same_intent_conflict_rules = _apply_same_intent_conflict_rules
        self._apply_conflicting_intent_pairs_rules = _apply_conflicting_intent_pairs_rules
        self._check_use_self_vs_take_conflicts = _check_use_self_vs_take_conflicts
        self._extract_primary_target_signature = _epfs

        # Define sample rules for testing the rule application functions directly
        self.sample_rules_same_intent: Dict[str, Tuple[set[str], Optional[Tuple[str, ...]]]] = {
            "EXCLUSIVE_ITEM_MANIPULATION": ({"take"}, ("item_static:", "item_instance:", "item_name:")),
            "MULTI_ATTACK": ({"attack"}, ("npc:", "player:")),
            "EXCLUSIVE_OBJECT_MANIPULATION_TEST": (
                {"interact", "use"},
                ("obj_static:", "obj_name:", "use_obj_static:", "use_obj_name:")
            ),
        }
        self.sample_rules_conflicting_pairs: Dict[frozenset[str], List[Tuple[str, Tuple[str, ...]]]] = {
            frozenset(["take", "use"]): [("item_contention", ("item_static:", "item_instance:", "item_name:"))],
            frozenset(["attack", "talk"]): [("disrupted_interaction_npc", ("npc:", "npc_name:"))],
        }


    def test_apply_same_intent_two_takes_on_item(self):
        action_p1 = create_parsed_action("take potion", "take", [ActionEntity(type="item_static_id", value="potion1")])
        action_p2 = create_parsed_action("grab potion", "take", [ActionEntity(type="item_static_id", value="potion1")])
        actions_on_target = [
            (self.player1_sim_actor, action_p1),
            (self.player2_sim_actor, action_p2)
        ]
        target_sig = "item_static:potion1"

        conflicts = self._apply_same_intent_conflict_rules(actions_on_target, target_sig, self.guild_id, self.sample_rules_same_intent)
        self.assertEqual(len(conflicts), 1)
        # If category is EXCLUSIVE_ITEM_MANIPULATION and intent is take, SUT generates this specific type:
        self.assertEqual(conflicts[0].conflict_type, "sim_item_take_contention_on_item_static_potion1")
        # Check that resolution details now only contain target_signature for this specific type
        self.assertEqual(conflicts[0].resolution_details_json, {"target_signature": target_sig})

    def test_apply_same_intent_three_attacks_on_npc(self):
        action_p1 = create_parsed_action("hit orc", "attack", [ActionEntity(type="target_npc_id", value="orc1")])
        action_p2 = create_parsed_action("strike orc", "attack", [ActionEntity(type="target_npc_id", value="orc1")])
        action_p3 = create_parsed_action("attack orc", "attack", [ActionEntity(type="target_npc_id", value="orc1")])
        actions_on_target = [
            (self.player1_sim_actor, action_p1),
            (self.player2_sim_actor, action_p2),
            (self.player3_sim_actor, action_p3)
        ]
        target_sig = "npc:orc1"
        conflicts = self._apply_same_intent_conflict_rules(actions_on_target, target_sig, self.guild_id, self.sample_rules_same_intent)
        self.assertEqual(len(conflicts), 1) # Should still be one conflict involving all 3
        # Based on the 'MULTI_ATTACK' category and 'attack' intent, the generated type is:
        self.assertEqual(conflicts[0].conflict_type, "sim_multi_attack_on_attack_for_npc_orc1")
        self.assertEqual(len(conflicts[0].involved_entities_json), 3)
        # Check that resolution details now only contain target_signature for this specific type
        # The 'else' branch for conflict_type_str also has a general resolution_details:
        expected_details = {"target_signature": target_sig, "category": "MULTI_ATTACK", "conflicting_intent": "attack"}
        self.assertEqual(conflicts[0].resolution_details_json, expected_details)


    def test_apply_same_intent_no_conflict_different_targets(self):
        # This function is called with actions already grouped by target, so this exact scenario isn't its direct responsibility.
        # However, if it were called with mixed targets, it should only find conflicts for matching target_sig.
        # We test its behavior given its inputs.
        action_p1 = create_parsed_action("take potion A", "take", [ActionEntity(type="item_static_id", value="potionA")])
        actions_on_target = [(self.player1_sim_actor, action_p1)] # Only one action for this target_sig
        target_sig = "item_static:potionA"
        conflicts = self._apply_same_intent_conflict_rules(actions_on_target, target_sig, self.guild_id, self.sample_rules_same_intent)
        self.assertEqual(len(conflicts), 0)

    def test_apply_same_intent_no_conflict_non_exclusive_intent(self):
        action_p1 = create_parsed_action("look at potion", "examine", [ActionEntity(type="item_static_id", value="potion1")])
        action_p2 = create_parsed_action("examine potion", "examine", [ActionEntity(type="item_static_id", value="potion1")])
        actions_on_target = [
            (self.player1_sim_actor, action_p1),
            (self.player2_sim_actor, action_p2)
        ]
        target_sig = "item_static:potion1"
        conflicts = self._apply_same_intent_conflict_rules(actions_on_target, target_sig, self.guild_id, self.sample_rules_same_intent)
        self.assertEqual(len(conflicts), 0) # Examine is not in self.sample_rules_same_intent's "intents" for any category

    def test_apply_conflicting_intent_pairs_take_vs_use(self):
        action_p1_take = create_parsed_action("take potion", "take", [ActionEntity(type="item_static_id", value="potion1")])
        action_p2_use = create_parsed_action("use potion", "use", [ActionEntity(type="item_static_id", value="potion1")])
        actions_on_target = [
            (self.player1_sim_actor, action_p1_take),
            (self.player2_sim_actor, action_p2_use)
        ]
        target_sig = "item_static:potion1"
        conflicts = self._apply_conflicting_intent_pairs_rules(actions_on_target, target_sig, self.guild_id, [], self.sample_rules_conflicting_pairs)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].conflict_type, "sim_item_contention_on_item_static_potion1")
        expected_details = {"target_signature": target_sig, "intents": sorted(["take", "use"])}
        self.assertEqual(conflicts[0].resolution_details_json, expected_details)

    def test_apply_conflicting_intent_pairs_attack_vs_talk(self):
        action_p1_attack = create_parsed_action("attack guard", "attack", [ActionEntity(type="target_npc_name", value="Guard")])
        action_p2_talk = create_parsed_action("talk to guard", "talk", [ActionEntity(type="target_npc_name", value="Guard")])
        actions_on_target = [
            (self.player1_sim_actor, action_p1_attack),
            (self.player2_sim_actor, action_p2_talk)
        ]
        target_sig = "npc_name:guard"
        conflicts = self._apply_conflicting_intent_pairs_rules(actions_on_target, target_sig, self.guild_id, [], self.sample_rules_conflicting_pairs)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].conflict_type, "sim_disrupted_interaction_npc_on_npc_name_guard")
        expected_details = {"target_signature": target_sig, "intents": sorted(["attack", "talk"])}
        self.assertEqual(conflicts[0].resolution_details_json, expected_details)

    def test_apply_conflicting_intent_pairs_no_conflict_unrelated_pair(self):
        action_p1_move = create_parsed_action("go north", "move", [ActionEntity(type="direction", value="north")])
        action_p2_look = create_parsed_action("look", "look", [])
        # These actions wouldn't typically be on the same target_sig, but testing the rule logic
        actions_on_target = [ # Assuming a hypothetical common target_sig for test purposes
            (self.player1_sim_actor, action_p1_move),
            (self.player2_sim_actor, action_p2_look)
        ]
        target_sig = "hypothetical_common_target"
        conflicts = self._apply_conflicting_intent_pairs_rules(actions_on_target, target_sig, self.guild_id, [], self.sample_rules_conflicting_pairs)
        self.assertEqual(len(conflicts), 0)

    def test_check_use_self_vs_take_conflict(self):
        # P1 uses potion (item_static_id: potionX) on self
        # P2 takes potion (item_static_id: potionX)
        action_p1_use_self = create_parsed_action("use my potion", "use", [ActionEntity(type="item_static_id", value="potionX")])
        actor1 = SimulatedActionActor(guild_id=self.guild_id, player=Player(id=1, name="P1", guild_id=self.guild_id), parsed_action=action_p1_use_self)

        action_p2_take = create_parsed_action("take the potion", "take", [ActionEntity(type="item_static_id", value="potionX")])
        actor2 = SimulatedActionActor(guild_id=self.guild_id, player=Player(id=2, name="P2", guild_id=self.guild_id), parsed_action=action_p2_take)

        simulated_actors = [actor1, actor2]
        conflicts = self._check_use_self_vs_take_conflicts(simulated_actors, self.guild_id, self._extract_primary_target_signature)
        self.assertEqual(len(conflicts), 1)
        # Rule 3 now produces sim_item_use_self_vs_take...
        self.assertEqual(conflicts[0].conflict_type, "sim_item_use_self_vs_take_item_static_potionx")
        # Rule 3 resolution_details is now just {"item_signature": item_sig}
        expected_details = {"item_signature": "item_static:potionX".lower()} # Ensure value matches potential lowercasing in conflict type

        actual_details_for_comp = {
            k: (v.lower() if isinstance(v, str) else v)
            for k,v in conflicts[0].resolution_details_json.items()
        }
        self.assertEqual(actual_details_for_comp, expected_details)

    def test_check_use_self_vs_take_no_conflict_different_items(self):
        action_p1_use_self = create_parsed_action("use potion A", "use", [ActionEntity(type="item_static_id", value="potionA")])
        actor1 = SimulatedActionActor(guild_id=self.guild_id, player=Player(id=1, name="P1", guild_id=self.guild_id), parsed_action=action_p1_use_self)

        action_p2_take = create_parsed_action("take potion B", "take", [ActionEntity(type="item_static_id", value="potionB")])
        actor2 = SimulatedActionActor(guild_id=self.guild_id, player=Player(id=2, name="P2", guild_id=self.guild_id), parsed_action=action_p2_take)

        simulated_actors = [actor1, actor2]
        conflicts = self._check_use_self_vs_take_conflicts(simulated_actors, self.guild_id, self._extract_primary_target_signature)
        self.assertEqual(len(conflicts), 0)

    def test_check_use_self_vs_take_no_conflict_only_one_action(self):
        action_p1_use_self = create_parsed_action("use potion A", "use", [ActionEntity(type="item_static_id", value="potionA")])
        actor1 = SimulatedActionActor(guild_id=self.guild_id, player=Player(id=1, name="P1", guild_id=self.guild_id), parsed_action=action_p1_use_self)

        simulated_actors = [actor1]
        conflicts = self._check_use_self_vs_take_conflicts(simulated_actors, self.guild_id, self._extract_primary_target_signature)
        self.assertEqual(len(conflicts), 0)

    def test_apply_same_intent_two_uses_on_object(self):
        action_p1 = create_parsed_action("use lever", "use", [ActionEntity(type="target_object_static_id", value="lever1")])
        action_p2 = create_parsed_action("activate lever", "use", [ActionEntity(type="target_object_static_id", value="lever1")])
        actions_on_target = [
            (self.player1_sim_actor, action_p1),
            (self.player2_sim_actor, action_p2)
        ]
        # _extract_primary_target_signature for "use" on object now returns "use_obj_static:..."
        target_sig = self._extract_primary_target_signature(action_p1) # Should be "use_obj_static:lever1"
        self.assertEqual(target_sig, "use_obj_static:lever1") # Corrected expectation

        conflicts = self._apply_same_intent_conflict_rules(actions_on_target, target_sig, self.guild_id, self.sample_rules_same_intent)
        self.assertEqual(len(conflicts), 1)
        # Based on EXCLUSIVE_OBJECT_MANIPULATION_TEST category and 'use' intent
        self.assertEqual(conflicts[0].conflict_type, "sim_exclusive_object_manipulation_test_on_use_for_use_obj_static_lever1") # Type uses the actual target_sig
        self.assertEqual(len(conflicts[0].involved_entities_json), 2)
        expected_details = {
            "target_signature": target_sig, # target_sig is "use_obj_static:lever1"
            "category": "EXCLUSIVE_OBJECT_MANIPULATION_TEST",
            "conflicting_intent": "use"
        }
        self.assertEqual(conflicts[0].resolution_details_json, expected_details)

    def test_apply_same_intent_interact_and_use_on_object_diff_sigs_no_conflict_here(self):
        # This test confirms that _apply_same_intent_conflict_rules does NOT find a conflict
        # if the target signatures are different, even if the underlying object is the same.
        action_p1_interact = create_parsed_action("interact with lever", "interact", [ActionEntity(type="target_object_static_id", value="lever1")])
        # interact -> obj_static:lever1
        target_sig_interact = self._extract_primary_target_signature(action_p1_interact)
        self.assertEqual(target_sig_interact, "obj_static:lever1")

        action_p2_use = create_parsed_action("use lever", "use", [ActionEntity(type="target_object_static_id", value="lever1")])
        # use -> use_obj_static:lever1 (as per current _extract_primary_target_signature)
        target_sig_use = self._extract_primary_target_signature(action_p2_use)
        self.assertEqual(target_sig_use, "use_obj_static:lever1") # This is the correct expectation now

        # Test for target_sig_interact
        actions_on_target_interact = [(self.player1_sim_actor, action_p1_interact)]
        conflicts_interact = self._apply_same_intent_conflict_rules(actions_on_target_interact, target_sig_interact, self.guild_id, self.sample_rules_same_intent)
        self.assertEqual(len(conflicts_interact), 0, "A single 'interact' should not conflict by itself")

        # Test for target_sig_use
        actions_on_target_use = [(self.player2_sim_actor, action_p2_use)]
        conflicts_use = self._apply_same_intent_conflict_rules(actions_on_target_use, target_sig_use, self.guild_id, self.sample_rules_same_intent)
        self.assertEqual(len(conflicts_use), 0, "A single 'use' should not conflict by itself")
        # The main simulate_conflict_detection function groups by signature, so these would be processed separately.


if __name__ == '__main__':
    unittest.main()

