# src/core/npc_combat_strategy.py

from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional, Union

from src.models.generated_npc import GeneratedNpc
from src.models.relationship import Relationship # Added import
from src.models.combat_encounter import CombatEncounter
from src.models.player import Player
from src.models.enums import CombatParticipantType as EntityType, RelationshipEntityType # FIX: Added RelationshipEntityType
from src.core.crud import crud_npc, crud_combat_encounter, crud_player, crud_relationship
from src.core.rules import get_rule

# Вспомогательные функции для загрузки данных

async def _get_npc_data(session: AsyncSession, npc_id: int, guild_id: int) -> Optional[GeneratedNpc]:
    """
    Loads NPC data from the database.
    """
    return await crud_npc.npc_crud.get_by_id_and_guild(session=session, id=npc_id, guild_id=guild_id) # FIX: db to session

async def _get_combat_encounter_data(session: AsyncSession, combat_instance_id: int, guild_id: int) -> Optional[CombatEncounter]:
    """
    Loads Combat Encounter data from the database.
    """
    return await crud_combat_encounter.combat_encounter_crud.get_by_id_and_guild(session=session, id=combat_instance_id, guild_id=guild_id) # FIX: db to session

async def _get_participant_entity(session: AsyncSession, participant_info: Dict[str, Any], guild_id: int) -> Optional[Union[Player, GeneratedNpc]]:
    """
    Loads a specific combat participant entity (Player or GeneratedNpc) from the database.
    participant_info is expected to be an entry from CombatEncounter.participants_json
    e.g. {"id": 1, "type": "player", "hp": 100, ...}
    """
    entity_id = participant_info.get("id")
    entity_type_str = participant_info.get("type")

    if not entity_id or not entity_type_str:
        return None

    try:
        entity_type = EntityType(entity_type_str)
    except ValueError:
        return None # Unknown entity type

    if entity_type == EntityType.PLAYER:
        return await crud_player.player_crud.get_by_id_and_guild(session=session, id=entity_id, guild_id=guild_id) # FIX: db to session
    elif entity_type == EntityType.NPC:
        return await crud_npc.npc_crud.get_by_id_and_guild(session=session, id=entity_id, guild_id=guild_id) # FIX: db to session

    return None

async def _get_relationship_value(
    session: AsyncSession,
    guild_id: int,
    entity1_type: RelationshipEntityType, # FIX: Changed to RelationshipEntityType
    entity1_id: int,
    entity2_type: RelationshipEntityType, # FIX: Changed to RelationshipEntityType
    entity2_id: int
) -> Optional[int]:
    """
    Retrieves the relationship value between two entities.
    Returns None if no relationship is found.
    """
    # The crud_relationship.get_relationship_between_entities already expects RelationshipEntityType
    relationship = await crud_relationship.get_relationship_between_entities(
        session=session,
        guild_id=guild_id,
        entity1_type=entity1_type, # This is now correctly RelationshipEntityType
        entity1_id=entity1_id,
        entity2_type=entity2_type, # This is now correctly RelationshipEntityType
        entity2_id=entity2_id
    )
    return relationship.value if relationship else None

