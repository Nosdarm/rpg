import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Player, GeneratedNpc, PendingConflict
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
        action = create_parsed_action("use magic scroll", "interact", [ActionEntity(type="item_static_id", value="scroll_of_fire")])
        self.assertEqual(_extract_primary_target_signature(action), "item_static:scroll_of_fire")

    def test_interact_location_object_name(self):
        action = create_parsed_action("pull the rusty lever", "interact", [ActionEntity(type="target_object_name", value="Rusty Lever")])
        self.assertEqual(_extract_primary_target_signature(action), "location_object_name:rusty lever")

    def test_move_location_static_id(self):
        action = create_parsed_action("go to tavern", "move", [ActionEntity(type="location_static_id", value="tavern_01")])
        self.assertEqual(_extract_primary_target_signature(action), "location_static:tavern_01")

    def test_move_direction(self):
        action = create_parsed_action("go north", "move", [ActionEntity(type="direction", value="North")])
        self.assertEqual(_extract_primary_target_signature(action), "direction:north")

    def test_no_entities(self):
        action = create_parsed_action("look around", "look", [])
        self.assertIsNone(_extract_primary_target_signature(action))

    def test_single_generic_entity_for_interact(self):
        action = create_parsed_action("examine stone", "examine", [ActionEntity(type="object_name", value="Mysterious Stone")])
        self.assertEqual(_extract_primary_target_signature(action), "named_entity:object_name:mysterious stone")

    def test_irrelevant_single_entity(self):
        action = create_parsed_action("walk carefully", "move", [ActionEntity(type="manner", value="carefully")])
        self.assertIsNone(_extract_primary_target_signature(action)) # 'manner' is not a target type


class TestSimulateConflictDetection(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)

        self.mock_player_crud_get = patch('src.core.crud.player_crud.get', new_callable=AsyncMock).start()
        self.mock_npc_crud_get = patch('src.core.crud.npc_crud.get', new_callable=AsyncMock).start()

        self.addCleanup(patch.stopall)

        self.player1 = Player(id=1, guild_id=1, discord_id=101, character_name="P1", collected_actions_json=[])
        self.player2 = Player(id=2, guild_id=1, discord_id=102, character_name="P2", collected_actions_json=[])
        self.player3 = Player(id=3, guild_id=1, discord_id=103, character_name="P3", collected_actions_json=[])
        self.npc1 = GeneratedNpc(id=1, guild_id=1, name_i18n={"en": "N1"}, description_i18n={}, properties_json={})

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

    async def test_two_actions_same_target_non_exclusive_intents_no_conflict(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("look at npc1", "look", [ActionEntity(type="target_npc_id", value="1")]).model_dump()}, # look is not in EXCLUSIVE_INTENTS
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("examine npc1", "examine", [ActionEntity(type="target_npc_id", value="1")]).model_dump()} # examine is not in EXCLUSIVE_INTENTS
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(result, [])

    async def test_two_actions_same_target_one_exclusive_no_conflict(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("attack npc1", "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()}, # exclusive
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("look at npc1", "look", [ActionEntity(type="target_npc_id", value="1")]).model_dump()}   # not exclusive
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(result, [])


    async def test_conflict_two_exclusive_actions_same_target(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("attack npc1", "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("use item on npc1", "use", [ActionEntity(type="target_npc_id", value="1"), ActionEntity(type="item_static_id", value="potion") ]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(len(result), 1)
        conflict = result[0]
        self.assertEqual(conflict.status, ConflictStatus.SIMULATED_INTERNAL_CONFLICT)
        self.assertEqual(conflict.conflict_type, "simulated_target_attack_use_on_npc") # Intents sorted alphabetically
        self.assertEqual(len(conflict.involved_entities_json), 2)
        self.assertIn(conflict.involved_entities_json[0]["action_intent"], ["attack", "use"])
        self.assertIn(conflict.involved_entities_json[1]["action_intent"], ["attack", "use"])


    async def test_conflict_three_exclusive_actions_same_target(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2, self.player3]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("attack npc1", "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("interact with npc1", "interact", [ActionEntity(type="target_npc_id", value="1")]).model_dump()},
            {"actor_id": 3, "actor_type": "player", "parsed_action": create_parsed_action("take from npc1", "take", [ActionEntity(type="target_npc_id", value="1")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(len(result), 1) # Should still be one conflict group for this target
        conflict = result[0]
        self.assertEqual(conflict.status, ConflictStatus.SIMULATED_INTERNAL_CONFLICT)
        self.assertEqual(conflict.conflict_type, "simulated_target_attack_interact_take_on_npc")
        self.assertEqual(len(conflict.involved_entities_json), 3)


    async def test_no_target_signature_actions_no_conflict(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("look around", "look", []).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("think", "think", []).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(result, [])

    async def test_mixed_targeted_and_non_targeted_actions(self):
        self.mock_player_crud_get.side_effect = [self.player1, self.player2, self.player3]
        actions_data = [
            {"actor_id": 1, "actor_type": "player", "parsed_action": create_parsed_action("attack npc1", "attack", [ActionEntity(type="target_npc_id", value="1")]).model_dump()},
            {"actor_id": 2, "actor_type": "player", "parsed_action": create_parsed_action("look around", "look", []).model_dump()},
            {"actor_id": 3, "actor_type": "player", "parsed_action": create_parsed_action("use potion on npc1", "use", [ActionEntity(type="target_npc_id", value="1")]).model_dump()}
        ]
        result = await simulate_conflict_detection(self.mock_session, 1, actions_data)
        self.assertEqual(len(result), 1)
        conflict = result[0]
        self.assertEqual(conflict.conflict_type, "simulated_target_attack_use_on_npc")
        self.assertEqual(len(conflict.involved_entities_json), 2) # Only p1 and p3
        ids_in_conflict = {entry["entity_id"] for entry in conflict.involved_entities_json}
        self.assertIn(1, ids_in_conflict)
        self.assertIn(3, ids_in_conflict)
        self.assertNotIn(2, ids_in_conflict)

if __name__ == '__main__':
    unittest.main()


