import logging
from typing import Optional, List, Union, Dict, Any, Tuple # Added Tuple

from sqlalchemy.ext.asyncio import AsyncSession

# Model imports
from src.models import Player, GeneratedNpc, CombatEncounter, Party # Added Party
from src.models.enums import CombatStatus, PlayerStatus, PartyTurnStatus, EventType

# Core module imports
from src.core import game_events, dice_roller, rules, check_resolver, npc_combat_strategy, combat_engine
from src.core.crud import crud_player, crud_party, crud_npc, crud_combat_encounter # May need specific cruds
from src.core.database import transactional # For atomic operations

logger = logging.getLogger(__name__)

# Placeholder for future systems - will be replaced by actual imports or proper заглушки
class XPAwarder: # Placeholder for Task 31
    async def award_xp(self, session: AsyncSession, guild_id: int, combat_encounter: CombatEncounter, winners: List[Union[Player, GeneratedNpc]], losers: List[Union[Player, GeneratedNpc]]):
        logger.info(f"[XPAwarder-Placeholder] Guild {guild_id}: Awarding XP for combat {combat_encounter.id}")
        # Actual logic for XP calculation and distribution will go here
        pass

class LootGenerator: # Placeholder for Task 42
    async def distribute_loot(self, session: AsyncSession, guild_id: int, combat_encounter: CombatEncounter, winners: List[Union[Player, GeneratedNpc]], losers: List[Union[Player, GeneratedNpc]]):
        logger.info(f"[LootGenerator-Placeholder] Guild {guild_id}: Distributing loot for combat {combat_encounter.id}")
        # Actual logic for loot generation and distribution
        pass

class RelationshipUpdater: # Placeholder for Task 36
    async def update_relationships_post_combat(self, session: AsyncSession, guild_id: int, combat_encounter: CombatEncounter, all_participants: List[Dict[str, Any]]):
        logger.info(f"[RelationshipUpdater-Placeholder] Guild {guild_id}: Updating relationships post-combat {combat_encounter.id}")
        # Actual logic for updating relationships based on combat outcome
        pass

class WorldStateUpdater: # Placeholder
    async def update_world_state_post_combat(self, session: AsyncSession, guild_id: int, combat_encounter: CombatEncounter):
        logger.info(f"[WorldStateUpdater-Placeholder] Guild {guild_id}: Updating world state post-combat {combat_encounter.id}")
        pass

class QuestSystem: # Placeholder for Task 41
    async def handle_combat_event_for_quests(self, session: AsyncSession, guild_id: int, combat_encounter: CombatEncounter, event_details: Dict[str, Any]):
        logger.info(f"[QuestSystem-Placeholder] Guild {guild_id}: Handling combat event for quests, combat {combat_encounter.id}")
        # Actual logic for checking quest objectives related to combat
        pass

# Instantiate placeholders
xp_awarder = XPAwarder()
loot_generator = LootGenerator()
relationship_updater = RelationshipUpdater()
world_state_updater = WorldStateUpdater()
quest_system = QuestSystem()


