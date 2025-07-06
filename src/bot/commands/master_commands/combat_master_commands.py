import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, and_

from src.core.crud.crud_combat_encounter import combat_encounter_crud
# from src.core.crud.crud_player import player_crud # Potentially for resetting status on delete
from src.core.database import get_db_session
# from src.core.crud_base_definitions import update_entity # Not used for CombatEncounter yet
from src.core.localization_utils import get_localized_message_template
from src.models.enums import CombatStatus # For status validation
# from src.models.enums import PlayerStatus # If resetting status on delete

logger = logging.getLogger(__name__)

class MasterCombatEncounterCog(commands.Cog, name="Master Combat Encounter Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterCombatEncounterCog initialized.")

    combat_master_cmds = app_commands.Group(
        name="master_combat_encounter",
        description="Master commands for managing Combat Encounters.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @combat_master_cmds.command(name="view", description="View details of a specific Combat Encounter.")
    @app_commands.describe(encounter_id="The database ID of the Combat Encounter to view.")
    async def combat_encounter_view(self, interaction: discord.Interaction, encounter_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            encounter = await combat_encounter_crud.get_by_id(session, id=encounter_id, guild_id=interaction.guild_id)

            if not encounter:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "combat_encounter_view:not_found", lang_code,
                    "Combat Encounter with ID {id} not found in this guild."
                ) # type: ignore
                await interaction.followup.send(not_found_msg.format(id=encounter_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "combat_encounter_view:title", lang_code,
                "Combat Encounter Details (ID: {id})"
            ) # type: ignore
            embed_title = title_template.format(id=encounter.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_red())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"combat_encounter_view:label_{key}", lang_code, default) # type: ignore

            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(encounter.guild_id), inline=True)
            embed.add_field(name=await get_label("location_id", "Location ID"), value=str(encounter.location_id) if encounter.location_id else "N/A", inline=True)
            embed.add_field(name=await get_label("status", "Status"), value=encounter.status.value if encounter.status else "N/A", inline=True)

            current_turn_number_val = getattr(encounter, 'current_turn_number', "N/A")
            current_index_val = getattr(encounter, 'current_index_in_turn_order', "N/A")
            embed.add_field(name=await get_label("turn_number", "Turn Number"), value=str(current_turn_number_val), inline=True)
            embed.add_field(name=await get_label("current_index", "Current Index"), value=str(current_index_val), inline=True)

            current_entity_id_val = str(encounter.current_turn_entity_id) if encounter.current_turn_entity_id else "N/A"
            # encounter.current_turn_entity_type is likely already a string if .value was an error
            current_entity_type_val = encounter.current_turn_entity_type if encounter.current_turn_entity_type else "N/A"
            embed.add_field(name=await get_label("current_entity", "Current Turn Entity"), value=f"ID: {current_entity_id_val}, Type: {current_entity_type_val}", inline=True)

            participants_str = await format_json_field_helper(encounter.participants_json, "combat_encounter_view:value_na_json", "combat_encounter_view:error_serialization_participants")
            embed.add_field(name=await get_label("participants", "Participants JSON"), value=f"```json\n{participants_str[:1000]}\n```" + ("..." if len(participants_str) > 1000 else ""), inline=False)

            turn_order_str = await format_json_field_helper(encounter.turn_order_json, "combat_encounter_view:value_na_json", "combat_encounter_view:error_serialization_turn_order")
            embed.add_field(name=await get_label("turn_order", "Turn Order JSON"), value=f"```json\n{turn_order_str[:1000]}\n```" + ("..." if len(turn_order_str) > 1000 else ""), inline=False)

            rules_snapshot_str = await format_json_field_helper(encounter.rules_config_snapshot_json, "combat_encounter_view:value_na_json", "combat_encounter_view:error_serialization_rules")
            embed.add_field(name=await get_label("rules_snapshot", "Rules Snapshot JSON"), value=f"```json\n{rules_snapshot_str[:1000]}\n```" + ("..." if len(rules_snapshot_str) > 1000 else ""), inline=False)

            combat_log_str = await format_json_field_helper(encounter.combat_log_json, "combat_encounter_view:value_na_json", "combat_encounter_view:error_serialization_log")
            embed.add_field(name=await get_label("combat_log", "Combat Log JSON"), value=f"```json\n{combat_log_str[:1000]}\n```" + ("..." if len(combat_log_str) > 1000 else ""), inline=False)

            created_at_val = discord.utils.format_dt(encounter.created_at, style='F') if hasattr(encounter, 'created_at') and encounter.created_at else "N/A"
            updated_at_val = discord.utils.format_dt(encounter.updated_at, style='F') if hasattr(encounter, 'updated_at') and encounter.updated_at else "N/A"
            embed.add_field(name=await get_label("created_at", "Created At"), value=created_at_val, inline=False)
            embed.add_field(name=await get_label("updated_at", "Updated At"), value=updated_at_val, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @combat_master_cmds.command(name="list", description="List Combat Encounters in this guild, optionally filtered by status.")
    @app_commands.describe(
        status="Optional: Filter by status (e.g., ACTIVE, FINISHED_PLAYER_WON, FINISHED_NPC_WON).",
        page="Page number to display.",
        limit="Number of Combat Encounters per page."
    )
    async def combat_encounter_list(self, interaction: discord.Interaction,
                                    status: Optional[str] = None,
                                    page: int = 1, limit: int = 5):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 5: limit = 5 # Max 5 for this embed to prevent clutter

        lang_code = str(interaction.locale)
        status_enum: Optional[CombatStatus] = None

        async with get_db_session() as session:
            if status:
                try:
                    status_enum = CombatStatus[status.upper()]
                except KeyError: # If status string is not a valid enum key
                    valid_statuses = ", ".join([s.name for s in CombatStatus])
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "ce_list:error_invalid_status", lang_code, "Invalid status. Valid: {list}") # type: ignore
                    await interaction.followup.send(error_msg.format(list=valid_statuses), ephemeral=True); return

            filters = [combat_encounter_crud.model.guild_id == interaction.guild_id]
            if status_enum:
                filters.append(combat_encounter_crud.model.status == status_enum)

            offset = (page - 1) * limit
            query = select(combat_encounter_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(combat_encounter_crud.model.id.desc())
            result = await session.execute(query)
            encounters = result.scalars().all()

            count_query = select(func.count(combat_encounter_crud.model.id)).where(and_(*filters))
            total_enc_result = await session.execute(count_query)
            total_encounters = total_enc_result.scalar_one_or_none() or 0

            filter_desc_key = "ce_list:filter_all" if not status_enum else "ce_list:filter_status"
            filter_desc_default = "All" if not status_enum else "Status: {status_name}"
            filter_desc_val = await get_localized_message_template(session, interaction.guild_id, filter_desc_key, lang_code, filter_desc_default) # type: ignore
            filter_display = filter_desc_val.format(status_name=status_enum.name if status_enum else "")

            if not encounters:
                no_enc_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ce_list:no_encounters_found_page", lang_code,
                    "No Combat Encounters found for {filter_criteria} (Page {page})."
                ) # type: ignore
                await interaction.followup.send(no_enc_msg.format(filter_criteria=filter_display, page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "ce_list:title", lang_code,
                "Combat Encounter List ({filter_criteria} - Page {page} of {total_pages})"
            ) # type: ignore
            total_pages = ((total_encounters - 1) // limit) + 1
            embed_title = title_template.format(filter_criteria=filter_display, page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_purple())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "ce_list:footer", lang_code,
                "Displaying {count} of {total} total Encounters."
            ) # type: ignore
            embed.set_footer(text=footer_template.format(count=len(encounters), total=total_encounters))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "ce_list:encounter_field_name", lang_code,
                "ID: {id} | Status: {status_val}"
            ) # type: ignore
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "ce_list:encounter_field_value", lang_code,
                "Location ID: {loc_id}, Turn: {turn}, Participants: {p_count}"
            ) # type: ignore

            for enc in encounters:
                participant_count = len(enc.participants_json.get("entities", [])) if enc.participants_json else 0
                current_turn_number_val = getattr(enc, 'current_turn_number', "N/A")
                embed.add_field(
                    name=field_name_template.format(id=enc.id, status_val=enc.status.value if enc.status else "N/A"),
                    value=field_value_template.format(
                        loc_id=str(enc.location_id) if enc.location_id else "N/A",
                        turn=current_turn_number_val,
                        p_count=participant_count
                    ),
                    inline=False
                )

            if len(embed.fields) == 0: # Should not happen if `not encounters` check passes
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ce_list:no_enc_to_display", lang_code,
                    "No Encounters found to display on page {page} for {filter_criteria}."
                ) # type: ignore
                await interaction.followup.send(no_display_msg.format(page=page, filter_criteria=filter_display), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @combat_master_cmds.command(name="delete", description="Delete a Combat Encounter.")
    @app_commands.describe(encounter_id="The database ID of the Combat Encounter to delete.")
    async def combat_encounter_delete(self, interaction: discord.Interaction, encounter_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return
        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            encounter_to_delete = await combat_encounter_crud.get_by_id(session, id=encounter_id, guild_id=interaction.guild_id)

            if not encounter_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ce_delete:error_not_found", lang_code,
                    "Combat Encounter with ID {id} not found. Nothing to delete."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(id=encounter_id), ephemeral=True)
                return

            deleted_encounter: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_encounter = await combat_encounter_crud.remove_by_id(session, id=encounter_id, guild_id=interaction.guild_id) # type: ignore

                if deleted_encounter:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "ce_delete:success", lang_code,
                        "Combat Encounter (ID: {id}) has been deleted successfully."
                    ) # type: ignore
                    await interaction.followup.send(success_msg.format(id=encounter_id), ephemeral=True)
                else: # Should not happen if found before
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "ce_delete:error_not_deleted_unknown", lang_code,
                        "Combat Encounter (ID: {id}) was found but could not be deleted."
                    ) # type: ignore
                    await interaction.followup.send(error_msg.format(id=encounter_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Combat Encounter {encounter_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ce_delete:error_generic", lang_code,
                    "An error occurred while deleting Combat Encounter (ID: {id}): {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(id=encounter_id, error_message=str(e)), ephemeral=True)
                return

async def setup(bot: commands.Bot):
    cog = MasterCombatEncounterCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterCombatEncounterCog loaded.")