async def _get_npc_ai_rules(
    session: AsyncSession,
    guild_id: int,
    actor_npc: GeneratedNpc,
    combat_encounter: CombatEncounter,
    actor_hidden_relationships: Optional[List[Relationship]] = None # Новый параметр
) -> Dict[str, Any]:
    """
    Loads and compiles AI behavior rules for the given NPC from RuleConfig.
    Includes standard relationship influences and specific hidden relationship effects.
    This is a placeholder implementation. Detailed logic will depend on RuleConfig structure.
    """
    base_rules_key = "ai_behavior:npc_default_strategy"
    npc_rules = await get_rule(session=session, guild_id=guild_id, key=base_rules_key, default={})

    default_strategy = {
        "target_selection": {
            "priority_order": ["lowest_hp_percentage", "highest_threat_score"],
            "hostility_rules": {"default": "attack_players_and_hostile_npcs"},
            "threat_factors": {"damage_dealt_to_self_factor": 1.5, "is_healer_factor": 1.2, "low_hp_target_bonus": 0.2}
        },
        "action_selection": {
            "offensive_bias": 0.75,
            "abilities_priority": [],
            "resource_thresholds": {
                "self_hp_below_for_heal_ability": 0.4,
                "target_hp_above_for_execute_ability": 0.8
            },
            "prefer_effective_actions": True
        },
        "simulation": {
            "enabled": False,
            "required_hit_chance_threshold": 0.5,
            "min_expected_damage_ratio_vs_target_hp": 0.05
        },
        "personality_modifiers": {
            "aggressive": {"offensive_bias_add": 0.2, "threat_factors_multiplier": {"damage_dealt_to_self_factor": 1.2}},
            "cautious": {"offensive_bias_subtract": 0.2, "resource_thresholds_modifier": {"self_hp_below_for_heal_ability": 0.1}}
        }
    }

    if not npc_rules:
        npc_rules = default_strategy
    else:
        for key, value in default_strategy.items():
            if key not in npc_rules:
                npc_rules[key] = value
            elif isinstance(npc_rules[key], dict) and isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if sub_key not in npc_rules[key]:
                        npc_rules[key][sub_key] = sub_value
            elif isinstance(npc_rules[key], list) and isinstance(value, list) and not npc_rules[key]: # only overwrite if current list is empty
                 npc_rules[key] = value

    actor_props = actor_npc.properties_json or {}
    actor_ai_meta = actor_npc.ai_metadata_json or {}

    # Merge relationship influence rules (standard relationships)
    rel_influence_key = "relationship_influence:npc_combat:behavior"
    rel_influence_rules_specific = await get_rule(session=session, guild_id=guild_id, key=rel_influence_key, default=None)
    default_rel_influence_rules = {
        "enabled": True, "hostility_threshold_modifier_formula": "-(relationship_value / 10)",
        "target_score_modifier_formula": "-(relationship_value * 0.2)",
        "action_choice": {
            "friendly_positive_threshold": 50, "hostile_negative_threshold": -50,
            "actions_if_friendly": [], "actions_if_hostile": []
        }
    }
    final_rel_influence_rules = default_rel_influence_rules.copy()
    if rel_influence_rules_specific and isinstance(rel_influence_rules_specific, dict):
        for key, value in rel_influence_rules_specific.items():
            if isinstance(value, dict) and isinstance(final_rel_influence_rules.get(key), dict):
                final_rel_influence_rules[key].update(value)
            else:
                final_rel_influence_rules[key] = value
    if "relationship_influence" not in npc_rules: npc_rules["relationship_influence"] = {}
    if "npc_combat" not in npc_rules["relationship_influence"]: npc_rules["relationship_influence"]["npc_combat"] = {}
    npc_rules["relationship_influence"]["npc_combat"]["behavior"] = final_rel_influence_rules

    # Load and parse hidden relationship combat effects
    # This part is moved from the original plan to be inside _get_npc_ai_rules
    # It assumes actor_hidden_relationships is passed to this function.
    # The plan was to pass actor_hidden_relationships to _get_npc_ai_rules,
    # This change IS NOW REFLECTED in the function signature.
    # The parameter `actor_hidden_relationships` is now directly available.

    if actor_hidden_relationships: # Use the passed parameter directly
        if "parsed_hidden_relationship_combat_effects" not in npc_rules:
             npc_rules["parsed_hidden_relationship_combat_effects"] = [] # Ensure list exists
        for rel in actor_hidden_relationships:
            # rel.relationship_type can be "secret_positive_to_faction:some_id"
            # Base type for rule lookup, e.g., "secret_positive_to_faction"
            base_rel_type_for_rule = rel.relationship_type.split(':')[0]

            # Attempt to load rule by exact relationship type string
            rule_key_exact = f"hidden_relationship_effects:npc_combat:{rel.relationship_type}"
            specific_hidden_rule = await get_rule(session=session, guild_id=guild_id, key=rule_key_exact, default=None) # Already session

            # Attempt to load rule by base relationship type (e.g. "secret_positive_to_faction")
            # This allows generic rules for categories of hidden relationships.
            rule_key_generic = f"hidden_relationship_effects:npc_combat:{base_rel_type_for_rule}"
            generic_hidden_rule = await get_rule(session=session, guild_id=guild_id, key=rule_key_generic, default=None) # Already session

            chosen_rule_data = None
            # Prioritize specific rule if enabled, then generic if enabled
            if isinstance(specific_hidden_rule, dict) and specific_hidden_rule.get("enabled", False):
                chosen_rule_data = specific_hidden_rule
            elif isinstance(generic_hidden_rule, dict) and generic_hidden_rule.get("enabled", False):
                chosen_rule_data = generic_hidden_rule

            if chosen_rule_data: # chosen_rule_data is a dict here
                # Ensure the list exists before appending
                if "parsed_hidden_relationship_combat_effects" not in npc_rules or not isinstance(npc_rules["parsed_hidden_relationship_combat_effects"], list):
                    npc_rules["parsed_hidden_relationship_combat_effects"] = []

                npc_rules["parsed_hidden_relationship_combat_effects"].append({
                    "rule_data": chosen_rule_data,
                    "applies_to_relationship": { # Store context of the relationship this rule applies to
                        "type": rel.relationship_type, # Full type, e.g. "secret_positive_to_faction:faction_id_123"
                        "value": rel.value,
                        "target_entity_type": rel.entity2_type.value, # The other entity in this relationship
                        "target_entity_id": rel.entity2_id
                    }
                })

        # Sort collected hidden relationship effects by priority (higher priority first)
        hidden_effects_list = npc_rules.get("parsed_hidden_relationship_combat_effects")
        if isinstance(hidden_effects_list, list): # Check it's a list before sort
            hidden_effects_list.sort(
                key=lambda x: x.get("rule_data", {}).get("priority", 0), reverse=True
            )
    # End of loading hidden relationship effects

    npc_personality = actor_props.get("personality", actor_ai_meta.get("personality"))
    personality_modifiers_rules = npc_rules.get("personality_modifiers", {})
    if npc_personality and isinstance(personality_modifiers_rules, dict) and npc_personality in personality_modifiers_rules:
        mods = personality_modifiers_rules[npc_personality]
        action_selection_rules = npc_rules.get("action_selection", {})
        if not isinstance(action_selection_rules, dict): action_selection_rules = {} # ensure dict

        current_bias = action_selection_rules.get("offensive_bias", default_strategy["action_selection"]["offensive_bias"])

        if isinstance(mods, dict) and "offensive_bias_add" in mods:
            current_bias = min(1.0, current_bias + mods["offensive_bias_add"])
        if "offensive_bias_subtract" in mods:
            current_bias = max(0.0, current_bias - mods["offensive_bias_subtract"])

        if "action_selection" not in npc_rules: npc_rules["action_selection"] = {}
        npc_rules["action_selection"]["offensive_bias"] = current_bias

        # Example for modifying nested structures like resource_thresholds
        if isinstance(mods, dict) and "resource_thresholds_modifier" in mods:
            if "resource_thresholds" not in action_selection_rules: # Use already defined action_selection_rules
                action_selection_rules["resource_thresholds"] = {}

            resource_threshold_mods = mods["resource_thresholds_modifier"]
            if isinstance(resource_threshold_mods, dict):
                for item, val_mod in resource_threshold_mods.items():
                    base_val = default_strategy.get("action_selection", {}).get("resource_thresholds", {}).get(item,0)
                    # Ensure action_selection_rules["resource_thresholds"] is a dict
                    if not isinstance(action_selection_rules.get("resource_thresholds"), dict):
                        action_selection_rules["resource_thresholds"] = {}
                    action_selection_rules["resource_thresholds"][item] = base_val + val_mod
            npc_rules["action_selection"] = action_selection_rules # Assign back if it was created/modified


    return npc_rules

# --- Functions for Target Selection ---