@transactional
async def start_combat(
    session: AsyncSession,
    guild_id: int,
    location_id: int,
    participant_entities: List[Union[Player, GeneratedNpc]],
    initiator_action_data: Optional[Dict[str, Any]] = None # Not used in this version of start_combat directly
) -> CombatEncounter:
    """
    Starts a new combat encounter.
    """
    logger.info(f"Guild {guild_id}, Location {location_id}: Starting new combat with {len(participant_entities)} participants.")

    # 1. Create CombatEncounter record
    combat_encounter = CombatEncounter(
        guild_id=guild_id,
        location_id=location_id,
        status=CombatStatus.PENDING_START, # Changed from STARTING
        participants_json={"entities": []}, # Initialize participants list
        turn_order_json={"order": [], "current_index": 0, "current_turn_number": 1},
        rules_config_snapshot_json={},
        combat_log_json={"entries": []}
    )
    session.add(combat_encounter)
    await session.flush() # To get combat_encounter.id for logging if needed early

    # 2. Determine participants and their initial data
    participants_for_json = []
    initiative_rolls = [] # List of tuples: (roll_result, participant_index_in_entities_list)

    for i, entity in enumerate(participant_entities):
        entity_type_str = "player" if isinstance(entity, Player) else "npc"
        team = "players" if isinstance(entity, Player) else "npcs" # Simple team assignment

        # Get base stats (simplified)
        max_hp = 100 # Default, should come from entity.stats or RuleConfig
        current_hp = max_hp
        armor_class = 10 # Default

        dex_modifier = 0 # Initialize dex_modifier once before conditional assignment
        if isinstance(entity, Player):
            # In a real scenario, fetch from player.stats, player.equipment etc.
            # For now, using placeholder values or direct model fields if available
            player_default_max_hp = await rules.get_rule(session=session, guild_id=guild_id, key="player:stats:default_max_hp", default=100)
            max_hp = getattr(entity, 'max_hp', player_default_max_hp) # Assuming Player model might have max_hp
            current_hp = getattr(entity, 'current_hp', max_hp) # And current_hp
            armor_class = getattr(entity, 'armor_class', 10) # And armor_class
            dex_modifier = (getattr(entity, 'dexterity', 10) - 10) // 2 # Example dexterity modifier for initiative

        elif isinstance(entity, GeneratedNpc):
            entity_props = entity.properties_json or {}
            npc_stats_block = entity_props.get("stats", {})
            max_hp = npc_stats_block.get("hp", 50)
            current_hp = npc_stats_block.get("current_hp", max_hp) # NPCs might have current_hp if pre-damaged
            armor_class = npc_stats_block.get("armor_class", 10)
            dex_modifier = (npc_stats_block.get("dexterity", 10) - 10) // 2
            # Example of using get_rule within start_combat if needed for an NPC default
            # max_hp = npc_stats_block.get("hp", await rules.get_rule(session, guild_id, "npc:default_max_hp", default=50))


        participant_data = {
            "id": entity.id,
            "type": entity_type_str,
            "name": entity.name if isinstance(entity, Player) else entity.name_i18n.get("en", "Unknown NPC"), # Simple name
            "team": team,
            "max_hp": max_hp,
            "current_hp": current_hp,
            "armor_class": armor_class,
            "status_effects": [], # Placeholder for active status effects
            "initiative_modifier": dex_modifier # Store for reference, used below
        }
        participants_for_json.append(participant_data)

        # Roll initiative
        initiative_dice_rule = await rules.get_rule(session=session, guild_id=guild_id, key="combat:initiative:dice", default="1d20")
        initiative_roll, _ = dice_roller.roll_dice(initiative_dice_rule)
        total_initiative = initiative_roll + dex_modifier
        initiative_rolls.append({"score": total_initiative, "participant_ref": participant_data}) # Link to the data

    # Sort by initiative (descending), then by original index as tie-breaker (implicit if stable sort not used)
    # A better tie-breaker might be dexterity score itself or random. For now, just score.
    initiative_rolls.sort(key=lambda x: x["score"], reverse=True)

    if combat_encounter.participants_json:
        combat_encounter.participants_json["entities"] = participants_for_json # Store all participants' data
    else: # Should not happen if initialized correctly
        combat_encounter.participants_json = {"entities": participants_for_json}

    current_turn_order = [
        {"id": item["participant_ref"]["id"], "type": item["participant_ref"]["type"]} for item in initiative_rolls
    ]

    if combat_encounter.turn_order_json:
        combat_encounter.turn_order_json["order"] = current_turn_order
    else: # Should not happen
        combat_encounter.turn_order_json = {"order": current_turn_order, "current_index": 0, "current_turn_number": 1}


    if current_turn_order:
        first_in_turn = current_turn_order[0]
        combat_encounter.current_turn_entity_id = first_in_turn.get("id")
        combat_encounter.current_turn_entity_type = first_in_turn.get("type")
    else: # Should not happen if participant_entities is not empty
        logger.error(f"Guild {guild_id}, Combat {combat_encounter.id}: No participants in turn order after initiative.")
        combat_encounter.status = CombatStatus.ERROR
        # No need to await session.commit() here due to @transactional, it will rollback if error is raised
        # or commit if function completes.
        return combat_encounter # Early exit

    # 3. Snapshot relevant rules
    # This is a simplified example. A real system might fetch all rules under a "combat:" prefix
    # or have a more structured way to define which rules are combat-relevant.
    combat_rules_keys = [
        "combat:attack:check_type", "combat:attack:attacker_main_attribute", "combat:attack:target_defense_attribute",
        "combat:attack:damage_formula", "combat:attack:damage_attribute", "combat:attack:crit_damage_multiplier",
        "combat:attack:crit_effect", "combat:initiative:dice", "combat:attributes:modifier_formula",
        # Add other relevant rule keys here
    ]
    rules_snapshot = {}
    for key_to_snap in combat_rules_keys: # Renamed 'key' to avoid conflict with 'key' parameter of get_rule
        rule_value = await rules.get_rule(session=session, guild_id=guild_id, key=key_to_snap, default=None)
        if rule_value is not None:
            rules_snapshot[key_to_snap] = rule_value
    combat_encounter.rules_config_snapshot_json = rules_snapshot

    # 4. Update CombatEncounter status and entity statuses
    combat_encounter.status = CombatStatus.ACTIVE

    participants_entities = combat_encounter.participants_json.get("entities", []) if combat_encounter.participants_json else []

    for p_data in participants_entities:
        p_data_id = p_data.get("id")
        if p_data.get("type") == "player" and p_data_id is not None:
            player = await session.get(Player, p_data_id)
            if player:
                player.current_status = PlayerStatus.COMBAT # Changed IN_COMBAT to COMBAT
                # Store current combat ID on player model if such a field exists
                if hasattr(player, 'current_combat_id'):
                    player.current_combat_id = combat_encounter.id # type: ignore
                else:
                    logger.warning(f"Player model (id: {player.id}) does not have 'current_combat_id' attribute.")
                session.add(player)
        # elif p_data.get("type") == "npc":
            # NPCs don't have a separate status field like PlayerStatus.IN_COMBAT in the current model.
            # Their participation is tracked by being in CombatEncounter.participants_json.
            # If NPCs had parties or groups, their status might be updated here.

    # Update party statuses if players involved are in parties
    # This is a simplified approach. A more robust method would iterate through parties
    # and check if any of their members are in this combat.
    player_ids_in_combat = [p.get("id") for p in participants_entities if p.get("type") == "player" and p.get("id") is not None]
    if player_ids_in_combat:
        # This could be optimized by fetching relevant parties once.
        # For now, iterate through all players and update their party status if they are in one.
        for player_id in player_ids_in_combat:
            player_obj = await session.get(Player, player_id)
            if player_obj and player_obj.current_party_id:
                party = await session.get(Party, player_obj.current_party_id)
                if party and party.turn_status != PartyTurnStatus.IN_COMBAT: # Check to avoid redundant updates
                    party.turn_status = PartyTurnStatus.IN_COMBAT # Now valid
                    if hasattr(party, 'current_combat_id'): # If party model tracks current combat
                         party.current_combat_id = combat_encounter.id # type: ignore
                    else:
                        logger.warning(f"Party model (id: {party.id}) does not have 'current_combat_id' attribute.")
                    session.add(party)


    # 5. Log COMBAT_START event
    # Construct entity_ids_json for the log event
    log_entity_ids = {
        "players": [p.get("id") for p in participants_entities if p.get("type") == "player" and p.get("id") is not None],
        "npcs": [p.get("id") for p in participants_entities if p.get("type") == "npc" and p.get("id") is not None],
        "location": location_id,
        "combat_encounter": combat_encounter.id
    }

    turn_order_for_log = combat_encounter.turn_order_json.get("order", []) if combat_encounter.turn_order_json else []

    await game_events.log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.COMBAT_START.name, # Changed to .name
        details_json={
            "combat_id": combat_encounter.id,
            "location_id": location_id,
            "participants": participants_entities,
            "turn_order": turn_order_for_log
        },
        entity_ids_json=log_entity_ids,
        location_id=location_id # Redundant with details_json but often a direct param for log_event
    )

    logger.info(f"Guild {guild_id}: Combat {combat_encounter.id} started successfully. Status: {combat_encounter.status}. Turn order: {turn_order_for_log}")
    await session.flush() # Ensure all updates are flushed before returning
    return combat_encounter


