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
# async def is_master(interaction: discord.Interaction) -> bool:
#     if interaction.guild is None: # Should not happen for guild commands
#         return False
#     # master_role = discord.utils.get(interaction.guild.roles, name=MASTER_ROLE_NAME)
#     # return master_role is not None and master_role in interaction.user.roles
#     # For now, let's assume guild owner is master, or any admin for simplicity in sandbox
#     return interaction.user.guild_permissions.administrator


class MasterAICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # This check is called for every interaction in this cog (app commands)
    async def interaction_check(self, interaction: discord.Interaction) -> bool: # type: ignore[override]
        if interaction.guild is None: # Should mostly be handled by guild_only=True on group/commands
            await interaction.response.send_message("Master commands can only be used in a server.", ephemeral=True, delete_after=10)
            return False
        # Assuming interaction.user has guild_permissions. For interactions in DMs, user might not have it.
        # However, these commands are guild_only.
        if not interaction.user.guild_permissions.administrator: # type: ignore
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True, delete_after=10)
            return False
        return True

    # Group for AI moderation commands
    master_ai_group = app_commands.Group(name="master_ai", description="Master commands for AI content moderation.", guild_only=True)

    @master_ai_group.command(name="review", description="Review a pending AI generation.")
    @app_commands.describe(pending_id="The ID of the pending generation to review.")
    async def review_ai(self, interaction: discord.Interaction, pending_id: int):
        """Displays details of a pending AI generation for review."""
        # Permission check is now handled by interaction_check

        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            pending_gen = await get_entity_by_id(session, PendingGeneration, pending_id, guild_id=interaction.guild_id)

            if not pending_gen:
                await interaction.followup.send(f"Pending generation with ID {pending_id} not found for this guild.", ephemeral=True)
                return

            embed = discord.Embed(title=f"Reviewing AI Generation ID: {pending_gen.id}", color=discord.Color.blue())
            embed.add_field(name="Status", value=pending_gen.status.name, inline=True)
            embed.add_field(name="Guild ID", value=str(pending_gen.guild_id), inline=True)
            embed.add_field(name="Triggered By User ID", value=str(pending_gen.triggered_by_user_id) or "N/A", inline=True)
            embed.add_field(name="Created At", value=pending_gen.created_at.strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)

            if pending_gen.trigger_context_json:
                embed.add_field(name="Trigger Context", value=f"```json\n{json.dumps(pending_gen.trigger_context_json, indent=2)}\n```", inline=False)

            if pending_gen.ai_prompt_text:
                embed.add_field(name="AI Prompt (first 500 chars)", value=f"```\n{pending_gen.ai_prompt_text[:500]}...\n```", inline=False)

            if pending_gen.raw_ai_response_text:
                 embed.add_field(name="Raw AI Response (first 500 chars)", value=f"```json\n{pending_gen.raw_ai_response_text[:500]}...\n```", inline=False)

            if pending_gen.parsed_validated_data_json:
                embed.add_field(name="Parsed/Validated Data (summary)", value=f"```json\n{json.dumps(pending_gen.parsed_validated_data_json, indent=2, ensure_ascii=False)[:500]}...\n```", inline=False)

            if pending_gen.validation_issues_json:
                embed.add_field(name="Validation Issues", value=f"```json\n{json.dumps(pending_gen.validation_issues_json, indent=2, ensure_ascii=False)}\n```", inline=False)

            if pending_gen.master_notes:
                embed.add_field(name="Master Notes", value=pending_gen.master_notes, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @master_ai_group.command(name="approve", description="Approve a pending AI generation.")
    @app_commands.describe(pending_id="The ID of the pending generation to approve.")
    async def approve_ai(self, interaction: discord.Interaction, pending_id: int):
        """Approves a pending AI generation, triggering saving logic."""
        # Permission check is now handled by interaction_check

        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            pending_gen = await get_entity_by_id(session, PendingGeneration, pending_id, guild_id=interaction.guild_id)

            if not pending_gen:
                await interaction.followup.send(f"Pending generation ID {pending_id} not found.", ephemeral=True)
                return

            if pending_gen.status not in [ModerationStatus.PENDING_MODERATION, ModerationStatus.EDITED_PENDING_APPROVAL, ModerationStatus.VALIDATION_FAILED]:
                await interaction.followup.send(f"Pending generation ID {pending_id} is not in a state that can be approved (current: {pending_gen.status.name}).", ephemeral=True)
                return

            # Update status to APPROVED first, then call save.
            # save_approved_generation will re-fetch and check status.
            updated_pending_gen = await update_entity(session, pending_gen, {
                "status": ModerationStatus.APPROVED,
                "master_notes": f"Approved by {interaction.user} (ID: {interaction.user.id})."
            })
            await session.commit() # Commit status change before calling save worker

        if updated_pending_gen:
            logger.info(f"PendingGeneration ID {pending_id} marked as APPROVED by {interaction.user}. Triggering save.")
            # Call the save worker logic (which is also @transactional, so it gets its own session)
            save_success = await save_approved_generation(pending_generation_id=pending_id, guild_id=interaction.guild_id) # type: ignore

            if save_success:
                await interaction.followup.send(f"Pending generation ID {pending_id} approved and entities are being saved.", ephemeral=True)
            else:
                await interaction.followup.send(f"Pending generation ID {pending_id} approved, but an error occurred during the saving process. Check logs.", ephemeral=True)
        else:
            await interaction.followup.send(f"Failed to update pending generation ID {pending_id} to APPROVED. Save not triggered.", ephemeral=True)


    @master_ai_group.command(name="reject", description="Reject a pending AI generation.")
    @app_commands.describe(pending_id="The ID of the pending generation to reject.", reason="Optional reason for rejection.")
    async def reject_ai(self, interaction: discord.Interaction, pending_id: int, reason: Optional[str] = None):
        """Rejects a pending AI generation."""
        # Permission check is now handled by interaction_check

        await interaction.response.defer(ephemeral=True)
        notes = f"Rejected by {interaction.user} (ID: {interaction.user.id})."
        if reason:
            notes += f" Reason: {reason}"

        async with get_db_session() as session:
            pending_gen = await get_entity_by_id(session, PendingGeneration, pending_id, guild_id=interaction.guild_id)
            if not pending_gen:
                await interaction.followup.send(f"Pending generation ID {pending_id} not found.", ephemeral=True)
                return

            # Store original status before rejecting, in case we need to revert a player
            original_player_id_if_any = pending_gen.triggered_by_user_id

            await update_entity(session, pending_gen, {"status": ModerationStatus.REJECTED, "master_notes": notes})

            # If a player triggered this and was awaiting moderation, revert their status
            if original_player_id_if_any:
                player = await get_entity_by_id(session, Player, entity_id=original_player_id_if_any, guild_id=interaction.guild_id) # type: ignore
                if player and player.current_status == PlayerStatus.AWAITING_MODERATION:
                    # Check if this was the *only* pending generation for this player.
                    # This is a simplified check. A more robust system might query PendingGeneration
                    # to see if other PENDING_MODERATION items exist for this player.
                    # For now, we assume rejecting this one means they are no longer awaiting this specific item.
                    await update_entity(session, player, {"current_status": PlayerStatus.EXPLORING})
                    logger.info(f"Player {player.id} status updated from {PlayerStatus.AWAITING_MODERATION.name} to {PlayerStatus.EXPLORING.name} after generation ID {pending_id} rejected.")

            await session.commit()

        await interaction.followup.send(f"Pending generation ID {pending_id} has been rejected.", ephemeral=True)

    @master_ai_group.command(name="edit", description="Edit the data of a pending AI generation.")
    @app_commands.describe(pending_id="ID of the pending generation.", new_data_json_str="JSON string of the new data for 'parsed_validated_data_json'.")
    async def edit_ai(self, interaction: discord.Interaction, pending_id: int, new_data_json_str: str):
        """Edits the 'parsed_validated_data_json' of a pending AI generation."""
        # Permission check is now handled by interaction_check

        await interaction.response.defer(ephemeral=True)

        try:
            new_parsed_data_dict = json.loads(new_data_json_str)
            # Attempt to re-validate the structure with ParsedAiData (or its components)
            # This is a simplified validation. A more robust one would re-run parts of parse_and_validate_ai_response
            # on the entities within new_parsed_data_dict["generated_entities"]
            try:
                # This assumes new_data_json_str is the full ParsedAiData structure
                ParsedAiData(**new_parsed_data_dict)
            except Exception as pydantic_error: # Catch Pydantic validation error specifically
                await interaction.followup.send(f"The provided JSON is not valid against ParsedAiData schema: {pydantic_error}", ephemeral=True)
                return

        except json.JSONDecodeError:
            await interaction.followup.send("Invalid JSON string provided for new data.", ephemeral=True)
            return

        async with get_db_session() as session:
            pending_gen = await get_entity_by_id(session, PendingGeneration, pending_id, guild_id=interaction.guild_id)
            if not pending_gen:
                await interaction.followup.send(f"Pending generation ID {pending_id} not found.", ephemeral=True)
                return

            if pending_gen.status not in [ModerationStatus.PENDING_MODERATION, ModerationStatus.VALIDATION_FAILED, ModerationStatus.EDITED_PENDING_APPROVAL]:
                 await interaction.followup.send(f"Pending generation ID {pending_id} cannot be edited in its current state: {pending_gen.status.name}.", ephemeral=True)
                 return

            await update_entity(session, pending_gen, {
                "parsed_validated_data_json": new_parsed_data_dict,
                "status": ModerationStatus.EDITED_PENDING_APPROVAL, # Or directly to PENDING_MODERATION
                "master_notes": f"Edited by {interaction.user} (ID: {interaction.user.id})."
            })
            await session.commit()

        await interaction.followup.send(f"Pending generation ID {pending_id} data updated and set to EDITED_PENDING_APPROVAL. Review and approve again if necessary.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MasterAICog(bot))
    logger.info("MasterAICog loaded.")

# Need to ensure this cog is added to BOT_COGS in settings.py
# Example: BOT_COGS = [..., "src.bot.commands.master_ai_commands"]
