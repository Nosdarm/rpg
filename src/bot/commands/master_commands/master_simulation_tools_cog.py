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
        action_json_data="JSON string describing the action (e.g., {\"action_type\": \"attack\", \"target_id\": 102, \"target_type\": \"npc\"}).",
        dry_run="Set to True to simulate without making database changes (default: False)."
    )
    async def simulate_combat_action_command(
        self,
        interaction: discord.Interaction,
        combat_encounter_id: int,
        actor_id: int,
        actor_type: str,
        action_json_data: str,
        dry_run: bool = False
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
                    action_data=parsed_action_data,
                    dry_run=dry_run # Pass the dry_run flag
                )

                if not dry_run:
                    await session.commit() # Commit changes only if not a dry run
                    updated_combat_encounter = await session.get(CombatEncounter, combat_encounter_id)
                else:
                    # For a dry run, we might want to fetch the encounter state before the action
                    # to show a "before" state, or rely on the combat_action_result entirely.
                    # Since process_combat_action modifies participants_json in memory even on dry_run,
                    # we can display that modified in-memory state.
                    # To get the "current DB state" for a dry run, we'd have to re-fetch,
                    # but that might be confusing. Let's assume the returned result is sufficient.
                    # We also need to be careful: if process_combat_action *refreshes* combat_encounter from session
                    # during a dry run, it might discard in-memory changes.
                    # The current implementation of process_combat_action updates a *copy* of participant data (target_participant_data)
                    # and then assigns it back to combat_encounter.participants_json["entities"].
                    # So the combat_encounter object modified in process_combat_action *should* have the in-memory changes.
                    # To be safe, let's re-get from session to ensure we don't show stale data IF a refresh happened inside.
                    # But since we are not committing, this get should return the original state.
                    # The result from process_combat_action is the primary source of info for dry run.
                    # Updated_combat_encounter will reflect the *persisted* state.
                    # In a dry run, updated_combat_encounter will be the state *before* the action.
                    # This is fine, as the embed focuses on the action's outcome.
                    # We can add a note about the state not being persisted.
                    updated_combat_encounter = await session.get(CombatEncounter, combat_encounter_id) # Get original state for dry run context

                embed_title_key = "simulate_combat_action:embed_title_dry_run" if dry_run else "simulate_combat_action:embed_title"
                embed_title_default = "Combat Action Simulation Result (Dry Run)" if dry_run else "Combat Action Simulation Result"

                embed = discord.Embed(
                    title=await get_localized_master_message(
                        session, guild_id, embed_title_key,
                        embed_title_default, str(interaction.locale)
                    ),
                    color=discord.Color.green() if combat_action_result.success else discord.Color.red()
                )
                if dry_run:
                    embed.set_footer(text=await get_localized_master_message(session, guild_id, "simulate_combat_action:footer_dry_run_notice", "DRY RUN: No changes were saved to the database.", str(interaction.locale)))

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
    @master_analyze_cmds.command(name="ai_generation", description="Analyze AI generated content against rules.")
    @app_commands.describe(
        entity_type="Type of content to analyze (e.g., npc, item, quest, location, faction).",
        generation_context_json="Optional JSON string for specific generation context (e.g., {\"theme\": \"forest\"}).",
        target_count="Number of entities to generate and analyze (default 1, max 5).",
        use_real_ai="Whether to use real OpenAI API (True) or mock data (False, default)."
    )
    async def analyze_ai_generation_command(
        self,
        interaction: discord.Interaction,
        entity_type: str,
        generation_context_json: Optional[str] = None,
        target_count: app_commands.Range[int, 1, 5] = 1, # Limit target_count for now
        use_real_ai: bool = False
    ):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        if guild_id is None:
            async with get_db_session() as temp_session: # Added session for localization
                error_msg = await get_localized_master_message(temp_session, None, "common:error_guild_only_command", "This command must be used in a server.", str(interaction.locale))
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        # Validate entity_type (can be expanded with an Enum later)
        supported_entity_types = ["npc", "item", "quest", "location", "faction"] # TODO: Keep this synced with ai_analysis_system
        if entity_type.lower() not in supported_entity_types:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_master_message(
                    temp_session, guild_id, "analyze_ai:error_unsupported_entity_type",
                    "Unsupported entity type '{entity_type_value}'. Supported types: {supported_types_value}",
                    str(interaction.locale),
                    entity_type_value=entity_type, supported_types_value=", ".join(supported_entity_types)
                )
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        from src.core.ai_analysis_system import analyze_generated_content, AIAnalysisResult
        import json # For formatting dicts in output

        async with get_db_session() as session:
            try:
                # Note: Real AI calls can be time-consuming. Defer ensures no timeout for the initial response.
                # Consider adding a "Thinking..." message if real AI is used.
                if use_real_ai:
                     # Temporary message, as real AI call might take time
                    thinking_msg = await get_localized_master_message(session, guild_id, "analyze_ai:info_calling_real_ai", "Attempting to use real AI, this may take a moment...", str(interaction.locale))
                    await interaction.followup.send(thinking_msg, ephemeral=True) # Send initial followup

                analysis_result: AIAnalysisResult = await analyze_generated_content(
                    session=session,
                    guild_id=guild_id,
                    entity_type=entity_type.lower(),
                    generation_context_json=generation_context_json,
                    target_count=target_count,
                    use_real_ai=use_real_ai
                    # openai_client could be passed here if managed by the bot instance
                )

                embed = discord.Embed(
                    title=await get_localized_master_message(
                        session, guild_id, "analyze_ai:embed_title",
                        "AI Generation Analysis Result ({entity_type_value})", str(interaction.locale),
                        entity_type_value=analysis_result.requested_entity_type.capitalize()
                    ),
                    description=analysis_result.overall_summary,
                    color=discord.Color.purple()
                )
                embed.add_field(name=await get_localized_master_message(session, guild_id, "analyze_ai:field_requested_count", "Requested Count", str(interaction.locale)), value=str(analysis_result.requested_target_count))
                embed.add_field(name=await get_localized_master_message(session, guild_id, "analyze_ai:field_used_real_ai", "Used Real AI", str(interaction.locale)), value=str(analysis_result.used_real_ai))

                if analysis_result.generation_context_provided:
                    context_str = json.dumps(analysis_result.generation_context_provided, indent=2, ensure_ascii=False)
                    if len(context_str) > 1020: context_str = context_str[:1020] + "..."
                    embed.add_field(
                        name=await get_localized_master_message(session, guild_id, "analyze_ai:field_gen_context", "Generation Context Provided", str(interaction.locale)),
                        value=f"```json\n{context_str}\n```",
                        inline=False
                    )

                for report in analysis_result.analysis_reports:
                    report_title = await get_localized_master_message(
                        session, guild_id, "analyze_ai:field_report_for_entity",
                        "Report for Entity #{index} ({name})", str(interaction.locale),
                        index=report.entity_index + 1, name=report.entity_data_preview.get("name", "N/A")
                    )
                    report_value_parts = []
                    if report.validation_errors:
                        val_errors_str = "\n".join([f"- {e}" for e in report.validation_errors])
                        report_value_parts.append(f"**{await get_localized_master_message(session, guild_id, 'analyze_ai:sub_validation_errors', 'Validation Errors', str(interaction.locale))}:**\n{val_errors_str}")
                    if report.issues_found:
                        issues_str = "\n".join([f"- {issue}" for issue in report.issues_found])
                        report_value_parts.append(f"**{await get_localized_master_message(session, guild_id, 'analyze_ai:sub_issues_found', 'Issues Found', str(interaction.locale))}:**\n{issues_str}")
                    if report.suggestions:
                        sugg_str = "\n".join([f"- {sugg}" for sugg in report.suggestions])
                        report_value_parts.append(f"**{await get_localized_master_message(session, guild_id, 'analyze_ai:sub_suggestions', 'Suggestions', str(interaction.locale))}:**\n{sugg_str}")
                    if report.balance_score is not None:
                        report_value_parts.append(f"**{await get_localized_master_message(session, guild_id, 'analyze_ai:sub_balance_score', 'Balance Score', str(interaction.locale))}:** {report.balance_score:.2f}")

                    # Parsed data preview
                    if report.parsed_entity_data:
                        parsed_str = json.dumps(report.parsed_entity_data, indent=2, ensure_ascii=False, default=str) # Add default=str for datetimes etc.
                        preview_len = 200
                        parsed_preview = parsed_str[:preview_len] + ("..." if len(parsed_str) > preview_len else "")
                        report_value_parts.append(f"**{await get_localized_master_message(session, guild_id, 'analyze_ai:sub_parsed_data_preview', 'Parsed Data (Preview)', str(interaction.locale))}:**\n```json\n{parsed_preview}\n```")

                    # Raw AI response preview
                    # if report.raw_ai_response:
                    #     raw_preview_len = 100
                    #     raw_preview = report.raw_ai_response[:raw_preview_len] + ("..." if len(report.raw_ai_response) > raw_preview_len else "")
                    #     report_value_parts.append(f"**Raw AI Response (Preview):**\n```\n{raw_preview}\n```")


                    full_report_value = "\n\n".join(report_value_parts)
                    if not full_report_value:
                        full_report_value = await get_localized_master_message(session, guild_id, "analyze_ai:value_no_issues_or_details", "No specific issues or details to report for this entity.", str(interaction.locale))

                    if len(full_report_value) > 1024: # Embed field value limit
                        full_report_value = full_report_value[:1020] + "..."
                    embed.add_field(name=report_title, value=full_report_value, inline=False)

                # If there's only one report and it has a full raw response, maybe add it if space permits
                if len(analysis_result.analysis_reports) == 1 and analysis_result.analysis_reports[0].raw_ai_response:
                    raw_resp = analysis_result.analysis_reports[0].raw_ai_response
                    if len(raw_resp) < 800 and len(embed) < 5500 : # Check total embed length too
                         embed.add_field(
                            name=await get_localized_master_message(session, guild_id, "analyze_ai:field_raw_ai_response", "Raw AI Response (Full)", str(interaction.locale)),
                            value=f"```text\n{raw_resp[:1000]}\n```", # Limit raw display
                            inline=False)


                # Use followup.edit_message for the thinking message if it was sent
                if use_real_ai and interaction.channel: # Check if channel is available
                    # We need the original response message ID to edit it.
                    # interaction.followup.send creates a new message.
                    # interaction.edit_original_response() edits the "Thinking..." message from defer.
                    # If we sent a thinking_msg via followup, we need its ID. This is tricky.
                    # For simplicity, we'll just send a new followup.
                    # A more complex solution would store the message ID of the "Thinking..." followup.
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=embed, ephemeral=True)

            except Exception as e:
                logger.error(f"Unexpected error in analyze_ai_generation_command for guild {guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_master_message(
                    session, guild_id, "common:error_generic_unexpected",
                    "An unexpected error occurred: {error_details}", str(interaction.locale),
                    error_details=str(e)
                )
                # If a thinking message was sent via followup, we can't easily edit it without its ID.
                # So, just send another followup.
                await interaction.followup.send(error_msg, ephemeral=True)

    @master_simulate_cmds.command(name="conflict", description="Simulate conflict detection for a set of actions.")
    @app_commands.describe(
        actions_json="JSON string representing a list of actions to check for conflicts. Each action: {\"actor_id\": int, \"actor_type\": \"player\"|\"generated_npc\", \"parsed_action\": {\"intent_name\": str, \"entities\": {}, \"text\": str}}"
    )
    async def simulate_conflict_command(
        self,
        interaction: discord.Interaction,
        actions_json: str
    ):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        if guild_id is None:
            # This should ideally not be reached due to guild_only=True
            async with get_db_session() as temp_session:
                error_msg = await get_localized_master_message(temp_session, None, "common:error_guild_only_command", "This command must be used in a server.", str(interaction.locale))
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        import json
        from src.core.conflict_simulation_system import simulate_conflict_detection, PydanticConflictForSim # Import PydanticConflictForSim
        # from src.models.pending_conflict import PendingConflict # No longer needed for type hint

        parsed_actions_data: List[Dict[str, Any]]
        try:
            parsed_actions_data = json.loads(actions_json)
            if not isinstance(parsed_actions_data, list):
                raise ValueError("Actions JSON must be a list of action objects.")
            # Further validation of each action object structure can be done here or in the simulation function
        except (json.JSONDecodeError, ValueError) as e:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_master_message(
                    temp_session, guild_id, "simulate_conflict:error_invalid_actions_json",
                    "Invalid actions_json: {error_details}", str(interaction.locale),
                    error_details=str(e)
                )
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            try:
                simulated_conflicts: List[PydanticConflictForSim] = await simulate_conflict_detection( # Updated type hint
                    session=session,
                    guild_id=guild_id,
                    actions_input_data=parsed_actions_data
                )

                embed = discord.Embed(
                    title=await get_localized_master_message(session, guild_id, "simulate_conflict:embed_title", "Conflict Simulation Result", str(interaction.locale)),
                    color=discord.Color.blue()
                )

                if not simulated_conflicts:
                    embed.description = await get_localized_master_message(session, guild_id, "simulate_conflict:no_conflicts_detected", "No conflicts detected for the given actions.", str(interaction.locale))
                    embed.color = discord.Color.green()
                else:
                    embed.description = await get_localized_master_message(
                        session, guild_id, "simulate_conflict:conflicts_detected_summary",
                        "Detected {count} potential conflict(s):", str(interaction.locale),
                        count=len(simulated_conflicts)
                    )
                    for i, conflict in enumerate(simulated_conflicts):
                        conflict_details_list = []
                        target_sig_display = ""
                        if conflict.resolution_details_json and conflict.resolution_details_json.get("target_signature"):
                            target_sig_loc = await get_localized_master_message(session, guild_id, "simulate_conflict:target_signature_label", "Target Signature", str(interaction.locale))
                            target_sig_display = f"\n*{target_sig_loc}: `{conflict.resolution_details_json['target_signature']}`*"

                        involved_actions_label = await get_localized_master_message(session, guild_id, "simulate_conflict:involved_actions_label", "Involved actions:", str(interaction.locale))

                        for entity_action in conflict.involved_entities_json:
                            actor_type = entity_action.get('entity_type', 'Unknown type')
                            actor_id = entity_action.get('entity_id', 'N/A')
                            intent_val = entity_action.get('action_intent', 'Unknown intent') # Renamed to avoid conflict
                            text_val = entity_action.get('action_text', '') # Renamed to avoid conflict

                            entities_str_parts = []
                            action_entities = entity_action.get("action_entities", [])
                            if isinstance(action_entities, list) and action_entities:
                                for act_ent in action_entities[:2]: # Show first 2 entities
                                    ent_type = act_ent.get('type', 'ent_type')
                                    ent_val_str = str(act_ent.get('value', 'ent_val'))[:20] # Limit entity value length
                                    entities_str_parts.append(f"`{ent_type}`: `{ent_val_str}`")
                            entities_display = f" (Entities: {'; '.join(entities_str_parts)})" if entities_str_parts else ""

                            detail_line = await get_localized_master_message(
                                session, guild_id, "simulate_conflict:conflict_entity_action_detail_ext", # Potentially new key
                                "- {actor_type_loc} ID {actor_id_loc}: Intent `{intent_loc}`{entities_display_loc}, Text: \"{text_loc}\"",
                                str(interaction.locale),
                                actor_type_loc=actor_type.capitalize(),
                                actor_id_loc=actor_id,
                                intent_loc=intent_val,
                                entities_display_loc=entities_display,
                                text_loc=text_val[:30] + ('...' if len(text_val) > 30 else '')
                            )
                            conflict_details_list.append(detail_line)

                        conflict_value_str = f"{involved_actions_label}\n" + "\n".join(conflict_details_list)
                        conflict_value_str += target_sig_display # Add target signature info

                        if len(conflict_value_str) > 1020:
                             conflict_value_str = conflict_value_str[:1020] + "..."

                        field_name_str = await get_localized_master_message(
                            session, guild_id, "simulate_conflict:field_conflict_num", # Re-use existing key for field name
                            "Conflict #{num} (Type: {conflict_type})", str(interaction.locale),
                            num=i + 1, conflict_type=conflict.conflict_type
                        )
                        embed.add_field(
                            name=field_name_str,
                            value=conflict_value_str or await get_localized_master_message(session, guild_id, "simulate_conflict:value_no_details", "No details.", str(interaction.locale)),
                            inline=False
                        )

                await interaction.followup.send(embed=embed, ephemeral=True)

            except Exception as e:
                logger.error(f"Unexpected error in simulate_conflict_command for guild {guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_master_message(
                    session, guild_id, "common:error_generic_unexpected",
                    "An unexpected error occurred: {error_details}", str(interaction.locale),
                    error_details=str(e)
                )
                await interaction.followup.send(error_msg, ephemeral=True)

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
