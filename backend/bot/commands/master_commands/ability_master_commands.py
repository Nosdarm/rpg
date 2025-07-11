import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, and_, or_

from backend.core.crud.crud_ability import ability_crud
from backend.core.database import get_db_session
from backend.core.crud_base_definitions import update_entity
from backend.core.localization_utils import get_localized_message_template
from backend.bot.utils import parse_json_parameter # Import the utility

logger = logging.getLogger(__name__)

class MasterAbilityCog(commands.Cog, name="Master Ability Commands"): # type: ignore[call-arg]
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterAbilityCog initialized.")

    ability_master_cmds = app_commands.Group(
        name="master_ability",
        description="Master commands for managing Abilities.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True # Guild-only for master commands, but abilities can be global or guild-specific
    )

    @ability_master_cmds.command(name="view", description="View details of a specific Ability.")
    @app_commands.describe(ability_id="The database ID of the Ability to view.")
    async def ability_view(self, interaction: discord.Interaction, ability_id: int):
        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            ability = None
            # Since commands are guild_only=True, interaction.guild_id should always be an int.
            # We add an explicit check and assertion for type safety and to satisfy pyright.
            if interaction.guild_id is None:
                # This case should ideally not be reached due to guild_only=True
                await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
                return
            current_guild_id: int = interaction.guild_id

            ability = await ability_crud.get(session, id=ability_id, guild_id=current_guild_id)

            if not ability: # Try fetching as global if not found in guild
                global_ability = await ability_crud.get(session, id=ability_id, guild_id=None)
                if global_ability:
                    ability = global_ability

            if not ability: # If still not found
                not_found_msg = await get_localized_message_template(
                    session, current_guild_id, "ability_view:not_found", lang_code,
                    "Ability with ID {id} not found in this guild or globally."
                )
                await interaction.followup.send(not_found_msg.format(id=ability_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, current_guild_id, "ability_view:title", lang_code,
                "Ability Details: {name} (ID: {id})"
            )
            name_display = ability.name_i18n.get(lang_code, ability.name_i18n.get("en", f"Ability {ability.id}"))
            embed_title = title_template.format(name=name_display, id=ability.id)
            embed_color = discord.Color.blue() if ability.guild_id else discord.Color.light_grey()
            embed = discord.Embed(title=embed_title, color=embed_color)

            async def get_label(key: str, default: str) -> str:
                # current_guild_id is available from the outer scope
                return await get_localized_message_template(session, current_guild_id, f"ability_view:label_{key}", lang_code, default)
            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                # current_guild_id is available from the outer scope
                na_str_val = await get_localized_message_template(session, current_guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str_val
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, current_guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

            na_value_str = await get_localized_message_template(session, current_guild_id, "common:value_na", lang_code, "N/A") # type: ignore
            scope_global_str = await get_localized_message_template(session, current_guild_id, "common:scope_global", lang_code, "Global") # type: ignore
            scope_guild_tmpl = await get_localized_message_template(session, current_guild_id, "common:scope_guild", lang_code, "Guild ({guild_id})") # type: ignore

            scope_display = scope_global_str if ability.guild_id is None else scope_guild_tmpl.format(guild_id=ability.guild_id)
            # guild_id field is removed as scope_display covers it.
            # embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(ability.guild_id) if ability.guild_id else scope_global_str, inline=True)
            embed.add_field(name=await get_label("scope", "Scope"), value=scope_display, inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=ability.static_id or na_value_str, inline=True)
            ability_type_val = getattr(ability, 'type', None)
            embed.add_field(name=await get_label("type", "Type"), value=ability_type_val or na_value_str, inline=True)
            name_i18n_str = await format_json_field_helper(ability.name_i18n, "ability_view:value_na_json", "ability_view:error_serialization_name")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)
            desc_i18n_str = await format_json_field_helper(ability.description_i18n, "ability_view:value_na_json", "ability_view:error_serialization_desc")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)
            props_str = await format_json_field_helper(ability.properties_json, "ability_view:value_na_json", "ability_view:error_serialization_props")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @ability_master_cmds.command(name="list", description="List Abilities, optionally filtered by scope.")
    @app_commands.describe(scope="Scope to filter by ('guild', 'global', or 'all'). Defaults to 'all'.", page="Page number.", limit="Abilities per page.")
    @app_commands.choices(scope=[app_commands.Choice(name="All (Guild & Global)", value="all"), app_commands.Choice(name="Guild-Specific", value="guild"), app_commands.Choice(name="Global Only", value="global"),])
    async def ability_list(self, interaction: discord.Interaction, scope: Optional[app_commands.Choice[str]] = None, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        lang_code = str(interaction.locale)
        # Early guild_id check for guild-specific scope
        if scope and scope.value == "guild" and interaction.guild_id is None:
            await interaction.followup.send("Guild-specific scope requires this command to be used in a guild.", ephemeral=True)
            return

        # Since commands are guild_only=True, interaction.guild_id should always be an int if not DM.
        # However, for 'global' or 'all' scope, guild_id might not be strictly necessary for DB query
        # but is needed for localization.
        # For guild-specific actions or localization, we need a valid guild_id.
        # The `guild_only=True` on the group should ensure interaction.guild_id is set.
        if interaction.guild_id is None:
            # This path should not be hit if command is used in a guild.
            # If it's a global command that can be run from DMs, this check might be different.
            # For now, assuming guild_only=True means guild_id is present.
            await interaction.followup.send("This command must be used in a server.", ephemeral=True)
            return
        current_guild_id: int = interaction.guild_id

        async with get_db_session() as session:
            filters = []
            scope_value = scope.value if scope else "all"

            if scope_value == "guild":
                filters.append(ability_crud.model.guild_id == current_guild_id)
            elif scope_value == "global":
                filters.append(ability_crud.model.guild_id.is_(None))
            else: # 'all'
                filters.append(or_(ability_crud.model.guild_id == current_guild_id, ability_crud.model.guild_id.is_(None)))


            offset = (page - 1) * limit
            query = select(ability_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(ability_crud.model.id.desc())
            result = await session.execute(query)
            abilities = result.scalars().all()
            count_query = select(func.count(ability_crud.model.id)).where(and_(*filters))
            total_abilities_res = await session.execute(count_query)
            total_abilities = total_abilities_res.scalar_one_or_none() or 0

            scope_display_key = f"ability_list:scope_{scope_value}"
            scope_display_default = scope_value.capitalize()
            scope_display = await get_localized_message_template(session, current_guild_id, scope_display_key, lang_code, scope_display_default)

            if not abilities:
                no_abilities_msg = await get_localized_message_template(session,current_guild_id,"ability_list:no_abilities_found",lang_code,"No Abilities found for scope '{sc}' (Page {p}).")
                await interaction.followup.send(no_abilities_msg.format(sc=scope_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,current_guild_id,"ability_list:title",lang_code,"Ability List ({scope} - Page {p} of {tp})")
            total_pages = ((total_abilities - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(scope=scope_display, p=page, tp=total_pages), color=discord.Color.teal())
            footer_tmpl = await get_localized_message_template(session,current_guild_id,"ability_list:footer",lang_code,"Displaying {c} of {t} total Abilities.")
            embed.set_footer(text=footer_tmpl.format(c=len(abilities), t=total_abilities))
            name_tmpl = await get_localized_message_template(session,current_guild_id,"ability_list:ability_name_field",lang_code,"ID: {id} | {name} (Static: {sid})")
            val_tmpl = await get_localized_message_template(session,current_guild_id,"ability_list:ability_value_field",lang_code,"Type: {type}, Scope: {scope_val}")

            for ab in abilities:
                na_value_str = await get_localized_message_template(session, current_guild_id, "common:value_na", lang_code, "N/A") # type: ignore
                ab_name = ab.name_i18n.get(lang_code, ab.name_i18n.get("en", na_value_str))

                scope_global_str = await get_localized_message_template(session, current_guild_id, "common:scope_global", lang_code, "Global") # type: ignore
                scope_guild_tmpl = await get_localized_message_template(session, current_guild_id, "common:scope_guild", lang_code, "Guild ({guild_id})") # type: ignore
                scope_val_disp = scope_global_str if ab.guild_id is None else scope_guild_tmpl.format(guild_id=ab.guild_id)

                ability_type_val = getattr(ab, 'type', None)
                embed.add_field(name=name_tmpl.format(id=ab.id, name=ab_name, sid=ab.static_id or na_value_str), value=val_tmpl.format(type=ability_type_val or na_value_str, scope_val=scope_val_disp), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @ability_master_cmds.command(name="create", description="Create a new Ability.")
    @app_commands.describe(static_id="Static ID for this Ability (unique for its scope: global or guild).", name_i18n_json="JSON for Ability name (e.g., {\"en\": \"Fireball\", \"ru\": \"Огненный шар\"}).", description_i18n_json="Optional: JSON for Ability description.", ability_type="Optional: Type of the ability (e.g., SPELL, SKILL, COMBAT_MANEUVER).", properties_json="Optional: JSON for additional properties (effects, costs, requirements).", is_global="Set to True if this is a global ability (not tied to this guild). Defaults to False (guild-specific).")
    async def ability_create(self, interaction: discord.Interaction, static_id: str, name_i18n_json: str, description_i18n_json: Optional[str] = None, ability_type: Optional[str] = None, properties_json: Optional[str] = None, is_global: bool = False):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)

        target_guild_id_for_ability: Optional[int] = interaction.guild_id if not is_global else None
        current_guild_id_for_messages: Optional[int] = interaction.guild_id

        if not is_global and current_guild_id_for_messages is None:
             await interaction.followup.send("Cannot create a guild-specific ability outside of a guild. Use `is_global=True` or run in a guild.", ephemeral=True)
             return

        # Fallback for current_guild_id_for_messages if it's None but needed for localization (e.g. global action from DM)
        # This should ideally be handled by how get_localized_message_template handles None guild_id
        effective_guild_id_for_loc = current_guild_id_for_messages if current_guild_id_for_messages is not None else 0


        async with get_db_session() as session:
            parsed_name_i18n = await parse_json_parameter(interaction, name_i18n_json, "name_i18n_json", session)
            if parsed_name_i18n is None: return
            # Additional validation specific to name_i18n
            error_detail_name_lang = await get_localized_message_template(session, effective_guild_id_for_loc, "ability_create:error_detail_name_lang", lang_code, "name_i18n_json must contain 'en' or current language key.")
            if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                error_msg = await get_localized_message_template(session, effective_guild_id_for_loc,"ability_create:error_invalid_json_content",lang_code,"Invalid JSON content: {details}")
                await interaction.followup.send(error_msg.format(details=error_detail_name_lang), ephemeral=True); return

            parsed_desc_i18n = await parse_json_parameter(interaction, description_i18n_json, "description_i18n_json", session)
            if parsed_desc_i18n is None and description_i18n_json is not None: return

            parsed_props = await parse_json_parameter(interaction, properties_json, "properties_json", session)
            if parsed_props is None and properties_json is not None: return

            existing_ab_static = await ability_crud.get_by_static_id(session, static_id=static_id, guild_id=target_guild_id_for_ability)
            if existing_ab_static:
                scope_global_str = await get_localized_message_template(session, effective_guild_id_for_loc, "common:scope_global", lang_code, "global")
                scope_guild_tmpl = await get_localized_message_template(session, effective_guild_id_for_loc, "common:scope_guild_detail", lang_code, "guild {guild_id}")
                scope_str = scope_global_str if target_guild_id_for_ability is None else scope_guild_tmpl.format(guild_id=target_guild_id_for_ability)
                error_msg = await get_localized_message_template(session, effective_guild_id_for_loc,"ability_create:error_static_id_exists",lang_code,"Ability static_id '{id}' already exists in scope {sc}.")
                await interaction.followup.send(error_msg.format(id=static_id, sc=scope_str), ephemeral=True); return

            ab_data_create: Dict[str, Any] = {
                "guild_id": target_guild_id_for_ability,
                "static_id": static_id,
                "name_i18n": parsed_name_i18n,
                "description_i18n": parsed_desc_i18n or {},
                "type": ability_type,
                "properties_json": parsed_props or {}
            }
            created_ab: Optional[Any] = None
            try:
                async with session.begin():
                    created_ab = await ability_crud.create(session, obj_in=ab_data_create)
                    await session.flush();
                    if created_ab: await session.refresh(created_ab)
            except Exception as e:
                logger.error(f"Error creating Ability: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,current_guild_id_for_messages,"ability_create:error_generic_create",lang_code,"Error creating Ability: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return
            if not created_ab:
                error_msg = await get_localized_message_template(session,current_guild_id_for_messages,"ability_create:error_unknown_fail",lang_code,"Ability creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session,current_guild_id_for_messages,"ability_create:success_title",lang_code,"Ability Created: {name} (ID: {id})")
            created_name = created_ab.name_i18n.get(lang_code, created_ab.name_i18n.get("en", ""))

            scope_global_str = await get_localized_message_template(session, current_guild_id_for_messages, "common:scope_global", lang_code, "Global") # type: ignore
            scope_guild_tmpl = await get_localized_message_template(session, current_guild_id_for_messages, "common:scope_guild", lang_code, "Guild ({guild_id})") # type: ignore
            scope_disp = scope_global_str if created_ab.guild_id is None else scope_guild_tmpl.format(guild_id=created_ab.guild_id)

            na_value_str = await get_localized_message_template(session, current_guild_id_for_messages, "common:value_na", lang_code, "N/A") # type: ignore
            embed = discord.Embed(title=success_title.format(name=created_name, id=created_ab.id), color=discord.Color.green())

            label_static_id = await get_localized_message_template(session, current_guild_id_for_messages, "ability_create:label_static_id", lang_code, "Static ID") # type: ignore
            label_type = await get_localized_message_template(session, current_guild_id_for_messages, "ability_create:label_type", lang_code, "Type") # type: ignore
            label_scope = await get_localized_message_template(session, current_guild_id_for_messages, "ability_create:label_scope", lang_code, "Scope") # type: ignore

            embed.add_field(name=label_static_id, value=created_ab.static_id, inline=True)
            embed.add_field(name=label_type, value=created_ab.type or na_value_str, inline=True)
            embed.add_field(name=label_scope, value=scope_disp, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @ability_master_cmds.command(name="update", description="Update a specific field for an Ability.")
    @app_commands.describe(ability_id="The database ID of the Ability to update.", field_to_update="Field to update (e.g., static_id, name_i18n_json, type, properties_json). Guild ID cannot be changed.", new_value="New value for the field (use JSON for complex types).")
    async def ability_update(self, interaction: discord.Interaction, ability_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        # Guild ID check is implicitly handled by how ability_to_update is fetched,
        # allowing updates to global abilities even if interaction.guild_id is None (e.g. from DM)
        # if the ability_id corresponds to a global ability.
        # Guild_id for messages should be handled carefully if command can be run from DMs.
        # For guild_only=True commands, interaction.guild_id can be assumed to be int.
        current_guild_id_for_messages: Optional[int] = interaction.guild_id
        if current_guild_id_for_messages is None:
            await interaction.followup.send("This command must be used in a server.", ephemeral=True)
            return

        allowed_fields = {"static_id": str, "name_i18n": dict, "description_i18n": dict, "type": (str, type(None)), "properties_json": dict}
        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower

        user_facing_field_name = field_to_update_lower # Default to lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json", "") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json", "")
        elif field_to_update_lower == "name_i18n_json": # Explicit mapping for clarity if needed
            db_field_name = "name_i18n"
            user_facing_field_name = "name_i18n_json"
        elif field_to_update_lower == "description_i18n_json":
            db_field_name = "description_i18n"
            user_facing_field_name = "description_i18n_json"
        elif field_to_update_lower == "properties_json": # Already matches db_field_name
            pass


        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session,current_guild_id_for_messages,"ability_update:error_field_not_allowed",lang_code,"Field '{f}' not allowed. Allowed: {l}")
            user_friendly_allowed_fields = [f + ("_json" if isinstance(allowed_fields[f], dict) and not f.endswith("_json") else "") for f in allowed_fields]
            await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(user_friendly_allowed_fields)), ephemeral=True); return

        parsed_value: Any = None
        async with get_db_session() as session:
            ability_to_update = None
            original_guild_id_of_ability = current_guild_id_for_messages

            ability_to_update = await ability_crud.get(session, id=ability_id, guild_id=current_guild_id_for_messages)

            if not ability_to_update:
                global_ability = await ability_crud.get(session, id=ability_id, guild_id=None)
                if global_ability:
                    ability_to_update = global_ability
                    original_guild_id_of_ability = None
                else:
                    error_msg = await get_localized_message_template(session,current_guild_id_for_messages,"ability_update:error_not_found",lang_code,"Ability ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=ability_id), ephemeral=True); return

            try:
                error_detail_static_id_empty = await get_localized_message_template(session, current_guild_id_for_messages, "ability_update:error_detail_static_id_empty", lang_code, "static_id cannot be empty.")
                error_detail_unknown_field_template = await get_localized_message_template(session, current_guild_id_for_messages, "ability_update:error_detail_unknown_field_internal", lang_code, "Internal error: field definition mismatch for {field_name}.")

                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError(error_detail_static_id_empty)
                    existing_ab = await ability_crud.get_by_static_id(session, static_id=parsed_value, guild_id=original_guild_id_of_ability)
                    if existing_ab and existing_ab.id != ability_id:
                        scope_global_str = await get_localized_message_template(session, current_guild_id_for_messages, "common:scope_global", lang_code, "global")
                        scope_guild_tmpl = await get_localized_message_template(session, current_guild_id_for_messages, "common:scope_guild_detail", lang_code, "guild {guild_id}")
                        scope_str = scope_global_str if original_guild_id_of_ability is None else scope_guild_tmpl.format(guild_id=original_guild_id_of_ability)
                        error_msg = await get_localized_message_template(session,current_guild_id_for_messages,"ability_update:error_static_id_exists",lang_code,"Static ID '{id}' already in use within its scope ({sc}).")
                        await interaction.followup.send(error_msg.format(id=parsed_value, sc=scope_str), ephemeral=True); return
                elif db_field_name in ["name_i18n", "description_i18n", "properties_json"]:
                    parsed_value = await parse_json_parameter(interaction, new_value, user_facing_field_name, session)
                    if parsed_value is None: return
                elif db_field_name == "type":
                    if new_value.lower() == 'none' or new_value.lower() == 'null': parsed_value = None
                    else: parsed_value = new_value
                else:
                    raise ValueError(error_detail_unknown_field_template.format(field_name=db_field_name))
            except ValueError as e: # This will catch explicit ValueErrors from above
                error_msg = await get_localized_message_template(session,current_guild_id_for_messages,"ability_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            updated_ab: Optional[Any] = None
            try:
                async with session.begin():
                    updated_ab = await update_entity(session, entity=ability_to_update, data=update_data)
                    await session.flush();
                    if updated_ab: await session.refresh(updated_ab)
            except Exception as e:
                logger.error(f"Error updating Ability {ability_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,current_guild_id_for_messages,"ability_update:error_generic_update",lang_code,"Error updating Ability {id}: {err}")
                await interaction.followup.send(error_msg.format(id=ability_id, err=str(e)), ephemeral=True); return

            if not updated_ab:
                 error_msg = await get_localized_message_template(session,current_guild_id_for_messages,"ability_update:error_unknown_update_fail",lang_code,"Ability update failed.")
                 await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session,current_guild_id_for_messages,"ability_update:success",lang_code,"Ability ID {id} updated. Field '{f}' set to '{v}'.")

            new_val_display_str: str
            if parsed_value is None:
                new_val_display_str = await get_localized_message_template(session, current_guild_id_for_messages, "common:value_none", lang_code, "None") # type: ignore
            elif isinstance(parsed_value, dict):
                try:
                    json_str = json.dumps(parsed_value, indent=2, ensure_ascii=False)
                    new_val_display_str = f"```json\n{json_str[:1000]}\n```"
                    if len(json_str) > 1000: new_val_display_str += "..."
                except TypeError:
                    new_val_display_str = await get_localized_message_template(session, current_guild_id_for_messages, "ability_update:error_serialization_new_value", lang_code, "Error displaying new value (non-serializable JSON).") # type: ignore
            else:
                new_val_display_str = str(parsed_value)

            await interaction.followup.send(success_msg.format(id=updated_ab.id, f=field_to_update, v=new_val_display_str), ephemeral=True)

    @ability_master_cmds.command(name="delete", description="Delete an Ability.")
    @app_commands.describe(ability_id="The database ID of the Ability to delete.")
    async def ability_delete(self, interaction: discord.Interaction, ability_id: int):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild_id is None:
            # This path should ideally not be reached for guild_only commands
            await interaction.followup.send("This command must be used in a server for guild-specific abilities. Global abilities can be deleted if ID is known (e.g. via DM if command allowed).", ephemeral=True)
            # For now, let's assume if guild_id is None, we might be trying to delete a global one.
            # If this command must be run in a guild context for localization, then this is an error.
            # For simplicity, we'll use a placeholder or handle None for current_guild_id_for_messages.
            # However, the core logic tries to fetch by interaction.guild_id first if not None.
            pass # Let the logic below try to find global if interaction.guild_id is None

        current_guild_id_for_messages: int = interaction.guild_id if interaction.guild_id is not None else 0 # Fallback for type checker

        lang_code = str(interaction.locale)
        async with get_db_session() as session:
            ability_to_delete = None
            target_guild_id_for_delete = interaction.guild_id
            is_global_to_delete = False

            if interaction.guild_id is not None:
                ability_to_delete = await ability_crud.get(session, id=ability_id, guild_id=interaction.guild_id)

            if not ability_to_delete:
                global_ability = await ability_crud.get(session, id=ability_id, guild_id=None)
                if global_ability:
                    ability_to_delete = global_ability
                    target_guild_id_for_delete = None
                    is_global_to_delete = True
                else: # Still not found
                    error_msg = await get_localized_message_template(session,current_guild_id_for_messages,"ability_delete:error_not_found",lang_code,"Ability ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=ability_id), ephemeral=True); return

            # If we found a guild-specific one, current_guild_id_for_messages is already interaction.guild_id
            # If we found a global one, current_guild_id_for_messages might be 0 if called from DM.
            # Ensure messages can still be fetched if it's a global entity being deleted from a guild context.
            if is_global_to_delete and interaction.guild_id is not None:
                 # We are in a guild, deleting a global entity, use current_guild_id for messages
                 pass
            elif is_global_to_delete and interaction.guild_id is None:
                 # Deleting global from DM, messages will use guild_id=0 (which might mean default lang)
                 # This case is tricky for localization if no guild_id is available at all.
                 # For now, current_guild_id_for_messages would be 0.
                 pass


            ab_name_for_msg = ability_to_delete.name_i18n.get(lang_code, ability_to_delete.name_i18n.get("en", f"Ability {ability_id}"))

            scope_global_str = await get_localized_message_template(session, current_guild_id_for_messages, "common:scope_global", lang_code, "Global") # type: ignore
            scope_guild_tmpl = await get_localized_message_template(session, current_guild_id_for_messages, "common:scope_guild", lang_code, "Guild ({guild_id})") # type: ignore
            scope_for_msg = scope_global_str if is_global_to_delete else scope_guild_tmpl.format(guild_id=target_guild_id_for_delete)

            deleted_ab: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_ab = await ability_crud.delete(session, id=ability_id, guild_id=target_guild_id_for_delete)
                if deleted_ab:
                    success_msg = await get_localized_message_template(session,current_guild_id_for_messages,"ability_delete:success",lang_code,"Ability '{name}' (ID: {id}, Scope: {scope}) deleted.")
                    await interaction.followup.send(success_msg.format(name=ab_name_for_msg, id=ability_id, scope=scope_for_msg), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,current_guild_id_for_messages,"ability_delete:error_unknown_delete_fail",lang_code,"Ability (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=ability_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Ability {ability_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,current_guild_id_for_messages,"ability_delete:error_generic_delete",lang_code,"Error deleting Ability '{name}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(name=ab_name_for_msg, id=ability_id, err=str(e)), ephemeral=True)

async def setup(bot: commands.Bot):
    cog = MasterAbilityCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterAbilityCog loaded.")