async def _is_hostile(
    session: AsyncSession,
    guild_id: int,
    actor_npc: GeneratedNpc,
    target_participant_info: Dict[str, Any], # A single participant entry from combat_encounter.participants_json
    target_entity: Union[Player, GeneratedNpc], # The actual Player or GeneratedNpc object for the target
    ai_rules: Dict[str, Any]
) -> bool:
    """
    Determines if the target is hostile to the actor_npc based on rules and relationships.
    """
    # Basic hostility: players are generally hostile to NPCs in combat unless specified otherwise.
    # NPCs vs NPCs: based on faction, relationships, or specific encounter rules.

    target_selection_rules = ai_rules.get("target_selection", {})
    if not isinstance(target_selection_rules, dict): target_selection_rules = {} # Ensure dict

    hostility_config = target_selection_rules.get("hostility_rules", {})
    if not isinstance(hostility_config, dict): hostility_config = {} # Ensure dict
    default_hostility_rule = hostility_config.get("default", "attack_players_and_hostile_npcs")

    actor_props = actor_npc.properties_json if actor_npc.properties_json is not None else {}
    actor_faction = actor_props.get("faction_id")

    target_faction = None
    if isinstance(target_entity, GeneratedNpc):
        target_entity_props = target_entity.properties_json if target_entity.properties_json is not None else {}
        target_faction = target_entity_props.get("faction_id")

    # 1. Check explicit relationship
    # Ensure target_participant_info has 'type' and 'id' before calling EntityType or using them
    target_participant_type_str = target_participant_info.get("type")
    target_participant_id = target_participant_info.get("id")

    relationship_val = None
    if target_participant_type_str and target_participant_id is not None:
        try:
            target_rel_entity_type = EntityType(target_participant_type_str) # This is CombatParticipantType
            # Map to RelationshipEntityType
            mapped_target_rel_type = None
            if target_rel_entity_type == EntityType.PLAYER:
                mapped_target_rel_type = RelationshipEntityType.PLAYER
            elif target_rel_entity_type == EntityType.NPC: # This is CombatParticipantType.NPC
                mapped_target_rel_type = RelationshipEntityType.GENERATED_NPC

            if mapped_target_rel_type:
                relationship_val = await _get_relationship_value(
                    session, guild_id,
                    RelationshipEntityType.GENERATED_NPC, actor_npc.id, # Actor is always GeneratedNpc here
                    mapped_target_rel_type, target_participant_id
                )
        except ValueError:
            pass # Invalid entity type string

    if relationship_val is not None:
        base_hostile_threshold = hostility_config.get("relationship_hostile_threshold", -50)
        base_friendly_threshold = hostility_config.get("relationship_friendly_threshold", 50)

        rel_influence_rules = ai_rules.get("relationship_influence", {})
        if not isinstance(rel_influence_rules, dict): rel_influence_rules = {}
        npc_combat_rules = rel_influence_rules.get("npc_combat", {})
        if not isinstance(npc_combat_rules, dict): npc_combat_rules = {}
        behavior_rules = npc_combat_rules.get("behavior", {})
        if not isinstance(behavior_rules, dict): behavior_rules = {}

        final_hostile_threshold = base_hostile_threshold
        final_friendly_threshold = base_friendly_threshold

        if behavior_rules.get("enabled", False):
            formula = behavior_rules.get("hostility_threshold_modifier_formula")
            if formula and isinstance(formula, str):
                try:
                    hostility_bias_mod = int(eval(formula, {"__builtins__": {}}, {"relationship_value": relationship_val}))
                    final_hostile_threshold += hostility_bias_mod
                    final_friendly_threshold -= hostility_bias_mod
                except Exception as e:
                    pass

        if relationship_val <= final_hostile_threshold:
            return True
        if relationship_val >= final_friendly_threshold:
            return False

    if actor_faction and target_faction and actor_faction == target_faction:
        if hostility_config.get("same_faction_is_friendly", True):
            return False

    # Check for hostility override from hidden relationship effects
    parsed_hidden_effects = ai_rules.get("parsed_hidden_relationship_combat_effects")
    if isinstance(parsed_hidden_effects, list): # Ensure it's a list
        for hidden_effect_entry in parsed_hidden_effects:
            if not isinstance(hidden_effect_entry, dict): continue
            rule_data = hidden_effect_entry.get("rule_data", {})
            if not isinstance(rule_data, dict): continue
            rel_details = hidden_effect_entry.get("applies_to_relationship", {})
            if not isinstance(rel_details, dict): continue

            override_rules = rule_data.get("hostility_override", {})
            if not isinstance(override_rules, dict): continue

            if override_rules.get("if_target_matches_relationship", False):
                # Ensure target_participant_info has 'type' and 'id' before using
                current_target_type_str = target_participant_info.get("type")
                current_target_id = target_participant_info.get("id")

                if current_target_type_str and current_target_id is not None:
                    try:
                        current_target_type_enum_val = EntityType(current_target_type_str).value
                        if rel_details.get("target_entity_type") == current_target_type_enum_val and \
                           rel_details.get("target_entity_id") == current_target_id:

                            condition_formula = override_rules.get("condition_formula", "True")
                            condition_met = False
                            try:
                                condition_met = eval(condition_formula, {"__builtins__": {}}, {"value": rel_details.get("value")})
                            except Exception:
                                pass

                            if condition_met:
                                new_status_str = override_rules.get("new_hostility_status")
                                if new_status_str == "friendly": return False
                                if new_status_str == "hostile": return True
                                if new_status_str == "neutral": return False
                    except ValueError: # Invalid current_target_type_str
                        pass


    # 3. Default rule application
    if default_hostility_rule == "attack_players_and_hostile_npcs":
        if target_participant_info.get("type") == EntityType.PLAYER.value:
            return True
        if target_participant_info.get("type") == EntityType.NPC.value:
            return True # Simplified: consider other NPCs hostile by default if not friendly
    elif default_hostility_rule == "attack_all_others":
        return True

    return False # Default to non-hostile if no rule matches

async def _get_potential_targets(
    session: AsyncSession,
    actor_npc: GeneratedNpc,
    combat_encounter: CombatEncounter, # Still needed for context, though participants_json not directly used
    ai_rules: Dict[str, Any],
    guild_id: int,
    participants_list: List[Dict[str, Any]] # Added parameter
) -> List[Dict[str, Union[Player, GeneratedNpc, Dict[str, Any]]]]:
    """
    Identifies potential hostile targets for the actor_npc from the combat encounter.
    Returns a list of dictionaries, each containing the entity object and its combat_data.
    Uses the provided participants_list instead of accessing combat_encounter.participants_json directly.
    """
    potential_targets = []
    # participants_list is already checked to be a list in the caller
    for participant_info in participants_list:
        if not isinstance(participant_info, dict): # Ensure each item is a dict
            # TODO: Log this malformed participant entry
            continue

        # Skip self
        # Use .get for safety, though id and type should ideally always be present
        if participant_info.get("id") == actor_npc.id and participant_info.get("type") == EntityType.NPC.value: # EntityType.NPC is CombatParticipantType.NPC
            continue

        # Skip defeated participants (current HP is in participant_info)
        if participant_info.get("current_hp", 0) <= 0: # Changed "hp" to "current_hp" for consistency with other parts
            continue

        target_entity = await _get_participant_entity(session, participant_info, guild_id)
        if not target_entity:
            # Log error: could not load participant entity
            continue

        is_target_hostile = await _is_hostile(session, guild_id, actor_npc, participant_info, target_entity, ai_rules)
        if is_target_hostile:
            potential_targets.append({
                "entity": target_entity,
                "combat_data": participant_info # This has current HP, status effects in combat, etc.
            })

    return potential_targets

