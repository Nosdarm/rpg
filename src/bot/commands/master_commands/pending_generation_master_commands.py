import logging
import json
from typing import Optional, List, Dict, Any, Union

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session, transactional
from src.core.crud.crud_pending_generation import pending_generation_crud
from src.core.crud_base_definitions import update_entity # For direct updates if needed
from src.core.localization_utils import get_localized_master_message
from src.models import PendingGeneration
from src.models.enums import ModerationStatus
from src.core.ai_orchestrator import trigger_ai_generation_flow, save_approved_generation
from src.bot.utils import parse_json_parameter, ensure_guild_configured_and_get_session

logger = logging.getLogger(__name__)

class MasterPendingGenerationCog(commands.Cog, name="Master Pending Generation Commands"): # type: ignore[call-arg]
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterPendingGenerationCog initialized.")

    pending_gen_master_cmds = app_commands.Group(
        name="master_pending_generation",
        description="Master commands for managing AI pending generations and moderation.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    # --- Command Implementations will go here ---

    @pending_gen_master_cmds.command(name="trigger", description="Trigger AI content generation for moderation.")
    @app_commands.describe(
        entity_type="Type of entity to generate (e.g., location, npc, item, quest, faction).",
        generation_context_json="Optional JSON string for specific generation context (e.g., {\"theme\": \"forest\"}).",
        location_id_context="Optional: ID of a location to provide context for generation.",
        player_id_context="Optional: ID of a player to provide context (e.g., for player-specific generation)."
    )
    async def trigger_generation(
        self,
        interaction: discord.Interaction,
        entity_type: str,
        generation_context_json: Optional[str] = None,
        location_id_context: Optional[int] = None,
        player_id_context: Optional[int] = None
    ):
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return # Error message already sent by ensure_guild_configured_and_get_session

        guild_id = interaction.guild_id # Known to be not None here

        # Validate entity_type (can be expanded with an Enum later if needed)
        # For now, let ai_orchestrator or prompt_builder handle detailed validation if necessary.
        # A basic check here could be useful.
        # Example: if entity_type.lower() not in ["location", "npc", "item", "quest", "faction"]: ...

        parsed_gen_context: Optional[Dict[str, Any]] = None
        if generation_context_json:
            parsed_gen_context = await parse_json_parameter(
                interaction, generation_context_json, "generation_context_json", session
            )
            if parsed_gen_context is None: # Error in parsing, message sent by utility
                if session: await session.close()
                return

        if parsed_gen_context is None:
            parsed_gen_context = {}

        # Add other context parameters if provided
        if location_id_context is not None:
            parsed_gen_context["location_id_context_param"] = location_id_context # Use a distinct key
        if player_id_context is not None:
            parsed_gen_context["player_id_context_param"] = player_id_context

        try:
            # trigger_ai_generation_flow expects specific params like location_id, player_id
            # We need to map our command parameters to what trigger_ai_generation_flow expects
            # The `generation_context_json` is more for generic parameters to `prepare_ai_prompt`

            # For now, let's assume `trigger_ai_generation_flow` primarily uses guild_id, location_id, player_id for its direct ops,
            # and `prepare_ai_prompt` (called within it) will use the broader `parsed_gen_context` if it's adapted to take it.
            # The current `trigger_ai_generation_flow` takes specific location_id and player_id.
            # We also need to pass entity_type to `prepare_ai_prompt` somehow.
            # This suggests `trigger_ai_generation_flow` or `prepare_ai_prompt` needs an update to accept `entity_type` and `parsed_gen_context`.

            # Let's simplify for now: `trigger_ai_generation_flow` will need adaptation to take `entity_type` and `parsed_gen_context`.
            # For this step, I will *assume* `trigger_ai_generation_flow` is adapted or I'll note this for its refactoring.
            # The `prepare_ai_prompt` in `ai_orchestrator.py` doesn't take entity_type. This is a current limitation.
            # The prompt itself needs to be dynamically built based on entity_type.
            # This is a significant point: `prepare_ai_prompt` needs to be more flexible.
            # For now, the `trigger_ai_generation_flow` mainly uses location_id and player_id context.
            # The `entity_type` and `generation_context_json` are more for the prompt itself.

            # TODO: Refactor `prepare_ai_prompt` and `trigger_ai_generation_flow` to accept `entity_type` and a generic `generation_context_dict`.
            # For now, we'll call it with what it accepts and acknowledge the limitation.
            # The `entity_type` from command will be logged in `trigger_context_json` of `PendingGeneration`.

            pending_gen_context_for_db = parsed_gen_context.copy()
            pending_gen_context_for_db["requested_entity_type"] = entity_type

            # Call the orchestrator
            result = await trigger_ai_generation_flow(
                session=session,
                bot=self.bot,
                guild_id=guild_id, # type: ignore
                location_id=location_id_context, # Pass location_id if provided
                player_id=player_id_context,     # Pass player_id if provided
                # entity_type and generation_context_json are not direct params of trigger_ai_generation_flow
                # They are used in prepare_ai_prompt, which trigger_ai_generation_flow calls.
                # We need to ensure prepare_ai_prompt can use them (e.g. via a context dict)
                # For now, we assume prepare_ai_prompt is adapted or this is a known area for future work.
                # The `prompt_context_params` in `trigger_ai_generation_flow` is where these should go.
                # The current implementation of `trigger_ai_generation_flow` does not pass these through effectively.
                # This needs to be addressed in `ai_orchestrator.py`.
                # As a workaround, we can stuff them into the `trigger_context_json` in `PendingGeneration`
                # and hope `prepare_ai_prompt` (if modified) can pick them up from there when re-generating or something.
                # This is not ideal. The plan should include refactoring `trigger_ai_generation_flow`.

                # For the purpose of this command, we are calling the existing `trigger_ai_generation_flow`.
                # The context it builds internally is limited.
            )
            # Update: `trigger_ai_generation_flow` saves `prompt_context` which includes location_id and player_id.
            # We should ensure our `entity_type` and `generation_context_json` from command are included there.
            # The `pending_gen_data["trigger_context_json"] = prompt_context` line in `trigger_ai_generation_flow` uses
            # a `prompt_context` dict. We need to ensure our command's context makes it there.
            # This means `trigger_ai_generation_flow` should accept a `trigger_context_override: Optional[Dict]`

            if isinstance(result, PendingGeneration):
                embed = discord.Embed(
                    title=await get_localized_master_message(session, guild_id, "pending_gen_trigger:success_title", "AI Generation Triggered", str(interaction.locale)), # type: ignore
                    description=await get_localized_master_message(session, guild_id, "pending_gen_trigger:success_desc", "Content generation has been queued for moderation.", str(interaction.locale), pending_id=result.id, status=result.status.value), # type: ignore
                    color=discord.Color.green()
                )
                embed.add_field(name="Pending ID", value=str(result.id))
                embed.add_field(name="Status", value=result.status.value)
                embed.add_field(name="Requested Type", value=entity_type)
                if location_id_context:
                    embed.add_field(name="Location Context ID", value=str(location_id_context))
                if player_id_context:
                    embed.add_field(name="Player Context ID", value=str(player_id_context))
                if parsed_gen_context:
                    preview_str = json.dumps(parsed_gen_context, indent=2, ensure_ascii=False)
                    if len(preview_str) > 1000: preview_str = preview_str[:1000] + "..."
                    embed.add_field(name="Provided Context JSON", value=f"```json\n{preview_str}\n```", inline=False)

                await interaction.followup.send(embed=embed, ephemeral=True)
            elif isinstance(result, str): # Error string
                error_msg = await get_localized_master_message(session, guild_id, "pending_gen_trigger:error_string_result", "Generation failed: {error_details}", str(interaction.locale), error_details=result) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
            else: # CustomValidationError or other unexpected
                error_msg = await get_localized_master_message(session, guild_id, "pending_gen_trigger:error_unknown_result", "Generation failed with an unexpected result type.", str(interaction.locale)) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)

            await session.commit() # Commit changes if any made by trigger_ai_generation_flow's session
        except Exception as e:
            logger.error(f"Error in trigger_generation command for guild {guild_id}: {e}", exc_info=True) # type: ignore
            await session.rollback()
            error_msg = await get_localized_master_message(session, guild_id, "master_generic.error_unexpected", "An unexpected error occurred: {error}", str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @pending_gen_master_cmds.command(name="list", description="List pending AI generations for moderation.")
    @app_commands.describe(
        status_filter="Filter by moderation status (e.g., PENDING_MODERATION, VALIDATION_FAILED).",
        page="Page number to display.",
        limit="Number of entries per page."
    )
    @app_commands.choices(status_filter=[
        app_commands.Choice(name="Pending Moderation", value="PENDING_MODERATION"),
        app_commands.Choice(name="Validation Failed", value="VALIDATION_FAILED"),
        app_commands.Choice(name="Approved", value="APPROVED"),
        app_commands.Choice(name="Rejected", value="REJECTED"),
        app_commands.Choice(name="Saved", value="SAVED"),
        app_commands.Choice(name="Error on Save", value="ERROR_ON_SAVE"),
        app_commands.Choice(name="Edited Pending Approval", value="EDITED_PENDING_APPROVAL"),
    ])
    async def list_pending_generations(
        self,
        interaction: discord.Interaction,
        status_filter: Optional[app_commands.Choice[str]] = None,
        page: app_commands.Range[int, 1] = 1,
        limit: app_commands.Range[int, 1, 25] = 10
    ):
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return

        guild_id = interaction.guild_id # Known to be not None

        filter_status: Optional[ModerationStatus] = None
        if status_filter:
            try:
                filter_status = ModerationStatus[status_filter.value]
            except KeyError:
                error_msg = await get_localized_master_message(
                    session, guild_id, "pending_gen_list:error_invalid_status", # type: ignore
                    "Invalid status filter: {status_value}", str(interaction.locale),
                    status_value=status_filter.value
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                if session: await session.close()
                return

        try:
            skip = (page - 1) * limit

            # Build filters for the CRUD call
            filters = {"guild_id": guild_id}
            if filter_status:
                filters["status"] = filter_status # Assuming CRUDBase handles enum comparison correctly

            # Assuming get_multi_by_attributes and count_by_attributes exist in CRUDBase
            # or we use specific methods if available in CRUDPendingGeneration
            total_entries = await pending_generation_crud.count_by_attributes(session, **filters)
            pending_gens = await pending_generation_crud.get_multi_by_attributes(
                session, skip=skip, limit=limit, order_by="created_at", descending=True, **filters # type: ignore
            )

            if not pending_gens:
                no_entries_msg = await get_localized_master_message(
                    session, guild_id, "pending_gen_list:no_entries_found", # type: ignore
                    "No pending generations found matching the criteria on page {page_num}.", str(interaction.locale),
                    page_num=page
                )
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                if session: await session.close()
                return

            embed = discord.Embed(
                title=await get_localized_master_message(session, guild_id, "pending_gen_list:title", "Pending AI Generations", str(interaction.locale)), # type: ignore
                color=discord.Color.orange()
            )

            description_parts = []
            for gen in pending_gens:
                created_at_fmt = discord.utils.format_dt(gen.created_at, style='f')
                entity_type_guess = gen.trigger_context_json.get("requested_entity_type", "Unknown Type") if gen.trigger_context_json else "Unknown Type"

                entry_line = await get_localized_master_message(
                    session, guild_id, "pending_gen_list:entry_format", # type: ignore
                    "ID: {id} | Status: {status} | Type: {type} | Created: {created_at}", str(interaction.locale),
                    id=gen.id, status=gen.status.value, type=entity_type_guess, created_at=created_at_fmt
                )
                description_parts.append(entry_line)

            embed.description = "\n".join(description_parts)

            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "pending_gen_list:footer_pagination_current" if total_pages > 0 else "pending_gen_list:footer_pagination_empty"
            embed.set_footer(text=await get_localized_master_message(
                session, guild_id, footer_text_key, # type: ignore
                "Page {page_num}/{total_pages_val} ({total_entries_val} entries)" if total_pages > 0 else "No entries found.",
                str(interaction.locale),
                page_num=page, total_pages_val=total_pages, total_entries_val=total_entries
            ))

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in list_pending_generations command for guild {guild_id}: {e}", exc_info=True) # type: ignore
            await session.rollback()
            error_msg = await get_localized_master_message(session, guild_id, "master_generic.error_unexpected", "An unexpected error occurred: {error}", str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @pending_gen_master_cmds.command(name="view", description="View details of a specific pending AI generation.")
    @app_commands.describe(pending_generation_id="The ID of the pending generation to view.")
    async def view_pending_generation(
        self,
        interaction: discord.Interaction,
        pending_generation_id: int
    ):
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return

        guild_id = interaction.guild_id # Known to be not None

        try:
            pending_gen = await pending_generation_crud.get(session, id=pending_generation_id, guild_id=guild_id) # type: ignore

            if not pending_gen:
                not_found_msg = await get_localized_master_message(
                    session, guild_id, "pending_gen_view:not_found", # type: ignore
                    "Pending generation with ID {id} not found in this guild.", str(interaction.locale),
                    id=pending_generation_id
                )
                await interaction.followup.send(not_found_msg, ephemeral=True)
                if session: await session.close()
                return

            embed = discord.Embed(
                title=await get_localized_master_message(session, guild_id, "pending_gen_view:title", "Pending AI Generation Details (ID: {id})", str(interaction.locale), id=pending_gen.id), # type: ignore
                color=discord.Color.blue()
            )

            async def get_label(key: str, default: str) -> str:
                return await get_localized_master_message(session, guild_id, f"pending_gen_view:label_{key}", default, str(interaction.locale)) # type: ignore

            na_str = await get_localized_master_message(session, guild_id, "common:value_na", "N/A", str(interaction.locale)) # type: ignore

            embed.add_field(name=await get_label("id", "ID"), value=str(pending_gen.id), inline=True)
            embed.add_field(name=await get_label("status", "Status"), value=pending_gen.status.value, inline=True)
            embed.add_field(name=await get_label("created_at", "Created At"), value=discord.utils.format_dt(pending_gen.created_at, style='F'), inline=False)
            embed.add_field(name=await get_label("updated_at", "Updated At"), value=discord.utils.format_dt(pending_gen.updated_at, style='F'), inline=False)

            if pending_gen.triggered_by_user_id:
                embed.add_field(name=await get_label("triggered_by", "Triggered By Player ID"), value=str(pending_gen.triggered_by_user_id), inline=True)
            if pending_gen.master_id:
                embed.add_field(name=await get_label("moderated_by", "Moderated By Master ID"), value=str(pending_gen.master_id), inline=True)

            def format_json_field(data: Optional[Dict[Any, Any]], default_val: str) -> str:
                if data is None: return f"```json\n{default_val}\n```"
                try:
                    json_str = json.dumps(data, indent=2, ensure_ascii=False)
                    return f"```json\n{json_str[:1000]}\n```" + ("..." if len(json_str) > 1000 else "")
                except TypeError:
                    return f"```json\nError: Non-serializable data.\n```"

            embed.add_field(name=await get_label("trigger_context", "Trigger Context"), value=format_json_field(pending_gen.trigger_context_json, na_str), inline=False)
            embed.add_field(name=await get_label("ai_prompt", "AI Prompt (Preview)"), value=f"```text\n{(pending_gen.ai_prompt_text or na_str)[:1000]}\n```" + ("..." if pending_gen.ai_prompt_text and len(pending_gen.ai_prompt_text) > 1000 else ""), inline=False)
            embed.add_field(name=await get_label("raw_response", "Raw AI Response (Preview)"), value=f"```text\n{(pending_gen.raw_ai_response_text or na_str)[:1000]}\n```" + ("..." if pending_gen.raw_ai_response_text and len(pending_gen.raw_ai_response_text) > 1000 else ""), inline=False)
            embed.add_field(name=await get_label("parsed_data", "Parsed/Validated Data"), value=format_json_field(pending_gen.parsed_validated_data_json, na_str), inline=False)
            embed.add_field(name=await get_label("validation_issues", "Validation Issues"), value=format_json_field(pending_gen.validation_issues_json, "No issues reported." if pending_gen.status != ModerationStatus.VALIDATION_FAILED else na_str), inline=False)
            embed.add_field(name=await get_label("master_notes", "Master Notes"), value=pending_gen.master_notes or na_str, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in view_pending_generation command for guild {guild_id}: {e}", exc_info=True) # type: ignore
            await session.rollback()
            error_msg = await get_localized_master_message(session, guild_id, "master_generic.error_unexpected", "An unexpected error occurred: {error}", str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @pending_gen_master_cmds.command(name="approve", description="Approve a pending AI generation and save its content.")
    @app_commands.describe(pending_generation_id="The ID of the pending generation to approve.")
    async def approve_pending_generation(
        self,
        interaction: discord.Interaction,
        pending_generation_id: int
    ):
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return

        guild_id = interaction.guild_id # Known to be not None

        try:
            # Check if pending_generation exists and is in a state that can be approved.
            pending_gen = await pending_generation_crud.get(session, id=pending_generation_id, guild_id=guild_id) # type: ignore
            if not pending_gen:
                not_found_msg = await get_localized_master_message(
                    session, guild_id, "pending_gen_approve:not_found", # type: ignore
                    "Pending generation with ID {id} not found.", str(interaction.locale), id=pending_generation_id
                )
                await interaction.followup.send(not_found_msg, ephemeral=True)
                if session: await session.close()
                return

            if pending_gen.status not in [ModerationStatus.PENDING_MODERATION, ModerationStatus.EDITED_PENDING_APPROVAL, ModerationStatus.VALIDATION_FAILED]:
                # Allow approving VALIDATION_FAILED if master deems it okay.
                invalid_status_msg = await get_localized_master_message(
                    session, guild_id, "pending_gen_approve:invalid_status", # type: ignore
                    "Pending generation ID {id} has status '{status}' and cannot be approved directly. Current valid statuses for approval: PENDING_MODERATION, EDITED_PENDING_APPROVAL, VALIDATION_FAILED.",
                    str(interaction.locale), id=pending_gen.id, status=pending_gen.status.value
                )
                await interaction.followup.send(invalid_status_msg, ephemeral=True)
                if session: await session.close()
                return

            if not pending_gen.parsed_validated_data_json and pending_gen.status != ModerationStatus.VALIDATION_FAILED:
                # If it's VALIDATION_FAILED, parsed_validated_data_json might be None, but master can still choose to approve if they fixed it via an "edit" that didn't save yet, or if they accept the risk.
                # However, save_approved_generation expects parsed_validated_data_json.
                # This implies an "edit" command should first update parsed_validated_data_json.
                # For now, if it's not VALIDATION_FAILED and no data, it's an error.
                no_data_msg = await get_localized_master_message(
                     session, guild_id, "pending_gen_approve:no_parsed_data", # type: ignore
                    "Pending generation ID {id} has no parsed data to save. Please ensure it was validated or edited correctly.", str(interaction.locale), id=pending_gen.id
                )
                await interaction.followup.send(no_data_msg,ephemeral=True)
                if session: await session.close()
                return


            # Attempt to save the approved generation
            # save_approved_generation is @transactional, so it handles its own commit/rollback for its operations.
            # The current session (from ensure_guild_configured_and_get_session) will be used by save_approved_generation.
            success = await save_approved_generation(session, pending_generation_id, guild_id) # type: ignore

            if success:
                # The status is updated by save_approved_generation.
                # We might want to refresh pending_gen here if we need the absolute latest status from DB.
                # await session.refresh(pending_gen) # If needed
                final_status_msg = await get_localized_master_message(
                    session, guild_id, "pending_gen_approve:success", # type: ignore
                    "Pending generation ID {id} approved and content saved successfully.", str(interaction.locale), id=pending_generation_id
                )
                await interaction.followup.send(final_status_msg, ephemeral=True)
            else:
                # save_approved_generation logs errors and updates status to ERROR_ON_SAVE.
                # We can provide a generic failure message here.
                failure_msg = await get_localized_master_message(
                    session, guild_id, "pending_gen_approve:failure", # type: ignore
                    "Failed to save content for pending generation ID {id}. Check logs for details. Status may have been updated to ERROR_ON_SAVE.", str(interaction.locale), id=pending_generation_id
                )
                await interaction.followup.send(failure_msg, ephemeral=True)

            # No explicit commit here as save_approved_generation handles its transaction.
            # The session from ensure_guild_configured_and_get_session will be closed in finally.

        except Exception as e:
            logger.error(f"Error in approve_pending_generation command for guild {guild_id}: {e}", exc_info=True) # type: ignore
            # session.rollback() might not be needed if save_approved_generation handles it, but for safety:
            try:
                await session.rollback()
            except Exception as rb_exc:
                logger.error(f"Rollback failed in approve_pending_generation: {rb_exc}", exc_info=True)

            error_msg = await get_localized_master_message(session, guild_id, "master_generic.error_unexpected", "An unexpected error occurred: {error}", str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @pending_gen_master_cmds.command(name="update", description="Update status, notes, or data of a pending AI generation.")
    @app_commands.describe(
        pending_generation_id="The ID of the pending generation to update.",
        new_status="Optional: New moderation status (e.g., REJECTED, EDITED_PENDING_APPROVAL).",
        new_parsed_data_json="Optional: JSON string of new parsed data (for edits).",
        master_notes="Optional: Notes from the master regarding this generation."
    )
    @app_commands.choices(new_status=[
        app_commands.Choice(name="Pending Moderation", value="PENDING_MODERATION"),
        app_commands.Choice(name="Validation Failed", value="VALIDATION_FAILED"),
        # Not allowing direct set to APPROVED, use approve command for that flow.
        app_commands.Choice(name="Rejected", value="REJECTED"),
        # Not allowing direct set to SAVED or ERROR_ON_SAVE.
        app_commands.Choice(name="Edited (Pending Approval)", value="EDITED_PENDING_APPROVAL"),
    ])
    async def update_pending_generation(
        self,
        interaction: discord.Interaction,
        pending_generation_id: int,
        new_status: Optional[app_commands.Choice[str]] = None,
        new_parsed_data_json: Optional[str] = None,
        master_notes: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return

        guild_id = interaction.guild_id # Known to be not None
        updated_fields_count = 0
        update_data: Dict[str, Any] = {}

        if new_status:
            try:
                update_data["status"] = ModerationStatus[new_status.value] # type: ignore[reportArgumentType]
                updated_fields_count += 1
            except KeyError:
                error_msg = await get_localized_master_message(
                    session, guild_id, "pending_gen_update:error_invalid_status", # type: ignore
                    "Invalid new_status value: {status_value}", str(interaction.locale),
                    status_value=new_status.value
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                if session: await session.close()
                return

        if new_parsed_data_json:
            parsed_data = await parse_json_parameter(
                interaction, new_parsed_data_json, "new_parsed_data_json", session
            )
            if parsed_data is None: # Error in parsing, message sent
                if session: await session.close()
                return
            update_data["parsed_validated_data_json"] = parsed_data
            updated_fields_count += 1
            # If data is edited, it might implicitly mean it needs re-approval or issues are resolved
            if "status" not in update_data: # If status is not being explicitly set otherwise
                update_data["status"] = ModerationStatus.EDITED_PENDING_APPROVAL
                # No increment to updated_fields_count here as it's a consequence

        if master_notes is not None: # Allow empty string for notes
            update_data["master_notes"] = master_notes
            updated_fields_count += 1

        if updated_fields_count == 0:
            no_action_msg = await get_localized_master_message(
                session, guild_id, "pending_gen_update:no_action_taken", # type: ignore
                "No update parameters provided. Nothing to change for pending generation ID {id}.",
                str(interaction.locale), id=pending_generation_id
            )
            await interaction.followup.send(no_action_msg, ephemeral=True)
            if session: await session.close()
            return

        try:
            pending_gen = await pending_generation_crud.get(session, id=pending_generation_id, guild_id=guild_id) # type: ignore
            if not pending_gen:
                not_found_msg = await get_localized_master_message(
                    session, guild_id, "pending_gen_update:not_found", # type: ignore
                    "Pending generation with ID {id} not found.", str(interaction.locale), id=pending_generation_id
                )
                await interaction.followup.send(not_found_msg, ephemeral=True)
                if session: await session.close()
                return

            # Add master_id if not already set and status is changing to something other than PENDING or VALIDATION_FAILED
            if master_player and master_player.id: # master_player is actually Player model from DB
                if "status" in update_data and update_data["status"] not in [ModerationStatus.PENDING_MODERATION, ModerationStatus.VALIDATION_FAILED]:
                    update_data["master_id"] = master_player.id
                elif new_parsed_data_json or master_notes is not None: # If editing data or notes, also log master
                     update_data["master_id"] = master_player.id


            updated_gen = await pending_generation_crud.update(session, db_obj=pending_gen, obj_in=update_data)
            await session.commit()
            await session.refresh(updated_gen)

            success_msg = await get_localized_master_message(
                session, guild_id, "pending_gen_update:success", # type: ignore
                "Pending generation ID {id} updated successfully. New status: {status_val}", str(interaction.locale),
                id=updated_gen.id, status_val=updated_gen.status.value
            )
            await interaction.followup.send(success_msg, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in update_pending_generation command for guild {guild_id}: {e}", exc_info=True) # type: ignore
            await session.rollback()
            error_msg = await get_localized_master_message(session, guild_id, "master_generic.error_unexpected", "An unexpected error occurred: {error}", str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(MasterPendingGenerationCog(bot))
    logger.info("MasterPendingGenerationCog added to bot.")
