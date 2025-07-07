import logging
import json # Added for player_view and other JSON parsing
from typing import Dict, Any, Optional # Added for type hinting

import discord
from discord import app_commands
from discord.ext import commands

# Импортируем декоратор is_administrator из master_ai_commands
# Это не самый лучший способ делить общий код, но для начала подойдет.
# В идеале, такой декоратор должен быть в общем утилитном модуле.
from .master_ai_commands import is_administrator

logger = logging.getLogger(__name__)

class MasterAdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Основная группа команд для Мастера
    master_admin_group = app_commands.Group(
        name="master_admin",
        description="General Master commands for server administration.",
        guild_only=True
    )

    # Пример простой команды внутри группы
    @master_admin_group.command(name="ping", description="A simple ping command for the Master Admin cog.")
    @is_administrator() # Используем существующий декоратор
    async def ping_command(self, interaction: discord.Interaction):
        """Responds with pong, testing the cog and permissions."""
        if interaction.guild_id is None: # Дополнительная проверка, хотя guild_only=True уже есть
            await interaction.response.send_message("This command must be used in a guild.", ephemeral=True)
            return
<<<<<<< HEAD
        
=======

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
        await interaction.response.send_message(f"Pong! Master Admin Cog is active in guild {interaction.guild_id}.", ephemeral=True)

    # --- Player CRUD ---
    player_group = app_commands.Group(name="player", description="Master commands for managing players.", parent=master_admin_group)

    @player_group.command(name="view", description="View details of a specific player.")
    @app_commands.describe(player_id="The database ID of the player to view.")
    @is_administrator()
    async def player_view(self, interaction: discord.Interaction, player_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        from src.core.crud.crud_player import player_crud # Local import
        from src.core.database import get_db_session # Local import
        from src.core.localization_utils import get_localized_message_template # For localization

        async with get_db_session() as session:
            player = await player_crud.get_by_id_and_guild(session, id=player_id, guild_id=interaction.guild_id)
            lang_code = str(interaction.locale)

            if not player:
                not_found_msg_template = await get_localized_message_template(
                    session, interaction.guild_id, "player_view:not_found", lang_code,
                    "Player with ID {player_id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg_template.format(player_id=player_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "player_view:title", lang_code,
                "Player Details: {player_name} (ID: {player_id})"
            )
            embed_title = title_template.format(player_name=player.name, player_id=player.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.green())

            # Helper function for field names
            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"player_view:field_{key}", lang_code, default)

            embed.add_field(name=await get_label("discord_id", "Discord ID"), value=str(player.discord_id), inline=True)
            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(player.guild_id), inline=True)
            embed.add_field(name=await get_label("level", "Level"), value=str(player.level), inline=True)
            embed.add_field(name=await get_label("xp", "XP"), value=str(player.xp), inline=True)
            embed.add_field(name=await get_label("unspent_xp", "Unspent XP"), value=str(player.unspent_xp), inline=True)
            embed.add_field(name=await get_label("location_id", "Current Location ID"), value=str(player.current_location_id) if player.current_location_id else "N/A", inline=True)
            embed.add_field(name=await get_label("party_id", "Current Party ID"), value=str(player.current_party_id) if player.current_party_id else "N/A", inline=True)
            embed.add_field(name=await get_label("status", "Status"), value=player.current_status.value if player.current_status else "N/A", inline=True)
            embed.add_field(name=await get_label("language", "Language"), value=player.language or "N/A", inline=True)
<<<<<<< HEAD
            
=======

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
            attributes_label = await get_label("attributes_json", "Attributes JSON")
            attributes_str = await get_localized_message_template(session, interaction.guild_id, "player_view:no_attributes", lang_code, "No attributes")
            if player.attributes_json:
                try:
                    attributes_str = json.dumps(player.attributes_json, indent=2, ensure_ascii=False)
                except TypeError:
                    attributes_str = await get_localized_message_template(session, interaction.guild_id, "player_view:error_attributes_serialization", lang_code, "Error displaying attributes (non-serializable).")
<<<<<<< HEAD
            
            embed.add_field(name=attributes_label, value=f"```json\n{attributes_str[:1000]}\n```" + ("..." if len(attributes_str) > 1000 else ""), inline=False)
            