async def _calculate_target_score(
    session: AsyncSession,
    guild_id: int,
    actor_npc: GeneratedNpc,
    target_info: Dict[str, Union[Player, GeneratedNpc, Dict[str, Any]]], # Contains 'entity' and 'combat_data'
    priority_metric: str,
    ai_rules: Dict[str, Any],
    combat_encounter: CombatEncounter # For things like combat log to calculate threat
) -> float:
    """
    Calculates a score for a target based on a given priority metric.
    Lower scores are generally better for "lowest_X" metrics, higher for "highest_X".
    This function will return values where "better" depends on the metric's nature.
    The caller (_select_target) will know whether to min or max.
    """
    target_entity_model_union = target_info.get("entity")
    target_combat_data = target_info.get("combat_data")

    if not isinstance(target_entity_model_union, (Player, GeneratedNpc)):
        return 0.0

    # Now target_entity_model_union is either Player or GeneratedNpc
    target_entity_model: Union[Player, GeneratedNpc] = target_entity_model_union

    if not isinstance(target_combat_data, dict):
        return 0.0


    score = 0.0
    current_hp = target_combat_data.get("current_hp", 0) # Use current_hp consistently

    if priority_metric == "lowest_hp_percentage":
        max_hp = 1
        if isinstance(target_entity_model, GeneratedNpc):
            target_props = target_entity_model.properties_json if target_entity_model.properties_json else {}
            base_stats = target_props.get("stats", {})
            max_hp = base_stats.get("hp", current_hp if current_hp > 0 else 1) # Max HP from base stats
        elif isinstance(target_entity_model, Player): # Player's max_hp might be in combat_data or model
            max_hp = target_combat_data.get("max_hp", getattr(target_entity_model, 'max_hp', current_hp if current_hp > 0 else 1))


        if max_hp <= 0: max_hp = 1
        score = (current_hp / max_hp) * 100 if max_hp > 0 else 0
        return score

    elif priority_metric == "highest_hp_percentage":
        max_hp = 1
        if isinstance(target_entity_model, GeneratedNpc):
            target_props = target_entity_model.properties_json if target_entity_model.properties_json else {}
            base_stats = target_props.get("stats", {})
            max_hp = base_stats.get("hp", current_hp if current_hp > 0 else 1)
        elif isinstance(target_entity_model, Player):
            max_hp = target_combat_data.get("max_hp", getattr(target_entity_model, 'max_hp', current_hp if current_hp > 0 else 1))


        if max_hp <= 0: max_hp = 1
        score = (current_hp / max_hp) * 100 if max_hp > 0 else 0
        return score

    elif priority_metric == "lowest_absolute_hp":
        score = current_hp
        return score

    elif priority_metric == "highest_absolute_hp":
        score = current_hp
        return score

    elif priority_metric == "highest_threat_score":
        threat = 0.0
        target_selection_rules = ai_rules.get("target_selection", {})
        if not isinstance(target_selection_rules, dict): target_selection_rules = {}
        threat_factors = target_selection_rules.get("threat_factors", {})
        if not isinstance(threat_factors, dict): threat_factors = {}

        threat += target_combat_data.get("threat_generated_towards_actor", 0.0) * threat_factors.get("damage_dealt_to_self_factor", 1.0)

        if isinstance(target_entity_model, GeneratedNpc):
            target_props = target_entity_model.properties_json if target_entity_model.properties_json else {}
            target_roles = target_props.get("roles", [])
            if isinstance(target_roles, list) and "healer" in target_roles and threat_factors.get("is_healer_factor"):
                threat += 100 * threat_factors.get("is_healer_factor", 0.0) # ensure factor is float

        if threat_factors.get("low_hp_target_bonus"):
            max_hp = 1
            if isinstance(target_entity_model, GeneratedNpc):
                target_props = target_entity_model.properties_json if target_entity_model.properties_json else {}
                target_stats = target_props.get("stats", {})
                max_hp = target_stats.get("hp", current_hp if current_hp > 0 else 1)
            elif isinstance(target_entity_model, Player):
                max_hp = target_combat_data.get("max_hp", getattr(target_entity_model, 'max_hp', current_hp if current_hp > 0 else 1))


            if max_hp <=0: max_hp = 1
            hp_percent = (current_hp / max_hp) if max_hp > 0 else 0
            if hp_percent < 0.3:
                threat += 50 * threat_factors.get("low_hp_target_bonus", 0.0) # ensure factor is float

        target_participant_type_str = target_combat_data.get("type")
        target_participant_id = target_combat_data.get("id")
        relationship_val = None

        if target_participant_type_str and target_participant_id is not None:
            try:
                target_rel_entity_type = EntityType(target_participant_type_str)
                mapped_target_rel_type = None
                if target_rel_entity_type == EntityType.PLAYER:
                    mapped_target_rel_type = RelationshipEntityType.PLAYER
                elif target_rel_entity_type == EntityType.NPC:
                    mapped_target_rel_type = RelationshipEntityType.GENERATED_NPC

                if mapped_target_rel_type:
                    relationship_val = await _get_relationship_value(
                        session, guild_id,
                        RelationshipEntityType.GENERATED_NPC, actor_npc.id,
                        mapped_target_rel_type, target_participant_id
                    )
            except ValueError:
                pass


        if relationship_val is not None:
            rel_influence_rules = ai_rules.get("relationship_influence", {})
            if not isinstance(rel_influence_rules, dict): rel_influence_rules = {}
            npc_combat_rules = rel_influence_rules.get("npc_combat", {})
            if not isinstance(npc_combat_rules, dict): npc_combat_rules = {}
            behavior_rules = npc_combat_rules.get("behavior", {})
            if not isinstance(behavior_rules, dict): behavior_rules = {}

            if behavior_rules.get("enabled", False):
                formula = behavior_rules.get("target_score_modifier_formula")
                if formula and isinstance(formula, str):
                    try:
                        adjustment = float(eval(formula, {"__builtins__": {}}, {"relationship_value": relationship_val}))
                        threat += adjustment
                    except Exception as e:
                        pass
            elif threat_factors.get("relationship_threat_modifier"):
                if relationship_val < -50 :
                     threat += 75 * threat_factors.get("relationship_threat_modifier", 0.0)

        parsed_hidden_effects = ai_rules.get("parsed_hidden_relationship_combat_effects")
        if isinstance(parsed_hidden_effects, list):
            for hidden_effect_entry in parsed_hidden_effects:
                if not isinstance(hidden_effect_entry, dict): continue
                rule_data = hidden_effect_entry.get("rule_data", {})
                if not isinstance(rule_data, dict): continue
                rel_details = hidden_effect_entry.get("applies_to_relationship", {})
                if not isinstance(rel_details, dict): continue

                current_target_type_str = target_combat_data.get("type")
                current_target_id = target_combat_data.get("id")

                if current_target_type_str and current_target_id is not None:
                    try:
                        current_target_type_enum_val = EntityType(current_target_type_str).value
                        if rel_details.get("target_entity_type") == current_target_type_enum_val and \
                           rel_details.get("target_entity_id") == current_target_id:
                            formula = rule_data.get("target_score_modifier_formula")
                            if formula and isinstance(formula, str):
                                try: # INNER TRY
                                    adjustment = float(eval(formula, {"__builtins__": {}}, {"value": rel_details.get("value"), "current_score": threat}))
                                    threat += adjustment
                                except Exception as e: # Belongs to INNER TRY
                                    pass # Body for inner except (e.g., log the error or ignore)
                            # Removed misplaced 'pass' that was here
                    except (ValueError, TypeError, Exception) as e: # For OUTER TRY
                        # Catching ValueError from EntityType, TypeError if types are wrong, or other eval errors
                        pass # Or log: logger.warning(f"Skipping hidden effect modifier due to error: {e}")
        return threat # Higher is better

    # TODO: Implement other metrics like "closest_target", "random", "specific_role_focus"

    return score # Default score if metric not handled


