import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Player, GeneratedNpc, PendingConflict, Item, InventoryItem # Added Item, InventoryItem
from src.models.actions import ParsedAction, ActionEntity
from src.models.enums import RelationshipEntityType, ConflictStatus
from src.core.conflict_simulation_system import simulate_conflict_detection, _extract_primary_target_signature, SimulatedActionActor

# Helper function to create ParsedAction instances easily
def create_parsed_action(
    raw_text: str,
    intent: str,
    entities: list[ActionEntity] = None, # Made entities optional for simpler calls
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
        self.assertEqual(_extract_primary_target_signature(action), "generic_target:item_static_id:scroll_of_fire")


    def test_interact_location_object_static_id(self):
        action = create_parsed_action("pull lever", "interact", [ActionEntity(type="target_object_static_id", value="lever_main_gate")])
        self.assertEqual(_extract_primary_target_signature(action), "obj_static:lever_main_gate")

    def test_interact_location_object_name(self):
        action = create_parsed_action("pull the rusty lever", "interact", [ActionEntity(type="target_object_name", value="Rusty Lever")])
        self.assertEqual(_extract_primary_target_signature(action), "obj_name:rusty lever")

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


class TestSimulateConflictDetection(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)

        self.mock_player_crud_get = patch('src.core.crud.player_crud.get', new_callable=AsyncMock).start()
        self.mock_npc_crud_get = patch('src.core.crud.npc_crud.get', new_callable=AsyncMock).start()
        # self.mock_pending_conflict_crud_create = patch('src.core.crud.pending_conflict_crud.create', new_callable=AsyncMock).start()


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
        self.assertTrue(conflict.conflict_type.startswith("sim_item_contention_on_item_instance_101"))
        self.assertEqual(len(conflict.involved_entities_json), 2)
        self.assertEqual(conflict.resolution_details_json, {"target_signature": "item_instance:101", "intents": sorted(["take", "use"])})


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
        # Based on CONFLICTING_INTENT_PAIRS_ON_SAME_TARGET for (take, use)
        self.assertTrue(conflict.conflict_type.startswith("sim_item_contention_on_item_static_artifact_xyz"))
        self.assertEqual(len(conflict.involved_entities_json), 2) # Only P1 and P2 conflict
        involved_ids = {e["entity_id"] for e in conflict.involved_entities_json}
        self.assertIn(1, involved_ids)
        self.assertIn(2, involved_ids)
        self.assertNotIn(3, involved_ids)


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

if __name__ == '__main__':
    unittest.main()