=======

            embed.add_field(name=attributes_label, value=f"```json\n{attributes_str[:1000]}\n```" + ("..." if len(attributes_str) > 1000 else ""), inline=False)

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
            await interaction.followup.send(embed=embed, ephemeral=True)

    @player_group.command(name="list", description="List players in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of players per page.")
    @is_administrator()
    async def player_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 25: limit = 25 # Max embed field limit consideration

        from src.core.crud.crud_player import player_crud # Local import
        from src.core.database import get_db_session # Local import
        from sqlalchemy import func, select # For count

        async with get_db_session() as session:
            offset = (page - 1) * limit
            players = await player_crud.get_multi_by_guild(session, guild_id=interaction.guild_id, skip=offset, limit=limit)
<<<<<<< HEAD
            
=======

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
            total_players_stmt = select(func.count(player_crud.model.id)).where(player_crud.model.guild_id == interaction.guild_id)
            total_players_result = await session.execute(total_players_stmt)
            total_players = total_players_result.scalar_one_or_none() or 0

            if not players:
                await interaction.followup.send(f"No players found for this guild (Page {page}).", ephemeral=True)
                return

            embed = discord.Embed(title=f"Player List (Page {page} of {((total_players - 1) // limit) + 1})", color=discord.Color.blue())
            embed.set_footer(text=f"Displaying {len(players)} of {total_players} total players.")

            for p in players:
<<<<<<< HEAD
                embed.add_field(name=f"ID: {p.id} | {p.name}", 
                                value=f"Discord: <@{p.discord_id}>\nLevel: {p.level}, Status: {p.current_status.value}", 
                                inline=False)
            
