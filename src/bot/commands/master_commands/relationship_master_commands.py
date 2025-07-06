import logging
import json
from typing import Dict, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select, func, and_

from src.core.crud.crud_relationship import crud_relationship
from src.core.crud.crud_player import player_crud
from src.core.crud.crud_npc import npc_crud
from src.core.crud.crud_faction import crud_faction
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template
from src.models.enums import RelationshipEntityType

logger = logging.getLogger(__name__)

class MasterRelationshipCog(commands.Cog, name="Master Relationship Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterRelationshipCog initialized.")

    relationship_master_cmds = app_commands.Group(
        name="master_relationship",
        description="Master commands for managing Relationships.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @relationship_master_cmds.command(name="view", description="View details of a specific Relationship.")
    @app_commands.describe(relationship_id="The database ID of the Relationship to view.")
    async def relationship_view(self, interaction: discord.Interaction, relationship_id: int):
        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            relationship = await crud_relationship.get_by_id_and_guild(session, id=relationship_id, guild_id=interaction.guild_id)

            if not relationship:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_view:not_found", lang_code,
                    "Relationship with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=relationship_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_view:title", lang_code,
                "Relationship Details (ID: {id})"
            )
            embed_title = title_template.format(id=relationship.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_purple())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"relationship_view:label_{key}", lang_code, default)

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(relationship.guild_id), inline=True)
            embed.add_field(name=await get_label("type", "Type"), value=relationship.relationship_type, inline=True)
            embed.add_field(name=await get_label("value", "Value"), value=str(relationship.value), inline=True)

            embed.add_field(name=await get_label("entity1_type", "Entity 1 Type"), value=relationship.entity1_type.value, inline=True)
            embed.add_field(name=await get_label("entity1_id", "Entity 1 ID"), value=str(relationship.entity1_id), inline=True)
            embed.add_field(name=await get_label("entity2_type", "Entity 2 Type"), value=relationship.entity2_type.value, inline=True)
            embed.add_field(name=await get_label("entity2_id", "Entity 2 ID"), value=str(relationship.entity2_id), inline=True)

            source_log_id_val = str(relationship.source_log_id) if relationship.source_log_id else "N/A"
            embed.add_field(name=await get_label("source_log_id", "Source Log ID"), value=source_log_id_val, inline=True)

            created_at_val = discord.utils.format_dt(relationship.created_at, style='F') if relationship.created_at else "N/A"
            updated_at_val = discord.utils.format_dt(relationship.updated_at, style='F') if relationship.updated_at else "N/A"
            embed.add_field(name=await get_label("created_at", "Created At"), value=created_at_val, inline=False)
            embed.add_field(name=await get_label("updated_at", "Updated At"), value=updated_at_val, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @relationship_master_cmds.command(name="list", description="List Relationships in this guild, with optional filters.")
    @app_commands.describe(
        entity1_id="Optional: Filter by ID of the first entity.",
        entity1_type="Optional: Filter by type of the first entity (PLAYER, GENERATED_NPC, FACTION, etc.).",
        entity2_id="Optional: Filter by ID of the second entity.",
        entity2_type="Optional: Filter by type of the second entity.",
        relationship_type_filter="Optional: Filter by relationship type (e.g., neutral, friendly).",
        page="Page number to display.",
        limit="Number of Relationships per page."
    )
    async def relationship_list(self, interaction: discord.Interaction,
                                entity1_id: Optional[int] = None, entity1_type: Optional[str] = None,
                                entity2_id: Optional[int] = None, entity2_type: Optional[str] = None,
                                relationship_type_filter: Optional[str] = None,
                                page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 5: limit = 5

        lang_code = str(interaction.locale)
        e1_type_enum: Optional[RelationshipEntityType] = None
        e2_type_enum: Optional[RelationshipEntityType] = None

        async with get_db_session() as session:
            if entity1_type:
                try: e1_type_enum = RelationshipEntityType[entity1_type.upper()]
                except KeyError:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_list:error_invalid_e1_type", lang_code, "Invalid entity1_type.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            if entity2_type:
                try: e2_type_enum = RelationshipEntityType[entity2_type.upper()]
                except KeyError:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_list:error_invalid_e2_type", lang_code, "Invalid entity2_type.")
                    await interaction.followup.send(error_msg, ephemeral=True); return

            filters = [crud_relationship.model.guild_id == interaction.guild_id]
            if entity1_id is not None and e1_type_enum is not None:
                filters.append(crud_relationship.model.entity1_id == entity1_id)
                filters.append(crud_relationship.model.entity1_type == e1_type_enum)
            elif entity1_id is not None or e1_type_enum is not None:
                 error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_list:error_partial_e1_filter", lang_code, "If filtering by entity1, both ID and Type must be provided.")
                 await interaction.followup.send(error_msg, ephemeral=True); return

            if entity2_id is not None and e2_type_enum is not None:
                filters.append(crud_relationship.model.entity2_id == entity2_id)
                filters.append(crud_relationship.model.entity2_type == e2_type_enum)
            elif entity2_id is not None or e2_type_enum is not None:
                 error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_list:error_partial_e2_filter", lang_code, "If filtering by entity2, both ID and Type must be provided.")
                 await interaction.followup.send(error_msg, ephemeral=True); return

            if relationship_type_filter:
                filters.append(crud_relationship.model.relationship_type.ilike(f"%{relationship_type_filter}%"))

            offset = (page - 1) * limit
            query = select(crud_relationship.model).where(and_(*filters)).offset(offset).limit(limit).order_by(crud_relationship.model.id.desc())
            result = await session.execute(query)
            relationships = result.scalars().all()

            count_query = select(func.count(crud_relationship.model.id)).where(and_(*filters))
            total_relationships_result = await session.execute(count_query)
            total_relationships = total_relationships_result.scalar_one_or_none() or 0

            if not relationships:
                no_rels_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_list:no_relationships_found_page", lang_code,
                    "No Relationships found for the given criteria (Page {page})."
                )
                await interaction.followup.send(no_rels_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_list:title", lang_code,
                "Relationship List (Page {page} of {total_pages})"
            )
            total_pages = ((total_relationships - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_gray())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_list:footer", lang_code,
                "Displaying {count} of {total} total Relationships."
            )
            embed.set_footer(text=footer_template.format(count=len(relationships), total=total_relationships))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_list:relationship_field_name", lang_code,
                "ID: {rel_id} | {e1_type} ({e1_id}) <=> {e2_type} ({e2_id})"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_list:relationship_field_value", lang_code,
                "Type: {type}, Value: {value}"
            )

            for rel in relationships:
                embed.add_field(
                    name=field_name_template.format(rel_id=rel.id, e1_type=rel.entity1_type.name, e1_id=rel.entity1_id, e2_type=rel.entity2_type.name, e2_id=rel.entity2_id),
                    value=field_value_template.format(type=rel.relationship_type, value=rel.value),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_list:no_rels_to_display", lang_code,
                    "No relationships found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @relationship_master_cmds.command(name="create", description="Create a new Relationship.")
    @app_commands.describe(
        entity1_id="ID of the first entity.",
        entity1_type="Type of the first entity (PLAYER, GENERATED_NPC, FACTION).",
        entity2_id="ID of the second entity.",
        entity2_type="Type of the second entity (PLAYER, GENERATED_NPC, FACTION).",
        relationship_type="Type of relationship (e.g., neutral, friendly, hostile, family).",
        value="Numerical value of the relationship (e.g., 0, 50, -100).",
        source_log_id="Optional: ID of the StoryLog entry that caused this relationship."
    )
    async def relationship_create(self, interaction: discord.Interaction,
                                  entity1_id: int, entity1_type: str,
                                  entity2_id: int, entity2_type: str,
                                  relationship_type: str,
                                  value: int,
                                  source_log_id: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)

        lang_code = str(interaction.locale)
        e1_type_enum: RelationshipEntityType
        e2_type_enum: RelationshipEntityType

        async def validate_entity(session: Any, entity_id_val: int, entity_type_str_val: str, entity_type_enum_val: RelationshipEntityType, guild_id_val: int, entity_label: str) -> bool:
            crud_map = {
                RelationshipEntityType.PLAYER: player_crud,
                RelationshipEntityType.GENERATED_NPC: npc_crud,
                RelationshipEntityType.FACTION: crud_faction,
            }
            crud_instance = crud_map.get(entity_type_enum_val)
            if not crud_instance:
                error_msg_loc = await get_localized_message_template(session, guild_id_val, "relationship_create:error_unsupported_type", lang_code, f"Unsupported entity type for {entity_label}: {{type}}")
                await interaction.followup.send(error_msg_loc.format(type=entity_type_str_val), ephemeral=True)
                return False

            entity = await crud_instance.get_by_id_and_guild(session, id=entity_id_val, guild_id=guild_id_val)
            if not entity:
                error_msg_loc = await get_localized_message_template(session, guild_id_val, "relationship_create:error_entity_not_found", lang_code, f"{entity_label} with ID {{id}} and Type {{type}} not found in this guild.")
                await interaction.followup.send(error_msg_loc.format(id=entity_id_val, type=entity_type_str_val), ephemeral=True)
                return False
            return True

        async with get_db_session() as session:
            try:
                e1_type_enum = RelationshipEntityType[entity1_type.upper()]
                e2_type_enum = RelationshipEntityType[entity2_type.upper()]
            except KeyError:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_create:error_invalid_entity_type", lang_code, "Invalid entity_type provided. Use PLAYER, GENERATED_NPC, or FACTION.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            if not await validate_entity(session, entity1_id, entity1_type, e1_type_enum, interaction.guild_id, "Entity 1"): return
            if not await validate_entity(session, entity2_id, entity2_type, e2_type_enum, interaction.guild_id, "Entity 2"): return

            if entity1_id == entity2_id and e1_type_enum == e2_type_enum:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_create:error_self_relationship", lang_code, "Entities cannot have a relationship with themselves.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            existing_rel = await crud_relationship.get_relationship_between_entities(
                session, guild_id=interaction.guild_id,
                entity1_id=entity1_id, entity1_type=e1_type_enum,
                entity2_id=entity2_id, entity2_type=e2_type_enum
            )
            if existing_rel:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_create:error_already_exists", lang_code, "A relationship between these entities already exists (ID: {id}). Use update instead.")
                await interaction.followup.send(error_msg.format(id=existing_rel.id), ephemeral=True); return

            relationship_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id,
                "entity1_id": entity1_id, "entity1_type": e1_type_enum,
                "entity2_id": entity2_id, "entity2_type": e2_type_enum,
                "relationship_type": relationship_type, "value": value,
                "source_log_id": source_log_id,
            }

            created_relationship: Optional[Any] = None
            try:
                async with session.begin():
                    created_relationship = await crud_relationship.create(session, obj_in=relationship_data_to_create)
                    await session.flush()
                    if created_relationship:
                         await session.refresh(created_relationship)
            except Exception as e:
                logger.error(f"Error creating Relationship: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_create:error_generic_create", lang_code, "Error creating relationship: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_relationship:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_create:error_creation_failed_unknown", lang_code, "Relationship creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_create:success", lang_code,
                "Relationship (ID: {id}) created: {e1_type}({e1_id}) <=> {e2_type}({e2_id}), Type: {type}, Value: {val}."
            )
            await interaction.followup.send(success_msg_template.format(
                id=created_relationship.id,
                e1_type=created_relationship.entity1_type.name, e1_id=created_relationship.entity1_id,
                e2_type=created_relationship.entity2_type.name, e2_id=created_relationship.entity2_id,
                type=created_relationship.relationship_type, val=created_relationship.value
            ), ephemeral=True)

    @relationship_master_cmds.command(name="update", description="Update a specific Relationship.")
    @app_commands.describe(
        relationship_id="The database ID of the Relationship to update.",
        field_to_update="Field to update (relationship_type or value).",
        new_value="New value for the field."
    )
    async def relationship_update(self, interaction: discord.Interaction, relationship_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        allowed_fields = {
            "relationship_type": str,
            "value": int,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        if field_to_update_lower not in allowed_fields:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "relationship_update:error_field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update. Allowed: {allowed_list}"
                )
            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True)
            return

        parsed_value: Any = None
        field_type = allowed_fields[field_to_update_lower]

        async with get_db_session() as session:
            try:
                if field_type == str:
                    parsed_value = new_value
                elif field_type == int:
                    parsed_value = int(new_value)
            except ValueError:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_update:error_invalid_value_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Expected type: {expected_type}."
                )
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, expected_type=field_type.__name__), ephemeral=True)
                return

            relationship_to_update = await crud_relationship.get_by_id_and_guild(session, id=relationship_id, guild_id=interaction.guild_id)
            if not relationship_to_update:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_update:error_relationship_not_found", lang_code,
                    "Relationship with ID {id} not found."
                )
                await interaction.followup.send(error_msg.format(id=relationship_id), ephemeral=True)
                return

            update_data_dict = {field_to_update_lower: parsed_value}
            updated_relationship: Optional[Any] = None
            try:
                async with session.begin():
                    updated_relationship = await update_entity(session, entity=relationship_to_update, data=update_data_dict)
                    await session.flush()
                    await session.refresh(updated_relationship)
            except Exception as e:
                logger.error(f"Error updating Relationship {relationship_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_update:error_generic_update", lang_code,
                    "Error updating Relationship {id}: {error_message}"
                )
                await interaction.followup.send(error_msg.format(id=relationship_id, error_message=str(e)), ephemeral=True)
                return

            success_msg_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_update:success", lang_code,
                "Relationship ID {id} updated. Field '{field}' set to '{val}'."
            )
            await interaction.followup.send(success_msg_template.format(id=updated_relationship.id, field=field_to_update, val=parsed_value), ephemeral=True)

    @relationship_master_cmds.command(name="delete", description="Delete a Relationship.")
    @app_commands.describe(relationship_id="The database ID of the Relationship to delete.")
    async def relationship_delete(self, interaction: discord.Interaction, relationship_id: int):
        await interaction.response.defer(ephemeral=True)

        lang_code = str(interaction.locale)
        async with get_db_session() as session:
            relationship_to_delete = await crud_relationship.get_by_id_and_guild(session, id=relationship_id, guild_id=interaction.guild_id)

            if not relationship_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_delete:error_not_found", lang_code,
                    "Relationship with ID {id} not found. Nothing to delete."
                )
                await interaction.followup.send(error_msg.format(id=relationship_id), ephemeral=True)
                return

            rel_repr = f"{relationship_to_delete.entity1_type.name}({relationship_to_delete.entity1_id}) <=> {relationship_to_delete.entity2_type.name}({relationship_to_delete.entity2_id})"
            deleted_relationship: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_relationship = await crud_relationship.remove(session, id=relationship_id)

                if deleted_relationship:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "relationship_delete:success", lang_code,
                        "Relationship (ID: {id}, Details: {repr}) has been deleted successfully."
                    )
                    await interaction.followup.send(success_msg.format(id=relationship_id, repr=rel_repr), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "relationship_delete:error_not_deleted_unknown", lang_code,
                        "Relationship (ID: {id}) was found but could not be deleted."
                    )
                    await interaction.followup.send(error_msg.format(id=relationship_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Relationship {relationship_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_delete:error_generic", lang_code,
                    "An error occurred while deleting Relationship (ID: {id}, Details: {repr}): {error_message}"
                )
                await interaction.followup.send(error_msg.format(id=relationship_id, repr=rel_repr, error_message=str(e)), ephemeral=True)
                return

async def setup(bot: commands.Bot):
    cog = MasterRelationshipCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterRelationshipCog loaded.")
