import json
import logging
from typing import Optional, Union

import discord
from discord import app_commands
from discord.ext import commands

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session, transactional
from src.models import PendingGeneration, Player
from src.models.enums import ModerationStatus, PlayerStatus
# Corrected import path for generic CRUD functions
from src.core.crud_base_definitions import get_entity_by_id, update_entity
from src.core.ai_orchestrator import save_approved_generation
# Corrected import for CustomValidationError
from src.core.ai_response_parser import parse_and_validate_ai_response, CustomValidationError, ParsedAiData
# from src.config.settings import MASTER_ROLE_NAME # Assuming a setting for Master role name

logger = logging.getLogger(__name__)

# A placeholder for checking master role. In a real bot, this would be more robust.
# For now, using discord.py's built-in permissions check.
# from src.config.settings import MASTER_ROLE_NAME # Assuming a setting for Master role name

# Helper for cog-wide permission check
def is_administrator():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild: # Should be caught by guild_only=True on commands
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True, delete_after=10)
            return False
        # Ensure user is not None and has guild_permissions attribute
        if interaction.user is None or not hasattr(interaction.user, 'guild_permissions'):
             await interaction.response.send_message("Could not verify permissions.", ephemeral=True, delete_after=10)
             return False
        if not interaction.user.guild_permissions.administrator: # type: ignore
            await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True, delete_after=10)
            return False
        return True
    return app_commands.check(predicate)


class MasterAICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Group for AI moderation commands
    master_ai_group = app_commands.Group(
        name="master_ai",
        description="Master commands for AI content moderation.",
        guild_only=True
    )

    @master_ai_group.command(name="review", description="Review a pending AI generation.")
    @app_commands.describe(pending_id="The ID of the pending generation to review.")
    @is_administrator()
    async def review_ai(self, interaction: discord.Interaction, pending_id: int):
        """Displays details of a pending AI generation for review."""
        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            if interaction.guild_id is None: # Should be caught by guild_only
                await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
                return

            pending_gen = await get_entity_by_id(session, PendingGeneration, entity_id=pending_id, guild_id=interaction.guild_id)

            if not pending_gen:
                await interaction.followup.send(f"Pending generation with ID {pending_id} not found for this guild.", ephemeral=True)
                return

            embed = discord.Embed(title=f"Reviewing AI Generation ID: {pending_gen.id}", color=discord.Color.blue())
            status_value = pending_gen.status.value if isinstance(pending_gen.status, ModerationStatus) else pending_gen.status
            embed.add_field(name="Status", value=status_value, inline=True)
            embed.add_field(name="Guild ID", value=str(pending_gen.guild_id), inline=True)
            embed.add_field(name="Triggered By User ID", value=str(pending_gen.triggered_by_user_id) if pending_gen.triggered_by_user_id else "N/A", inline=True)
            embed.add_field(name="Created At", value=pending_gen.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if pending_gen.created_at else "N/A", inline=True)

            if pending_gen.trigger_context_json:
                try:
                    trigger_ctx_str = json.dumps(pending_gen.trigger_context_json, indent=2, ensure_ascii=False)
                    embed.add_field(name="Trigger Context", value=f"```json\n{trigger_ctx_str[:1000]}\n```" + ("..." if len(trigger_ctx_str) > 1000 else ""), inline=False)
                except TypeError:
                    embed.add_field(name="Trigger Context", value="Error displaying context (likely non-serializable data).", inline=False)


            if pending_gen.ai_prompt_text:
                embed.add_field(name="AI Prompt (first 1000 chars)", value=f"```\n{pending_gen.ai_prompt_text[:1000]}...\n```", inline=False)

            if pending_gen.raw_ai_response_text:
                 embed.add_field(name="Raw AI Response (first 1000 chars)", value=f"```json\n{pending_gen.raw_ai_response_text[:1000]}...\n```", inline=False)

            if pending_gen.parsed_validated_data_json:
                try:
                    parsed_data_str = json.dumps(pending_gen.parsed_validated_data_json, indent=2, ensure_ascii=False)
                    embed.add_field(name="Parsed/Validated Data (summary)", value=f"```json\n{parsed_data_str[:1000]}\n```" + ("..." if len(parsed_data_str) > 1000 else ""), inline=False)
                except TypeError:
                     embed.add_field(name="Parsed/Validated Data", value="Error displaying data (likely non-serializable data).", inline=False)


            if pending_gen.validation_issues_json:
                try:
                    validation_issues_str = json.dumps(pending_gen.validation_issues_json, indent=2, ensure_ascii=False)
                    embed.add_field(name="Validation Issues", value=f"```json\n{validation_issues_str[:1000]}\n```" + ("..." if len(validation_issues_str) > 1000 else ""), inline=False)
                except TypeError:
                    embed.add_field(name="Validation Issues", value="Error displaying issues (likely non-serializable data).", inline=False)

            if pending_gen.master_notes:
                embed.add_field(name="Master Notes", value=pending_gen.master_notes[:1020] + ("..." if len(pending_gen.master_notes) > 1020 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @master_ai_group.command(name="approve", description="Approve a pending AI generation.")
    @app_commands.describe(pending_id="The ID of the pending generation to approve.")
    @is_administrator()
    async def approve_ai(self, interaction: discord.Interaction, pending_id: int):
        """Approves a pending AI generation, triggering saving logic."""
        await interaction.response.defer(ephemeral=True)

        if interaction.guild_id is None:
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        # Use @transactional for the whole approval process to ensure atomicity
        # However, save_approved_generation is already @transactional.
        # Nested @transactional is fine if the outer one uses get_db_session()
        # and the inner one also uses get_db_session() or is passed the session.
        # For clarity, let's make this operation transactional.

        async def _approve_task(session: AsyncSession, pending_id: int, guild_id: int, user_id: int, user_name: str):
            pending_gen = await get_entity_by_id(session, PendingGeneration, entity_id=pending_id, guild_id=guild_id)

            if not pending_gen:
                return f"Pending generation ID {pending_id} not found."

            current_status_val = pending_gen.status.value if isinstance(pending_gen.status, ModerationStatus) else pending_gen.status
            allowed_statuses_for_approval = [
                ModerationStatus.PENDING_MODERATION.value,
                ModerationStatus.EDITED_PENDING_APPROVAL.value,
                ModerationStatus.VALIDATION_FAILED.value # Allow approving even if validation failed, Master's choice
            ]
            if current_status_val not in allowed_statuses_for_approval:
                return f"Pending generation ID {pending_id} is not in a state that can be approved (current: {current_status_val})."

            # Update status to APPROVED first. save_approved_generation will handle the rest.
            # Note: save_approved_generation itself is @transactional, so it will use its own session.
            # Committing here means the status update is durable before save_approved_generation runs.
            await update_entity(session, pending_gen, {
                "status": ModerationStatus.APPROVED, # Ensure this is the enum member, not value for DB
                "master_notes": f"Approved by {user_name} (ID: {user_id})."
            })
            # No explicit commit here, @transactional on _approve_task will handle it.
            logger.info(f"PendingGeneration ID {pending_id} marked as APPROVED by {user_name}. Triggering save.")
            return None # Indicates success in this part


        # Wrap the DB operations in a single transaction
        async with get_db_session() as session:
            approval_message = await _approve_task(session, pending_id, interaction.guild_id, interaction.user.id, str(interaction.user))
            if approval_message: # An error message was returned
                await interaction.followup.send(approval_message, ephemeral=True)
                return
            # If _approve_task was successful, the session will commit its changes.

        # Now, call save_approved_generation, which runs in its own transaction.
        # This is fine, as the state change to APPROVED is already committed.
        save_success = await save_approved_generation(pending_generation_id=pending_id, guild_id=interaction.guild_id)

        if save_success:
            await interaction.followup.send(f"Pending generation ID {pending_id} approved and entities are being saved.", ephemeral=True)
        else:
            # The status is APPROVED in DB, but saving failed. Master might need to re-trigger save or investigate.
            await interaction.followup.send(f"Pending generation ID {pending_id} approved, but an error occurred during the saving process. Status remains APPROVED. Check logs. You may need to manually trigger a save or re-assess.", ephemeral=True)


    @master_ai_group.command(name="reject", description="Reject a pending AI generation.")
    @app_commands.describe(pending_id="The ID of the pending generation to reject.", reason="Optional reason for rejection.")
    @is_administrator()
    # Removed @transactional decorator
    async def reject_ai(self, interaction: discord.Interaction, pending_id: int, reason: Optional[str] = None): # No session parameter here
        """Rejects a pending AI generation."""
        await interaction.response.defer(ephemeral=True)
        notes = f"Rejected by {interaction.user} (ID: {interaction.user.id})."
        if reason:
            notes += f" Reason: {reason}"

        if interaction.guild_id is None: # Should be caught by guild_only on group
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session: # Obtain session using context manager
            pending_gen = await get_entity_by_id(session, PendingGeneration, entity_id=pending_id, guild_id=interaction.guild_id)
            if not pending_gen:
                await interaction.followup.send(f"Pending generation ID {pending_id} not found.", ephemeral=True)
                return

            original_player_id_if_any = pending_gen.triggered_by_user_id
            await update_entity(session, pending_gen, {"status": ModerationStatus.REJECTED, "master_notes": notes})

            if original_player_id_if_any:
                player = await get_entity_by_id(session, Player, entity_id=original_player_id_if_any, guild_id=interaction.guild_id) # Ensure guild_id for player fetch
                if player and player.current_status == PlayerStatus.AWAITING_MODERATION:
                    # TODO: More robust check if this was the *only* pending item for the player.
                    await update_entity(session, player, {"current_status": PlayerStatus.EXPLORING})
                    logger.info(f"Player {player.id} status updated from {PlayerStatus.AWAITING_MODERATION.name} to {PlayerStatus.EXPLORING.name} after generation ID {pending_id} rejected.")
            await session.commit() # Commit changes within the session block

        await interaction.followup.send(f"Pending generation ID {pending_id} has been rejected.", ephemeral=True)


    @master_ai_group.command(name="edit", description="Edit the data of a pending AI generation.")
    @app_commands.describe(pending_id="ID of the pending generation.", new_data_json_str="JSON string of the new data for 'parsed_validated_data_json'.")
    @is_administrator()
    # Removed @transactional decorator
    async def edit_ai(self, interaction: discord.Interaction, pending_id: int, new_data_json_str: str): # No session parameter here
        """Edits the 'parsed_validated_data_json' of a pending AI generation."""
        await interaction.response.defer(ephemeral=True)

        if interaction.guild_id is None: # Should be caught by guild_only on group
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        try:
            new_parsed_data_dict = json.loads(new_data_json_str)
            ParsedAiData(**new_parsed_data_dict) # Basic validation
        except json.JSONDecodeError:
            await interaction.followup.send("Invalid JSON string provided for new data.", ephemeral=True)
            return
        except Exception as pydantic_error: # Catch Pydantic validation error
            await interaction.followup.send(f"The provided JSON is not valid against ParsedAiData schema: {pydantic_error}", ephemeral=True)
            return

        async with get_db_session() as session: # Obtain session using context manager
            pending_gen = await get_entity_by_id(session, PendingGeneration, entity_id=pending_id, guild_id=interaction.guild_id)
            if not pending_gen:
                await interaction.followup.send(f"Pending generation ID {pending_id} not found.", ephemeral=True)
                return

            current_status_val = pending_gen.status.value if isinstance(pending_gen.status, ModerationStatus) else pending_gen.status
            allowed_statuses_for_edit = [
                ModerationStatus.PENDING_MODERATION.value,
                ModerationStatus.VALIDATION_FAILED.value,
                ModerationStatus.EDITED_PENDING_APPROVAL.value,
                ModerationStatus.REJECTED.value # Allow editing a rejected item
            ]
            if current_status_val not in allowed_statuses_for_edit:
                 await interaction.followup.send(f"Pending generation ID {pending_id} cannot be edited in its current state: {current_status_val}.", ephemeral=True)
                 return

            await update_entity(session, pending_gen, {
                "parsed_validated_data_json": new_parsed_data_dict,
                "status": ModerationStatus.EDITED_PENDING_APPROVAL,
                "validation_issues_json": None, # Clear previous validation issues as data is new
                "master_notes": f"Edited by {interaction.user} (ID: {interaction.user.id}). Previous notes: {pending_gen.master_notes or ''}"
            })
            await session.commit() # Commit changes within the session block

        await interaction.followup.send(f"Pending generation ID {pending_id} data updated and set to EDITED_PENDING_APPROVAL. Review and approve again if necessary.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MasterAICog(bot))
    logger.info("MasterAICog loaded.")

# Need to ensure this cog is added to BOT_COGS in settings.py
# Example: BOT_COGS = [..., "src.bot.commands.master_ai_commands"]