async def _select_target(
    session: AsyncSession,
    guild_id: int,
    actor_npc: GeneratedNpc,
    potential_targets: List[Dict[str, Union[Player, GeneratedNpc, Dict[str, Any]]]],
    ai_rules: Dict[str, Any],
    combat_encounter: CombatEncounter
) -> Optional[Dict[str, Union[Player, GeneratedNpc, Dict[str, Any]]]]:
    """
    Selects a specific target from the list of potential_targets based on AI rules.
    """
    if not potential_targets:
        return None

    priority_order = ai_rules.get("target_selection", {}).get("priority_order", ["lowest_hp_percentage"])

    # Apply tie-breaking or filtering by relationship first if configured
    # relationship_filter_rules = ai_rules.get("target_selection", {}).get("relationship_filter", {})
    # if relationship_filter_rules.get("enabled"):
    #     min_val = relationship_filter_rules.get("min_relationship_value_to_avoid", -1000) # Don't attack if relationship is above this
    #     # Filter out targets actor_npc might not want to attack based on good relationship
    #     filtered_targets_by_rel = []
    #     for target_info in potential_targets:
    #         rel_val = await _get_relationship_value(session, guild_id, EntityType.NPC, actor_npc.id, EntityType(target_info["combat_data"]["type"]), target_info["combat_data"]["id"])
    #         if rel_val is None or rel_val < min_val:
    #             filtered_targets_by_rel.append(target_info)
    #     if filtered_targets_by_rel: # Only use this filter if it doesn't remove all targets
    #         potential_targets = filtered_targets_by_rel
    #     elif not potential_targets and relationship_filter_rules.get("attack_anyone_if_no_preferred_non_friends", True):
    #          pass # Original potential_targets list is used

    best_target = None

    for metric in priority_order:
        if not potential_targets: break # Should not happen if initial list wasn't empty

        scored_targets = []
        for target_info in potential_targets:
            score = await _calculate_target_score(session, guild_id, actor_npc, target_info, metric, ai_rules, combat_encounter)
            scored_targets.append({"target_info": target_info, "score": score})

        if not scored_targets:
            continue # Should not happen if potential_targets had items

        # Determine if lower score is better for this metric
        # Convention: "lowest_" prefix means lower is better. Otherwise, higher is better.
        if metric.startswith("lowest_"):
            scored_targets.sort(key=lambda x: x["score"])
        else: # "highest_" or other metrics
            scored_targets.sort(key=lambda x: x["score"], reverse=True)

        # The best target according to this metric is the first one after sorting.
        # For now, we take the top one from the first metric that yields results.
        # A more advanced system could take top N, then apply next metric as tie-breaker.
        if scored_targets:
            best_target = scored_targets[0]["target_info"]
            # For simplicity, use the first metric that successfully selects a target.
            # A more robust system might filter the list of potential_targets at each step.
            # E.g., keep only the top N (e.g., 3) targets from this metric for the next metric.
            # For now, if a metric gives a best target, we use it.
            return best_target


    # Fallback if no metric yields a clear best target (e.g. all scores are equal, or list becomes empty)
    # or if priority_order was empty.
    if not best_target and potential_targets:
        # Random choice as a last resort if not None
        import random
        return random.choice(potential_targets)

    return best_target

# --- End of Target Selection ---

# --- Functions for Action Selection ---

def _get_available_abilities(
    actor_npc: GeneratedNpc,
    actor_combat_data: Dict[str, Any], # From CombatEncounter.participants_json for the actor
    ai_rules: Dict[str, Any] # For resource thresholds etc.
) -> List[Dict[str, Any]]:
    """
    Gets a list of abilities available for the NPC to use, considering resources and cooldowns.
    Each ability in the list is a dictionary from actor_npc.properties_json['abilities'].
    It now also adds a 'category' field to the ability dictionary if defined in ability_props.
    """
    available_abilities = []
    # Use direct attribute access for properties_json, ensure it's a dict
    actor_props = actor_npc.properties_json if actor_npc.properties_json is not None else {}

    npc_abilities_raw = actor_props.get("abilities")
    npc_abilities = npc_abilities_raw if isinstance(npc_abilities_raw, list) else []

    current_resources = actor_combat_data.get("resources", {})
    if not isinstance(current_resources, dict): current_resources = {} # Ensure dict

    active_cooldowns = actor_combat_data.get("cooldowns", {})
    if not isinstance(active_cooldowns, dict): active_cooldowns = {} # Ensure dict


    for ability_props_original in npc_abilities:
        if not isinstance(ability_props_original, dict):
            continue
        ability_props = ability_props_original.copy()

        ability_static_id = ability_props.get("static_id")
        if not ability_static_id:
            continue

        # Ensure ability_static_id is a valid key type for active_cooldowns (e.g. string)
        if isinstance(ability_static_id, str) and active_cooldowns.get(ability_static_id, 0) > 0:
            continue

        cost = ability_props.get("cost", {})
        if not isinstance(cost, dict): cost = {} # Ensure dict
        can_afford = True
        for resource_type, amount_needed_any in cost.items():
            amount_needed = amount_needed_any if isinstance(amount_needed_any, (int, float)) else 0
            if current_resources.get(resource_type, 0) < amount_needed:
                can_afford = False
                break
        if not can_afford:
            continue

        if "category" not in ability_props:
            ability_props["category"] = ability_props.get("default_category", "ability_generic")

        available_abilities.append(ability_props)

    return available_abilities

async def _simulate_action_outcome(
    session: AsyncSession,
    guild_id: int,
    actor_npc: GeneratedNpc,
    actor_combat_data: Dict[str, Any],
    target_info: Dict[str, Union[Player, GeneratedNpc, Dict[str, Any]]],
    action_details: Dict[str, Any],
    ai_rules: Dict[str, Any],
    combat_engine_api: Any
) -> Dict[str, Any]:
    """
    Simulates the outcome of an action to estimate its effectiveness.
    """
    simulation_rules = ai_rules.get("simulation", {})
    if not isinstance(simulation_rules, dict): simulation_rules = {}

    if not simulation_rules.get("enabled", False):
        return {"hit_chance": 1.0, "expected_damage": 10.0, "critical_chance": 0.05, "applied_statuses": []}

    hit_chance = 0.7
    expected_damage = 0.0 # Use float for damage
    crit_chance = 0.05

    actor_props = actor_npc.properties_json if actor_npc.properties_json is not None else {}
    actor_stats = actor_props.get("stats", {})
    if not isinstance(actor_stats, dict): actor_stats = {}


    action_type = action_details.get("type")
    if action_type == "attack":
        expected_damage = float(actor_stats.get("base_attack_damage", 5.0))
    elif action_type == "ability":
        ability_props = action_details.get("ability_props", {})
        if not isinstance(ability_props, dict): ability_props = {}

        effects_list = ability_props.get("effects", [])
        if not isinstance(effects_list, list): effects_list = []

        damage_effect = next((eff for eff in effects_list if isinstance(eff, dict) and eff.get("type") == "damage"), None)
        if isinstance(damage_effect, dict): # Check if damage_effect is a dict
            dmg_formula = damage_effect.get("value", "5")
            if isinstance(dmg_formula, (int, float)):
                expected_damage = float(dmg_formula)
            elif isinstance(dmg_formula, str):
                if 'd' in dmg_formula:
                    try:
                        parts = dmg_formula.split('d')
                        num_dice = int(parts[0])
                        dice_face_str = parts[1].split('+')[0].split('-')[0]
                        dice_face = int(dice_face_str)
                        expected_damage = num_dice * (dice_face / 2.0 + 0.5)
                        if '+' in dmg_formula: expected_damage += float(dmg_formula.split('+')[-1])
                        elif '-' in dmg_formula: expected_damage -= float(dmg_formula.split('-')[-1])
                    except (ValueError, IndexError, TypeError):
                        expected_damage = 5.0 # Default damage on parsing error
                else:
                    try:
                        expected_damage = float(dmg_formula)
                    except ValueError:
                        expected_damage = 5.0
            else: # Not str, int, or float
                 expected_damage = 5.0
        else: # No damage effect or invalid effect structure
            expected_damage = 2.0

    # Ensure target_entity_model is Player or GeneratedNpc before accessing properties
    target_entity_model_union = target_info.get("entity")
    if isinstance(target_entity_model_union, (Player, GeneratedNpc)):
        target_entity_model: Union[Player, GeneratedNpc] = target_entity_model_union # Pyright now knows the type

        target_props = None
        if isinstance(target_entity_model, GeneratedNpc):
            target_props = target_entity_model.properties_json if target_entity_model.properties_json else {}
        # For Player, stats might be directly on model or via a method, simplified here
        # target_stats = target_props.get("stats", {}) if target_props else getattr(target_entity_model, 'stats', {})
        # target_defense = target_stats.get("defense", 0)
        # expected_damage = max(1.0, expected_damage - float(target_defense))


    return {
        "hit_chance": hit_chance,
        "expected_damage": expected_damage,
        "critical_chance": crit_chance,
        "applied_statuses": []
    }


