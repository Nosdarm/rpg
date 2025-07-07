import logging
import json
from typing import Dict, Any, Optional, cast
from datetime import datetime # Added for casting

import discord
from discord import app_commands
from discord.ext import commands

from src.core.database import get_db_session
from src.models.enums import ConflictStatus
from src.core.crud.crud_pending_conflict import pending_conflict_crud
from src.core.localization_utils import get_localized_message_template

logger = logging.getLogger(__name__)

class MasterConflictCog(commands.Cog, name="Master Conflict Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterConflictCog initialized.")

    conflict_master_cmds = app_commands.Group(
        name="master_conflict",
        description="Master commands for managing pending conflicts.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @conflict_master_cmds.command(name="resolve", description="Resolve a pending conflict.")
    @app_commands.describe(
        pending_conflict_id="The ID of the pending conflict to resolve.",
        outcome_status="The resolution status (e.g., RESOLVED_BY_MASTER_FAVOR_ACTION1, RESOLVED_BY_MASTER_CUSTOM_ACTION).",
        notes="Optional notes about the resolution."
    )
    async def conflict_resolve(self, interaction: discord.Interaction,
                               pending_conflict_id: int,
                               outcome_status: str,
                               notes: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        # lang_code = str(interaction.locale) # Already defined

        try:
            # Assuming ConflictStatus enum members exist as defined.
            # If these specific values are causing "Cannot access attribute" errors,
            # the ConflictStatus enum definition itself needs to be verified.
            valid_resolution_statuses = {
                ConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION1,
                ConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION2,
                ConflictStatus.RESOLVED_BY_MASTER_CUSTOM_ACTION,
                ConflictStatus.RESOLVED_BY_MASTER_DISMISS
            }
            resolved_status_enum: Optional[ConflictStatus] = None
            # This block needs a session to call get_localized_message_template if a ValueError is raised.
            # It's better to acquire the session before this try-except or pass it into a helper.
            # For now, assuming session is available from an outer scope if error messages are localized inside.
            # Corrected: Moved session acquisition to encompass this try block.
            async with get_db_session() as session_for_validation: # Use a temporary session for validation messages
                for status_member in ConflictStatus:
                    if status_member.name.upper() == outcome_status.upper() or status_member.value.upper() == outcome_status.upper():
                        if status_member in valid_resolution_statuses:
                            resolved_status_enum = status_member
                            break
                        else:
                            allowed_values_str = ", ".join([s.name for s in valid_resolution_statuses])
                            error_detail_template = await get_localized_message_template(session_for_validation, interaction.guild_id, "conflict_resolve:error_detail_invalid_master_outcome", lang_code, "Invalid outcome_status for master resolution. Allowed: {allowed_list}")
                            raise ValueError(error_detail_template.format(allowed_list=allowed_values_str))

                if not resolved_status_enum:
                    allowed_values_str = ", ".join([s.name for s in valid_resolution_statuses])
                    error_detail_template = await get_localized_message_template(session_for_validation, interaction.guild_id, "conflict_resolve:error_detail_unrecognized_outcome", lang_code, "Outcome status not recognized or not a valid master resolution. Allowed: {allowed_list}")
                    raise ValueError(error_detail_template.format(allowed_list=allowed_values_str))

        except ValueError as e: # Catch specific ValueErrors from above or general ones
            # If session_for_validation was used above, this temp_session_for_error_msg is redundant for this specific path.
            # However, keeping it for safety if other ValueErrors can occur before session_for_validation is used.
            async with get_db_session() as temp_session_for_error_msg:
                error_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "conflict_resolve:error_processing_outcome", lang_code,
                    "Error processing outcome_status '{provided_status}': {details}"
                )
            await interaction.followup.send(error_msg.format(provided_status=outcome_status, details=str(e)), ephemeral=True)
            return

        update_data: Dict[str, Any] = {
            "status": resolved_status_enum,
            "resolution_notes": notes,
            "resolved_at": discord.utils.utcnow() # This is fine
        }

        async with get_db_session() as session:
            # lang_code already defined
            try:
                async with session.begin():
                    conflict_to_update = await pending_conflict_crud.get(session, id=pending_conflict_id, guild_id=interaction.guild_id)

                    if not conflict_to_update:
                        not_found_msg = await get_localized_message_template(
                            session, interaction.guild_id, "conflict_resolve:not_found", lang_code,
                            "PendingConflict with ID {conflict_id} not found in this guild."
                        )
                        await interaction.followup.send(not_found_msg.format(conflict_id=pending_conflict_id), ephemeral=True)
                        return

                    if conflict_to_update.status != ConflictStatus.PENDING_MASTER_RESOLUTION:
                        not_pending_msg = await get_localized_message_template(
                            session, interaction.guild_id, "conflict_resolve:not_pending_master_resolution", lang_code,
                            "Conflict ID {conflict_id} is not awaiting master resolution (current status: {current_status})."
                        )
                        await interaction.followup.send(not_pending_msg.format(conflict_id=pending_conflict_id, current_status=conflict_to_update.status.value), ephemeral=True)
                        return

                    updated_conflict = await pending_conflict_crud.update(session, db_obj=conflict_to_update, obj_in=update_data)
                    if updated_conflict: # Ensure refresh only on success
                        await session.refresh(updated_conflict)
                    logger.info(f"Conflict {updated_conflict.id} resolved by Master. Status: {updated_conflict.status.value if updated_conflict.status else 'N/A'}. Notes: '{updated_conflict.resolution_notes}'.")

                # After successful commit of conflict resolution
                # Check for remaining conflicts and trigger turn processing if none are left.
                from src.core.turn_controller import trigger_guild_turn_processing # Moved import
                import asyncio # Moved import

                # Query for remaining conflicts within the same session, after the commit.
                # The previous transaction is committed, so this query sees the updated state.
                remaining_conflicts_count = await pending_conflict_crud.get_count_by_guild_and_status(
                    session, guild_id=interaction.guild_id, status=ConflictStatus.PENDING_MASTER_RESOLUTION
                )

                # lang_code is already defined in this scope
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")

                base_success_msg_template = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_resolve:success_base", lang_code,
                    "Conflict ID {conflict_id} has been resolved with status '{status_name}'. Notes: {notes_value}."
                )

                final_message = base_success_msg_template.format(
                    conflict_id=pending_conflict_id,
                    status_name=resolved_status_enum.name if resolved_status_enum else "UNKNOWN", # Guard if resolved_status_enum is None
                    notes_value=(notes or na_value_str)
                )

                if remaining_conflicts_count == 0:
                    logger.info(f"Conflict {pending_conflict_id} resolved for guild {interaction.guild_id}. No other pending conflicts. Triggering turn reprocessing.")
                    reprocessing_triggered_msg = await get_localized_message_template(
                        session, interaction.guild_id, "conflict_resolve:success_reprocessing_triggered", lang_code,
                        " All pending conflicts resolved. Guild turn reprocessing will be attempted."
                    )
                    final_message += reprocessing_triggered_msg
                    # Use asyncio.create_task to run this in the background without blocking the command response.
                    # It needs its own session context.
                    asyncio.create_task(trigger_guild_turn_processing(interaction.guild_id, get_db_session))
                else:
                    logger.info(f"Conflict {pending_conflict_id} resolved for guild {interaction.guild_id}. {remaining_conflicts_count} other conflict(s) still pending. Turn processing remains paused.")
                    other_pending_msg = await get_localized_message_template(
                        session, interaction.guild_id, "conflict_resolve:success_others_pending", lang_code,
                        " However, {count} other conflict(s) are still pending for this guild. Turn processing will resume once all are resolved."
                    )
                    final_message += other_pending_msg.format(count=remaining_conflicts_count)

                await interaction.followup.send(final_message, ephemeral=True)

            except Exception as e:
                logger.error(f"Error resolving conflict {pending_conflict_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                # Ensure lang_code is available for error message
                generic_error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_resolve:error_generic", lang_code,
                    "An error occurred while resolving conflict {conflict_id}: {error_message}"
                )
                await interaction.followup.send(generic_error_msg.format(conflict_id=pending_conflict_id, error_message=str(e)), ephemeral=True)
                return

    @conflict_master_cmds.command(name="view", description="View details of a specific pending conflict.")
    @app_commands.describe(pending_conflict_id="The ID of the pending conflict to view.")
    async def conflict_view(self, interaction: discord.Interaction, pending_conflict_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            conflict = await pending_conflict_crud.get(session, id=pending_conflict_id, guild_id=interaction.guild_id)

            if not conflict:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_view:not_found", lang_code,
                    "PendingConflict with ID {conflict_id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(conflict_id=pending_conflict_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_view:title", lang_code,
                "Conflict Details (ID: {conflict_id})"
            )
            embed = discord.Embed(title=title_template.format(conflict_id=conflict.id), color=discord.Color.red())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"conflict_view:label_{key}", lang_code, default)

            embed.add_field(name=await get_label("status", "Status"), value=conflict.status.value, inline=True)
            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(conflict.guild_id), inline=True)

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")

            created_at_val = discord.utils.format_dt(cast(datetime, conflict.created_at), style='F') if conflict.created_at else na_value_str # Cast for Pyright
            embed.add_field(name=await get_label("created_at", "Created At"), value=created_at_val, inline=True)

            if conflict.resolved_at:
                resolved_at_val = discord.utils.format_dt(cast(datetime, conflict.resolved_at), style='F') # Cast for Pyright
                embed.add_field(name=await get_label("resolved_at", "Resolved At"), value=resolved_at_val, inline=True)
            # else: # Optionally show N/A if not resolved
            #     embed.add_field(name=await get_label("resolved_at", "Resolved At"), value=na_value_str, inline=True)


            error_serialization_msg_str = await get_localized_message_template(session, interaction.guild_id, "conflict_view:error_serialization", lang_code, "Error: Non-serializable data")
            # na_msg used for JSON fields if they are None or empty, _format_json_field_helper handles this

            async def format_json_field_helper_local(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                # Using the session and lang_code from the outer scope of conflict_view
                na_str_val = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str_val
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            involved_str = await format_json_field_helper_local(conflict.involved_entities_json, "conflict_view:value_na_json", "conflict_view:error_serialization")
            embed.add_field(name=await get_label("involved_entities", "Involved Entities"), value=f"```json\n{involved_str[:1000]}\n```" + ("..." if len(involved_str) > 1000 else ""), inline=False)

            actions_str = await format_json_field_helper_local(conflict.conflicting_actions_json, "conflict_view:value_na_json", "conflict_view:error_serialization")
            embed.add_field(name=await get_label("conflicting_actions", "Conflicting Actions"), value=f"```json\n{actions_str[:1000]}\n```" + ("..." if len(actions_str) > 1000 else ""), inline=False)

            if conflict.resolution_notes:
                embed.add_field(name=await get_label("resolution_notes", "Resolution Notes"), value=conflict.resolution_notes[:1020] + ("..." if len(conflict.resolution_notes) > 1020 else ""), inline=False)

            if conflict.resolved_action_json:
                resolved_action_str = await format_json_field_helper_local(conflict.resolved_action_json, "conflict_view:value_na_json", "conflict_view:error_serialization")
                embed.add_field(name=await get_label("resolved_action", "Resolved Action"), value=f"```json\n{resolved_action_str[:1000]}\n```" + ("..." if len(resolved_action_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @conflict_master_cmds.command(name="list", description="List pending conflicts in this guild.")
    @app_commands.describe(
        status="Filter by status (e.g., PENDING_MASTER_RESOLUTION, RESOLVED_BY_MASTER_CUSTOM_ACTION). Optional.",
        page="Page number to display.",
        limit="Number of conflicts per page."
    )
    async def conflict_list(self, interaction: discord.Interaction, status: Optional[str] = None, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        status_enum: Optional[ConflictStatus] = None
        lang_code = str(interaction.locale)
        if interaction.guild_id is None: # Moved lang_code definition up
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        # lang_code = str(interaction.locale) # Already defined

        async with get_db_session() as session:
            if status:
                try:
                    status_enum = ConflictStatus[status.upper()]
                except KeyError:
                    try: # Attempt to match by value if name matching fails
                        status_enum = ConflictStatus(status)
                    except ValueError: # Neither name nor value matched
                        invalid_status_msg = await get_localized_message_template(
                            session, interaction.guild_id, "conflict_list:error_invalid_status", lang_code,
                            "Invalid status value '{provided_status}'. Valid statuses are: {valid_statuses}"
                        )
                        valid_statuses_str = ", ".join([s.name for s in ConflictStatus])
                        await interaction.followup.send(invalid_status_msg.format(provided_status=status, valid_statuses=valid_statuses_str), ephemeral=True)
                        return

            offset = (page - 1) * limit
            # These CRUD methods are assumed to exist and correctly handle guild_id
            conflicts = await pending_conflict_crud.get_multi_by_guild_and_status_paginated(
                session, guild_id=interaction.guild_id, status=status_enum, skip=offset, limit=limit
            )
            total_conflicts = await pending_conflict_crud.get_count_by_guild_and_status(
                session, guild_id=interaction.guild_id, status=status_enum
            )

            if not conflicts:
                no_conflicts_msg = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_list:no_conflicts_found", lang_code,
                    "No conflicts found for the given criteria (Status: {status_filter}, Page: {page_num})."
                )
                status_filter_str = status_enum.name if status_enum else "Any"
                await interaction.followup.send(no_conflicts_msg.format(status_filter=status_filter_str, page_num=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_list:title", lang_code,
                "Conflict List (Status: {status_filter}, Page {page_num} of {total_pages})"
            )
            total_pages = ((total_conflicts - 1) // limit) + 1

            status_any_str = await get_localized_message_template(session, interaction.guild_id, "common:filter_any", lang_code, "Any")
            status_filter_display = status_enum.name if status_enum else status_any_str

            embed_title = title_template.format(status_filter=status_filter_display, page_num=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.orange())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_list:footer", lang_code,
                "Displaying {count} of {total} total conflicts."
            )
            embed.set_footer(text=footer_template.format(count=len(conflicts), total=total_conflicts))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_list:conflict_field_name", lang_code,
                "ID: {conflict_id} | Status: {status_value}"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_list:conflict_field_value", lang_code,
                "Created: {created_at_dt}\nInvolved: {involved_count} entities"
            )

            for c in conflicts:
                involved_count = len(c.involved_entities_json) if isinstance(c.involved_entities_json, list) else 0
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
                created_at_dt_str = discord.utils.format_dt(cast(datetime, c.created_at), style='R') if c.created_at else na_value_str # Cast for Pyright
                embed.add_field(
                    name=field_name_template.format(conflict_id=c.id, status_value=c.status.value),
                    value=field_value_template.format(created_at_dt=created_at_dt_str, involved_count=involved_count),
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

    @conflict_master_cmds.command(name="delete", description="Delete a specific pending conflict.")
    @app_commands.describe(pending_conflict_id="The ID of the pending conflict to delete.")
    async def conflict_delete(self, interaction: discord.Interaction, pending_conflict_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            conflict_to_delete = await pending_conflict_crud.get(session, id=pending_conflict_id, guild_id=interaction.guild_id)
            if not conflict_to_delete:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "conflict_delete:not_found", lang_code, "PendingConflict with ID {conflict_id} not found.")
                await interaction.followup.send(not_found_msg.format(conflict_id=pending_conflict_id), ephemeral=True); return

            try:
                async with session.begin():
                    deleted_conflict = await pending_conflict_crud.delete(session, id=pending_conflict_id, guild_id=interaction.guild_id)

                if deleted_conflict:
                    success_msg = await get_localized_message_template(session, interaction.guild_id, "conflict_delete:success", lang_code, "PendingConflict ID {conflict_id} has been deleted.")
                    await interaction.followup.send(success_msg.format(conflict_id=pending_conflict_id), ephemeral=True)
                else: # Should not happen if found before
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "conflict_delete:error_not_deleted_unknown", lang_code, "PendingConflict (ID: {conflict_id}) was found but could not be deleted.")
                    await interaction.followup.send(error_msg.format(conflict_id=pending_conflict_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting PendingConflict {pending_conflict_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                generic_error_msg = await get_localized_message_template(session, interaction.guild_id, "conflict_delete:error_generic", lang_code, "An error occurred while deleting conflict {conflict_id}: {error_message}")
                await interaction.followup.send(generic_error_msg.format(conflict_id=pending_conflict_id, error_message=str(e)), ephemeral=True)


async def setup(bot: commands.Bot):
    cog = MasterConflictCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterConflictCog loaded.")
