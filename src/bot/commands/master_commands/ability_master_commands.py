import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, and_, or_

from src.core.crud.crud_ability import ability_crud
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template

logger = logging.getLogger(__name__)

class MasterAbilityCog(commands.Cog, name="Master Ability Commands"):
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
            ability = await ability_crud.get_by_id_and_guild(session, id=ability_id, guild_id=interaction.guild_id)
            if not ability:
                ability = await ability_crud.get(session, id=ability_id)
                if ability and ability.guild_id is not None: # Found but belongs to another guild
                    ability = None

            if not ability:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ability_view:not_found", lang_code,
                    "Ability with ID {id} not found in this guild or globally."
                )
                await interaction.followup.send(not_found_msg.format(id=ability_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "ability_view:title", lang_code,
                "Ability Details: {name} (ID: {id})"
            )
            name_display = ability.name_i18n.get(lang_code, ability.name_i18n.get("en", f"Ability {ability.id}"))
            embed_title = title_template.format(name=name_display, id=ability.id)
            embed_color = discord.Color.blue() if ability.guild_id else discord.Color.light_grey()
            embed = discord.Embed(title=embed_title, color=embed_color)

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"ability_view:label_{key}", lang_code, default)
            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(ability.guild_id) if ability.guild_id else "Global", inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=ability.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("type", "Type"), value=ability.type or "N/A", inline=True)
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
        async with get_db_session() as session:
            filters = []
            scope_value = scope.value if scope else "all"
            if scope_value == "guild": filters.append(ability_crud.model.guild_id == interaction.guild_id)
            elif scope_value == "global": filters.append(ability_crud.model.guild_id.is_(None))
            else: filters.append(or_(ability_crud.model.guild_id == interaction.guild_id, ability_crud.model.guild_id.is_(None)))

            offset = (page - 1) * limit
            query = select(ability_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(ability_crud.model.id.desc())
            result = await session.execute(query)
            abilities = result.scalars().all()
            count_query = select(func.count(ability_crud.model.id)).where(and_(*filters))
            total_abilities_res = await session.execute(count_query)
            total_abilities = total_abilities_res.scalar_one_or_none() or 0

            scope_display_key = f"ability_list:scope_{scope_value}"
            scope_display_default = scope_value.capitalize()
            scope_display = await get_localized_message_template(session, interaction.guild_id, scope_display_key, lang_code, scope_display_default)

            if not abilities:
                no_abilities_msg = await get_localized_message_template(session,interaction.guild_id,"ability_list:no_abilities_found",lang_code,"No Abilities found for scope '{sc}' (Page {p}).")
                await interaction.followup.send(no_abilities_msg.format(sc=scope_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"ability_list:title",lang_code,"Ability List ({scope} - Page {p} of {tp})")
            total_pages = ((total_abilities - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(scope=scope_display, p=page, tp=total_pages), color=discord.Color.teal())
            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"ability_list:footer",lang_code,"Displaying {c} of {t} total Abilities.")
            embed.set_footer(text=footer_tmpl.format(c=len(abilities), t=total_abilities))
            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"ability_list:ability_name_field",lang_code,"ID: {id} | {name} (Static: {sid})")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"ability_list:ability_value_field",lang_code,"Type: {type}, Scope: {scope_val}")

            for ab in abilities:
                ab_name = ab.name_i18n.get(lang_code, ab.name_i18n.get("en", "N/A"))
                scope_val_disp = "Global" if ab.guild_id is None else f"Guild ({ab.guild_id})"
                embed.add_field(name=name_tmpl.format(id=ab.id, name=ab_name, sid=ab.static_id or "N/A"), value=val_tmpl.format(type=ab.type or "N/A", scope_val=scope_val_disp), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @ability_master_cmds.command(name="create", description="Create a new Ability.")
    @app_commands.describe(static_id="Static ID for this Ability (unique for its scope: global or guild).", name_i18n_json="JSON for Ability name (e.g., {\"en\": \"Fireball\", \"ru\": \"Огненный шар\"}).", description_i18n_json="Optional: JSON for Ability description.", ability_type="Optional: Type of the ability (e.g., SPELL, SKILL, COMBAT_MANEUVER).", properties_json="Optional: JSON for additional properties (effects, costs, requirements).", is_global="Set to True if this is a global ability (not tied to this guild). Defaults to False (guild-specific).")
    async def ability_create(self, interaction: discord.Interaction, static_id: str, name_i18n_json: str, description_i18n_json: Optional[str] = None, ability_type: Optional[str] = None, properties_json: Optional[str] = None, is_global: bool = False):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]; parsed_desc_i18n: Optional[Dict[str, str]] = None; parsed_props: Optional[Dict[str, Any]] = None
        target_guild_id: Optional[int] = interaction.guild_id if not is_global else None

        async with get_db_session() as session:
            existing_ab_static = await ability_crud.get_by_static_id(session, static_id=static_id, guild_id=target_guild_id)
            if existing_ab_static:
                scope_str = "global" if target_guild_id is None else f"guild {target_guild_id}"
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_create:error_static_id_exists",lang_code,"Ability static_id '{id}' already exists in scope {sc}.")
                await interaction.followup.send(error_msg.format(id=static_id, sc=scope_str), ephemeral=True); return
            try:
                parsed_name_i18n = json.loads(name_i18n_json)
                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k,str)and isinstance(v,str) for k,v in parsed_name_i18n.items()): raise ValueError("name_i18n_json must be a dict of str:str.")
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code): raise ValueError("name_i18n_json must contain 'en' or current language key.")
                if description_i18n_json:
                    parsed_desc_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_desc_i18n, dict) or not all(isinstance(k,str)and isinstance(v,str) for k,v in parsed_desc_i18n.items()): raise ValueError("description_i18n_json must be a dict of str:str.")
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
            except (json.JSONDecodeError, ValueError) as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_create:error_invalid_json",lang_code,"Invalid JSON: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            ab_data_create: Dict[str, Any] = {"guild_id": target_guild_id, "static_id": static_id, "name_i18n": parsed_name_i18n, "description_i18n": parsed_desc_i18n or {}, "type": ability_type, "properties_json": parsed_props or {}}
            created_ab: Optional[Any] = None
            try:
                async with session.begin():
                    created_ab = await ability_crud.create(session, obj_in=ab_data_create)
                    await session.flush();
                    if created_ab: await session.refresh(created_ab)
            except Exception as e:
                logger.error(f"Error creating Ability: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_create:error_generic_create",lang_code,"Error creating Ability: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return
            if not created_ab:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_create:error_unknown_fail",lang_code,"Ability creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session,interaction.guild_id,"ability_create:success_title",lang_code,"Ability Created: {name} (ID: {id})")
            created_name = created_ab.name_i18n.get(lang_code, created_ab.name_i18n.get("en", ""))
            scope_disp = "Global" if created_ab.guild_id is None else f"Guild {created_ab.guild_id}"
            embed = discord.Embed(title=success_title.format(name=created_name, id=created_ab.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_ab.static_id, inline=True)
            embed.add_field(name="Type", value=created_ab.type or "N/A", inline=True)
            embed.add_field(name="Scope", value=scope_disp, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @ability_master_cmds.command(name="update", description="Update a specific field for an Ability.")
    @app_commands.describe(ability_id="The database ID of the Ability to update.", field_to_update="Field to update (e.g., static_id, name_i18n_json, type, properties_json). Guild ID cannot be changed.", new_value="New value for the field (use JSON for complex types).")
    async def ability_update(self, interaction: discord.Interaction, ability_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        allowed_fields = {"static_id": str, "name_i18n": dict, "description_i18n": dict, "type": (str, type(None)), "properties_json": dict}
        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json", "") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json", "")
        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session,interaction.guild_id,"ability_update:error_field_not_allowed",lang_code,"Field '{f}' not allowed. Allowed: {l}")
            user_friendly_allowed_fields = [f + "_json" if isinstance(allowed_fields[f], dict) else f for f in allowed_fields]
            await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(user_friendly_allowed_fields)), ephemeral=True); return

        parsed_value: Any = None
        async with get_db_session() as session:
            ability_to_update = await ability_crud.get_by_id_and_guild(session, id=ability_id, guild_id=interaction.guild_id)
            original_guild_id_of_ability = interaction.guild_id
            if not ability_to_update:
                temp_ab = await ability_crud.get(session, id=ability_id)
                if temp_ab and temp_ab.guild_id is None: ability_to_update = temp_ab; original_guild_id_of_ability = None
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_not_found",lang_code,"Ability ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=ability_id), ephemeral=True); return
            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    existing_ab = await ability_crud.get_by_static_id(session, static_id=parsed_value, guild_id=original_guild_id_of_ability)
                    if existing_ab and existing_ab.id != ability_id:
                        scope_str = "global" if original_guild_id_of_ability is None else f"guild {original_guild_id_of_ability}"
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_static_id_exists",lang_code,"Static ID '{id}' already in use within its scope ({sc}).")
                        await interaction.followup.send(error_msg.format(id=parsed_value, sc=scope_str), ephemeral=True); return
                elif db_field_name in ["name_i18n", "description_i18n", "properties_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict): raise ValueError(f"{db_field_name} must be a dict.")
                elif db_field_name == "type":
                    if new_value.lower() == 'none' or new_value.lower() == 'null': parsed_value = None
                    else: parsed_value = new_value
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_unknown_field_internal",lang_code,"Internal error: field definition mismatch.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}")
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
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_generic_update",lang_code,"Error updating Ability {id}: {err}")
                await interaction.followup.send(error_msg.format(id=ability_id, err=str(e)), ephemeral=True); return

            if not updated_ab:
                 error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_unknown_update_fail",lang_code,"Ability update failed.")
                 await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:success",lang_code,"Ability ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            elif parsed_value is None: new_val_display = "None"
            await interaction.followup.send(success_msg.format(id=updated_ab.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @ability_master_cmds.command(name="delete", description="Delete an Ability.")
    @app_commands.describe(ability_id="The database ID of the Ability to delete.")
    async def ability_delete(self, interaction: discord.Interaction, ability_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        async with get_db_session() as session:
            ability_to_delete = await ability_crud.get_by_id_and_guild(session, id=ability_id, guild_id=interaction.guild_id)
            is_global_to_delete = False
            if not ability_to_delete:
                temp_ab = await ability_crud.get(session, id=ability_id)
                if temp_ab and temp_ab.guild_id is None: ability_to_delete = temp_ab; is_global_to_delete = True
            if not ability_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_delete:error_not_found",lang_code,"Ability ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=ability_id), ephemeral=True); return

            ab_name_for_msg = ability_to_delete.name_i18n.get(lang_code, ability_to_delete.name_i18n.get("en", f"Ability {ability_id}"))
            scope_for_msg = "Global" if is_global_to_delete else f"Guild {interaction.guild_id}"
            deleted_ab: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_ab = await ability_crud.remove(session, id=ability_id)
                if deleted_ab:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"ability_delete:success",lang_code,"Ability '{name}' (ID: {id}, Scope: {scope}) deleted.")
                    await interaction.followup.send(success_msg.format(name=ab_name_for_msg, id=ability_id, scope=scope_for_msg), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_delete:error_unknown_delete_fail",lang_code,"Ability (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=ability_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Ability {ability_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_delete:error_generic_delete",lang_code,"Error deleting Ability '{name}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(name=ab_name_for_msg, id=ability_id, err=str(e)), ephemeral=True)

async def setup(bot: commands.Bot):
    cog = MasterAbilityCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterAbilityCog loaded.")