@transactional
async def process_combat_turn(
    session: AsyncSession,
    guild_id: int,
    combat_id: int,
    # action_data is now passed by player through action_processor to combat_engine directly
    # This function is more about orchestrating whose turn it is and triggering NPC actions
    # or advancing turn after a player action has been processed by combat_engine.
    # For now, let's assume player action was already processed if it was their turn.
    # This function will primarily handle NPC turns and turn advancement.
) -> CombatEncounter:
    """
    Processes the current turn in a combat encounter.
    If it's an NPC's turn, gets their action and processes it.
    Advances the turn order. Checks for combat end.
    """
    combat_encounter = await session.get(CombatEncounter, combat_id)
    if not combat_encounter or combat_encounter.guild_id != guild_id:
        # This should ideally not happen if called correctly
        logger.error(f"Guild {guild_id}: Combat encounter {combat_id} not found or mismatch.")
        raise ValueError(f"Combat encounter {combat_id} not found for guild {guild_id}.") # Or return a specific status

    if combat_encounter.status != CombatStatus.ACTIVE:
        logger.warning(f"Guild {guild_id}: process_combat_turn called for non-active combat {combat_id} (status: {combat_encounter.status}).")
        return combat_encounter # No action if combat is not active

    turn_order_json = combat_encounter.turn_order_json if combat_encounter.turn_order_json is not None else {}
    logger.info(f"Guild {guild_id}: Processing turn {turn_order_json.get('current_turn_number', 0)} for combat {combat_id}. Current entity: {combat_encounter.current_turn_entity_type}:{combat_encounter.current_turn_entity_id}")

    active_entity_id_optional = combat_encounter.current_turn_entity_id
    active_entity_type_optional = combat_encounter.current_turn_entity_type

    if active_entity_id_optional is None or active_entity_type_optional is None:
        logger.error(f"Guild {guild_id}: Combat {combat_id} has no current active entity (ID or Type is None). Status: {combat_encounter.status}")
        combat_encounter.status = CombatStatus.ERROR
        session.add(combat_encounter)
        return combat_encounter

    # Now we know they are not None
    active_entity_id: int = active_entity_id_optional
    active_entity_type: str = active_entity_type_optional

    # Ensure participants_json and its 'entities' list exist
    if combat_encounter.participants_json is None: combat_encounter.participants_json = {"entities": []}
    if "entities" not in combat_encounter.participants_json: combat_encounter.participants_json["entities"] = []

    actor_participant_data = next((p for p in combat_encounter.participants_json["entities"] if p["id"] == active_entity_id and p["type"] == active_entity_type), None)

    if not actor_participant_data:
        logger.error(f"Guild {guild_id}: Active entity {active_entity_type}:{active_entity_id} not found in participants_json for combat {combat_id}.")
        # This is a critical error, potentially advance turn or mark combat as error
        combat_encounter.status = CombatStatus.ERROR # Mark combat as errored
        session.add(combat_encounter)
        return combat_encounter

    # Check if current actor is defeated (e.g. due to damage over time effects before their turn)
    if actor_participant_data.get("current_hp", 0) <= 0:
        logger.info(f"Guild {guild_id}: Entity {active_entity_type}:{active_entity_id} is defeated at start of their turn. Skipping turn.")
        # Don't process action, just advance turn. The advance_turn logic will handle skipping.

    elif active_entity_type == "npc":
        npc_action_data = await npc_combat_strategy.get_npc_combat_action(
            session=session,
            guild_id=guild_id,
            npc_id=active_entity_id,
            combat_instance_id=combat_id
        )
        if npc_action_data and npc_action_data.get("action_type") != "idle" and npc_action_data.get("action_type") != "error":
            logger.info(f"Guild {guild_id}: NPC {active_entity_id} in combat {combat_id} performing action: {npc_action_data}")
            action_result = await combat_engine.process_combat_action(
                guild_id=guild_id,
                session=session,
                combat_instance_id=combat_id,
                actor_id=active_entity_id, # type: int
                actor_type=active_entity_type, # type: str
                action_data=npc_action_data
            )
            # combat_engine already logs COMBAT_ACTION and updates participants_json
            logger.debug(f"Guild {guild_id}: NPC action result for combat {combat_id}: {action_result.model_dump_json()}")
            # Trigger quest system hook for NPC actions too
            await quest_system.handle_combat_event_for_quests(session, guild_id, combat_encounter, {"type": "npc_action", "result": action_result.model_dump()})

        else:
            logger.info(f"Guild {guild_id}: NPC {active_entity_id} in combat {combat_id} chose to be idle or an error occurred: {npc_action_data.get('reason', 'No action taken')}")
            # Log NPC idle action to StoryLog for completeness, if desired
            await game_events.log_event(
                session=session, guild_id=guild_id, event_type=EventType.NPC_ACTION.name, # Changed to NPC_ACTION.name, or a more specific Enum like NPC_IDLE_IN_COMBAT
                details_json={"combat_id": combat_id, "npc_id": active_entity_id, "action_type": "idle", "reason": npc_action_data.get('reason', 'No action taken')},
                entity_ids_json={"npcs": [active_entity_id], "combat_encounter": combat_id},
                location_id=combat_encounter.location_id
            )

    # If it was a player's turn, their action would have been processed by combat_engine
    # directly from action_processor calling it. This function, process_combat_turn,
    # would then be called to advance the state.

    # Check for combat end after any action (player or NPC)
    # The combat_engine updates HPs in participants_json
    # We need to re-fetch combat_encounter to get the latest participants_json if combat_engine committed separately.
    # However, if all are within the same @transactional scope, session.refresh(combat_encounter) might be enough.
    # For simplicity, assume combat_engine modified the session's combat_encounter object.

    await session.refresh(combat_encounter) # Ensure we have the latest state after combat_engine might have changed it.

    combat_ended, winning_team = await _check_combat_end(session, guild_id, combat_encounter)

    if combat_ended:
        logger.info(f"Guild {guild_id}: Combat {combat_id} has ended. Winning team: {winning_team if winning_team else 'Draw/Error'}.")
        if winning_team == "players":
            combat_encounter.status = CombatStatus.ENDED_VICTORY_PLAYERS
        elif winning_team == "npcs":
            combat_encounter.status = CombatStatus.ENDED_VICTORY_NPCS
        else: # Draw or other non-specific end (e.g. error during check_combat_end)
            combat_encounter.status = CombatStatus.ENDED_STALEMATE # Default to stalemate if no clear winner

        await _handle_combat_end_consequences(session, guild_id, combat_encounter, winning_team)
        # Log COMBAT_END (moved to _handle_combat_end_consequences)
        session.add(combat_encounter)
        await session.flush()
        return combat_encounter

    # If combat not ended, advance turn
    await _advance_turn(session, combat_encounter) # Pass session here if _advance_turn needs it for rule lookups etc.

    turn_order_json_after_advance = combat_encounter.turn_order_json if combat_encounter.turn_order_json is not None else {}
    logger.info(f"Guild {guild_id}: Advanced turn for combat {combat_id}. New entity: {combat_encounter.current_turn_entity_type}:{combat_encounter.current_turn_entity_id}. Turn #: {turn_order_json_after_advance.get('current_turn_number')}")

    session.add(combat_encounter)
    await session.flush() # Ensure updates to turn order are saved before returning

    # If the new current turn is an NPC and they are not defeated, process their turn immediately.
    # This makes NPC turns flow automatically until a player's turn or combat ends.
    new_active_id = combat_encounter.current_turn_entity_id
    new_active_type = combat_encounter.current_turn_entity_type
    if new_active_type == "npc" and combat_encounter.status == CombatStatus.ACTIVE:
        new_actor_participant_data = next((p for p in combat_encounter.participants_json["entities"] if p["id"] == new_active_id and p["type"] == new_active_type), None)
        if new_actor_participant_data and new_actor_participant_data.get("current_hp", 0) > 0:
            logger.info(f"Guild {guild_id}: Combat {combat_id} - new turn is NPC {new_active_id}, processing their turn.")
            # RECURSIVE CALL - be careful with depth if many NPCs and no players
            # This will continue until a player's turn or combat ends.
            return await process_combat_turn(session, guild_id, combat_id)
            # Non-recursive alternative: return and let an external loop call process_combat_turn again.
            # For now, recursive seems to match the "NPCs act until player turn" idea.

    return combat_encounter

