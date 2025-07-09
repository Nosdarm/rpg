import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord # type: ignore
from discord.ext import commands # Added for commands.Bot

from src.bot.commands.master_commands.master_simulation_tools_cog import MasterSimulationToolsCog
from src.models.enums import RelationshipEntityType
from src.models.check_results import CheckResult, CheckOutcome, ModifierDetail
from src.models.combat_outcomes import CombatActionResult # Added for the new test

# Mock discord.Interaction and other discord objects as needed
class MockGuild:
    def __init__(self, id: int):
        self.id = id

class MockUser:
    def __init__(self, id: int):
        self.id = id

class MockInteraction:
    def __init__(self, guild_id: int, locale_str: str = "en"):
        self.guild_id = guild_id
        self.guild = MockGuild(guild_id) if guild_id else None
        self.user = MockUser(12345) # Mock user
        # Create a mock for discord.Locale
        mock_locale = MagicMock(spec=discord.Locale)
        mock_locale.__str__ = MagicMock(return_value=locale_str) # Ensures str(interaction.locale) returns the string
        self.locale = mock_locale
        self.response = AsyncMock()
        self.response.defer = AsyncMock()
        self.followup = AsyncMock()
        self.followup.send = AsyncMock()

class TestMasterSimulationToolsCog(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.bot_mock = AsyncMock(spec=commands.Bot) # Use commands.Bot
        self.cog = MasterSimulationToolsCog(self.bot_mock)
        self.mock_db_session = AsyncMock()

    @patch('src.bot.commands.master_commands.master_simulation_tools_cog.get_db_session')
    @patch('src.core.check_resolver.resolve_check')
    @patch('src.core.crud_base_definitions.get_entity_by_id_and_type_str')
    async def test_simulate_check_command_success(
        self,
        mock_get_entity_by_id_and_type_str: AsyncMock,
        mock_resolve_check: AsyncMock,
        mock_get_db_session_cm: MagicMock
    ):
        mock_get_db_session_cm.return_value.__aenter__.return_value = self.mock_db_session
        mock_get_db_session_cm.return_value.__aexit__.return_value = None
        mock_interaction = MockInteraction(guild_id=1, locale_str="en")
        mock_actor_model = MagicMock()
        mock_actor_model.name = "Test Actor"
        mock_get_entity_by_id_and_type_str.return_value = mock_actor_model
        mock_check_result = CheckResult(
            guild_id=1, check_type="perception", entity_doing_check_id=101,
            entity_doing_check_type=RelationshipEntityType.PLAYER.value,
            target_entity_id=None, target_entity_type=None, difficulty_class=15, # type: ignore[reportCallIssue]
            dice_notation="1d20", raw_rolls=[10], roll_used=10, total_modifier=2,
            modifier_details=[ModifierDetail(source="test", value=2, description="Test mod")],
            final_value=12, outcome=CheckOutcome(status="failure", description="Failed perception check."),
            rule_config_snapshot={"test_rule": "value"}, check_context_provided={"lang": "en"}
        )
        mock_resolve_check.return_value = mock_check_result
        async def mock_get_localized_master_message(session, guild_id, key, default, locale, **kwargs):
            return default.format(**kwargs) if kwargs else default
        with patch('src.bot.commands.master_commands.master_simulation_tools_cog.get_localized_master_message', side_effect=mock_get_localized_master_message):
            from typing import cast
            # The first argument to command.callback is the Interaction,
            # `self` (the cog instance) is bound by the decorator.
            await self.cog.simulate_check_command.callback( # type: ignore[arg-type]
                self.cog,
                cast(discord.Interaction, mock_interaction), # Interaction
                "perception", # check_type
                101,          # actor_id
                "player",     # actor_type
                None,         # target_id
                None,         # target_type
                15            # difficulty_dc
                # json_context is omitted as it's optional and not used here
            )
        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_resolve_check.assert_called_once()
        called_args, called_kwargs = mock_resolve_check.call_args
        self.assertEqual(called_kwargs['actor_entity_type'], RelationshipEntityType.PLAYER)
        mock_interaction.followup.send.assert_called_once()
        sent_embed = mock_interaction.followup.send.call_args[1].get('embed')
        self.assertIsNotNone(sent_embed)
        self.assertEqual(sent_embed.title, "Check Simulation Result")
        self.assertIn("perception", [field.value for field in sent_embed.fields if field.name == "Check Type"])
        self.assertIn("12", [field.value for field in sent_embed.fields if field.name == "Final Value"])

    @patch('src.bot.commands.master_commands.master_simulation_tools_cog.get_db_session')
    async def test_simulate_check_invalid_json_context(self, mock_get_db_session_cm: MagicMock):
        mock_get_db_session_cm.return_value.__aenter__.return_value = self.mock_db_session
        mock_get_db_session_cm.return_value.__aexit__.return_value = None
        mock_interaction = MockInteraction(guild_id=1, locale_str="en")
        async def mock_get_localized_master_message(session, guild_id, key, default, locale, **kwargs):
            return default.format(**kwargs) if kwargs else default
        with patch('src.bot.commands.master_commands.master_simulation_tools_cog.get_localized_master_message', side_effect=mock_get_localized_master_message):
            from typing import cast
            await self.cog.simulate_check_command.callback( # type: ignore[arg-type]
                self.cog,
                cast(discord.Interaction, mock_interaction), # Interaction
                "test", 1, "player", # Positional: check_type, actor_id, actor_type
                json_context="not_a_valid_json" # Keyword argument
            )
        mock_interaction.followup.send.assert_called_once()
        args, _ = mock_interaction.followup.send.call_args
        self.assertIn("Invalid JSON context", args[0])

    @patch('src.bot.commands.master_commands.master_simulation_tools_cog.get_db_session')
    @patch('src.core.crud_base_definitions.get_entity_by_id_and_type_str', new_callable=AsyncMock)
    async def test_simulate_check_actor_not_found(
        self, mock_get_entity_by_id_and_type_str: AsyncMock, mock_get_db_session_cm: MagicMock
    ):
        mock_get_db_session_cm.return_value.__aenter__.return_value = self.mock_db_session
        mock_get_db_session_cm.return_value.__aexit__.return_value = None
        mock_interaction = MockInteraction(guild_id=1, locale_str="en")
        mock_get_entity_by_id_and_type_str.return_value = None
        async def mock_get_localized_master_message(session, guild_id, key, default, locale, **kwargs):
            return default.format(**kwargs) if kwargs else default
        with patch('src.bot.commands.master_commands.master_simulation_tools_cog.get_localized_master_message', side_effect=mock_get_localized_master_message):
            from typing import cast
            await self.cog.simulate_check_command.callback( # type: ignore[arg-type]
                self.cog,
                cast(discord.Interaction, mock_interaction), # Interaction
                "test", # check_type
                999,    # actor_id
                "player" # actor_type
                # Optional args (target_id, target_type, difficulty_dc, json_context) are omitted
            )
        mock_interaction.followup.send.assert_called_once()
        args, _ = mock_interaction.followup.send.call_args
        self.assertIn("Actor player with ID 999 not found.", args[0])

    @patch('src.bot.commands.master_commands.master_simulation_tools_cog.get_db_session')
    @patch('src.core.combat_engine.process_combat_action')
    # Patching CombatActionResult at the location it's imported in the cog, if it were a class.
    # However, it's a Pydantic model, so we typically mock the function returning it.
    # If we need to assert its creation, we'd patch it where it's instantiated.
    # For this test, mocking process_combat_action's return value is sufficient.
    async def test_simulate_combat_action_command_success(
        self,
        mock_process_combat_action: AsyncMock,
        mock_get_db_session_cm: MagicMock
    ):
        mock_get_db_session_cm.return_value.__aenter__.return_value = self.mock_db_session
        mock_get_db_session_cm.return_value.__aexit__.return_value = None
        mock_interaction = MockInteraction(guild_id=1, locale_str="en")

        # Create a mock that can be configured like a Pydantic model instance
        mock_action_result_instance = MagicMock(spec=CombatActionResult)
        mock_action_result_instance.success = True
        mock_action_result_instance.action_type = "attack"
        mock_action_result_instance.actor_type = "player"
        mock_action_result_instance.actor_id = 101
        mock_action_result_instance.target_id = 201
        mock_action_result_instance.target_type = "npc"
        mock_action_result_instance.description_i18n = {"en": "Player attacks NPC."}
        mock_action_result_instance.damage_dealt = 10
        mock_action_result_instance.healing_done = None
        mock_action_result_instance.check_result = None
        mock_process_combat_action.return_value = mock_action_result_instance

        mock_combat_encounter = MagicMock()
        mock_combat_encounter.participants_json = {"entities": [{"id": 101, "type": "player", "hp": 50}, {"id": 201, "type": "npc", "hp": 30}]}
        self.mock_db_session.get = AsyncMock(return_value=mock_combat_encounter)
        self.mock_db_session.commit = AsyncMock()

        action_data_str = json.dumps({"action_type": "attack", "target_id": 201, "target_type": "npc"})

        async def mock_get_localized_master_message(session, guild_id, key, default, locale, **kwargs):
            return default.format(**kwargs) if kwargs else default

        with patch('src.bot.commands.master_commands.master_simulation_tools_cog.get_localized_master_message', side_effect=mock_get_localized_master_message):
            from typing import cast
            await self.cog.simulate_combat_action_command.callback( # type: ignore[arg-type]
                self.cog,
                cast(discord.Interaction, mock_interaction), # Interaction
                1,          # combat_encounter_id
                101,        # actor_id
                "player",   # actor_type
                action_data_str # action_json_data
                # dry_run is optional and defaults to False
            )

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_process_combat_action.assert_called_once()
        called_kwargs = mock_process_combat_action.call_args.kwargs
        self.assertEqual(called_kwargs['guild_id'], 1)
        self.assertEqual(called_kwargs['combat_instance_id'], 1)
        self.assertEqual(called_kwargs['actor_id'], 101)
        self.assertEqual(called_kwargs['actor_type'], "player")
        self.assertEqual(called_kwargs['action_data'], json.loads(action_data_str))

        self.mock_db_session.commit.assert_called_once()
        mock_interaction.followup.send.assert_called_once()
        sent_embed = mock_interaction.followup.send.call_args[1].get('embed')
        self.assertIsNotNone(sent_embed)
        self.assertEqual(sent_embed.title, "Combat Action Simulation Result")
        outcome_desc_field = next((f for f in sent_embed.fields if f.name == "Outcome"), None)
        self.assertIsNotNone(outcome_desc_field)
        self.assertIn("Player attacks NPC.", outcome_desc_field.value) # type: ignore
        damage_field = next((f for f in sent_embed.fields if f.name == "Damage Dealt"), None)
        self.assertIsNotNone(damage_field)
        self.assertEqual(damage_field.value, "10") # type: ignore

if __name__ == "__main__":
    unittest.main()