async def _evaluate_action_effectiveness(
    session: AsyncSession,
    guild_id: int,
    actor_npc: GeneratedNpc,
    actor_combat_data: Dict[str, Any],
    target_info: Dict[str, Union[Player, GeneratedNpc, Dict[str, Any]]],
    action_details: Dict[str, Any],
    ai_rules: Dict[str, Any]
) -> float:
    effectiveness_score = 0.0
    sim_results = await _simulate_action_outcome(session, guild_id, actor_npc, actor_combat_data, target_info, action_details, ai_rules, None)

    effective_damage = sim_results.get("expected_damage", 0.0) * sim_results.get("hit_chance", 0.0)
    effectiveness_score += effective_damage

    action_selection_rules = ai_rules.get("action_selection", {})
    if not isinstance(action_selection_rules, dict): action_selection_rules = {}

    if action_details.get("type") == "ability":
        effectiveness_score *= action_selection_rules.get("ability_base_effectiveness_multiplier", 1.1)

        ability_props = action_details.get("ability_props", {})
        if not isinstance(ability_props, dict): ability_props = {}

        effects_list = ability_props.get("effects", [])
        if not isinstance(effects_list, list): effects_list = []

        for effect in effects_list:
            if not isinstance(effect, dict): continue
            if effect.get("type") == "apply_status":
                status_static_id = effect.get("status_static_id")
                status_strategic_value_rules = action_selection_rules.get("status_strategic_value", {})
                if not isinstance(status_strategic_value_rules, dict): status_strategic_value_rules = {}
                status_value = status_strategic_value_rules.get(status_static_id, 0)
                effectiveness_score += status_value
            elif effect.get("type") == "heal":
                heal_amount = 0.0
                try:
                    heal_formula = effect.get("value", "5")
                    if isinstance(heal_formula, (int, float)):
                        heal_amount = float(heal_formula)
                    elif isinstance(heal_formula, str):
                        if 'd' in heal_formula.lower(): # Use lower() for case-insensitivity like 'D'
                            parts = heal_formula.lower().split('d')
                            num_dice = int(parts[0])

                            dice_part_str = parts[1]
                            modifier = 0

                            # Extract dice face and modifier (e.g., from "6+2" or "4-1" or just "8")
                            if '+' in dice_part_str:
                                val_parts = dice_part_str.split('+', 1)
                                dice_face = int(val_parts[0])
                                modifier = float(val_parts[1])
                            elif '-' in dice_part_str:
                                val_parts = dice_part_str.split('-', 1)
                                dice_face = int(val_parts[0])
                                modifier = -float(val_parts[1])
                            else:
                                dice_face = int(dice_part_str)

                            heal_amount = num_dice * (dice_face / 2.0 + 0.5) # Average roll
                            heal_amount += modifier
                        else:
                            heal_amount = float(heal_formula) # If not dice, try to parse as plain number
                except (ValueError, TypeError, IndexError):
                    heal_amount = 5.0 # Default on any parsing error

                actor_props = actor_npc.properties_json if actor_npc.properties_json else {}
                actor_stats = actor_props.get("stats", {})
                if not isinstance(actor_stats, dict): actor_stats = {}
                actor_max_hp = float(actor_stats.get("hp",1.0))
                actor_current_hp = float(actor_combat_data.get("current_hp", actor_max_hp)) # Changed "hp" to "current_hp"
                hp_deficit_ratio = 1.0 - (actor_current_hp / actor_max_hp if actor_max_hp > 0 else 1.0)
                low_hp_mult = action_selection_rules.get("low_hp_heal_urgency_multiplier", 2.0)
                effectiveness_score += heal_amount * (1.0 + hp_deficit_ratio * float(low_hp_mult))

    simulation_rules = ai_rules.get("simulation", {})
    if not isinstance(simulation_rules, dict): simulation_rules = {}

    if simulation_rules.get("enabled", False):
        if sim_results.get("hit_chance", 1.0) < simulation_rules.get("required_hit_chance_threshold", 0.0):
            return -1.0

        target_combat_data_dict = target_info.get("combat_data")
        if not isinstance(target_combat_data_dict, dict): target_combat_data_dict = {}
        target_current_hp = float(target_combat_data_dict.get("current_hp", 1.0)) # Changed "hp" to "current_hp"
        if target_current_hp <= 0: target_current_hp = 1.0

        sim_expected_damage = sim_results.get("expected_damage", 0.0)
        damage_ratio_vs_target_hp = sim_expected_damage / target_current_hp
        if damage_ratio_vs_target_hp < simulation_rules.get("min_expected_damage_ratio_vs_target_hp", 0.0):
            if sim_expected_damage > 0 :
                 return -1.0

    return effectiveness_score


