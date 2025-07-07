import logging
import json
from typing import Dict, Any, Optional

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
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        lang_code = str(interaction.locale)

        try:
            # Assuming ConflictStatus enum members exist as defined.
            # If these specific values are causing "Cannot access attribute" errors,
            # the ConflictStatus enum definition itself needs to be verified.
            valid_resolution_statuses = {
                ConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION1, # type: ignore
                ConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION2, # type: ignore
                ConflictStatus.RESOLVED_BY_MASTER_CUSTOM_ACTION, # type: ignore
                ConflictStatus.RESOLVED_BY_MASTER_DISMISS        # type: ignore
            }
            resolved_status_enum: Optional[ConflictStatus] = None
            for status_member in ConflictStatus:
                if status_member.name.upper() == outcome_status.upper() or status_member.value.upper() == outcome_status.upper():
                    if status_member in valid_resolution_statuses:
                        resolved_status_enum = status_member
                        break
                    else:
                        allowed_values_str = ", ".join([s.name for s in valid_resolution_statuses])
                        async with get_db_session() as temp_session_for_error_msg:
                            invalid_outcome_msg = await get_localized_message_template(
                                temp_session_for_error_msg, interaction.guild_id, "conflict_resolve:error_invalid_outcome_for_master", lang_code,
                                "Invalid outcome_status '{provided_status}'. Allowed values for master resolution: {allowed_list}"
                            ) # type: ignore
                        await interaction.followup.send(invalid_outcome_msg.format(provided_status=outcome_status, allowed_list=allowed_values_str), ephemeral=True)
                        return

            if not resolved_status_enum:
                allowed_values_str = ", ".join([s.name for s in valid_resolution_statuses])
                async with get_db_session() as temp_session_for_error_msg:
                    unrecognized_outcome_msg = await get_localized_message_template(
                        temp_session_for_error_msg, interaction.guild_id, "conflict_resolve:error_unrecognized_outcome", lang_code,
                        "Outcome status '{provided_status}' not recognized or not a valid master resolution. Allowed: {allowed_list}"
                    ) # type: ignore
                await interaction.followup.send(unrecognized_outcome_msg.format(provided_status=outcome_status, allowed_list=allowed_values_str), ephemeral=True)
                return
        except ValueError: # This might catch issues if outcome_status cannot be compared or enum itself is problematic
            async with get_db_session() as temp_session_for_error_msg:
                internal_error_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "conflict_resolve:error_internal_status_check", lang_code,
                    "Internal error processing outcome_status: '{provided_status}'."
                ) # type: ignore
            await interaction.followup.send(internal_error_msg.format(provided_status=outcome_status), ephemeral=True)
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
                        ) # type: ignore
                        await interaction.followup.send(not_found_msg.format(conflict_id=pending_conflict_id), ephemeral=True)
                        return

                    if conflict_to_update.status != ConflictStatus.PENDING_MASTER_RESOLUTION:
                        not_pending_msg = await get_localized_message_template(
                            session, interaction.guild_id, "conflict_resolve:not_pending_master_resolution", lang_code,
                            "Conflict ID {conflict_id} is not awaiting master resolution (current status: {current_status})."
                        ) # type: ignore
                        await interaction.followup.send(not_pending_msg.format(conflict_id=pending_conflict_id, current_status=conflict_to_update.status.value), ephemeral=True)
                        return

                    updated_conflict = await pending_conflict_crud.update(session, db_obj=conflict_to_update, obj_in=update_data)
                    if updated_conflict: # Ensure refresh only on success
                        await session.refresh(updated_conflict)
                    # logger.info(f"Conflict {updated_conflict.id} resolved by Master. Current status: {updated_conflict.status.value}. Notes: '{updated_conflict.resolution_notes}'. Action Processor signaling mechanism TBD.")

                success_msg = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_resolve:success", lang_code,
                    "Conflict ID {conflict_id} has been resolved with status '{status_name}'. Notes: {notes_value}"
                ) # type: ignore
                await interaction.followup.send(success_msg.format(conflict_id=pending_conflict_id, status_name=resolved_status_enum.name, notes_value=(notes or "N/A")), ephemeral=True)
            except Exception as e:
                logger.error(f"Error resolving conflict {pending_conflict_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                generic_error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_resolve:error_generic", lang_code,
                    "An error occurred while resolving conflict {conflict_id}: {error_message}"
                ) # type: ignore
                await interaction.followup.send(generic_error_msg.format(conflict_id=pending_conflict_id, error_message=str(e)), ephemeral=True)
                return

    @conflict_master_cmds.command(name="view", description="View details of a specific pending conflict.")
    @app_commands.describe(pending_conflict_id="The ID of the pending conflict to view.")
    async def conflict_view(self, interaction: discord.Interaction, pending_conflict_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            conflict = await pending_conflict_crud.get(session, id=pending_conflict_id, guild_id=interaction.guild_id)

            if not conflict:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_view:not_found", lang_code,
                    "PendingConflict with ID {conflict_id} not found in this guild."
                ) # type: ignore
                await interaction.followup.send(not_found_msg.format(conflict_id=pending_conflict_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_view:title", lang_code,
                "Conflict Details (ID: {conflict_id})"
            ) # type: ignore
            embed = discord.Embed(title=title_template.format(conflict_id=conflict.id), color=discord.Color.red())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"conflict_view:label_{key}", lang_code, default) # type: ignore

            embed.add_field(name=await get_label("status", "Status"), value=conflict.status.value, inline=True)
            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(conflict.guild_id), inline=True)
            # Assuming conflict.created_at and conflict.resolved_at are standard datetime.datetime or None
            created_at_val = discord.utils.format_dt(conflict.created_at, style='F') if conflict.created_at else await get_label("value_na", "N/A") # type: ignore[arg-type]
            embed.add_field(name=await get_label("created_at", "Created At"), value=created_at_val, inline=True)

            if conflict.resolved_at:
                resolved_at_val = discord.utils.format_dt(conflict.resolved_at, style='F') # type: ignore[arg-type]
                embed.add_field(name=await get_label("resolved_at", "Resolved At"), value=resolved_at_val, inline=True)

            error_serialization_msg = await get_localized_message_template(session, interaction.guild_id, "conflict_view:error_serialization", lang_code, "Error: Non-serializable data") # type: ignore
            na_msg = await get_localized_message_template(session, interaction.guild_id, "conflict_view:value_na_json", lang_code, "Not available") # type: ignore

            involved_str = na_msg
            if conflict.involved_entities_json:
                try:
                    involved_str = json.dumps(conflict.involved_entities_json, indent=2, ensure_ascii=False)
                except TypeError: involved_str = error_serialization_msg
            embed.add_field(name=await get_label("involved_entities", "Involved Entities"), value=f"```json\n{involved_str[:1000]}\n```" + ("..." if len(involved_str) > 1000 else ""), inline=False)

            actions_str = na_msg
            if conflict.conflicting_actions_json:
                try:
                    actions_str = json.dumps(conflict.conflicting_actions_json, indent=2, ensure_ascii=False)
                except TypeError: actions_str = error_serialization_msg
            embed.add_field(name=await get_label("conflicting_actions", "Conflicting Actions"), value=f"```json\n{actions_str[:1000]}\n```" + ("..." if len(actions_str) > 1000 else ""), inline=False)

            if conflict.resolution_notes:
                embed.add_field(name=await get_label("resolution_notes", "Resolution Notes"), value=conflict.resolution_notes[:1020] + ("..." if len(conflict.resolution_notes) > 1020 else ""), inline=False)

            if conflict.resolved_action_json:
                resolved_action_str = na_msg
                try:
                    resolved_action_str = json.dumps(conflict.resolved_action_json, indent=2, ensure_ascii=False)
                except TypeError: resolved_action_str = error_serialization_msg
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
                        ) # type: ignore
                        valid_statuses_str = ", ".join([s.name for s in ConflictStatus])
                        await interaction.followup.send(invalid_status_msg.format(provided_status=status, valid_statuses=valid_statuses_str), ephemeral=True)
                        return

            offset = (page - 1) * limit
            # These CRUD methods are assumed to exist and correctly handle guild_id
            conflicts = await pending_conflict_crud.get_multi_by_guild_and_status_paginated(
                session, guild_id=interaction.guild_id, status=status_enum, skip=offset, limit=limit # type: ignore
            )
            total_conflicts = await pending_conflict_crud.get_count_by_guild_and_status(
                session, guild_id=interaction.guild_id, status=status_enum # type: ignore
            )

            if not conflicts:
                no_conflicts_msg = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_list:no_conflicts_found", lang_code,
                    "No conflicts found for the given criteria (Status: {status_filter}, Page: {page_num})."
                ) # type: ignore
                status_filter_str = status_enum.name if status_enum else "Any"
                await interaction.followup.send(no_conflicts_msg.format(status_filter=status_filter_str, page_num=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_list:title", lang_code,
                "Conflict List (Status: {status_filter}, Page {page_num} of {total_pages})"
            ) # type: ignore
            total_pages = ((total_conflicts - 1) // limit) + 1
            status_filter_display = status_enum.name if status_enum else await get_localized_message_template(session, interaction.guild_id, "conflict_list:status_any", lang_code, "Any") # type: ignore
            embed_title = title_template.format(status_filter=status_filter_display, page_num=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.orange())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_list:footer", lang_code,
                "Displaying {count} of {total} total conflicts."
            ) # type: ignore
            embed.set_footer(text=footer_template.format(count=len(conflicts), total=total_conflicts))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_list:conflict_field_name", lang_code,
                "ID: {conflict_id} | Status: {status_value}"
            ) # type: ignore
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_list:conflict_field_value", lang_code,
                "Created: {created_at_dt}\nInvolved: {involved_count} entities"
            ) # type: ignore

            for c in conflicts:
                involved_count = len(c.involved_entities_json) if isinstance(c.involved_entities_json, list) else 0
                # Assuming c.created_at is a standard datetime object or None
<<<<<<< HEAD
                created_at_dt_str = discord.utils.format_dt(c.created_at, style='R') if c.created_at else "N/A"
=======
                created_at_dt_str = discord.utils.format_dt(c.created_at, style='R') if c.created_at else "N/A" # type: ignore[arg-type]
>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
                embed.add_field(
                    name=field_name_template.format(conflict_id=c.id, status_value=c.status.value),
                    value=field_value_template.format(created_at_dt=created_at_dt_str, involved_count=involved_count),
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    cog = MasterConflictCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterConflictCog loaded.")