=======
                embed.add_field(name=f"ID: {p.id} | {p.name}",
                                value=f"Discord: <@{p.discord_id}>\nLevel: {p.level}, Status: {p.current_status.value}",
                                inline=False)

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
            if len(embed.fields) == 0 : # Should be caught by "not players" but as a safeguard
                 await interaction.followup.send(f"No players found to display on page {page}.", ephemeral=True)
                 return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @player_group.command(name="update", description="Update a specific field for a player.")
    @app_commands.describe(
        player_id="The database ID of the player to update.",
        field_to_update="The name of the player field to update (e.g., name, level, xp, language).",
        new_value="The new value for the field (use JSON for complex types if supported)."
    )
    @is_administrator()
    async def player_update(self, interaction: discord.Interaction, player_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        from src.core.crud.crud_player import player_crud
        from src.core.database import get_db_session, transactional # transactional might be used if update_entity is not
        from src.core.crud_base_definitions import update_entity # Using generic update

        allowed_fields = {
            "name": str,
            "level": int,
            "xp": int,
            "unspent_xp": int,
            "language": str,
            "current_location_id": int, # Added
            "current_party_id": (int, type(None)), # Added, allow None
            # "attributes_json": dict, # Example for future: requires JSON parsing for new_value
            # "current_status": PlayerStatus # Example for future: requires enum conversion
        }

        field_type = allowed_fields.get(field_to_update.lower())
        if not field_type:
            await interaction.followup.send(f"Field '{field_to_update}' is not allowed for update or does not exist. Allowed fields: {', '.join(allowed_fields.keys())}", ephemeral=True)
            return

        parsed_value: any = None
        try:
            if field_type == str:
                parsed_value = new_value
            elif field_type == int:
                parsed_value = int(new_value)
            elif field_type == dict: # For future attributes_json
                parsed_value = json.loads(new_value)
            elif field_type == (int, type(None)): # For nullable int fields like current_party_id
                if new_value.lower() == 'none' or new_value.lower() == 'null':
                    parsed_value = None
                else:
                    parsed_value = int(new_value)
            # Add more type conversions as needed (e.g., for enums like PlayerStatus)
            else:
                await interaction.followup.send(f"Internal error: Type conversion for field '{field_to_update}' not implemented.", ephemeral=True)
                return

        except ValueError:
            await interaction.followup.send(f"Invalid value '{new_value}' for field '{field_to_update}'. Expected type: {field_type.__name__ if not isinstance(field_type, tuple) else 'int or None'}.", ephemeral=True)
            return
        except json.JSONDecodeError:
            await interaction.followup.send(f"Invalid JSON string '{new_value}' for field '{field_to_update}'.", ephemeral=True)
            return

        update_data = {field_to_update.lower(): parsed_value}

        async with get_db_session() as session:
            player = await player_crud.get_by_id_and_guild(session, id=player_id, guild_id=interaction.guild_id)
            if not player:
                await interaction.followup.send(f"Player with ID {player_id} not found in this guild.", ephemeral=True)
                return
<<<<<<< HEAD
            
=======

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
            # Use the generic update_entity function
            try:
                # update_entity is already @transactional or expects session to handle commit
                updated_player = await update_entity(session, entity=player, data=update_data)
                await session.commit() # Commit the changes made by update_entity
                await session.refresh(updated_player) # Refresh to get latest state if needed by embed
            except Exception as e:
                await session.rollback() # Rollback on error
                logger.error(f"Error updating player {player_id}: {e}", exc_info=True)
                await interaction.followup.send(f"An error occurred while updating player {player_id}: {e}", ephemeral=True)
                return

            embed = discord.Embed(title=f"Player Updated: {updated_player.name} (ID: {updated_player.id})", color=discord.Color.orange())
            embed.add_field(name="Field Updated", value=field_to_update, inline=True)
            embed.add_field(name="New Value", value=str(parsed_value) if not isinstance(parsed_value, dict) else f"```json\n{json.dumps(parsed_value, indent=2)}\n```", inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    # --- RuleConfig CRUD ---
    ruleconfig_group = app_commands.Group(name="ruleconfig", description="Master commands for managing RuleConfig entries.", parent=master_admin_group)

    @ruleconfig_group.command(name="get", description="Get a specific RuleConfig value.")
    @app_commands.describe(key="The key of the RuleConfig entry to view.")
    @is_administrator()
    async def ruleconfig_get(self, interaction: discord.Interaction, key: str):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        from src.core.rules import get_rule # Local import
        from src.core.database import get_db_session # Local import

        async with get_db_session() as session:
            # get_rule returns the value directly, or None if not found (using default=None)
            rule_value = await get_rule(session, guild_id=interaction.guild_id, key=key)

            if rule_value is None: # Check if rule was not found
                await interaction.followup.send(f"RuleConfig with key '{key}' not found for this guild.", ephemeral=True)
                return

            embed = discord.Embed(title=f"RuleConfig: {key}", color=discord.Color.purple())
            try:
                value_str = json.dumps(rule_value, indent=2, ensure_ascii=False)
            except TypeError:
                value_str = "Error displaying value (non-serializable)."
<<<<<<< HEAD
            
            embed.add_field(name="Key", value=key, inline=False)
            embed.add_field(name="Value", value=f"```json\n{value_str[:1000]}\n```" + ("..." if len(value_str) > 1000 else ""), inline=False)
            
=======

            embed.add_field(name="Key", value=key, inline=False)
            embed.add_field(name="Value", value=f"```json\n{value_str[:1000]}\n```" + ("..." if len(value_str) > 1000 else ""), inline=False)

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
            await interaction.followup.send(embed=embed, ephemeral=True)

    @ruleconfig_group.command(name="set", description="Set or update a RuleConfig value.")
    @app_commands.describe(key="The key of the RuleConfig entry.", value_json="The new JSON value for the rule.")
    @is_administrator()
    async def ruleconfig_set(self, interaction: discord.Interaction, key: str, value_json: str):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        from src.core.rules import update_rule_config # Local import
        from src.core.database import get_db_session # Local import for the context, though update_rule_config is @transactional

        try:
            new_value = json.loads(value_json)
        except json.JSONDecodeError:
            await interaction.followup.send(f"Invalid JSON string provided for value: {value_json}", ephemeral=True)
            return

        async with get_db_session() as session: # Session for update_rule_config if it wasn't @transactional
            try:
                # update_rule_config is @transactional, so it handles its own session and commit/rollback
                updated_rule = await update_rule_config(session, guild_id=interaction.guild_id, key=key, value=new_value)
                # No explicit commit here, as update_rule_config should handle it.
            except Exception as e:
                # If update_rule_config raises an error that isn't caught by its own transactional rollback,
                # we might log it here. But typically, @transactional should handle DB errors.
                logger.error(f"Error calling update_rule_config for key {key}: {e}", exc_info=True)
                await interaction.followup.send(f"An error occurred while setting rule '{key}': {e}", ephemeral=True)
                return
<<<<<<< HEAD
        
=======

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
        await interaction.followup.send(f"RuleConfig '{key}' has been set/updated successfully.", ephemeral=True)

    @ruleconfig_group.command(name="list", description="List all RuleConfig entries for this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of rules per page.")
    @is_administrator()
    async def ruleconfig_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10 # Embeds can get very long with many JSON values

        from src.core.rules import get_all_rules_for_guild # Local import
        from src.core.database import get_db_session # Local import

        async with get_db_session() as session:
            all_rules = await get_all_rules_for_guild(session, guild_id=interaction.guild_id)

        if not all_rules:
            await interaction.followup.send("No RuleConfig entries found for this guild.", ephemeral=True)
            return

        rules_list = sorted(all_rules.items()) # Sort by key for consistent paging
        total_rules = len(rules_list)
<<<<<<< HEAD
        
=======

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
        start_index = (page - 1) * limit
        end_index = start_index + limit
        paginated_rules = rules_list[start_index:end_index]

        if not paginated_rules:
            await interaction.followup.send(f"No rules found on page {page}.", ephemeral=True)
            return

        embed = discord.Embed(title=f"RuleConfig List (Page {page} of {((total_rules - 1) // limit) + 1})", color=discord.Color.dark_purple())
        embed.set_footer(text=f"Displaying {len(paginated_rules)} of {total_rules} total rules.")

        for key, value in paginated_rules:
            try:
                value_str = json.dumps(value, ensure_ascii=False) # Compact display for list
                if len(value_str) > 150: # Truncate very long values in list view
                    value_str = value_str[:150] + "..."
            except TypeError:
                value_str = "Error: Non-serializable value."
            embed.add_field(name=key, value=f"```json\n{value_str}\n```", inline=False)
<<<<<<< HEAD
        
=======

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- PendingConflict Management ---
    conflict_group = app_commands.Group(name="conflict", description="Master commands for managing pending conflicts.", parent=master_admin_group)

    @conflict_group.command(name="resolve", description="Resolve a pending conflict.")
    @app_commands.describe(
        pending_conflict_id="The ID of the pending conflict to resolve.",
        outcome_status="The resolution status (e.g., RESOLVED_BY_MASTER_FAVOR_ACTION1, RESOLVED_BY_MASTER_CUSTOM).",
        # resolved_action_json="Optional JSON for the custom resolved action (if outcome requires it).", # TODO: Add later if needed
        notes="Optional notes about the resolution."
    )
    @is_administrator()
<<<<<<< HEAD
    async def conflict_resolve(self, interaction: discord.Interaction, 
                               pending_conflict_id: int, 
                               outcome_status: str, 
=======
    async def conflict_resolve(self, interaction: discord.Interaction,
                               pending_conflict_id: int,
                               outcome_status: str,
>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
                               # resolved_action_json: Optional[str] = None, # TODO
                               notes: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        from src.core.database import get_db_session, transactional
        from src.models.pending_conflict import PendingConflict
        from src.models.enums import ConflictStatus
        from src.core.crud_base_definitions import get_entity_by_id, update_entity # Generic helpers
        from typing import Dict, Any, Optional # For type hinting

        try:
            # Validate outcome_status against ConflictStatus enum
            # We only allow resolution statuses that imply Master action.
            valid_resolution_statuses = {
                ConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION1,
                ConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION2, # Assuming there might be a second action
                ConflictStatus.RESOLVED_BY_MASTER_CUSTOM_ACTION,
                ConflictStatus.RESOLVED_BY_MASTER_DISMISS
            }
            resolved_status_enum: Optional[ConflictStatus] = None
            for status_member in ConflictStatus: # Iterate through enum members
                if status_member.name.upper() == outcome_status.upper() or status_member.value.upper() == outcome_status.upper():
                    if status_member in valid_resolution_statuses:
                        resolved_status_enum = status_member
                        break
                    else:
                        allowed_values = ", ".join([s.name for s in valid_resolution_statuses])
                        await interaction.followup.send(f"Invalid outcome_status '{outcome_status}'. Allowed values for master resolution: {allowed_values}", ephemeral=True)
                        return
<<<<<<< HEAD
            
=======

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
            if not resolved_status_enum:
                allowed_values = ", ".join([s.name for s in valid_resolution_statuses])
                await interaction.followup.send(f"Outcome status '{outcome_status}' not recognized or not a valid master resolution. Allowed: {allowed_values}", ephemeral=True)
                return

        except ValueError: # Should not happen with enum name check, but as safeguard
            await interaction.followup.send(f"Invalid value for outcome_status: '{outcome_status}'.", ephemeral=True)
            return

        # TODO: Parse resolved_action_json if provided and outcome_status is RESOLVED_BY_MASTER_CUSTOM_ACTION
        # parsed_resolved_action = None
        # if resolved_action_json and resolved_status_enum == ConflictStatus.RESOLVED_BY_MASTER_CUSTOM_ACTION:
        #     try:
        #         parsed_resolved_action = json.loads(resolved_action_json)
        #         # Potentially validate against ParsedAction model if needed
        #     except json.JSONDecodeError:
        #         await interaction.followup.send("Invalid JSON string for resolved_action_json.", ephemeral=True)
        #         return
        # elif resolved_action_json: # Provided but not needed for this status
        #     await interaction.followup.send(f"resolved_action_json is only applicable if outcome_status is RESOLVED_BY_MASTER_CUSTOM_ACTION.", ephemeral=True)
        #     return


        update_data: Dict[str, Any] = {
            "status": resolved_status_enum, # Store the enum member itself
            "resolution_notes": notes,
            "resolved_at": discord.utils.utcnow() # Set resolution time
        }
        # if parsed_resolved_action:
        #     update_data["resolved_action_json"] = parsed_resolved_action

        async with get_db_session() as session:
            try:
                # Using session.begin() to ensure atomicity for the read-update operation
                async with session.begin():
                    conflict = await get_entity_by_id(session, PendingConflict, entity_id=pending_conflict_id, guild_id=interaction.guild_id)

                    if not conflict:
                        await interaction.followup.send(f"PendingConflict with ID {pending_conflict_id} not found in this guild.", ephemeral=True)
                        # No specific rollback needed as session.begin() handles it if an error occurs before this point or if we return early
                        return

                    if conflict.status != ConflictStatus.PENDING_MASTER_RESOLUTION:
                        await interaction.followup.send(f"Conflict ID {pending_conflict_id} is not awaiting master resolution (current status: {conflict.status.value}).", ephemeral=True)
                        return

                    updated_conflict = await update_entity(session, entity=conflict, data=update_data)
                    # update_entity should have added to session and flushed. session.begin() will commit.
<<<<<<< HEAD
                    
                    # Placeholder for actual signaling:
                    logger.info(f"Conflict {updated_conflict.id} resolved by Master. Current status: {updated_conflict.status.value}. Notes: '{updated_conflict.resolution_notes}'. Action Processor signaling mechanism TBD.")
                
=======

                    # Placeholder for actual signaling:
                    logger.info(f"Conflict {updated_conflict.id} resolved by Master. Current status: {updated_conflict.status.value}. Notes: '{updated_conflict.resolution_notes}'. Action Processor signaling mechanism TBD.")

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
                # If we reach here, the transaction was successful
                await interaction.followup.send(f"Conflict ID {pending_conflict_id} has been resolved with status '{resolved_status_enum.name}'. Notes: {notes or 'N/A'}", ephemeral=True)

            except Exception as e:
                # session.begin() handles rollback on exception
                logger.error(f"Error resolving conflict {pending_conflict_id}: {e}", exc_info=True)
                await interaction.followup.send(f"An error occurred while resolving conflict {pending_conflict_id}: {e}", ephemeral=True)
                # No explicit rollback call needed here due to session.begin()
                return
<<<<<<< HEAD
    
=======

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
    @conflict_group.command(name="view", description="View details of a specific pending conflict.")
    @app_commands.describe(pending_conflict_id="The ID of the pending conflict to view.")
    @is_administrator()
    async def conflict_view(self, interaction: discord.Interaction, pending_conflict_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        from src.core.database import get_db_session
        from src.models.pending_conflict import PendingConflict
        from src.core.crud_base_definitions import get_entity_by_id

        async with get_db_session() as session:
            conflict = await get_entity_by_id(session, PendingConflict, entity_id=pending_conflict_id, guild_id=interaction.guild_id)

            if not conflict:
                await interaction.followup.send(f"PendingConflict with ID {pending_conflict_id} not found in this guild.", ephemeral=True)
                return

            embed = discord.Embed(title=f"Conflict Details (ID: {conflict.id})", color=discord.Color.red())
            embed.add_field(name="Status", value=conflict.status.value, inline=True)
            embed.add_field(name="Guild ID", value=str(conflict.guild_id), inline=True)
            embed.add_field(name="Created At", value=discord.utils.format_dt(conflict.created_at, style='F') if conflict.created_at else "N/A", inline=True)
            if conflict.resolved_at:
                embed.add_field(name="Resolved At", value=discord.utils.format_dt(conflict.resolved_at, style='F'), inline=True)

            involved_str = "Not available"
            if conflict.involved_entities_json:
                try:
                    involved_str = json.dumps(conflict.involved_entities_json, indent=2, ensure_ascii=False)
                except TypeError: involved_str = "Error: Non-serializable data"
            embed.add_field(name="Involved Entities", value=f"```json\n{involved_str[:1000]}\n```" + ("..." if len(involved_str) > 1000 else ""), inline=False)
<<<<<<< HEAD
            
=======

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
            actions_str = "Not available"
            if conflict.conflicting_actions_json:
                try:
                    actions_str = json.dumps(conflict.conflicting_actions_json, indent=2, ensure_ascii=False)
                except TypeError: actions_str = "Error: Non-serializable data"
            embed.add_field(name="Conflicting Actions", value=f"```json\n{actions_str[:1000]}\n```" + ("..." if len(actions_str) > 1000 else ""), inline=False)

            if conflict.resolution_notes:
                embed.add_field(name="Resolution Notes", value=conflict.resolution_notes[:1020] + ("..." if len(conflict.resolution_notes) > 1020 else ""), inline=False)
<<<<<<< HEAD
            
=======

>>>>>>> 3648882d7ce127ff9cdbdd88b7ec75d55362e395
            if conflict.resolved_action_json:
                resolved_action_str = "Not available"
                try:
                    resolved_action_str = json.dumps(conflict.resolved_action_json, indent=2, ensure_ascii=False)
                except TypeError: resolved_action_str = "Error: Non-serializable data"
                embed.add_field(name="Resolved Action", value=f"```json\n{resolved_action_str[:1000]}\n```" + ("..." if len(resolved_action_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    # Need to import json for player_view's attributes_json
    import json # Make json available in the cog's scope if methods need it
    cog = MasterAdminCog(bot)
    # Manually attach the player_group to the master_admin_group if not done by parent param.
    # This is usually handled by the parent=master_admin_group in Group definition.
    # For clarity, we can log or verify this.
    # logger.debug(f"MasterAdminCog master_admin_group: {cog.master_admin_group}")
    # logger.debug(f"Player group parent: {cog.player_group.parent}")
    await bot.add_cog(cog)
    logger.info("MasterAdminCog loaded successfully with player commands.")

# Не забудьте добавить "src.bot.commands.master_admin_commands" в BOT_COGS в src/config/settings.py
# BOT_COGS = [
#     "src.bot.commands.general_commands",
#     "src.bot.commands.movement_commands",
#     "src.bot.commands.party_commands",
#     "src.bot.commands.master_ai_commands",
#     "src.bot.commands.master_map_commands",
#     "src.bot.commands.character_commands", # Task 32
#     "src.bot.commands.master_admin_commands", # Новая строка
# ]