async def _choose_action(
    session: AsyncSession,
    guild_id: int,
    actor_npc: GeneratedNpc,
    actor_combat_data: Dict[str, Any],
    target_info: Dict[str, Union[Player, GeneratedNpc, Dict[str, Any]]],
    ai_rules: Dict[str, Any],
    combat_encounter: CombatEncounter
) -> Dict[str, Any]:
    possible_actions = []
    basic_attack_action = {"type": "attack", "name": "Basic Attack", "category": "attack_basic"}

    available_abilities = _get_available_abilities(actor_npc, actor_combat_data, ai_rules)
    for ability_prop in available_abilities:
        if isinstance(ability_prop, dict): # Ensure ability_prop is a dict
            possible_actions.append({
                "type": "ability",
                "name": ability_prop.get("name", "Unknown Ability"),
                "ability_props": ability_prop,
                "category": ability_prop.get("category", "ability_generic")
            })
    possible_actions.append(basic_attack_action)

    action_evaluations = []
    for action_detail_item in possible_actions:
        if isinstance(action_detail_item, dict): # Ensure action_detail_item is a dict
            effectiveness = await _evaluate_action_effectiveness(
                session, guild_id, actor_npc, actor_combat_data, target_info, action_detail_item, ai_rules
            )
            if effectiveness >= 0: # Ensure effectiveness is a number
                action_evaluations.append({"action": action_detail_item, "score": float(effectiveness)})

    if not action_evaluations:
        simulation_rules = ai_rules.get("simulation",{})
        if not isinstance(simulation_rules, dict): simulation_rules = {}
        basic_attack_effectiveness = await _evaluate_action_effectiveness(
            session, guild_id, actor_npc, actor_combat_data, target_info, basic_attack_action,
            {**ai_rules, "simulation": {**simulation_rules, "enabled":False}}
        )
        if basic_attack_effectiveness > 0:
             return basic_attack_action
        return {"type": "idle", "reason": "All actions deemed ineffective or failed simulation"}

    action_evaluations.sort(key=lambda x: x.get("score", 0.0), reverse=True) # Use .get for score

    best_evaluated_action_dict = action_evaluations[0] if action_evaluations else {"action": basic_attack_action, "score": 0.0}


    rel_influence_rules = ai_rules.get("relationship_influence", {})
    if not isinstance(rel_influence_rules, dict): rel_influence_rules = {}
    npc_combat_rules = rel_influence_rules.get("npc_combat", {})
    if not isinstance(npc_combat_rules, dict): npc_combat_rules = {}
    std_rel_influence_config = npc_combat_rules.get("behavior", {})
    if not isinstance(std_rel_influence_config, dict): std_rel_influence_config = {}

    action_choice_rules = std_rel_influence_config.get("action_choice")
    if std_rel_influence_config.get("enabled", False) and isinstance(action_choice_rules, dict):
        target_combat_data_dict = target_info.get("combat_data")
        if not isinstance(target_combat_data_dict, dict): target_combat_data_dict = {}

        target_participant_type_str = target_combat_data_dict.get("type")
        target_participant_id = target_combat_data_dict.get("id")
        current_relationship_val = None

        if target_participant_type_str and target_participant_id is not None:
            try:
                target_rel_entity_type = EntityType(target_participant_type_str)
                mapped_target_rel_type = None
                if target_rel_entity_type == EntityType.PLAYER: mapped_target_rel_type = RelationshipEntityType.PLAYER
                elif target_rel_entity_type == EntityType.NPC: mapped_target_rel_type = RelationshipEntityType.GENERATED_NPC

                if mapped_target_rel_type:
                    current_relationship_val = await _get_relationship_value(
                        session, guild_id,
                        RelationshipEntityType.GENERATED_NPC, actor_npc.id,
                        mapped_target_rel_type, target_participant_id
                    )
            except ValueError: pass


        if current_relationship_val is not None:
            relationship_category = "neutral"
            if current_relationship_val >= action_choice_rules.get("friendly_positive_threshold", 50):
                relationship_category = "friendly"
            elif current_relationship_val <= action_choice_rules.get("hostile_negative_threshold", -50):
                relationship_category = "hostile"

            rules_for_category = action_choice_rules.get(f"actions_if_{relationship_category}", [])
            if isinstance(rules_for_category, list):
                for eval_item in action_evaluations:
                    action_dict = eval_item.get("action", {})
                    if not isinstance(action_dict, dict): continue
                    action_type = action_dict.get("type")
                    ability_props = action_dict.get("ability_props", {})
                    if not isinstance(ability_props, dict): ability_props = {}
                    ability_static_id = ability_props.get("static_id") if action_type == "ability" else None

                    for rule_mod in rules_for_category:
                        if not isinstance(rule_mod, dict): continue
                        matches_type = (rule_mod.get("action_type") == action_type)
                        matches_id = (not rule_mod.get("ability_static_id") or rule_mod.get("ability_static_id") == ability_static_id)

                        if matches_type and matches_id:
                            weight_multiplier = rule_mod.get("weight_multiplier", 1.0)
                            eval_item["score"] = eval_item.get("score", 0.0) * float(weight_multiplier)
                            break
                action_evaluations.sort(key=lambda x: x.get("score",0.0), reverse=True)
                if action_evaluations:
                    best_evaluated_action_dict = action_evaluations[0]

    parsed_hidden_effects = ai_rules.get("parsed_hidden_relationship_combat_effects")
    if isinstance(parsed_hidden_effects, list) and action_evaluations:
        for hidden_effect_entry in parsed_hidden_effects:
            if not isinstance(hidden_effect_entry, dict): continue
            rule_data = hidden_effect_entry.get("rule_data", {})
            if not isinstance(rule_data, dict): continue
            rel_details = hidden_effect_entry.get("applies_to_relationship", {})
            if not isinstance(rel_details, dict): continue

            target_combat_data_dict = target_info.get("combat_data")
            if not isinstance(target_combat_data_dict, dict): target_combat_data_dict = {}
            current_target_type_str = target_combat_data_dict.get("type")
            current_target_id = target_combat_data_dict.get("id")

            if current_target_type_str and current_target_id is not None:
                try:
                    current_target_type_enum_val = EntityType(current_target_type_str).value
                    if rel_details.get("target_entity_type") == current_target_type_enum_val and \
                       rel_details.get("target_entity_id") == current_target_id:

                        weight_multipliers_rules = rule_data.get("action_weight_multipliers", [])
                        if not isinstance(weight_multipliers_rules, list): weight_multipliers_rules = []
                        for eval_item in action_evaluations:
                            action_dict = eval_item.get("action", {})
                            if not isinstance(action_dict, dict): continue
                            action_category = action_dict.get("category", "unknown")

                            for wm_rule in weight_multipliers_rules:
                                if not isinstance(wm_rule, dict): continue
                                if wm_rule.get("action_category") == action_category:
                                    formula = wm_rule.get("multiplier_formula")
                                    if formula and isinstance(formula, str):
                                        try:
                                            multiplier = float(eval(formula, {"__builtins__": {}}, {"value": rel_details.get("value")}))
                                            eval_item["score"] = eval_item.get("score",0.0) * multiplier
                                        except Exception as e:
                                            pass
                                    break
                except ValueError: pass


        action_evaluations.sort(key=lambda x: x.get("score",0.0), reverse=True)
        if action_evaluations: # Re-assign best_evaluated_action_dict after potential re-sort
            best_evaluated_action_dict = action_evaluations[0]


    actor_props = actor_npc.properties_json if actor_npc.properties_json is not None else {}
    actor_stats = actor_props.get("stats", {})
    if not isinstance(actor_stats, dict): actor_stats = {}

    actor_max_hp = float(actor_stats.get("hp",1.0))
    actor_current_hp = float(actor_combat_data.get("current_hp", actor_max_hp)) # Changed "hp" to "current_hp"
    hp_percentage = (actor_current_hp / actor_max_hp) if actor_max_hp > 0 else 1.0

    action_selection_rules_for_heal = ai_rules.get("action_selection",{})
    if not isinstance(action_selection_rules_for_heal, dict): action_selection_rules_for_heal = {}
    resource_thresholds_for_heal = action_selection_rules_for_heal.get("resource_thresholds",{})
    if not isinstance(resource_thresholds_for_heal, dict): resource_thresholds_for_heal = {}
    heal_threshold = resource_thresholds_for_heal.get("self_hp_below_for_heal_ability")

    if heal_threshold is not None and hp_percentage < float(heal_threshold):
        healing_actions = []
        for eval_action_item in action_evaluations:
            if not isinstance(eval_action_item, dict): continue
            action_dict = eval_action_item.get("action", {})
            if not isinstance(action_dict, dict): continue
            ability_props = action_dict.get("ability_props",{})
            if not isinstance(ability_props, dict): ability_props = {}

            effects_list = ability_props.get("effects",[])
            if not isinstance(effects_list, list): effects_list = []

            is_healing = any(isinstance(effect, dict) and effect.get("type") == "heal" and effect.get("target_scope","self") == "self" for effect in effects_list)
            if is_healing:
                healing_actions.append(eval_action_item)

        if healing_actions:
            healing_actions.sort(key=lambda x: x.get("score",0.0), reverse=True)
            best_action_to_return = healing_actions[0].get("action")
            if isinstance(best_action_to_return, dict): return best_action_to_return


    best_action_final = best_evaluated_action_dict.get("action")
    if isinstance(best_action_final, dict):
        return best_action_final

    # Fallback if somehow best_action_final is not a dict
    return {"type": "idle", "reason": "No valid best action determined."}


