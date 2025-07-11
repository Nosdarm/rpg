import logging
import discord
from discord.ext import commands
from typing import Optional

from backend.core.database import get_db_session
from backend.core.crud.crud_player import player_crud
from backend.core.crud.crud_party import party_crud
from backend.core.crud.crud_location import location_crud # For party location consistency
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
                party = await party_crud.remove_player_from_party_json(session, party=party, player_id=player.id)
                player.current_party_id = None
                await session.merge(player)

                party_name = party.name
                logger.info(f"Игрок {player.name} (ID: {player.id}) покинул группу '{party_name}' (ID: {party.id}) на сервере {guild_id}.")

                # Check if party is now empty
                if not party.player_ids_json:
                    logger.info(f"Группа '{party_name}' (ID: {party.id}) пуста и будет распущена.")
                    await party_crud.delete(session, id=party.id, guild_id=guild_id)
                    await session.commit()
                    await ctx.send(f"{ctx.author.mention} покинул группу '{party_name}'. Группа была распущена, так как стала пустой.")
                else:
                    await session.commit()
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

                # TODO: Add leader check here in the future. For now, any member can disband.
                # if party.leader_id != player.id: # Assuming a leader_id field on Party model
                #     await ctx.send(f"{ctx.author.mention}, только лидер может распустить группу.")
                #     return

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

                # TODO: Добавить проверки (например, максимальное количество участников в группе из RuleConfig)

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


async def setup(bot: commands.Bot):
    await bot.add_cog(PartyCog(bot))
    logger.info("PartyCog успешно загружен и добавлен в бота.")
