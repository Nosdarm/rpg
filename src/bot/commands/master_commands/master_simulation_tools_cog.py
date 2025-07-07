import logging
from typing import Optional, List, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands

from src.core.database import get_db_session # For type hinting or direct use if needed
from src.core.localization_utils import get_localized_master_message # Removed get_localized_message_template as get_localized_master_message is preferred for master commands

logger = logging.getLogger(__name__)

class MasterSimulationToolsCog(commands.Cog, name="Master Simulation Tools"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterSimulationToolsCog initialized.")

    master_simulate_cmds = app_commands.Group(
        name="master_simulate",
        description="Master commands for simulating game mechanics and analyzing AI generation.",
        default_permissions=discord.Permissions(administrator=True), # Ensures only admins can see/use by default
        guild_only=True # These commands are guild-specific
    )

    master_analyze_cmds = app_commands.Group(
        name="master_analyze",
        description="Master commands for analyzing AI-generated content.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @master_simulate_cmds.command(name="check", description="Simulate a game check based on rules.")
    @app_commands.describe(
        check_type="Type of check (e.g., perception, attack_roll, stealth).",
        actor_id="ID of the entity performing the check.",
        actor_type="Type of the actor (Player, GeneratedNpc).",
        target_id="ID of the target entity (optional).",
        target_type="Type of the target entity (Player, GeneratedNpc, optional).",
        difficulty_dc="Difficulty Class (DC) for the check (optional).",
        json_context="Additional context for the check in JSON format (optional)."
    )
    async def simulate_check_command(
        self,
        interaction: discord.Interaction,
        check_type: str,
        actor_id: int,
        actor_type: str,
        target_id: Optional[int] = None,
        target_type: Optional[str] = None,
        difficulty_dc: Optional[int] = None,
        json_context: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        if guild_id is None: # Should be caught by guild_only=True, but good practice
            # This part of the code might be unreachable due to guild_only=True
            # but kept for robustness or if guild_only is ever removed.
            async with get_db_session() as temp_session: # Added session for localization
                error_msg = await get_localized_master_message(
                    temp_session, None, "common:error_guild_only_command",
                    "This command must be used in a server.", str(interaction.locale)
                )
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        from src.core.check_resolver import resolve_check, CheckError
        from src.core.crud_base_definitions import get_entity_by_id_and_type_str
        from src.models.enums import RelationshipEntityType
        import json # For parsing json_context

        parsed_context = {}
        if json_context:
            try:
                parsed_context = json.loads(json_context)
                if not isinstance(parsed_context, dict):
                    raise ValueError("JSON context must be a dictionary.")
            except (json.JSONDecodeError, ValueError) as e:
                async with get_db_session() as temp_session:
                    error_msg = await get_localized_master_message(
                        temp_session, guild_id, "simulate_check:error_invalid_json_context",
                        "Invalid JSON context: {error_details}", str(interaction.locale),
                        error_details=str(e)
                    )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

        parsed_context["lang"] = str(interaction.locale) # Add language to context for potential use in resolver

        async with get_db_session() as session:
            try:
                # Validate and convert actor_type and target_type to RelationshipEntityType enum
                try:
                    actor_rel_entity_type = RelationshipEntityType(actor_type.lower())
                except ValueError:
                    error_msg = await get_localized_master_message(
                        session, guild_id, "simulate_check:error_invalid_actor_type",
                        "Invalid actor_type: {actor_type_value}. Valid types: {valid_types}", str(interaction.locale),
                        actor_type_value=actor_type, valid_types=", ".join([e.value for e in RelationshipEntityType])
                    )
                    await interaction.followup.send(error_msg, ephemeral=True)
                    return

                target_rel_entity_type: Optional[RelationshipEntityType] = None
                if target_type:
                    try:
                        target_rel_entity_type = RelationshipEntityType(target_type.lower())
                    except ValueError:
                        error_msg = await get_localized_master_message(
                            session, guild_id, "simulate_check:error_invalid_target_type",
                            "Invalid target_type: {target_type_value}. Valid types: {valid_types}", str(interaction.locale),
                            target_type_value=target_type, valid_types=", ".join([e.value for e in RelationshipEntityType])
                        )
                        await interaction.followup.send(error_msg, ephemeral=True)
                        return

                # Fetch actor and target models (optional, resolve_check can do this too)
                # Passing them can be an optimization if already loaded or for specific testing.
                actor_model = await get_entity_by_id_and_type_str(session, entity_type_str=actor_rel_entity_type.value, entity_id=actor_id, guild_id=guild_id)
                target_model = None
                if target_id and target_rel_entity_type:
                    target_model = await get_entity_by_id_and_type_str(session, entity_type_str=target_rel_entity_type.value, entity_id=target_id, guild_id=guild_id)

                if not actor_model:
                    error_msg = await get_localized_master_message(
                        session, guild_id, "simulate_check:error_actor_not_found",
                        "Actor {actor_type_value} with ID {actor_id_value} not found.", str(interaction.locale),
                        actor_type_value=actor_rel_entity_type.value, actor_id_value=actor_id
                    )
                    await interaction.followup.send(error_msg, ephemeral=True)
                    return
                if target_id and not target_model: # Only error if target_id was given but model not found
                    error_msg = await get_localized_master_message(
                        session, guild_id, "simulate_check:error_target_not_found",
                        "Target {target_type_value} with ID {target_id_value} not found.", str(interaction.locale),
                        target_type_value=target_rel_entity_type.value if target_rel_entity_type else "Unknown", target_id_value=target_id
                    )
                    await interaction.followup.send(error_msg, ephemeral=True)
                    return


                check_result = await resolve_check(
                    session=session,
                    guild_id=guild_id,
                    check_type=check_type,
                    actor_entity_id=actor_id,
                    actor_entity_type=actor_rel_entity_type, # Pass enum member
                    actor_entity_model=actor_model,
                    target_entity_id=target_id,
                    target_entity_type=target_rel_entity_type, # Pass enum member or None
                    target_entity_model=target_model,
                    difficulty_dc=difficulty_dc,
                    check_context=parsed_context
                )

                # Format the result into an embed
                embed = discord.Embed(
                    title=await get_localized_master_message(
                        session, guild_id, "simulate_check:embed_title", "Check Simulation Result", str(interaction.locale)
                    ),
                    color=discord.Color.blue() if check_result.outcome.status in ["success", "critical_success", "critical_success_value", "value_determined"] else discord.Color.orange()
                )

                embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_check_type", "Check Type", str(interaction.locale)), value=check_result.check_type, inline=True)
                embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_actor", "Actor", str(interaction.locale)), value=f"{check_result.entity_doing_check_type.capitalize()} ID: {check_result.entity_doing_check_id}", inline=True)
                if check_result.target_entity_id and check_result.target_entity_type:
                    embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_target", "Target", str(interaction.locale)), value=f"{check_result.target_entity_type.capitalize()} ID: {check_result.target_entity_id}", inline=True)
                if check_result.difficulty_class is not None:
                    embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_dc", "DC", str(interaction.locale)), value=str(check_result.difficulty_class), inline=True)

                embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_dice_notation", "Dice Notation", str(interaction.locale)), value=check_result.dice_notation, inline=True)
                embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_raw_rolls", "Raw Rolls", str(interaction.locale)), value=str(check_result.raw_rolls), inline=True)
                embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_roll_used", "Roll Used", str(interaction.locale)), value=str(check_result.roll_used), inline=True)
                embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_total_modifier", "Total Modifier", str(interaction.locale)), value=str(check_result.total_modifier), inline=True)
                embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_final_value", "Final Value", str(interaction.locale)), value=str(check_result.final_value), inline=True)

                outcome_status_loc = await get_localized_master_message(
                    session, guild_id, f"check_outcome_status:{check_result.outcome.status}",
                    check_result.outcome.status.replace("_", " ").capitalize(), str(interaction.locale)
                )
                embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_outcome_status", "Outcome Status", str(interaction.locale)), value=outcome_status_loc, inline=True)
                embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_outcome_desc", "Outcome Description", str(interaction.locale)), value=check_result.outcome.description, inline=False)

                if check_result.modifier_details:
                    details_str = "\n".join([f"- {md.source}: {md.value} ({md.description})" for md in check_result.modifier_details])
                    if len(details_str) > 1020: details_str = details_str[:1020] + "..."
                    embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_modifier_details", "Modifier Details", str(interaction.locale)), value=details_str, inline=False)

                if check_result.rule_config_snapshot:
                    snapshot_str = json.dumps(check_result.rule_config_snapshot, indent=2, ensure_ascii=False)
                    if len(snapshot_str) > 1020: snapshot_str = snapshot_str[:1020] + "..."
                    embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_rules_snapshot", "Rules Snapshot Used", str(interaction.locale)), value=f"```json\n{snapshot_str}\n```", inline=False)

                if check_result.check_context_provided:
                    context_str = json.dumps(check_result.check_context_provided, indent=2, ensure_ascii=False)
                    if len(context_str) > 1020: context_str = context_str[:1020] + "..."
                    embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_check:field_context_provided", "Context Provided", str(interaction.locale)), value=f"```json\n{context_str}\n```", inline=False)

                await interaction.followup.send(embed=embed, ephemeral=True)

            except CheckError as e:
                error_msg = await get_localized_master_message(
                    session, guild_id, "simulate_check:error_check_resolver",
                    "Error during check resolution: {error_details}", str(interaction.locale),
                    error_details=str(e)
                )
                await interaction.followup.send(error_msg, ephemeral=True)
            except Exception as e:
                logger.error(f"Unexpected error in simulate_check_command for guild {guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_master_message(
                    session, guild_id, "common:error_generic_unexpected",
                    "An unexpected error occurred: {error_details}", str(interaction.locale),
                    error_details=str(e)
                )
                await interaction.followup.send(error_msg, ephemeral=True)

    @master_simulate_cmds.command(name="combat_action", description="Simulate a combat action.")
    @app_commands.describe(
        combat_encounter_id="ID of the existing CombatEncounter.",
        actor_id="ID of the entity performing the action.",
        actor_type="Type of the actor (Player, GeneratedNpc).",
        action_json_data="JSON string describing the action (e.g., {\"action_type\": \"attack\", \"target_id\": 102, \"target_type\": \"npc\"})."
    )
    async def simulate_combat_action_command(
        self,
        interaction: discord.Interaction,
        combat_encounter_id: int,
        actor_id: int,
        actor_type: str,
        action_json_data: str
    ):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        if guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_master_message(
                    temp_session, None, "common:error_guild_only_command",
                    "This command must be used in a server.", str(interaction.locale)
                )
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        from src.core.combat_engine import process_combat_action
        from src.models import CombatEncounter # For fetching and displaying combat state
        from src.models.combat_outcomes import CombatActionResult
        import json

        parsed_action_data: dict
        try:
            parsed_action_data = json.loads(action_json_data)
            if not isinstance(parsed_action_data, dict):
                raise ValueError("Action JSON data must be a dictionary.")
        except (json.JSONDecodeError, ValueError) as e:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_master_message(
                    temp_session, guild_id, "simulate_combat_action:error_invalid_action_json",
                    "Invalid action_json_data: {error_details}", str(interaction.locale),
                    error_details=str(e)
                )
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            # For a true dry run, we'd ideally pass a dry_run=True flag to process_combat_action.
            # If that's not possible, we wrap in a transaction that we always rollback.
            # Let's assume for now process_combat_action can be called and we'll see its direct result,
            # and the "dry run" aspect means we don't want to *commit* changes if it makes any.
            # The safest way for a dry run without modifying process_combat_action is to use a nested transaction and roll it back.

            # However, process_combat_action itself uses @transactional if it's the main entry point.
            # If called from here, it will use the session we provide.
            # The key is that this command's session block should not commit if it's a dry run.
            # The simplest approach for now: Call it, get the result, and report.
            # The "dry run" is achieved by not committing this session here, or by explicit rollback.
            # Since process_combat_action might log events which cause commits within its own scope if not careful,
            # a true dry_run flag in the engine is better.
            # For now, we will proceed as if it's a simulation that *could* write, and rely on the user
            # knowing this is for testing. A production version would need strict dry_run.

            # Let's attempt to use a nested transaction for the simulation part.
            # This requires that process_combat_action doesn't manage its own top-level transaction when called.
            # process_combat_action itself is NOT @transactional. It expects a session.
            # It calls log_event, which IS @transactional. This is problematic for a dry run.

            # Simplification for this step: We will call process_combat_action.
            # It *will* write to the DB (e.g. StoryLog via log_event).
            # A true dry run requires more significant changes to combat_engine or log_event.
            # For Task 48, "simulation" might mean "execute and see what happens" rather than "execute without side effects".
            # Let's assume "execute and see" for now.
            # ВНИМАНИЕ: Эта симуляция НЕ является dry run. Она записывает изменения в БД (например, StoryLog).
            # Для истинного dry run потребовались бы изменения в core.combat_engine и/или core.game_events.
            try:
                combat_action_result: CombatActionResult = await process_combat_action(
                    guild_id=guild_id,
                    session=session, # process_combat_action will use this session
                    combat_instance_id=combat_encounter_id,
                    actor_id=actor_id,
                    actor_type=actor_type.lower(), # Ensure lowercase for consistency
                    action_data=parsed_action_data
                )
                # If process_combat_action commits internally (e.g. via log_event), those changes ARE persisted.
                # To make this a true dry run, process_combat_action would need a dry_run flag that
                # is propagated to log_event and any other DB-writing functions.

                # Fetch the combat encounter to show its state *after* the action
                # This read should happen after process_combat_action has potentially modified it.
                # If process_combat_action committed, we'll see the new state.
                await session.commit() # Commit the changes made by process_combat_action (including log_event)
                                     # This makes it NOT a dry run.
                                     # If a dry run is strictly needed, this commit must not happen,
                                     # and log_event must also be prevented from committing.

                updated_combat_encounter = await session.get(CombatEncounter, combat_encounter_id)

                embed = discord.Embed(
                    title=await get_localized_master_message(
                        session, guild_id, "simulate_combat_action:embed_title",
                        "Combat Action Simulation Result", str(interaction.locale)
                    ),
                    color=discord.Color.green() if combat_action_result.success else discord.Color.red()
                )
                embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_combat_action:field_action_type", "Action Type", str(interaction.locale)), value=combat_action_result.action_type, inline=True)
                embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_combat_action:field_actor", "Actor", str(interaction.locale)), value=f"{combat_action_result.actor_type.capitalize()} ID: {combat_action_result.actor_id}", inline=True)
                if combat_action_result.target_id and combat_action_result.target_type:
                    embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_combat_action:field_target", "Target", str(interaction.locale)), value=f"{combat_action_result.target_type.capitalize()} ID: {combat_action_result.target_id}", inline=True)

                desc_key = "simulate_combat_action:field_outcome_desc_success" if combat_action_result.success else "simulate_combat_action:field_outcome_desc_failure"
                desc_default = "Action Succeeded." if combat_action_result.success else "Action Failed."
                embed.add_field(
                    name=await get_localized_master_message(session, guild_id, "simulate_combat_action:field_outcome_description", "Outcome", str(interaction.locale)),
                    value=combat_action_result.description_i18n.get(str(interaction.locale), combat_action_result.description_i18n.get("en", await get_localized_master_message(session, guild_id, desc_key, desc_default, str(interaction.locale)))),
                    inline=False
                )
                if combat_action_result.damage_dealt is not None:
                    embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_combat_action:field_damage_dealt", "Damage Dealt", str(interaction.locale)), value=str(combat_action_result.damage_dealt), inline=True)
                if combat_action_result.healing_done is not None:
                    embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_combat_action:field_healing_done", "Healing Done", str(interaction.locale)), value=str(combat_action_result.healing_done), inline=True)

                if combat_action_result.check_result:
                    cr = combat_action_result.check_result
                    cr_outcome_loc = await get_localized_master_message(
                        session, guild_id, f"check_outcome_status:{cr.outcome.status}",
                        cr.outcome.status.replace("_", " ").capitalize(), str(interaction.locale)
                    )
                    cr_text = await get_localized_master_message(
                        session, guild_id, "simulate_combat_action:check_result_details",
                        "Check: {final_value} vs DC {dc} ({outcome_status_loc}). Roll: {roll}({dice})+{mod}",
                        str(interaction.locale),
                        final_value=cr.final_value, dc=cr.difficulty_class, outcome_status_loc=cr_outcome_loc,
                        roll=cr.roll_used, dice=cr.dice_notation, mod=cr.total_modifier
                    )
                    embed.add_field(name=await get_localized_master_message(session, guild_id, "simulate_combat_action:field_check_result", "Check Result", str(interaction.locale)), value=cr_text, inline=False)

                if updated_combat_encounter and updated_combat_encounter.participants_json:
                    participants_str = json.dumps(updated_combat_encounter.participants_json.get("entities", []), indent=2, ensure_ascii=False)
                    if len(participants_str) > 1018: participants_str = participants_str[:1018] + "..."
                    embed.add_field(
                        name=await get_localized_master_message(session, guild_id, "simulate_combat_action:field_participants_state", "Participants State (Post-Action)", str(interaction.locale)),
                        value=f"```json\n{participants_str}\n```",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=await get_localized_master_message(session, guild_id, "simulate_combat_action:field_participants_state", "Participants State (Post-Action)", str(interaction.locale)),
                        value=await get_localized_master_message(session, guild_id, "simulate_combat_action:value_not_found", "Not found or no participants.", str(interaction.locale)),
                        inline=False)


                await interaction.followup.send(embed=embed, ephemeral=True)

            except Exception as e:
                logger.error(f"Unexpected error in simulate_combat_action_command for guild {guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_master_message(
                    session, guild_id, "common:error_generic_unexpected",
                    "An unexpected error occurred: {error_details}", str(interaction.locale),
                    error_details=str(e)
                )
                await interaction.followup.send(error_msg, ephemeral=True)


    # Placeholder for /master_analyze ai_generation
    # @master_analyze_cmds.command(name="ai_generation", description="Analyze AI generated content against rules.")
    # @app_commands.describe(generation_type="Type of content to analyze (e.g., npc, quest).")
    # @is_administrator()
    # async def analyze_ai_generation_command(self, interaction: discord.Interaction, generation_type: str):
    #     if interaction.guild_id is None:
    #         await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
    #         return
    #     await interaction.response.send_message(f"Analyzing AI generation for '{generation_type}' in guild {interaction.guild_id}. (Not implemented yet)", ephemeral=True)


async def setup(bot: commands.Bot):
    cog = MasterSimulationToolsCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterSimulationToolsCog loaded and added to bot.")

# Example of how to use get_localized_master_message (for future reference within this Cog)
# async def _example_usage_localization(interaction: discord.Interaction):
#     async with get_db_session() as session:
#         msg = await get_localized_master_message(
#             session,
#             interaction.guild_id, # type: ignore
#             message_key="example:success",
#             default_template="Operation successful for {entity_name}.",
#             locale=str(interaction.locale),
#             entity_name="Test Entity"
#         )
#     await interaction.response.send_message(msg, ephemeral=True)