def _format_action_result(
    chosen_action_details: Dict[str, Any],
    target_info: Dict[str, Union[Player, GeneratedNpc, Dict[str, Any]]]
) -> Dict[str, Any]:
    action_type_str = chosen_action_details.get("type")

    target_entity_model_union = target_info.get("entity")
    target_combat_data = target_info.get("combat_data")

    if not isinstance(target_entity_model_union, (Player, GeneratedNpc)):
        return {"action_type": "error", "message": "Invalid target entity type in _format_action_result."}
    target_entity_model: Union[Player, GeneratedNpc] = target_entity_model_union


    if not isinstance(target_combat_data, dict):
        return {"action_type": "error", "message": "Invalid target combat data in _format_action_result."}


    formatted_action: Dict[str,Any] = { # Ensure type hint for formatted_action
        "action_type": action_type_str,
        "target_id": target_entity_model.id,
        "target_type": target_combat_data.get("type")
    }

    if action_type_str == "ability":
        ability_props = chosen_action_details.get("ability_props", {})
        if isinstance(ability_props, dict): # ensure dict
            formatted_action["ability_id"] = ability_props.get("static_id")
        else: # ability_props was not a dict
            formatted_action["ability_id"] = None # Or handle error

        if not formatted_action.get("ability_id"):
            # Log error or handle missing ability_id for an ability action
            pass

    return formatted_action

# --- End of Action Selection ---

# Main function
async def get_npc_combat_action(
    session: AsyncSession,
    guild_id: int,
    npc_id: int,
    combat_instance_id: int
) -> Dict[str, Any]:
    actor_npc = await _get_npc_data(session, npc_id, guild_id)
    if not actor_npc:
        return {"action_type": "error", "message": f"NPC {npc_id} not found for guild {guild_id}."}

    combat_encounter = await _get_combat_encounter_data(session, combat_instance_id, guild_id)
    if not combat_encounter:
        return {"action_type": "error", "message": f"Combat encounter {combat_instance_id} not found for guild {guild_id}."}

    # Ensure participants_json from combat_encounter is a dict, and its 'entities' key holds a list
    participants_data_outer = combat_encounter.participants_json
    participants_list_raw = []
    if isinstance(participants_data_outer, dict):
        participants_list_raw = participants_data_outer.get("entities", [])

    if not isinstance(participants_list_raw, list):
        return {"action_type": "error", "message": f"Combat encounter {combat_instance_id} has invalid participants_json['entities'] format."}

    # Filter out non-dict items from participants_list_raw before processing
    participants_list = [p for p in participants_list_raw if isinstance(p, dict)]


    actor_combat_data = next((p for p in participants_list if p.get("id") == actor_npc.id and p.get("type") == EntityType.NPC.value), None)
    if not actor_combat_data: # actor_combat_data could be None
        return {"action_type": "error", "message": f"Actor NPC {npc_id} not found in combat {combat_instance_id} participants."}

    if actor_combat_data.get("current_hp", 0) <= 0: # Changed "hp" to "current_hp"
        return {"action_type": "idle", "reason": "Actor is defeated."}

    actor_all_relationships = await crud_relationship.get_relationships_for_entity(
        session=session, # FIX: db to session
        guild_id=guild_id,
        entity_id=actor_npc.id,
        entity_type=RelationshipEntityType.GENERATED_NPC # Mapped from CombatParticipantType.NPC
    )

    actor_hidden_relationships = []
    if actor_all_relationships: # Check if None
        hidden_prefixes = ("secret_", "internal_", "personal_debt", "hidden_fear", "betrayal_")
        for rel in actor_all_relationships:
            if rel.relationship_type and rel.relationship_type.startswith(hidden_prefixes): # Check rel.relationship_type not None
                actor_hidden_relationships.append(rel)

    ai_rules = await _get_npc_ai_rules(session, guild_id, actor_npc, combat_encounter, actor_hidden_relationships)

    potential_targets = await _get_potential_targets(session, actor_npc, combat_encounter, ai_rules, guild_id, participants_list)
    if not potential_targets:
       return {"action_type": "idle", "reason": "No targets available."}

    selected_target_info = await _select_target(session, guild_id, actor_npc, potential_targets, ai_rules, combat_encounter)
    if not selected_target_info: # selected_target_info can be None
       return {"action_type": "idle", "reason": "Could not select a target."}

    selected_target_combat_data = selected_target_info.get("combat_data")
    selected_target_entity_union = selected_target_info.get("entity")

    if not isinstance(selected_target_combat_data, dict) or not isinstance(selected_target_entity_union, (Player, GeneratedNpc)):
         return {"action_type": "idle", "reason": "Selected target info is invalid."}

    # Now selected_target_entity_union is known to be Player or GeneratedNpc
    selected_target_entity: Union[Player, GeneratedNpc] = selected_target_entity_union

    if selected_target_combat_data.get("current_hp", 0) <= 0: # Changed "hp" to "current_hp"
        remaining_targets = [
            t for t in potential_targets
            if isinstance(t.get("entity"), (Player, GeneratedNpc)) and \
               t.get("entity").id != selected_target_entity.id and \
               isinstance(t.get("combat_data"), dict) and \
               t.get("combat_data", {}).get("current_hp", 0) > 0 # Changed "hp"
        ]
        if remaining_targets:
            selected_target_info = await _select_target(session, guild_id, actor_npc, remaining_targets, ai_rules, combat_encounter)
            if not selected_target_info:
                 return {"action_type": "idle", "reason": "Selected target defeated, no other valid targets."}
        else:
            return {"action_type": "idle", "reason": "Selected target defeated, no other targets."}

    chosen_action_details = await _choose_action(
        session, guild_id, actor_npc, actor_combat_data, selected_target_info, ai_rules, combat_encounter
    )

    if chosen_action_details.get("type") == "idle":
        return {"action_type": "idle", "reason": chosen_action_details.get("reason", "No effective action found.")}

    formatted_action = _format_action_result(chosen_action_details, selected_target_info)
    return formatted_action
