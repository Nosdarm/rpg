import logging
from typing import Tuple, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.relationship import Relationship # Assuming Relationship model is in src/models/relationship.py
from ..models.enums import RelationshipEntityType, EventType # Assuming enums are in src/models/enums.py
from .crud.crud_relationship import crud_relationship # Assuming crud_relationship is in src/core/crud/
from .rules import get_rule # Assuming get_rule is in src/core/rules.py
from .game_events import log_event # Assuming log_event is in src/core/game_events.py
from ..models import GuildConfig, Player, GeneratedNpc, GeneratedFaction # For type hinting if needed for entity_doing_id etc.

logger = logging.getLogger(__name__)

# TODO: Implement the API and helper functions as per the plan. # This TODO can be removed after implementation

async def update_relationship( # noqa C901
    session: AsyncSession,
    guild_id: int,
    entity_doing_id: int,
    entity_doing_type: RelationshipEntityType,
    target_entity_id: int,
    target_entity_type: RelationshipEntityType,
    event_type: str, # This should be a string key of EventType enum, e.g., "COMBAT_ACTION"
    event_details_log_id: int
) -> None:
    """
    Updates or creates a relationship value between two entities based on a game event
    and configurable rules.
    """
    logger.debug(
        f"Updating relationship for guild {guild_id} due to event {event_type} (log_id: {event_details_log_id}) "
        f"between {entity_doing_type.value}:{entity_doing_id} and {target_entity_type.value}:{target_entity_id}"
    )

    # 1. Determine the canonical pair for the primary entities involved
    c_entity1_id, c_entity1_type, c_entity2_id, c_entity2_type = _get_canonical_entity_pair(
        entity_doing_id, entity_doing_type, target_entity_id, target_entity_type
    )

    # 2. Get relationship change rules from RuleConfig
    # Example rule key: "relationship_rules:COMBAT_VICTORY"
    # Example rule structure: {"delta": 10, "min_val": -100, "max_val": 100, "relationship_type": "personal_feeling"}
    #                        or {"delta_formula": "event_specific_value * 2", ...} (more complex, for future)
    rule_key = f"relationship_rules:{event_type.upper()}" # Ensure event_type is upper for consistency
    relationship_rule = await get_rule(session, guild_id, rule_key)

    if not relationship_rule:
        logger.warning(
            f"No relationship rule found for guild {guild_id}, event_type '{event_type.upper()}'. "
            f"Rule key: '{rule_key}'. Skipping relationship update."
        )
        return

    # Validate rule structure (basic validation)
    if not isinstance(relationship_rule, dict) or "delta" not in relationship_rule:
        logger.error(
            f"Invalid relationship rule structure for guild {guild_id}, key '{rule_key}'. "
            f"Rule: {relationship_rule}. Expected dict with at least 'delta'. Skipping update."
        )
        return

    delta = relationship_rule.get("delta", 0)
    if not isinstance(delta, (int, float)): # Allow float for potential fractional changes, then cast to int
        logger.error(
            f"Invalid 'delta' in relationship rule for guild {guild_id}, key '{rule_key}'. "
            f"Delta: {delta}. Must be a number. Skipping update."
        )
        return

    delta = int(delta) # Ensure delta is an integer for relationship value

    min_val = relationship_rule.get("min_val", -100)  # Default min relationship value
    max_val = relationship_rule.get("max_val", 100)  # Default max relationship value
    # Default relationship type if not specified in rule, or use a global default
    # For now, let's assume the rule specifies it or we use a generic one.
    # The Relationship model has default="neutral" for relationship_type.
    # We should allow the rule to specify the type of relationship being affected.
    relationship_type_from_rule = relationship_rule.get("relationship_type", "personal_feeling")


    # 3. Find or create the Relationship record
    existing_relationship = await crud_relationship.get_relationship_between_entities(
        session=session, # FIX: db to session
        guild_id=guild_id,
        entity1_type=c_entity1_type,
        entity1_id=c_entity1_id,
        entity2_type=c_entity2_type,
        entity2_id=c_entity2_id,
        # Assuming get_relationship_between_entities also checks for relationship_type or we handle it here
        # For now, let's assume one numerical relationship per pair, or the rule defines which one.
        # If multiple relationship types can exist (e.g. 'personal', 'faction_standing'),
        # then get_relationship_between_entities would need relationship_type as an argument.
        # The current CRUDRelationship does not filter by relationship_type.
        # Let's refine this: we should fetch or create for a *specific* relationship_type.
    )

    # Refined search: if relationship_type is important, we might need to adjust crud or filter here.
    # For now, let's assume we find THE relationship, and its type is either default or set once.
    # Or, more robustly, a rule should define WHICH relationship type it's affecting.

    current_value = 0
    # original_relationship_type will be determined based on whether a relationship exists or is created.
    # If created, it's from the rule. If existing, it's from the existing record.

    if existing_relationship:
        current_value = existing_relationship.value
        original_relationship_type = existing_relationship.relationship_type # Use the type from the existing relationship

        # Optional: Log a warning if the rule's suggested type differs from the existing one.
        # This implies the rule might be intended for a different kind of relationship or a new one.
        if relationship_type_from_rule != original_relationship_type:
            logger.warning(
                f"Rule's suggested relationship_type ('{relationship_type_from_rule}') differs from "
                f"existing relationship_type ('{original_relationship_type}') for pair "
                f"({c_entity1_type.value}:{c_entity1_id}, {c_entity2_type.value}:{c_entity2_id}) "
                f"in guild {guild_id}. The existing relationship's type and value will be updated."
            )
            # Current logic updates the existing relationship. If the intent was to affect a *different typed*
            # relationship, the system would need to support multiple relationships between same pair but different types,
            # which means the UniqueConstraint on Relationship model would need to include `relationship_type`.
            # For now, we assume one relationship object per pair, and its type is taken from existing if available.
    else:
        # No existing relationship, so the type will be what the rule suggests (or default if rule doesn't specify)
        original_relationship_type = relationship_type_from_rule

    new_value = current_value + delta
    new_value = max(min_val, min(new_value, max_val)) # Clamp value

    if existing_relationship:
        # If new_value is same as old, and source_log_id is also same, then no actual change.
        if existing_relationship.value == new_value and existing_relationship.source_log_id == event_details_log_id:
            logger.debug(f"Relationship value and source_log_id for {c_entity1_type.value}:{c_entity1_id} and "
                         f"{c_entity2_type.value}:{c_entity2_id} unchanged. Skipping update and log.")
            return

        update_data = {
            "value": new_value,
            "source_log_id": event_details_log_id
        }
        # Potentially update relationship_type if rule implies it, but that's complex.
        # For now, type is set at creation and remains.
        # If rule has a "set_relationship_type" field, that could be used here.
        # existing_relationship.value = new_value
        # existing_relationship.source_log_id = event_details_log_id
        try:
            updated_rel = await crud_relationship.update(session=session, db_obj=existing_relationship, obj_in=update_data) # FIX: db to session
            if not updated_rel: # Should not happen if update is successful
                 logger.error(f"Failed to update relationship for pair ({c_entity1_id}, {c_entity2_id}) in guild {guild_id}")
                 return
            logger.info(
                f"Updated relationship for guild {guild_id}: {c_entity1_type.value}:{c_entity1_id} "
                f"<-> {c_entity2_type.value}:{c_entity2_id} (type: {updated_rel.relationship_type}) "
                f"from {current_value} to {new_value} (delta: {delta}). Log ID: {event_details_log_id}"
            )
        except Exception as e:
            logger.error(f"Error updating relationship for pair ({c_entity1_id}, {c_entity2_id}) in guild {guild_id}: {e}")
            await session.rollback() # Rollback on error within this logical unit of work
            raise # Re-raise after logging and rollback
    else:
        create_data = {
            "guild_id": guild_id,
            "entity1_id": c_entity1_id,
            "entity1_type": c_entity1_type,
            "entity2_id": c_entity2_id,
            "entity2_type": c_entity2_type,
            "value": new_value,
            "relationship_type": relationship_type_from_rule, # Use type from rule for new relationships
            "source_log_id": event_details_log_id,
        }
        try:
            # Use the standard CRUDBase.create method.
            # CRUDBase.create handles guild_id if it's part of obj_in and model supports it,
            # or if passed as a direct parameter to CRUDBase.create (which it is not here for obj_in,
            # but guild_id is already in create_data which is good).
            created_rel = await crud_relationship.create(session=session, obj_in=create_data)
            # create_with_guild_id might not be standard. Assuming it's like crud_relationship.create(db=session, obj_in=Relationship(**create_data))
            # Let's use the standard CRUDBase.create
            # new_rel_obj = Relationship(**create_data) # This would be if obj_in was a Pydantic model
            # For now, assume create_data is a dict suitable for Relationship model init
            # created_rel = await crud_relationship.create(db=session, obj_in=new_rel_obj)
            # Let's use the direct model creation then add and flush
            new_relationship_obj = Relationship(**create_data)
            session.add(new_relationship_obj)
            await session.flush()
            await session.refresh(new_relationship_obj)
            created_rel = new_relationship_obj

            logger.info(
                f"Created new relationship for guild {guild_id}: {c_entity1_type.value}:{c_entity1_id} "
                f"<-> {c_entity2_type.value}:{c_entity2_id} (type: {created_rel.relationship_type}) "
                f"set to {new_value} (delta from 0: {delta}). Log ID: {event_details_log_id}"
            )
        except Exception as e:
            logger.error(f"Error creating relationship for pair ({c_entity1_id}, {c_entity2_id}) in guild {guild_id}: {e}")
            await session.rollback()
            raise

    # 4. Log the relationship change event
    log_details = {
        "entity1_id": c_entity1_id,
        "entity1_type": c_entity1_type.value, # Log enum value
        "entity2_id": c_entity2_id,
        "entity2_type": c_entity2_type.value, # Log enum value
        "relationship_type": original_relationship_type, # The type of the relationship that was affected
        "old_value": current_value if existing_relationship else 0, # Old value was 0 if newly created
        "new_value": new_value,
        "change_amount": delta,
        "original_event_type": event_type,
        "original_event_log_id": event_details_log_id,
        "rule_key_used": rule_key # For traceability
    }

    # Determine involved player/party for the log_event function signature
    # This is tricky as update_relationship is generic.
    # The caller of update_relationship (e.g. combat system, quest system)
    # should ideally provide the primary player/party context if available.
    # For now, we'll pass None and rely on entity_ids_json in log_event.

    # entity_ids_json should reflect the entities whose relationship changed.
    # And potentially the "actor" of the original event.
    # For RELATIONSHIP_CHANGE, the core entities are c_entity1 and c_entity2.
    # We can also include entity_doing if it's different.

    involved_entities_for_log = {
        c_entity1_type.value.lower() + "s": [c_entity1_id], # e.g. "players": [id]
        c_entity2_type.value.lower() + "s": [c_entity2_id]
    }
    # Add entity_doing if it's not one of the canonical pair (though it should be)
    # This structure { "players": [...], "npcs": [...] } is expected by log_event's entity_ids_json
    # We need to ensure the keys are pluralized correctly if using this dynamic approach.
    # A simpler way: list of dicts: [{"type": type.value, "id": id}, ...]
    # However, log_event expects specific keys like "players", "parties".

    # Let's prepare entity_ids_json more carefully for log_event
    entity_ids_for_log_event = {}

    def add_to_log_entities(ent_id, ent_type):
        key_name = ent_type.value.lower() + "s" # e.g. "players"
        if key_name not in entity_ids_for_log_event:
            entity_ids_for_log_event[key_name] = []
        if ent_id not in entity_ids_for_log_event[key_name]:
            entity_ids_for_log_event[key_name].append(ent_id)

    add_to_log_entities(c_entity1_id, c_entity1_type)
    add_to_log_entities(c_entity2_id, c_entity2_type)
    # Also add the original actor of the event if it's not one of the pair (though it usually is)
    if not ((entity_doing_id == c_entity1_id and entity_doing_type == c_entity1_type) or \
            (entity_doing_id == c_entity2_id and entity_doing_type == c_entity2_type)):
        add_to_log_entities(entity_doing_id, entity_doing_type)


    await log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.RELATIONSHIP_CHANGE.value, # Use enum's value
        details_json=log_details,
        entity_ids_json=entity_ids_for_log_event
        # player_id and party_id in log_event are somewhat legacy; entity_ids_json is more flexible.
    )
    logger.debug(f"RELATIONSHIP_CHANGE event logged for guild {guild_id}.")

    # TODO: Consider if this function should return the updated/created Relationship object. For now, None.
    # TODO: Advanced: Handle rules that might trigger changes between factions of entities, not just direct entities.
    #       This would involve fetching faction memberships and applying another layer of rules.
    #       Example: Player P attacks NPC N of Faction F. P vs N relationship changes. P's Faction vs Faction F might also change.


def _get_canonical_entity_pair(
    e1_id: int, e1_type: RelationshipEntityType,
    e2_id: int, e2_type: RelationshipEntityType
) -> Tuple[int, RelationshipEntityType, int, RelationshipEntityType]:
    """
    Orders a pair of entities canonically to ensure consistent storage and retrieval.
    Order by entity_type.value (string representing the enum member name) first,
    then by entity_id if types are the same.
    """
    # Ensure we are comparing enum string values if types are different
    if e1_type.value < e2_type.value:
        return e1_id, e1_type, e2_id, e2_type
    if e1_type.value > e2_type.value:
        return e2_id, e2_type, e1_id, e1_type

    # Types are the same, compare by ID
    if e1_id < e2_id:
        return e1_id, e1_type, e2_id, e2_type
    # else (e1_id >= e2_id, including equality though IDs should be unique for same type)
    return e2_id, e2_type, e1_id, e1_type


logger.info("Relationship system module implementation updated.")
