import logging
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db_session, transactional
import re
from backend.core.crud.crud_player import player_crud
from backend.core.crud.crud_party import party_crud
from backend.core.crud.crud_location import location_crud
from backend.core.rules import get_rule
from backend.models.player import Player
from backend.models.party import Party, PartyTurnStatus
from backend.models.location import Location
from backend.core.locations_utils import get_localized_text

logger = logging.getLogger(__name__)

@app_commands.guild_only()
class PartyCog(commands.GroupCog, name="party"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("PartyCog (slash) инициализирован.")

    @app_commands.command(name="create", description="Создать новую группу.")
    @app_commands.describe(party_name="Название для вашей новой группы.")
    @transactional()
    async def party_create(self, interaction: discord.Interaction, party_name: str, session: AsyncSession):
        if not interaction.guild:
            await interaction.response.send_message("Эта команда может быть использована только на сервере.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        discord_id = interaction.user.id

        try:
            player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=discord_id)
            if not player:
                await interaction.response.send_message("Сначала начните игру командой `/start`.", ephemeral=True)
                return

            if player.current_party_id:
                existing_party = await party_crud.get(session, id=player.current_party_id)
                await interaction.response.send_message(f"Вы уже состоите в группе '{existing_party.name if existing_party else 'Неизвестная группа'}'. Сначала покиньте ее.", ephemeral=True)
                return

            name_validation_regex_str = await get_rule(session, guild_id, "party:name_validation_regex", default="^[a-zA-Z0-9А-Яа-яЁё\\s'-_]{3,32}$")
            name_max_length = await get_rule(session, guild_id, "party:name_max_length", default=32)

            if not re.match(name_validation_regex_str, party_name) or len(party_name) > name_max_length:
                await interaction.response.send_message(f"Название группы содержит недопустимые символы или не соответствует требованиям по длине (3-{name_max_length} символов).", ephemeral=True)
                return

            existing_named_party = await party_crud.get_by_name(session, name=party_name, guild_id=guild_id)
            if existing_named_party:
                await interaction.response.send_message(f"Группа с названием '{party_name}' уже существует.", ephemeral=True)
                return

            new_party = await party_crud.create(
                session,
                obj_in={
                    "name": party_name,
                    "guild_id": guild_id,
                    "leader_player_id": player.id,
                    "current_location_id": player.current_location_id,
                    "player_ids_json": [player.id],
                }
            )

            player.current_party_id = new_party.id
            session.add(player)

            logger.info(f"Игрок {player.name} (ID: {player.id}) создал группу '{new_party.name}' (ID: {new_party.id}) на сервере {guild_id}.")
            await interaction.response.send_message(f"Группа '{new_party.name}' успешно создана! Вы ее лидер.")

        except Exception as e:
            logger.error(f"Ошибка при создании группы для {interaction.user} на сервере {guild_id}: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка при создании группы.", ephemeral=True)

    @app_commands.command(name="leave", description="Покинуть текущую группу.")
    @transactional()
    async def party_leave(self, interaction: discord.Interaction, session: AsyncSession):
        if not interaction.guild:
            await interaction.response.send_message("Эта команда может быть использована только на сервере.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        discord_id = interaction.user.id

        try:
            player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=discord_id)
            if not player or not player.current_party_id:
                await interaction.response.send_message("Вы не состоите в группе.", ephemeral=True)
                return

            party = await party_crud.get(session, id=player.current_party_id)
            if not party:
                player.current_party_id = None
                session.add(player)
                await interaction.response.send_message("Вашей группы больше не существует. Данные исправлены.", ephemeral=True)
                return

            party_name = party.name
            was_leader = (party.leader_player_id == player.id)

            party = await party_crud.remove_player_from_party_json(session, party=party, player_id=player.id)
            player.current_party_id = None
            session.add(player)

            logger.info(f"Игрок {player.name} покинул группу '{party_name}'.")

            disband_party = False
            if not party.player_ids_json:
                disband_party = True
            elif was_leader:
                policy = await get_rule(session, guild_id, "party:leader_transfer_policy", "promote_oldest_member")
                if policy == "promote_oldest_member" and party.player_ids_json:
                    party.leader_player_id = party.player_ids_json[0]
                    session.add(party)
                    logger.info(f"Лидерство в '{party_name}' передано игроку ID: {party.leader_player_id}.")
                else:
                    disband_party = True

            if not disband_party:
                threshold = await get_rule(session, guild_id, "party:auto_disband_threshold", 1)
                if party.player_ids_json and len(party.player_ids_json) < threshold:
                    disband_party = True

            if disband_party:
                await party_crud.delete(session, id=party.id)
                await interaction.response.send_message(f"Вы покинули группу '{party_name}'. Группа была распущена.")
            else:
                await interaction.response.send_message(f"Вы покинули группу '{party_name}'.")

        except Exception as e:
            logger.error(f"Ошибка при выходе из группы для {interaction.user}: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка.", ephemeral=True)

    @app_commands.command(name="disband", description="Распустить вашу группу (только для лидера).")
    @transactional()
    async def party_disband(self, interaction: discord.Interaction, session: AsyncSession):
        if not interaction.guild:
            await interaction.response.send_message("Эта команда может быть использована только на сервере.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        discord_id = interaction.user.id

        try:
            player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=discord_id)
            if not player or not player.current_party_id:
                await interaction.response.send_message("Вы не состоите в группе.", ephemeral=True)
                return

            party = await party_crud.get(session, id=player.current_party_id)
            if not party:
                player.current_party_id = None
                session.add(player)
                await interaction.response.send_message("Вашей группы больше не существует. Данные исправлены.", ephemeral=True)
                return

            if party.leader_player_id != player.id:
                await interaction.response.send_message("Только лидер группы может ее распустить.", ephemeral=True)
                return

            party_name = party.name
            member_ids = list(party.player_ids_json) if party.player_ids_json else []

            await party_crud.delete(session, id=party.id)

            for member_id in member_ids:
                member = await player_crud.get(session, id=member_id)
                if member:
                    member.current_party_id = None
                    session.add(member)

            logger.info(f"Игрок {player.name} распустил группу '{party_name}'.")
            await interaction.response.send_message(f"Группа '{party_name}' была успешно распущена.")

        except Exception as e:
            logger.error(f"Ошибка при роспуске группы для {interaction.user}: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка.", ephemeral=True)

    @app_commands.command(name="join", description="Присоединиться к существующей группе.")
    @app_commands.describe(party_identifier="Название или ID группы.")
    @transactional()
    async def party_join(self, interaction: discord.Interaction, party_identifier: str, session: AsyncSession):
        if not interaction.guild:
            await interaction.response.send_message("Эта команда может быть использована только на сервере.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        discord_id = interaction.user.id

        try:
            player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=discord_id)
            if not player:
                await interaction.response.send_message("Сначала начните игру командой `/start`.", ephemeral=True)
                return

            if player.current_party_id:
                await interaction.response.send_message("Вы уже состоите в группе.", ephemeral=True)
                return

            target_party = await party_crud.get_by_name(session, name=party_identifier, guild_id=guild_id)
            if not target_party:
                await interaction.response.send_message(f"Группа '{party_identifier}' не найдена.", ephemeral=True)
                return

            max_size = await get_rule(session, guild_id, "party:max_size", 5)
            if target_party.player_ids_json and len(target_party.player_ids_json) >= max_size:
                await interaction.response.send_message(f"Группа '{target_party.name}' уже заполнена.", ephemeral=True)
                return

            # Simplified validation for now

            target_party = await party_crud.add_player_to_party_json(session, party=target_party, player_id=player.id)
            player.current_party_id = target_party.id
            if player.current_location_id != target_party.current_location_id:
                player.current_location_id = target_party.current_location_id
            session.add(player)

            await interaction.response.send_message(f"Вы успешно присоединились к группе '{target_party.name}'.")

        except Exception as e:
            logger.error(f"Ошибка при присоединении к группе для {interaction.user}: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка.", ephemeral=True)

    @app_commands.command(name="kick", description="Исключить игрока из вашей группы (только для лидера).")
    @app_commands.describe(target_player="Игрок, которого нужно исключить.")
    @transactional()
    async def party_kick(self, interaction: discord.Interaction, target_player: discord.Member, session: AsyncSession):
        if not interaction.guild:
            await interaction.response.send_message("Команда только для сервера.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        kicker_player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=interaction.user.id)
        if not kicker_player or not kicker_player.current_party_id:
            await interaction.response.send_message("Вы не в группе.", ephemeral=True)
            return

        party = await party_crud.get(session, id=kicker_player.current_party_id)
        if not party or party.leader_player_id != kicker_player.id:
            await interaction.response.send_message("Только лидер может исключать игроков.", ephemeral=True)
            return

        if target_player.id == interaction.user.id:
            await interaction.response.send_message("Нельзя исключить самого себя.", ephemeral=True)
            return

        target_player_db = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=target_player.id)
        if not target_player_db or target_player_db.current_party_id != party.id:
            await interaction.response.send_message("Этот игрок не в вашей группе.", ephemeral=True)
            return

        party = await party_crud.remove_player_from_party_json(session, party=party, player_id=target_player_db.id)
        target_player_db.current_party_id = None
        session.add(target_player_db)

        await interaction.response.send_message(f"Игрок {target_player.mention} был исключен из группы.")

    @app_commands.command(name="promote", description="Назначить нового лидера группы (только для лидера).")
    @app_commands.describe(new_leader="Участник, который станет новым лидером.")
    @transactional()
    async def party_promote(self, interaction: discord.Interaction, new_leader: discord.Member, session: AsyncSession):
        if not interaction.guild:
            await interaction.response.send_message("Команда только для сервера.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        promoter_player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=interaction.user.id)
        if not promoter_player or not promoter_player.current_party_id:
            await interaction.response.send_message("Вы не в группе.", ephemeral=True)
            return

        party = await party_crud.get(session, id=promoter_player.current_party_id)
        if not party or party.leader_player_id != promoter_player.id:
            await interaction.response.send_message("Только лидер может назначать нового лидера.", ephemeral=True)
            return

        if new_leader.id == interaction.user.id:
            await interaction.response.send_message("Вы уже лидер.", ephemeral=True)
            return

        new_leader_db = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=new_leader.id)
        if not new_leader_db or not new_leader_db.current_party_id != party.id:
            await interaction.response.send_message(f"{new_leader.mention} не в вашей группе.", ephemeral=True)
            return

        party.leader_player_id = new_leader_db.id
        session.add(party)
        await interaction.response.send_message(f"{new_leader.mention} теперь новый лидер группы '{party.name}'!")

    @app_commands.command(name="view", description="Посмотреть информацию о группе.")
    @app_commands.describe(party_identifier="Название или ID группы (если не указано, покажет вашу).")
    @transactional(read_only=True)
    async def party_view(self, interaction: discord.Interaction, party_identifier: Optional[str] = None, session: Optional[AsyncSession] = None):
        if not interaction.guild or not session:
            await interaction.response.send_message("Команда только для сервера.", ephemeral=True)
            return

        requester_player = await player_crud.get_by_discord_id(session, guild_id=interaction.guild.id, discord_id=interaction.user.id)
        if not requester_player:
            await interaction.response.send_message("Сначала начните игру.", ephemeral=True)
            return

        party_to_view = None
        if party_identifier:
            party_to_view = await party_crud.get_by_name(session, name=party_identifier, guild_id=interaction.guild.id)
        elif requester_player.current_party_id:
            party_to_view = await party_crud.get(session, id=requester_player.current_party_id)

        if not party_to_view:
            msg = f"Группа '{party_identifier}' не найдена." if party_identifier else "Вы не состоите в группе."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        embed = discord.Embed(title=f"Информация о группе: {party_to_view.name}", color=discord.Color.blurple())

        leader = await player_crud.get(session, id=party_to_view.leader_player_id)
        embed.add_field(name="Лидер", value=leader.name if leader else "Неизвестен", inline=True)

        member_names = []
        if party_to_view.player_ids_json:
            for player_id in party_to_view.player_ids_json:
                p = await player_crud.get(session, id=player_id)
                if p:
                    member_names.append(p.name)

        embed.add_field(name=f"Участники ({len(member_names)})", value=", ".join(member_names) if member_names else "Нет", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="invite", description="Пригласить игрока в вашу группу.")
    @app_commands.describe(target_player="Игрок, которого вы хотите пригласить.")
    @transactional(read_only=True)
    async def party_invite(self, interaction: discord.Interaction, target_player: discord.Member, session: AsyncSession):
        if not interaction.guild:
            await interaction.response.send_message("Команда только для сервера.", ephemeral=True)
            return

        inviter_player = await player_crud.get_by_discord_id(session, guild_id=interaction.guild.id, discord_id=interaction.user.id)
        if not inviter_player or not inviter_player.current_party_id:
            await interaction.response.send_message("Вы не в группе.", ephemeral=True)
            return

        party = await party_crud.get(session, id=inviter_player.current_party_id)
        if not party:
            await interaction.response.send_message("Ошибка: не найдена ваша группа.", ephemeral=True)
            return

        # Simplified validation for now

        try:
            dm_message = f"{interaction.user.display_name} приглашает вас в группу '{party.name}' на сервере '{interaction.guild.name}'.\nИспользуйте `/party join {party.name}` для вступления."
            await target_player.send(dm_message)
            await interaction.response.send_message(f"Приглашение отправлено {target_player.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"Не удалось отправить ЛС {target_player.mention}.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(PartyCog(bot))
    logger.info("PartyCog (slash) успешно загружен и добавлен в дерево команд.")
