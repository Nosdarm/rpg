import logging
import discord
from discord import app_commands # Added app_commands
from discord.ext import commands
from typing import Optional

from backend.core.database import get_db_session
import re # For regex validation
from backend.core.crud.crud_player import player_crud
from backend.core.crud.crud_party import party_crud
from backend.core.crud.crud_location import location_crud # For party location consistency
from backend.core.rules import get_rule # For validation rules
from backend.models.player import Player
from backend.models.party import Party, PartyTurnStatus
from backend.models.location import Location
from backend.core.locations_utils import get_localized_text

logger = logging.getLogger(__name__)

class PartyCog(commands.Cog, name="Party Commands"): # type: ignore[call-arg]
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("PartyCog инициализирован.")

    @commands.group(name="party", invoke_without_command=True, help="Управление группами (пати).")
    async def party_group(self, ctx: commands.Context):
        """Основная команда для управления группами. Вызовите без подкоманд для помощи."""
        if ctx.invoked_subcommand is None:
            # TODO: Implement a more detailed help message for party commands
            await ctx.send("Доступные команды для party: `create <название>`, `leave`, `disband`, `join <название_партии_или_ID>` (пока не реализовано), `info` (пока не реализовано).")

    @party_group.command(name="create", help="Создать новую группу. Пример: /party create Искатели приключений") # type: ignore[attr-defined]
    async def party_create(self, ctx: commands.Context, *, party_name: str):
        if not ctx.guild:
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        guild_id = ctx.guild.id
        discord_id = ctx.author.id

        async with get_db_session() as session:
            try:
                player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=discord_id)
                if not player:
                    await ctx.send(f"{ctx.author.mention}, сначала начни игру командой `/start`.")
                    return

                if player.current_party_id:
                    existing_party = await party_crud.get(session, id=player.current_party_id, guild_id=guild_id)
                    await ctx.send(f"{ctx.author.mention}, ты уже состоишь в группе '{existing_party.name if existing_party else 'Неизвестная группа'}'. Сначала покинь ее.")
                    return

                # Validate party name
                name_validation_regex_str = await get_rule(session, guild_id, "party:name_validation_regex", default="^[a-zA-Z0-9А-Яа-яЁё\\s'-_]{3,32}$")
                if not isinstance(name_validation_regex_str, str) : # Fallback if rule is misconfigured
                    name_validation_regex_str = "^[a-zA-Z0-9А-Яа-яЁё\\s'-_]{3,32}$"

                name_max_length = await get_rule(session, guild_id, "party:name_max_length", default=32)
                if not isinstance(name_max_length, int): name_max_length = 32


                if not re.match(name_validation_regex_str, party_name):
                    # TODO: Provide more specific feedback based on regex (e.g., "Name contains invalid characters.")
                    await ctx.send(f"{ctx.author.mention}, название группы содержит недопустимые символы или не соответствует требованиям по длине (3-32 символа, буквы, цифры, пробелы, дефисы, апострофы).")
                    return

                if len(party_name) > name_max_length:
                    await ctx.send(f"{ctx.author.mention}, название группы слишком длинное (максимум {name_max_length} символов).")
                    return

                # Check for name uniqueness
                existing_named_party = await party_crud.get_by_name(session, name=party_name, guild_id=guild_id)
                if existing_named_party:
                    await ctx.send(f"{ctx.author.mention}, группа с названием '{party_name}' уже существует. Пожалуйста, выбери другое название.")
                    return

                # Create the new party
                new_party_data = {
                    "guild_id": guild_id,
                    "name": party_name,
                    "player_ids_json": [player.id], # Creator is the first member
                    "current_location_id": player.current_location_id,
                    "turn_status": PartyTurnStatus.IDLE # Or ACTIVE_TURN if turns start immediately
                }
                new_party = await party_crud.create(session, obj_in=new_party_data) # guild_id is in obj_in

                # Update player's current_party_id
                player.current_party_id = new_party.id
                await session.merge(player) # or player_crud.update(session, db_obj=player, obj_in={"current_party_id": new_party.id})

                await session.commit() # Commit changes for player and party
                logger.info(f"Игрок {player.name} (ID: {player.id}) создал группу '{new_party.name}' (ID: {new_party.id}) на сервере {guild_id}.")
                await ctx.send(f"{ctx.author.mention}, группа '{new_party.name}' успешно создана! Ты ее первый участник.")

            except Exception as e:
                logger.error(f"Ошибка при создании группы для {ctx.author} на сервере {guild_id}: {e}", exc_info=True)
                await ctx.send("Произошла ошибка при создании группы.")
                # Rollback is handled by get_db_session

    @party_group.command(name="leave", help="Покинуть текущую группу.") # type: ignore[attr-defined]
    async def party_leave(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        guild_id = ctx.guild.id
        discord_id = ctx.author.id

        async with get_db_session() as session:
            try:
                player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=discord_id)
                if not player or not player.current_party_id:
                    await ctx.send(f"{ctx.author.mention}, ты не состоишь в группе.")
                    return

                party_id = player.current_party_id
                party = await party_crud.get(session, id=party_id, guild_id=guild_id)

                if not party:
                    logger.warning(f"Игрок {player.name} пытался покинуть несуществующую группу ID: {party_id} на сервере {guild_id}.")
                    player.current_party_id = None # Clean up inconsistent data
                    await session.merge(player)
                    await session.commit()
                    await ctx.send(f"{ctx.author.mention}, похоже, твоей группы больше не существует. Ты был удален из нее.")
                    return

                # Remove player from party's JSON list and update player
                party_name = party.name # Store before potential modification
                was_leader = (party.leader_player_id == player.id)

                # Remove player from party's JSON list
                party = await party_crud.remove_player_from_party_json(session, party=party, player_id=player.id)
                player.current_party_id = None
                await session.merge(player) # Player update

                logger.info(f"Игрок {player.name} (ID: {player.id}) покинул группу '{party_name}' (ID: {party.id}) на сервере {guild_id}.")

                disband_party_flag = False
                new_leader_id: Optional[int] = None

                if not party.player_ids_json: # Party is now empty
                    disband_party_flag = True
                elif was_leader:
                    leader_transfer_policy = await get_rule(session, guild_id, "party:leader_transfer_policy", default="disband_if_empty_else_promote")
                    if leader_transfer_policy == "disband_if_empty_else_promote": # Default behavior
                        if party.player_ids_json: # If members remain, promote first one
                            new_leader_id = party.player_ids_json[0]
                        else: # Should be caught by previous `not party.player_ids_json`
                            disband_party_flag = True
                    elif leader_transfer_policy == "promote_oldest_member": # Simplification: promote first
                         if party.player_ids_json:
                            new_leader_id = party.player_ids_json[0]
                         else: # Should not happen if logic is correct
                            disband_party_flag = True
                    elif leader_transfer_policy == "disband_on_leader_leave": # Example of another policy
                        disband_party_flag = True
                    # If policy is "require_manual_promote", party might become leaderless if not handled by a separate command.
                    # For now, if no explicit promotion, and not disbanding, it remains leaderless (or leader_id points to non-member).
                    # A better approach for "require_manual_promote" might be to set leader_id to None if no other rule applies.

                    if new_leader_id:
                        party.leader_player_id = new_leader_id
                        await session.merge(party) # Party update for new leader
                        # TODO: Log leader change event, notify party
                        logger.info(f"Лидерство в группе '{party_name}' передано игроку ID: {new_leader_id}.")


                # Check auto-disband threshold if not already flagged for disband
                if not disband_party_flag:
                    auto_disband_threshold = await get_rule(session, guild_id, "party:auto_disband_threshold", default=1)
                    if not isinstance(auto_disband_threshold, int) or auto_disband_threshold < 0: auto_disband_threshold = 1 # Ensure valid
                    if len(party.player_ids_json) < auto_disband_threshold:
                        disband_party_flag = True
                        logger.info(f"Группа '{party_name}' (ID: {party.id}) имеет {len(party.player_ids_json)} участников, что меньше порога автороспуска ({auto_disband_threshold}).")

                if disband_party_flag:
                    logger.info(f"Группа '{party_name}' (ID: {party.id}) будет распущена.")
                    await party_crud.delete(session, id=party.id, guild_id=guild_id)
                    # Player's current_party_id already set to None. Other members' IDs are not updated by this command path.
                    # Disband command handles updating all members. Here, we assume they'll find out or /start again.
                    # A more robust solution would iterate remaining party.player_ids_json and update their Player records.
                    await session.commit()
                    await ctx.send(f"{ctx.author.mention} покинул группу '{party_name}'. Группа была распущена.")
                else:
                    await session.commit() # Commit player and potential party (new leader) changes
                    # TODO: Notify party about member leaving and potential new leader
                    await ctx.send(f"{ctx.author.mention} покинул группу '{party_name}'.")

            except Exception as e:
                logger.error(f"Ошибка при выходе из группы для {ctx.author} на сервере {guild_id}: {e}", exc_info=True)
                await ctx.send("Произошла ошибка при выходе из группы.")

    @party_group.command(name="disband", help="Распустить текущую группу (только для создателя/лидера - пока не реализовано).") # type: ignore[attr-defined]
    async def party_disband(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        guild_id = ctx.guild.id
        discord_id = ctx.author.id

        async with get_db_session() as session:
            try:
                player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=discord_id)
                if not player or not player.current_party_id:
                    await ctx.send(f"{ctx.author.mention}, ты не состоишь в группе.")
                    return

                party_id = player.current_party_id
                party = await party_crud.get(session, id=party_id, guild_id=guild_id)

                if not party:
                    logger.warning(f"Игрок {player.name} пытался распустить несуществующую группу ID: {party_id} на сервере {guild_id}.")
                    player.current_party_id = None
                    await session.merge(player)
                    await session.commit()
                    await ctx.send(f"{ctx.author.mention}, похоже, твоей группы больше не существует.")
                    return

                if party.leader_player_id != player.id:
                    # TODO: Localize this message
                    await ctx.send(f"{ctx.author.mention}, только лидер группы может ее распустить.")
                    return

                party_name = party.name
                member_ids_to_update = list(party.player_ids_json) if party.player_ids_json else []

                # Delete the party
                await party_crud.delete(session, id=party.id, guild_id=guild_id)

                # Update all former members
                if member_ids_to_update:
                    for member_pk_id in member_ids_to_update:
                        member_player = await player_crud.get(session, id=member_pk_id, guild_id=guild_id)
                        if member_player:
                            member_player.current_party_id = None
                            await session.merge(member_player)

                await session.commit()
                logger.info(f"Игрок {player.name} (ID: {player.id}) распустил группу '{party_name}' (ID: {party.id}) на сервере {guild_id}.")
                await ctx.send(f"{ctx.author.mention}, группа '{party_name}' была успешно распущена. Все участники покинули группу.")

            except Exception as e:
                logger.error(f"Ошибка при роспуске группы для {ctx.author} на сервере {guild_id}: {e}", exc_info=True)
                await ctx.send("Произошла ошибка при роспуске группы.")

    # TODO: Implement /party join <party_name_or_id>
    # This would involve:
    # 1. Finding the target party.
    # 2. Checking if player can join (not in another party, party not full, etc.).
    # 3. Adding player to Party.player_ids_json.
    # 4. Updating Player.current_party_id.
    # 5. Ensuring party location consistency if player is in a different location.

    # TODO: Implement /party info [party_name_or_id]
    # This would display party name, members, current location, etc.

    @party_group.command(name="join", help="Присоединиться к существующей группе. Пример: /party join ИмяГруппы") # type: ignore[attr-defined]
    async def party_join(self, ctx: commands.Context, *, party_identifier: str):
        if not ctx.guild:
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        guild_id = ctx.guild.id
        discord_id = ctx.author.id

        async with get_db_session() as session:
            try:
                player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=discord_id)
                if not player:
                    await ctx.send(f"{ctx.author.mention}, сначала начни игру командой `/start`.")
                    return

                if player.current_party_id:
                    existing_party = await party_crud.get(session, id=player.current_party_id, guild_id=guild_id)
                    await ctx.send(f"{ctx.author.mention}, ты уже состоишь в группе '{existing_party.name if existing_party else 'Неизвестная группа'}'.")
                    return

                target_party: Optional[Party] = None
                # Попытка найти группу по ID, если party_identifier это число
                try:
                    party_id_int = int(party_identifier)
                    target_party = await party_crud.get(session, id=party_id_int, guild_id=guild_id)
                except ValueError:
                    # Если не число, ищем по имени
                    pass

                if not target_party:
                    target_party = await party_crud.get_by_name(session, guild_id=guild_id, name=party_identifier)

                if not target_party:
                    await ctx.send(f"{ctx.author.mention}, группа с именем или ID '{party_identifier}' не найдена.")
                    return

                # Validation checks based on RuleConfig and party properties
                max_party_size = await get_rule(session, guild_id, "party:max_size", default=5)
                if not isinstance(max_party_size, int) or max_party_size <= 0: max_party_size = 5 # Fallback
                current_party_size = len(target_party.player_ids_json) if target_party.player_ids_json else 0
                if current_party_size >= max_party_size:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, группа '{target_party.name}' уже заполнена (максимум {max_party_size} участников).")
                    return

                party_properties = target_party.properties_json if isinstance(target_party.properties_json, dict) else {}
                invite_policy = party_properties.get("invite_policy", await get_rule(session, guild_id, "party:default_invite_policy", default="open"))
                if invite_policy == "invite_only":
                    # TODO: Implement actual invitation system check. For now, just deny if policy is "invite_only".
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, для вступления в группу '{target_party.name}' требуется приглашение.")
                    return

                min_level_req = party_properties.get("min_level_req", await get_rule(session, guild_id, "party:default_min_level_req", default=1))
                if not isinstance(min_level_req, int) or min_level_req < 1: min_level_req = 1 # Fallback
                if player.level < min_level_req:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, твой уровень ({player.level}) слишком низок для вступления в группу '{target_party.name}'. Требуемый уровень: {min_level_req}.")
                    return

                # Добавляем игрока в JSON список партии
                target_party = await party_crud.add_player_to_party_json(session, party=target_party, player_id=player.id)

                # Обновляем ID партии у игрока и его локацию, если она отличается от локации партии
                player.current_party_id = target_party.id
                if player.current_location_id != target_party.current_location_id:
                    logger.info(f"Игрок {player.name} (ID: {player.id}) присоединяется к группе '{target_party.name}' и перемещается в ее локацию (ID: {target_party.current_location_id}).")
                    player.current_location_id = target_party.current_location_id

                await session.merge(player)
                # party_crud.add_player_to_party_json уже делает flush и refresh для party

                await session.commit()
                logger.info(f"Игрок {player.name} (ID: {player.id}) присоединился к группе '{target_party.name}' (ID: {target_party.id}) на сервере {guild_id}.")

                player_location_name = "неизвестно"
                if player.current_location_id:
                    player_loc_obj = await location_crud.get(session, id=player.current_location_id, guild_id=guild_id)
                    if player_loc_obj:
                        # Pass the i18n dictionary (e.g., name_i18n) to get_localized_text
                        # Correct parameter names: language, default_lang
                        player_location_name = get_localized_text(
                            i18n_dict=player_loc_obj.name_i18n,
                            language=player.selected_language or "en",
                            default_lang="en"
                        )
                        if not player_location_name: # Handle case where get_localized_text returns empty
                            player_location_name = "неизвестная локация"


                await ctx.send(f"{ctx.author.mention} успешно присоединился к группе '{target_party.name}'! Текущая локация группы: {player_location_name}.")

            except Exception as e:
                logger.error(f"Ошибка при присоединении к группе для {ctx.author} на сервере {guild_id}: {e}", exc_info=True)
                await ctx.send("Произошла ошибка при присоединении к группе.")

    @party_group.command(name="kick", help="Исключить игрока из вашей группы. Пример: /party kick @Игрок") # type: ignore[attr-defined]
    @app_commands.describe(target_player="Игрок, которого вы хотите исключить.")
    async def party_kick(self, ctx: commands.Context, target_player: discord.Member):
        if not ctx.guild:
            # TODO: Localize
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        guild_id = ctx.guild.id
        kicker_discord_id = ctx.author.id

        async with get_db_session() as session:
            try:
                kicker_player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=kicker_discord_id)
                if not kicker_player:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, сначала начни игру командой `/start`.")
                    return

                if not kicker_player.current_party_id:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, ты не состоишь в группе.")
                    return

                party = await party_crud.get(session, id=kicker_player.current_party_id, guild_id=guild_id)
                if not party:
                    logger.error(f"Player {kicker_player.name} in party ID {kicker_player.current_party_id} but party not found.")
                    # TODO: Localize
                    await ctx.send("Ошибка: не удалось найти твою группу.")
                    return

                party_name = party.name # For messages

                # Permission Check
                kick_permission_rule = await get_rule(session, guild_id, "party:kick_permissions", default="leader_only")
                if kick_permission_rule == "leader_only" and party.leader_player_id != kicker_player.id:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, только лидер группы может исключать участников.")
                    return
                # TODO: Add other permission policies like "officers_can_kick" or role-based.

                # Target Player Validation
                if target_player.id == kicker_discord_id:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, нельзя исключить самого себя. Используй `/party leave`.")
                    return

                if target_player.bot:
                     # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, нельзя исключать ботов из группы.")
                    return

                target_player_db = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=target_player.id)
                if not target_player_db or target_player_db.current_party_id != party.id:
                    # TODO: Localize
                    await ctx.send(f"{target_player.mention} не является участником твоей группы '{party_name}'.")
                    return

                if party.leader_player_id == target_player_db.id:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, нельзя исключить лидера группы. Лидер может покинуть группу (`/party leave`) или передать лидерство (`/party promote`).")
                    return

                # Action: Remove player
                party = await party_crud.remove_player_from_party_json(session, party=party, player_id=target_player_db.id)
                target_player_db.current_party_id = None
                await session.merge(target_player_db)

                logger.info(f"Player {kicker_player.name} kicked {target_player_db.name} from party {party_name} (ID: {party.id}).")
                # TODO: Log PARTY_PLAYER_KICKED event

                # Auto-disband check (copied and adapted from party_leave)
                disband_party_flag = False
                if not party.player_ids_json:
                    disband_party_flag = True
                else:
                    auto_disband_threshold = await get_rule(session, guild_id, "party:auto_disband_threshold", default=1)
                    if not isinstance(auto_disband_threshold, int) or auto_disband_threshold < 0: auto_disband_threshold = 1
                    if len(party.player_ids_json) < auto_disband_threshold:
                        disband_party_flag = True
                        logger.info(f"Party '{party_name}' (ID: {party.id}) now has {len(party.player_ids_json)} members, below threshold {auto_disband_threshold}.")

                if disband_party_flag:
                    logger.info(f"Party '{party_name}' (ID: {party.id}) is being disbanded after kick.")
                    await party_crud.delete(session, id=party.id, guild_id=guild_id)
                    await session.commit()
                    # TODO: Localize and notify all (kicker, kicked, remaining if any before disband)
                    await ctx.send(f"Игрок {target_player.mention} исключен из группы '{party_name}'. Группа распущена.")
                else:
                    await session.commit()
                    # TODO: Localize and notify kicker, kicked, and party
                    await ctx.send(f"Игрок {target_player.mention} исключен из группы '{party_name}'.")

            except Exception as e:
                logger.error(f"Ошибка в команде /party kick для {ctx.author} на сервере {guild_id}: {e}", exc_info=True)
                # TODO: Localize
                await ctx.send("Произошла ошибка при попытке исключить игрока.")

    @party_group.command(name="promote", help="Назначить нового лидера группы. Пример: /party promote @НовыйЛидер") # type: ignore[attr-defined]
    @app_commands.describe(new_leader="Участник, которого вы хотите сделать новым лидером.")
    async def party_promote(self, ctx: commands.Context, new_leader: discord.Member):
        if not ctx.guild:
            # TODO: Localize
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        guild_id = ctx.guild.id
        promoter_discord_id = ctx.author.id

        async with get_db_session() as session:
            try:
                promoter_player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=promoter_discord_id)
                if not promoter_player:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, сначала начни игру командой `/start`.")
                    return

                if not promoter_player.current_party_id:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, ты не состоишь в группе.")
                    return

                party = await party_crud.get(session, id=promoter_player.current_party_id, guild_id=guild_id)
                if not party:
                    logger.error(f"Player {promoter_player.name} in party ID {promoter_player.current_party_id} but party not found.")
                    # TODO: Localize
                    await ctx.send("Ошибка: не удалось найти твою группу.")
                    return

                # Permission Check: Only current leader can promote
                if party.leader_player_id != promoter_player.id:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, только текущий лидер группы может назначать нового.")
                    return

                # Target Player (New Leader) Validation
                if new_leader.id == promoter_discord_id:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, ты уже являешься лидером этой группы.")
                    return

                if new_leader.bot:
                     # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, нельзя назначить бота лидером группы.")
                    return

                new_leader_db = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=new_leader.id)
                if not new_leader_db or new_leader_db.current_party_id != party.id:
                    # TODO: Localize
                    await ctx.send(f"{new_leader.mention} не является участником твоей группы '{party.name}'.")
                    return

                # Action: Update leader
                old_leader_id = party.leader_player_id
                party.leader_player_id = new_leader_db.id
                await session.merge(party)
                await session.commit()

                logger.info(f"Player {promoter_player.name} promoted {new_leader_db.name} to leader of party {party.name} (ID: {party.id}). Old leader ID: {old_leader_id}")
                # TODO: Log PARTY_LEADER_CHANGED event
                # await log_event(...)

                # TODO: Localize feedback to promoter, new leader, and other party members.
                # Consider sending DMs or a message to a party channel if one exists.
                await ctx.send(f"{new_leader.mention} успешно назначен новым лидером группы '{party.name}'!")

            except Exception as e:
                logger.error(f"Ошибка в команде /party promote для {ctx.author} на сервере {guild_id}: {e}", exc_info=True)
                # TODO: Localize
                await ctx.send("Произошла ошибка при попытке назначить нового лидера.")

    @party_group.command(name="view", aliases=["info"], help="Посмотреть информацию о группе. Пример: /party view [название_или_ID_группы]") # type: ignore[attr-defined]
    @app_commands.describe(party_identifier="Название или ID группы для просмотра (если не указано, покажет вашу текущую группу).")
    async def party_view(self, ctx: commands.Context, *, party_identifier: Optional[str] = None):
        if not ctx.guild:
            # TODO: Localize
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        guild_id = ctx.guild.id
        requester_discord_id = ctx.author.id

        async with get_db_session() as session:
            try:
                requester_player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=requester_discord_id)
                if not requester_player:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, сначала начни игру командой `/start`.")
                    return

                party_to_view: Optional[Party] = None

                if not party_identifier:
                    if requester_player.current_party_id:
                        party_to_view = await party_crud.get(session, id=requester_player.current_party_id, guild_id=guild_id)
                        if not party_to_view:
                             # TODO: Localize
                            await ctx.send("Не удалось найти твою текущую группу. Возможно, она была распущена.")
                            return
                    else:
                        # TODO: Localize
                        await ctx.send(f"{ctx.author.mention}, ты не состоишь в группе. Укажи название или ID группы для просмотра.")
                        return
                else:
                    try:
                        party_id_int = int(party_identifier)
                        party_to_view = await party_crud.get(session, id=party_id_int, guild_id=guild_id)
                    except ValueError:
                        party_to_view = await party_crud.get_by_name(session, guild_id=guild_id, name=party_identifier)

                    if not party_to_view:
                        # TODO: Localize
                        await ctx.send(f"Группа с идентификатором '{party_identifier}' не найдена.")
                        return

                # At this point, party_to_view should be the Party object
                embed = discord.Embed(title=f"Информация о группе: {party_to_view.name}", color=discord.Color.blurple())

                leader_name = "Неизвестен"
                if party_to_view.leader_player_id:
                    leader = await player_crud.get(session, id=party_to_view.leader_player_id, guild_id=guild_id)
                    if leader:
                        leader_name = leader.name
                embed.add_field(name="Лидер", value=leader_name, inline=True)

                member_names = []
                if party_to_view.player_ids_json:
                    for member_id in party_to_view.player_ids_json:
                        member = await player_crud.get(session, id=member_id, guild_id=guild_id)
                        member_names.append(member.name if member else f"ID:{member_id} (??)")
                embed.add_field(name=f"Участники ({len(member_names)})", value=", ".join(member_names) if member_names else "Нет", inline=False)

                location_name = "Неизвестно"
                if party_to_view.current_location_id:
                    loc = await location_crud.get(session, id=party_to_view.current_location_id, guild_id=guild_id)
                    if loc:
                        # Assuming requester_player.selected_language or guild default for localization
                        lang_for_loc = requester_player.selected_language or await get_rule(session, guild_id, "guild_main_language", "en")
                        if not isinstance(lang_for_loc, str): lang_for_loc = "en"
                        location_name = get_localized_text(loc.name_i18n, lang_for_loc, loc.static_id or f"ID:{loc.id}")
                embed.add_field(name="Текущая локация", value=location_name, inline=True)

                party_props = party_to_view.properties_json if isinstance(party_to_view.properties_json, dict) else {}
                invite_policy_val = party_props.get("invite_policy", await get_rule(session, guild_id, "party:default_invite_policy", "open"))
                min_level_val = party_props.get("min_level_req", await get_rule(session, guild_id, "party:default_min_level_req", 1))

                embed.add_field(name="Политика приглашений", value=str(invite_policy_val), inline=True)
                embed.add_field(name="Мин. уровень для вступления", value=str(min_level_val), inline=True)

                await ctx.send(embed=embed)

            except Exception as e:
                logger.error(f"Ошибка в команде /party view для {ctx.author} на сервере {guild_id}: {e}", exc_info=True)
                # TODO: Localize
                await ctx.send("Произошла ошибка при просмотре информации о группе.")

    @party_group.command(name="invite", help="Пригласить игрока в вашу группу. Пример: /party invite @Игрок") # type: ignore[attr-defined]
    @app_commands.describe(target_player="Игрок, которого вы хотите пригласить.")
    async def party_invite(self, ctx: commands.Context, target_player: discord.Member):
        if not ctx.guild:
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        guild_id = ctx.guild.id
        inviter_discord_id = ctx.author.id

        async with get_db_session() as session:
            try:
                inviter_player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=inviter_discord_id)
                if not inviter_player:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, сначала начни игру командой `/start`.")
                    return

                if not inviter_player.current_party_id:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, ты не состоишь в группе, чтобы приглашать в нее.")
                    return

                party = await party_crud.get(session, id=inviter_player.current_party_id, guild_id=guild_id)
                if not party:
                    # Should not happen if player.current_party_id is consistent
                    logger.error(f"Player {inviter_player.name} in party ID {inviter_player.current_party_id} but party not found.")
                    # TODO: Localize
                    await ctx.send("Ошибка: не удалось найти твою группу.")
                    return

                # Permission Check
                invite_permission_rule = await get_rule(session, guild_id, "party:invite_permissions", default="leader_only")
                if invite_permission_rule == "leader_only" and party.leader_player_id != inviter_player.id:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, только лидер группы может приглашать новых участников.")
                    return
                # TODO: Add other permission policies like "members_can_invite" or role-based.

                # Target Player Validation
                if target_player.id == inviter_discord_id:
                    # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, нельзя пригласить самого себя.")
                    return

                if target_player.bot:
                     # TODO: Localize
                    await ctx.send(f"{ctx.author.mention}, нельзя приглашать ботов в группу.")
                    return

                target_player_db = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=target_player.id)
                if not target_player_db:
                    # TODO: Localize
                    await ctx.send(f"{target_player.mention} еще не начал игру на этом сервере. Попроси его использовать `/start`.")
                    return

                if target_player_db.current_party_id:
                    # TODO: Localize
                    await ctx.send(f"{target_player.mention} уже состоит в другой группе.")
                    return

                # Party Full Check
                max_party_size = await get_rule(session, guild_id, "party:max_size", default=5)
                if not isinstance(max_party_size, int) or max_party_size <= 0: max_party_size = 5
                current_party_size = len(party.player_ids_json) if party.player_ids_json else 0
                if current_party_size >= max_party_size:
                    # TODO: Localize
                    await ctx.send(f"Группа '{party.name}' уже заполнена (максимум {max_party_size} участников).")
                    return

                # Simplified: Send DM to target player
                try:
                    # TODO: Localize DM message
                    dm_message = (
                        f"Привет, {target_player.display_name}!\n"
                        f"{ctx.author.display_name} приглашает тебя присоединиться к группе '{party.name}' на сервере '{ctx.guild.name}'.\n"
                        f"Чтобы принять приглашение, используй команду: `/party join {party.name}` или `/party join {party.id}`"
                    )
                    await target_player.send(dm_message)
                    # TODO: Log PARTY_INVITE_SENT event
                    # await log_event(...)
                    logger.info(f"Player {inviter_player.name} invited {target_player_db.name} to party {party.name} (ID: {party.id}). DM sent.")
                    # TODO: Localize feedback to inviter
                    await ctx.send(f"Приглашение отправлено игроку {target_player.mention}.")

                except discord.Forbidden:
                    # TODO: Localize
                    await ctx.send(f"Не удалось отправить личное сообщение {target_player.mention}. Возможно, он заблокировал ЛС от участников сервера или от бота.")
                except Exception as e_dm:
                    logger.error(f"Ошибка при отправке DM-приглашения игроку {target_player.id}: {e_dm}", exc_info=True)
                    # TODO: Localize
                    await ctx.send(f"Произошла ошибка при отправке приглашения игроку {target_player.mention}.")

            except Exception as e:
                logger.error(f"Ошибка в команде /party invite для {ctx.author} на сервере {guild_id}: {e}", exc_info=True)
                # TODO: Localize
                await ctx.send("Произошла ошибка при попытке пригласить игрока.")

async def setup(bot: commands.Bot):
    await bot.add_cog(PartyCog(bot))
    logger.info("PartyCog успешно загружен и добавлен в бота.")