async def _check_combat_end(session: AsyncSession, guild_id: int, combat_encounter: CombatEncounter) -> Tuple[bool, Optional[str]]:
    """
    Checks if the combat has ended.
    Returns (True, winning_team_name or None for draw) or (False, None).
    Assumes simple two-team combat ("players" vs "npcs").
    """
    if not combat_encounter.participants_json or not combat_encounter.participants_json.get("entities"):
        logger.warning(f"Guild {guild_id}: Combat {combat_encounter.id} has no participant data to check for end.")
        return True, None # No participants, effectively ended

    teams = {"players": {"alive_count": 0, "present": False}, "npcs": {"alive_count": 0, "present": False}}

    for p_data in combat_encounter.participants_json["entities"]:
        team_name = p_data.get("team")
        if team_name in teams:
            teams[team_name]["present"] = True
            if p_data.get("current_hp", 0) > 0:
                teams[team_name]["alive_count"] += 1
        else:
            logger.warning(f"Guild {guild_id}: Unknown team '{team_name}' in combat {combat_encounter.id} for participant {p_data.get('id')}")

    # If only one team ever became present (e.g. combat started with only one team type somehow)
    if teams["players"]["present"] and not teams["npcs"]["present"]:
        return True, "players" # Players win by default if no NPC opponents were ever there
    if teams["npcs"]["present"] and not teams["players"]["present"]:
        return True, "npcs" # NPCs win if no players were ever there

    # Standard win conditions
    if teams["players"]["present"] and teams["players"]["alive_count"] == 0 and teams["npcs"]["alive_count"] > 0:
        return True, "npcs" # All players defeated
    if teams["npcs"]["present"] and teams["npcs"]["alive_count"] == 0 and teams["players"]["alive_count"] > 0:
        return True, "players" # All NPCs defeated

    # Draw or mutual destruction (or if a team was never present but the other also died)
    if teams["players"]["alive_count"] == 0 and teams["npcs"]["alive_count"] == 0:
        return True, None # Draw / Mutual Annihilation

    return False, None # Combat continues

