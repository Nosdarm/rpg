import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from src.core.crud.crud_party import party_crud
from src.core.crud.crud_player import player_crud
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template
from src.models.party import PartyTurnStatus, Party

logger = logging.getLogger(__name__)

class MasterPartyCog(commands.Cog, name="Master Party Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterPartyCog initialized.")

    party_master_cmds = app_commands.Group(
        name="master_party",
        description="Master commands for managing parties.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @party_master_cmds.command(name="view", description="View details of a specific party.")
    @app_commands.describe(party_id="The database ID of the party to view.")
    async def party_view(self, interaction: discord.Interaction, party_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            party = await party_crud.get(session, id=party_id, guild_id=interaction.guild_id)

            if not party:
                not_found_msg_template = await get_localized_message_template(
                    session, interaction.guild_id, "party_view:not_found", lang_code,
                    "Party with ID {party_id} not found in this guild."
                ) # type: ignore
                await interaction.followup.send(not_found_msg_template.format(party_id=party_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "party_view:title", lang_code,
                "Party Details: {party_name} (ID: {party_id})"
            ) # type: ignore
            # Use party.name directly as name_i18n is not in the model
            embed_title = title_template.format(party_name=party.name, party_id=party.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_gold())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"party_view:label_{key}", lang_code, default) # type: ignore

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(party.guild_id), inline=True)
            embed.add_field(name=await get_label("leader_id", "Leader Player ID"), value=str(party.leader_player_id) if party.leader_player_id else "N/A", inline=True)
            embed.add_field(name=await get_label("status", "Turn Status"), value=party.turn_status.value if party.turn_status else "N/A", inline=True)

            # Display the simple party.name instead of name_i18n
            embed.add_field(name=await get_label("name", "Name"), value=party.name, inline=False)

            properties_str = await get_localized_message_template(session, interaction.guild_id, "party_view:value_na_json", lang_code, "Not available") # type: ignore
            if hasattr(party, 'properties_json') and party.properties_json: # type: ignore[attr-defined] # Check if properties_json exists
                try:
                    properties_str = json.dumps(party.properties_json, indent=2, ensure_ascii=False) # type: ignore[attr-defined]
                except TypeError:
                    properties_str = await get_localized_message_template(session, interaction.guild_id, "party_view:error_serialization", lang_code, "Error serializing Properties JSON") # type: ignore
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{properties_str[:1000]}\n```" + ("..." if len(properties_str) > 1000 else ""), inline=False)

            player_ids = party.player_ids_json if party.player_ids_json else []
            members_info = []
            if player_ids:
                players_in_party = await player_crud.get_many_by_ids(session, ids=player_ids, guild_id=interaction.guild_id)
                player_id_to_name_map = {p.id: p.name for p in players_in_party}

                for p_id in player_ids:
                    p_name = player_id_to_name_map.get(p_id, "Unknown Player")
                    members_info.append(f"ID: {p_id} (Name: {p_name})")

            members_label = await get_label("members", "Members")
            if members_info:
                embed.add_field(name=f"{members_label} ({len(members_info)})", value="\n".join(members_info)[:1020] + ("..." if len("\n".join(members_info)) > 1020 else ""), inline=False)
            else:
                no_members_msg = await get_localized_message_template(session, interaction.guild_id, "party_view:no_members", lang_code, "No members in this party.") # type: ignore
                embed.add_field(name=members_label, value=no_members_msg, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @party_master_cmds.command(name="list", description="List parties in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of parties per page.")
    async def party_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            parties = await party_crud.get_multi(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_parties_stmt = select(func.count(party_crud.model.id)).where(party_crud.model.guild_id == interaction.guild_id)
            total_parties_result = await session.execute(total_parties_stmt)
            total_parties = total_parties_result.scalar_one_or_none() or 0

            if not parties:
                no_parties_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_list:no_parties_found_page", lang_code,
                    "No parties found for this guild (Page {page})."
                ) # type: ignore
                await interaction.followup.send(no_parties_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "party_list:title", lang_code,
                "Party List (Page {page} of {total_pages})"
            ) # type: ignore
            total_pages = ((total_parties - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_teal())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "party_list:footer", lang_code,
                "Displaying {count} of {total} total parties."
            ) # type: ignore
            embed.set_footer(text=footer_template.format(count=len(parties), total=total_parties))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "party_list:party_field_name", lang_code,
                "ID: {party_id} | {party_name}"
            ) # type: ignore
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "party_list:party_field_value", lang_code,
                "Leader ID: {leader_id}, Members: {member_count}, Status: {status}"
            ) # type: ignore

            for p in parties:
                # Use p.name directly
                member_count = len(p.player_ids_json) if p.player_ids_json else 0
                embed.add_field(
                    name=field_name_template.format(party_id=p.id, party_name=p.name),
                    value=field_value_template.format(
                        leader_id=str(p.leader_player_id) if p.leader_player_id else "N/A",
                        member_count=member_count,
                        status=p.turn_status.value if p.turn_status else "N/A"
                    ),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_list:no_parties_to_display", lang_code,
                    "No parties found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @party_master_cmds.command(name="create", description="Create a new party in this guild.")
    @app_commands.describe(
        name="The name of the party.",
        leader_player_id="Optional: The database ID of the player who will lead this party.",
        player_ids_json="Optional: JSON string of player IDs to add to this party (e.g., [1, 2, 3]).",
        properties_json="Optional: JSON string for additional party properties."
    )
    async def party_create(self, interaction: discord.Interaction,
                           name: str, # Changed from name_i18n_json
                           leader_player_id: Optional[int] = None,
                           player_ids_json: Optional[str] = None,
                           properties_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        lang_code = str(interaction.locale) # Keep for other localizations if any
        # parsed_name_i18n is no longer needed
        parsed_player_ids: Optional[List[int]] = None
        parsed_properties: Optional[Dict[str, Any]] = None
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            if leader_player_id:
                leader_player = await player_crud.get(session, id=leader_player_id, guild_id=interaction.guild_id)
                if not leader_player:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "party_create:error_leader_not_found", lang_code,
                        "Leader player with ID {player_id} not found in this guild."
                    ) # type: ignore
                    await interaction.followup.send(error_msg.format(player_id=leader_player_id), ephemeral=True)
                    return

            # name_i18n_json logic removed

            if player_ids_json:
                try:
                    parsed_player_ids = json.loads(player_ids_json)
                    if not isinstance(parsed_player_ids, list) or not all(isinstance(pid, int) for pid in parsed_player_ids):
                        raise ValueError("player_ids_json must be a list of integers.")
                    if parsed_player_ids:
                        found_players = await player_crud.get_many_by_ids(session, ids=parsed_player_ids, guild_id=interaction.guild_id)
                        found_player_ids = {p.id for p in found_players}
                        missing_player_ids = [pid for pid in parsed_player_ids if pid not in found_player_ids]
                        if missing_player_ids:
                            error_msg = await get_localized_message_template(
                                session, interaction.guild_id, "party_create:error_member_not_found", lang_code,
                                "One or more player IDs in player_ids_json not found in this guild: {missing_ids}"
                            ) # type: ignore
                            await interaction.followup.send(error_msg.format(missing_ids=", ".join(map(str, missing_player_ids))), ephemeral=True)
                            return
                except ValueError as e:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "party_create:error_invalid_player_ids_json", lang_code,
                        "Invalid format for player_ids_json: {error_details}"
                    ) # type: ignore
                    await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                    return
                # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
                # except json.JSONDecodeError as e:
                #     error_msg = await get_localized_message_template(
                #         session, interaction.guild_id, "party_create:error_invalid_player_ids_json", lang_code,
                #         "Invalid format for player_ids_json: {error_details}"
                #     ) # type: ignore
                #     await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                #     return

            if properties_json:
                try:
                    parsed_properties = json.loads(properties_json)
                    if not isinstance(parsed_properties, dict):
                        raise ValueError("properties_json must be a dictionary.")
                except ValueError as e:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "party_create:error_invalid_properties_json", lang_code,
                        "Invalid format for properties_json: {error_details}"
                    ) # type: ignore
                    await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                    return
                # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
                # except json.JSONDecodeError as e:
                #     error_msg = await get_localized_message_template(
                #         session, interaction.guild_id, "party_create:error_invalid_properties_json", lang_code,
                #         "Invalid format for properties_json: {error_details}"
                #     ) # type: ignore
                #     await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                #     return

            party_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, # Already checked not None
                "name": name, # Use the new 'name' parameter
                "leader_player_id": leader_player_id,
                "player_ids_json": parsed_player_ids if parsed_player_ids else [],
                "turn_status": PartyTurnStatus.IDLE, # Default status, ACTIVE was not a valid member
                "properties_json": parsed_properties if parsed_properties else {}
            }
            # name_i18n default logic removed

            created_party: Optional[Party] = None
            try:
                async with session.begin():
                    # guild_id is already in party_data_to_create and handled by CRUDBase.create
                    created_party = await party_crud.create(session, obj_in=party_data_to_create)
                    if created_party and parsed_player_ids:
                        for p_id in parsed_player_ids:
                            player_to_update = await player_crud.get(session, id=p_id, guild_id=interaction.guild_id)
                            if player_to_update:
                                player_to_update.current_party_id = created_party.id
                                session.add(player_to_update)
                    await session.flush()
                    if created_party:
                        await session.refresh(created_party)
            except Exception as e:
                logger.error(f"Error creating party with data {party_data_to_create}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_create:error_generic_create", lang_code,
                    "An error occurred while creating the party: {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True)
                return

            if not created_party:
                error_msg = await get_localized_message_template(
                     session, interaction.guild_id, "party_create:error_creation_failed_unknown", lang_code,
                    "Party creation failed for an unknown reason."
                ) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "party_create:success_title", lang_code,
                "Party Created: {party_name} (ID: {party_id})"
            ) # type: ignore
            # Use created_party.name directly
            embed = discord.Embed(title=success_title_template.format(party_name=created_party.name, party_id=created_party.id), color=discord.Color.green())
            embed.add_field(name="Leader Player ID", value=str(created_party.leader_player_id) if created_party.leader_player_id else "N/A", inline=True)
            embed.add_field(name="Member Count", value=str(len(created_party.player_ids_json or [])), inline=True) # type: ignore
            embed.add_field(name="Status", value=created_party.turn_status.value, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @party_master_cmds.command(name="update", description="Update a specific field for a party.")
    @app_commands.describe(
        party_id="The database ID of the party to update.",
        field_to_update="The name of the party field to update (e.g., name, leader_player_id, player_ids_json, properties_json, turn_status).",
        new_value="The new value for the field (use JSON for complex types; for player_ids_json, provide a complete new list; for turn_status, use enum name like ACTIVE)."
    )
    async def party_update(self, interaction: discord.Interaction, party_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        allowed_fields = {
            "name": str, # Changed from name_i18n
            "leader_player_id": (int, type(None)),
            "player_ids_json": list,
            "properties_json": dict,
            "turn_status": PartyTurnStatus,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        # Remove specific handling for name_i18n_json as it's now just 'name'
        if field_to_update_lower.endswith("_json") and field_to_update_lower in allowed_fields:
             db_field_name = field_to_update_lower # No replace needed if direct match

        field_type = allowed_fields.get(db_field_name)

        if not field_type:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "party_update:error_field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update or does not exist. Allowed fields: {allowed_list}"
                ) # type: ignore
            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True)
            return

        parsed_value: Any = None
        original_player_ids_before_update: Optional[List[int]] = None

        async with get_db_session() as session:
            try:
                if db_field_name == "name":
                    parsed_value = new_value # It's a simple string now
                elif db_field_name == "leader_player_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None:
                            leader_player = await player_crud.get(session, id=parsed_value, guild_id=interaction.guild_id)
                            if not leader_player:
                                error_msg = await get_localized_message_template(
                                    session, interaction.guild_id, "party_update:error_leader_not_found", lang_code,
                                    "New leader player with ID {player_id} not found in this guild."
                                ) # type: ignore
                                await interaction.followup.send(error_msg.format(player_id=parsed_value), ephemeral=True)
                                return
                # name_i18n case removed
                elif db_field_name == "player_ids_json":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, list) or not all(isinstance(pid, int) for pid in parsed_value):
                        raise ValueError("player_ids_json must be a list of integers.")
                    if parsed_value: # Only validate if list is not empty
                        found_players = await player_crud.get_many_by_ids(session, ids=parsed_value, guild_id=interaction.guild_id)
                        found_player_ids = {p.id for p in found_players}
                        missing_player_ids = [pid for pid in parsed_value if pid not in found_player_ids]
                        if missing_player_ids:
                            error_msg = await get_localized_message_template(
                                session, interaction.guild_id, "party_update:error_member_not_found", lang_code,
                                "One or more player IDs in new player_ids_json not found: {missing_ids}"
                            ) # type: ignore
                            await interaction.followup.send(error_msg.format(missing_ids=", ".join(map(str, missing_player_ids))), ephemeral=True)
                            return
                elif db_field_name == "properties_json":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict):
                        raise ValueError("properties_json must be a dictionary.")
                elif db_field_name == "turn_status":
                    try:
                        parsed_value = PartyTurnStatus[new_value.upper()]
                    except KeyError:
                        valid_statuses = ", ".join([s.name for s in PartyTurnStatus])
                        error_msg = await get_localized_message_template(
                            session, interaction.guild_id, "party_update:error_invalid_turn_status", lang_code,
                            "Invalid turn_status '{value}'. Valid statuses: {statuses}"
                        ) # type: ignore
                        await interaction.followup.send(error_msg.format(value=new_value, statuses=valid_statuses), ephemeral=True)
                        return
                else: # Should not be reached if field_type check is correct
                    error_msg = await get_localized_message_template(
                         session, interaction.guild_id, "party_update:error_unknown_field_type", lang_code,
                        "Internal error: Unknown field type for '{field_name}'."
                    ) # type: ignore
                    await interaction.followup.send(error_msg.format(field_name=db_field_name), ephemeral=True)
                    return
            except ValueError as e: # Specific exception first
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_update:error_invalid_value_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Expected type: {expected_type}. Details: {details}"
                ) # type: ignore
                expected_type_str = field_type.__name__ if not isinstance(field_type, tuple) else 'int or None' # type: ignore
                if field_type == PartyTurnStatus: expected_type_str = "PartyTurnStatus enum name" # type: ignore
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, expected_type=expected_type_str, details=str(e)), ephemeral=True)
                return
            # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
            # except json.JSONDecodeError as e:
            #     error_msg = await get_localized_message_template(
            #         session, interaction.guild_id, "party_update:error_invalid_json", lang_code,
            #         "Invalid JSON string '{value}' for field '{field_name}'. Details: {details}"
            #     ) # type: ignore
            #     await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
            #     return

            party_to_update = await party_crud.get(session, id=party_id, guild_id=interaction.guild_id)
            if not party_to_update:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_update:error_party_not_found", lang_code,
                    "Party with ID {party_id} not found in this guild."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(party_id=party_id), ephemeral=True)
                return

            if db_field_name == "player_ids_json":
                original_player_ids_before_update = list(party_to_update.player_ids_json) if party_to_update.player_ids_json else []

            update_data_dict = {db_field_name: parsed_value}
            updated_party: Optional[Party] = None # Explicitly type
            try:
                async with session.begin():
                    updated_party = await update_entity(session, entity=party_to_update, data=update_data_dict)
                    if db_field_name == "player_ids_json" and parsed_value is not None and updated_party is not None:
                        new_player_ids_set = set(parsed_value)
                        old_player_ids_set = set(original_player_ids_before_update if original_player_ids_before_update is not None else [])
                        players_to_remove_from_party = old_player_ids_set - new_player_ids_set
                        players_to_add_to_party = new_player_ids_set - old_player_ids_set
                        for p_id in players_to_remove_from_party:
                            player = await player_crud.get(session, id=p_id, guild_id=interaction.guild_id)
                            if player and player.current_party_id == updated_party.id:
                                player.current_party_id = None
                                session.add(player)
                        for p_id in players_to_add_to_party:
                            player = await player_crud.get(session, id=p_id, guild_id=interaction.guild_id)
                            if player:
                                player.current_party_id = updated_party.id
                                session.add(player)
                    await session.flush()
                    if updated_party: # Refresh only if not None
                        await session.refresh(updated_party)
            except Exception as e:
                logger.error(f"Error updating party {party_id} with data {update_data_dict}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_update:error_generic_update", lang_code,
                    "An error occurred while updating party {party_id}: {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(party_id=party_id, error_message=str(e)), ephemeral=True)
                return

            if not updated_party: # Check after potential refresh
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_update:error_update_failed_unknown", lang_code,
                    "Party update failed for an unknown reason."
                ) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return


            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "party_update:success_title", lang_code,
                "Party Updated: {party_name} (ID: {party_id})"
            ) # type: ignore
            # Use updated_party.name directly
            embed = discord.Embed(title=success_title_template.format(party_name=updated_party.name, party_id=updated_party.id), color=discord.Color.orange())

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "party_update:label_field_updated", lang_code, "Field Updated") # type: ignore
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "party_update:label_new_value", lang_code, "New Value") # type: ignore

            new_value_display = str(parsed_value)
            if isinstance(parsed_value, (dict, list)):
                new_value_display = f"```json\n{json.dumps(parsed_value, indent=2, ensure_ascii=False)}\n```"
            elif isinstance(parsed_value, PartyTurnStatus):
                new_value_display = parsed_value.name
            elif parsed_value is None:
                 new_value_display = "None"

            embed.add_field(name=field_updated_label, value=field_to_update, inline=True)
            embed.add_field(name=new_value_label, value=new_value_display, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @party_master_cmds.command(name="delete", description="Delete a party from this guild.")
    @app_commands.describe(party_id="The database ID of the party to delete.")
    async def party_delete(self, interaction: discord.Interaction, party_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        lang_code = str(interaction.locale)
        async with get_db_session() as session:
            party_to_delete = await party_crud.get(session, id=party_id, guild_id=interaction.guild_id)

            if not party_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_delete:error_not_found", lang_code,
                    "Party with ID {party_id} not found in this guild. Nothing to delete."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(party_id=party_id), ephemeral=True)
                return

            # Use party_to_delete.name directly
            party_name_for_message = party_to_delete.name
            player_ids_in_party = list(party_to_delete.player_ids_json) if party_to_delete.player_ids_json else []

            try:
                async with session.begin():
                    if player_ids_in_party:
                        for p_id in player_ids_in_party:
                            player = await player_crud.get(session, id=p_id, guild_id=interaction.guild_id)
                            if player and player.current_party_id == party_id:
                                player.current_party_id = None
                                session.add(player)
                    deleted_party = await party_crud.delete(session, id=party_id, guild_id=interaction.guild_id)

                if deleted_party:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "party_delete:success", lang_code,
                        "Party '{party_name}' (ID: {party_id}) has been deleted successfully."
                    ) # type: ignore
                    await interaction.followup.send(success_msg.format(party_name=party_name_for_message, party_id=party_id), ephemeral=True)
                else: # Should not happen if found before
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "party_delete:error_not_deleted_unknown", lang_code,
                        "Party (ID: {party_id}) was found but could not be deleted for an unknown reason."
                    ) # type: ignore
                    await interaction.followup.send(error_msg.format(party_id=party_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting party {party_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_delete:error_generic", lang_code,
                    "An error occurred while deleting party '{party_name}' (ID: {party_id}): {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(party_name=party_name_for_message, party_id=party_id, error_message=str(e)), ephemeral=True)
                return

async def setup(bot: commands.Bot):
    cog = MasterPartyCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterPartyCog loaded.")
