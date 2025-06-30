import logging
import discord
from discord.ext import commands
from typing import Optional

from core.database import get_db_session
from core.crud.crud_player import player_crud
from core.crud.crud_party import party_crud
from core.crud.crud_location import location_crud # For party location consistency
from models.player import Player
from models.party import Party, PartyTurnStatus
from models.location import Location
from core.locations_utils import get_localized_text

logger = logging.getLogger(__name__)

class PartyCog(commands.Cog, name="Party Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("PartyCog инициализирован.")

    @commands.group(name="party", invoke_without_command=True, help="Управление группами (пати).")
    async def party_group(self, ctx: commands.Context):
        """Основная команда для управления группами. Вызовите без подкоманд для помощи."""
        if ctx.invoked_subcommand is None:
            # TODO: Implement a more detailed help message for party commands
            await ctx.send("Доступные команды для party: `create <название>`, `leave`, `disband`, `join <название_партии_или_ID>` (пока не реализовано), `info` (пока не реализовано).")

    @party_group.command(name="create", help="Создать новую группу. Пример: /party create Искатели приключений")
    async def party_create(self, ctx: commands.Context, *, party_name: str):
        if not ctx.guild:
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        guild_id = ctx.guild.id
        discord_id = ctx.author.id

        async for session in get_db_session():
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

    @party_group.command(name="leave", help="Покинуть текущую группу.")
    async def party_leave(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        guild_id = ctx.guild.id
        discord_id = ctx.author.id

        async for session in get_db_session():
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

    @party_group.command(name="disband", help="Распустить текущую группу (только для создателя/лидера - пока не реализовано).")
    async def party_disband(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        guild_id = ctx.guild.id
        discord_id = ctx.author.id

        async for session in get_db_session():
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

async def setup(bot: commands.Bot):
    await bot.add_cog(PartyCog(bot))
    logger.info("PartyCog успешно загружен и добавлен в бота.")