async def _advance_turn(session: AsyncSession, combat_encounter: CombatEncounter): # Added session for potential rule lookups
    """
    Advances the turn to the next participant in the order.
    Skips defeated participants. Updates combat_encounter in place.
    """
    turn_order_data = combat_encounter.turn_order_json
    if not turn_order_data or not turn_order_data.get("order"): # Check .get("order") as order_list can be empty
        logger.error(f"Combat {combat_encounter.id}: Turn order data is missing or its 'order' list is empty. Cannot advance turn.")
        combat_encounter.status = CombatStatus.ERROR # Mark as error
        return

    order_list = turn_order_data.get("order", []) # Default to empty list if "order" key is missing
    if not order_list: # Double check if order_list is empty after .get()
        logger.error(f"Combat {combat_encounter.id}: 'order' list within turn_order_data is empty. Cannot advance turn.")
        combat_encounter.status = CombatStatus.ERROR
        return

    current_idx = turn_order_data.get("current_index", -1) # Start before the first element for the first +1
    current_turn_number = turn_order_data.get("current_turn_number", 1)


    # Loop to find the next non-defeated participant
    for i in range(len(order_list)): # Max iterations = length of order list
        current_idx = (current_idx + 1) % len(order_list)
        if i > 0 and current_idx == 0: # Completed a full round (ensure i > 0 to correctly count first round)
            current_turn_number += 1
            logger.info(f"Combat {combat_encounter.id}: Starting new round, turn number {current_turn_number}.")
            # TODO: Here, process round-based effects (e.g., status effect durations, cooldowns decrement)
            # This would involve iterating through participants_json and updating their status_effects, cooldowns.

        next_entity_ref = order_list[current_idx]
        next_entity_id = next_entity_ref.get("id")
        next_entity_type = next_entity_ref.get("type")

        if next_entity_id is None or next_entity_type is None:
            logger.error(f"Combat {combat_encounter.id}: Invalid entity reference in turn order at index {current_idx}: {next_entity_ref}")
            continue # Skip this invalid entry and try the next

        # Check if this next entity is still alive
        current_participants_json = combat_encounter.participants_json or {}
        participant_entities_list = current_participants_json.get("entities", [])

        participant_data = next(
            (p for p in participant_entities_list if p.get("id") == next_entity_id and p.get("type") == next_entity_type),
            None
        )
        if participant_data and participant_data.get("current_hp", 0) > 0:
            turn_order_data["current_index"] = current_idx
            turn_order_data["current_turn_number"] = current_turn_number
            combat_encounter.current_turn_entity_id = next_entity_id
            combat_encounter.current_turn_entity_type = next_entity_type
            combat_encounter.turn_order_json = turn_order_data # Ensure the dict is marked as changed for SQLAlchemy
            return

    # If loop completes, it means no one is left alive (should have been caught by _check_combat_end)
    # Or all remaining are defeated. This state implies combat should have ended.
    logger.warning(f"Combat {combat_encounter.id}: _advance_turn looped through all participants and found no one alive. Combat should have ended.")
    # _check_combat_end should ideally prevent this. If it happens, set to error or re-evaluate end.
    # For now, if this is reached, it's likely an issue.
    # combat_encounter.status = CombatStatus.ERROR


async def _handle_combat_end_consequences(
    session: AsyncSession, guild_id: int, combat_encounter: CombatEncounter, winning_team: Optional[str]
):
    """
    Handles the consequences of combat ending (XP, loot, status updates, logging).
    """
    logger.info(f"Guild {guild_id}: Handling end consequences for combat {combat_encounter.id}. Winning team: {winning_team}")

    # Determine winners and losers
    winners = []
    losers = []

    current_participants_json = combat_encounter.participants_json or {}
    participant_entities_list = current_participants_json.get("entities", [])
    all_participants_for_rel_update = list(participant_entities_list) # Create a copy for this specific use


    if winning_team:
        for p_data in participant_entities_list:
            entity_model = None
            if p_data.get("type") == "player": # Use .get for safety
                entity_model = await session.get(Player, p_data.get("id"))
            elif p_data.get("type") == "npc":
                entity_model = await session.get(GeneratedNpc, p_data.get("id"))

            if entity_model: # Ensure entity was found
                if p_data.get("team") == winning_team and p_data.get("current_hp",0) > 0 : # Winners must be alive
                    winners.append(entity_model)
                else: # Everyone else is a loser (defeated members of winning team, or all of losing team)
                    losers.append(entity_model)
    else: # Draw or mutual destruction, all are considered losers for XP/loot (or handle differently based on rules)
        for p_data in participant_entities_list:
            entity_model = None
            if p_data.get("type") == "player": entity_model = await session.get(Player, p_data.get("id")) # Safe with .get("id")
            elif p_data.get("type") == "npc": entity_model = await session.get(GeneratedNpc, p_data.get("id")) # Safe with .get("id")
            if entity_model: losers.append(entity_model)


    # 1. Award XP (using placeholder)
    await xp_awarder.award_xp(session, guild_id, combat_encounter, winners, losers)

    # 2. Distribute Loot (using placeholder)
    await loot_generator.distribute_loot(session, guild_id, combat_encounter, winners, losers)

    # 3. Update Relationships (using placeholder)
    await relationship_updater.update_relationships_post_combat(session, guild_id, combat_encounter, all_participants_for_rel_update)

    # 4. Update WorldState (using placeholder)
    await world_state_updater.update_world_state_post_combat(session, guild_id, combat_encounter)

    # 5. Update Quest Progress (using placeholder) - Will be replaced by direct call after COMBAT_END log.
    # await quest_system.handle_combat_event_for_quests(session, guild_id, combat_encounter, {"type": "combat_end", "winning_team": winning_team})

    # 6. Reset player/party statuses (before logging COMBAT_END, so log reflects final state)
    # participant_entities_list is already defined and checked from current_participants_json above
    involved_player_ids_for_quest_check: List[int] = []
    involved_party_ids_for_quest_check: List[int] = [] # Though typically one party if any

    for p_data in participant_entities_list:
        p_data_id = p_data.get("id")
        if p_data.get("type") == "player" and p_data_id is not None:
            player = await session.get(Player, p_data_id)
            if player:
                if player.id not in involved_player_ids_for_quest_check:
                    involved_player_ids_for_quest_check.append(player.id)
                if player.current_party_id and player.current_party_id not in involved_party_ids_for_quest_check:
                    involved_party_ids_for_quest_check.append(player.current_party_id)

                player.current_status = PlayerStatus.EXPLORING
                if hasattr(player, 'current_combat_id') and player.current_combat_id == combat_encounter.id:
                    player.current_combat_id = None
                session.add(player)

                if player.current_party_id:
                    party = await session.get(Party, player.current_party_id)
                    if party and party.turn_status == PartyTurnStatus.IN_COMBAT:
                        # Check if any other member of this party is still in *this specific* combat
                        # This is simplified; a robust check would see if other members are in *any* active combat.
                        # For now, if this combat is ending, assume party can leave combat status if no other known combat.
                        if hasattr(party, 'current_combat_id') and party.current_combat_id == combat_encounter.id:
                            party.turn_status = PartyTurnStatus.IDLE
                            party.current_combat_id = None
                        elif not hasattr(party, 'current_combat_id'):
                             party.turn_status = PartyTurnStatus.IDLE
                        if party: session.add(party)


    # 7. Log COMBAT_END event
    log_entity_ids_for_combat_end = {
        "players": [p.id for p in winners if isinstance(p, Player)] + [p.id for p in losers if isinstance(p, Player)],
        "npcs": [p.id for p in winners if isinstance(p, GeneratedNpc)] + [p.id for p in losers if isinstance(p, GeneratedNpc)],
        "location_id": combat_encounter.location_id, # Corrected key
        "combat_encounter_id": combat_encounter.id # Corrected key
    }
    log_entity_ids_for_combat_end["players"] = list(set(log_entity_ids_for_combat_end["players"]))
    log_entity_ids_for_combat_end["npcs"] = list(set(log_entity_ids_for_combat_end["npcs"]))

    combat_end_log_entry = await game_events.log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.COMBAT_END.name,
        details_json={
            "combat_id": combat_encounter.id,
            "winning_team": winning_team,
            "location_id": combat_encounter.location_id,
        },
        entity_ids_json=log_entity_ids_for_combat_end, # Use the corrected structure
        location_id=combat_encounter.location_id
    )

    logger.info(f"Guild {guild_id}: Combat {combat_encounter.id} end consequences handled, COMBAT_END event logged (ID: {combat_end_log_entry.id if combat_end_log_entry else 'N/A'}).")

    # 8. Call Quest System after COMBAT_END event is logged
    if combat_end_log_entry:
        from src.core.quest_system import handle_player_event_for_quest
        # Determine primary player/party context for quest check.
        # If multiple players/parties were involved, this might need refinement
        # or calling handle_player_event_for_quest for each relevant player/party.
        # For now, use the first player/party found in the involved lists if any.

        # This needs to consider all players and parties involved in the combat.
        # involved_player_ids_for_quest_check and involved_party_ids_for_quest_check collected earlier can be used.

        # If there are parties involved, process by party. If only individual players, process by player.
        # This assumes a party context is primary if present.
        # A more granular approach would be to iterate through all involved_player_ids_for_quest_check
        # and pass their individual party_id if they are in one, or just their player_id.

        if involved_party_ids_for_quest_check:
            for p_party_id in involved_party_ids_for_quest_check:
                # Find a representative player from this party who was in combat to pass as player_id hint, if needed by handle_player_event
                # This is optional, handle_player_event_for_quest should derive players from party_id.
                # representative_player_id = next((pid for pid in involved_player_ids_for_quest_check if (await session.get(Player, pid)).current_party_id == p_party_id), None)

                logger.info(f"Calling quest system for party {p_party_id} after combat {combat_encounter.id}")
                await handle_player_event_for_quest(
                    session=session, # Use the same session as it's part of the same transaction
                    guild_id=guild_id,
                    event_log_entry=combat_end_log_entry,
                    player_id=None, # Let party_id dictate the players
                    party_id=p_party_id
                )
        elif involved_player_ids_for_quest_check: # No parties, but individual players
             for p_player_id in involved_player_ids_for_quest_check:
                logger.info(f"Calling quest system for player {p_player_id} after combat {combat_encounter.id}")
                await handle_player_event_for_quest(
                    session=session,
                    guild_id=guild_id,
                    event_log_entry=combat_end_log_entry,
                    player_id=p_player_id,
                    party_id=None
                )
        else:
            logger.info(f"No specific players or parties identified for quest check after combat {combat_encounter.id}, though combat involved entities.")
    else:
        logger.error(f"Guild {guild_id}: COMBAT_END event was not logged for combat {combat_encounter.id}. Quest system trigger skipped.")



logger.info("Combat Cycle Manager module structure initialized.")

# Add to src/core/__init__.py:
# from . import combat_cycle_manager
# from .combat_cycle_manager import start_combat # (and later process_combat_turn)
