# src/core/npc_combat_strategy.py

from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional, Union

from src.models.generated_npc import GeneratedNpc
from src.models.combat_encounter import CombatEncounter
from src.models.player import Player
from src.models.enums import CombatParticipantType as EntityType # Changed to CombatParticipantType
from src.core.crud import crud_npc, crud_combat_encounter, crud_player, crud_relationship
from src.core.rules import get_rule

# Вспомогательные функции для загрузки данных

async def _get_npc_data(session: AsyncSession, npc_id: int, guild_id: int) -> Optional[GeneratedNpc]:
    """
    Loads NPC data from the database.
    """
    return await crud_npc.npc_crud.get_by_id_and_guild(db=session, id=npc_id, guild_id=guild_id)

async def _get_combat_encounter_data(session: AsyncSession, combat_instance_id: int, guild_id: int) -> Optional[CombatEncounter]:
    """
    Loads Combat Encounter data from the database.
    """
    return await crud_combat_encounter.combat_encounter_crud.get_by_id_and_guild(db=session, id=combat_instance_id, guild_id=guild_id)

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
        return await crud_player.player_crud.get_by_id_and_guild(db=session, id=entity_id, guild_id=guild_id)
    elif entity_type == EntityType.NPC:
        return await crud_npc.npc_crud.get_by_id_and_guild(db=session, id=entity_id, guild_id=guild_id)

    return None

async def _get_relationship_value(
    session: AsyncSession,
    guild_id: int,
    entity1_type: EntityType,
    entity1_id: int,
    entity2_type: EntityType,
    entity2_id: int
) -> Optional[int]:
    """
    Retrieves the relationship value between two entities.
    Returns None if no relationship is found.
    """
    relationship = await crud_relationship.get_relationship_between_entities(
        session=session,
        guild_id=guild_id,
        entity1_type=entity1_type,
        entity1_id=entity1_id,
        entity2_type=entity2_type,
        entity2_id=entity2_id
    )
    return relationship.value if relationship else None

async def _get_npc_ai_rules(
    session: AsyncSession,
    guild_id: int,
    actor_npc: GeneratedNpc,
    combat_encounter: CombatEncounter
) -> Dict[str, Any]:
    """
    Loads and compiles AI behavior rules for the given NPC from RuleConfig.
    This is a placeholder implementation. Detailed logic will depend on RuleConfig structure.
    """
    base_rules_key = "ai_behavior:npc_default_strategy"
    npc_rules = await get_rule(db=session, guild_id=guild_id, key=base_rules_key, default={})

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

    # Merge relationship influence rules
    rel_influence_key = "relationship_influence:npc_combat:behavior"
    rel_influence_rules_specific = await get_rule(db=session, guild_id=guild_id, key=rel_influence_key, default=None)

    default_rel_influence_rules = {
        "enabled": True,
        "hostility_threshold_modifier_formula": "-(relationship_value / 10)",
        "target_score_modifier_formula": "-(relationship_value * 0.2)",
        "action_choice": {
            "friendly_positive_threshold": 50,
            "hostile_negative_threshold": -50,
            "actions_if_friendly": [], # Example: {"action_type": "ability", "ability_static_id": "aid_friend", "weight_multiplier": 2.0}
            "actions_if_hostile": []   # Example: {"action_type": "attack", "weight_multiplier": 1.2}
        }
    }

    final_rel_influence_rules = default_rel_influence_rules.copy()
    if rel_influence_rules_specific and isinstance(rel_influence_rules_specific, dict):
        # Deep merge might be better if structures are complex
        for key, value in rel_influence_rules_specific.items():
            if isinstance(value, dict) and isinstance(final_rel_influence_rules.get(key), dict):
                final_rel_influence_rules[key].update(value)
            else:
                final_rel_influence_rules[key] = value

    # Add the merged relationship rules to the main npc_rules structure
    # This assumes ai_rules is the final, comprehensive rule set for the NPC's turn.
    # We store it under a distinct key to avoid clashes with 'target_selection', 'action_selection' etc.
    if "relationship_influence" not in npc_rules:
        npc_rules["relationship_influence"] = {}
    if "npc_combat" not in npc_rules["relationship_influence"]:
        npc_rules["relationship_influence"]["npc_combat"] = {}
    npc_rules["relationship_influence"]["npc_combat"]["behavior"] = final_rel_influence_rules
    # End of merging relationship influence rules


    npc_personality = actor_props.get("personality", actor_ai_meta.get("personality"))
    if npc_personality and npc_personality in npc_rules.get("personality_modifiers", {}): # This refers to the base npc_rules personality_modifiers
        mods = npc_rules["personality_modifiers"][npc_personality]
        current_bias = npc_rules.get("action_selection", {}).get("offensive_bias", default_strategy["action_selection"]["offensive_bias"])

        if "offensive_bias_add" in mods:
            current_bias = min(1.0, current_bias + mods["offensive_bias_add"])
        if "offensive_bias_subtract" in mods:
            current_bias = max(0.0, current_bias - mods["offensive_bias_subtract"])

        if "action_selection" not in npc_rules: npc_rules["action_selection"] = {}
        npc_rules["action_selection"]["offensive_bias"] = current_bias

        # Example for modifying nested structures like resource_thresholds
        if "resource_thresholds_modifier" in mods:
            if "resource_thresholds" not in npc_rules["action_selection"]:
                npc_rules["action_selection"]["resource_thresholds"] = {}
            for item, val_mod in mods["resource_thresholds_modifier"].items():
                base_val = default_strategy["action_selection"]["resource_thresholds"].get(item,0)
                npc_rules["action_selection"]["resource_thresholds"][item] = base_val + val_mod


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

    hostility_config = ai_rules.get("target_selection", {}).get("hostility_rules", {})
    default_hostility_rule = hostility_config.get("default", "attack_players_and_hostile_npcs")

    actor_props = actor_npc.properties_json or {}
    actor_faction = actor_props.get("faction_id")

    target_faction = None
    if isinstance(target_entity, GeneratedNpc):
        target_props = target_entity.properties_json or {}
        target_faction = target_props.get("faction_id")

    # 1. Check explicit relationship
    relationship_val = await _get_relationship_value(
        session, guild_id,
        EntityType.NPC, actor_npc.id,
        EntityType(target_participant_info["type"]), target_participant_info["id"]
    )

    if relationship_val is not None:
        # Get base thresholds
        base_hostile_threshold = hostility_config.get("relationship_hostile_threshold", -50)
        base_friendly_threshold = hostility_config.get("relationship_friendly_threshold", 50)

        # Apply modifier from relationship_influence rule if present
        # This rule would be part of the broader 'relationship_influence:npc_combat:behavior'
        # For simplicity, assume ai_rules might already contain a pre-processed version
        # or we fetch it here. Let's assume it's part of ai_rules structure.
        rel_influence_config = ai_rules.get("relationship_influence", {}).get("npc_combat", {}).get("behavior", {})

        final_hostile_threshold = base_hostile_threshold
        final_friendly_threshold = base_friendly_threshold

        if rel_influence_config.get("enabled", False):
            formula = rel_influence_config.get("hostility_threshold_modifier_formula")
            if formula and isinstance(formula, str):
                try:
                    # Formula expected to return a value that MODIFIES the threshold
                    # e.g. "-(relationship_value / 10)" means positive relationship increases effective threshold (less likely hostile)
                    # For hostile_threshold (e.g. -50), a positive modifier makes it less negative (e.g. -40)
                    # For friendly_threshold (e.g. 50), a positive modifier makes it higher (e.g. 60)
                    # Let's assume formula directly calculates the *adjustment*
                    adjustment = int(eval(formula, {"__builtins__": {}}, {"relationship_value": relationship_val}))

                    # How adjustment applies depends on interpretation.
                    # If formula is e.g. "relationship_value / 5":
                    # Hostile: -50 + (rel_val/5). If rel_val is 50, threshold becomes -40.
                    # Friendly: 50 - (rel_val/5). If rel_val is 50, threshold becomes 40. (This seems counterintuitive for friendly)
                    # Let's redefine: formula gives a value. Positive value = more friendly bias.
                    # Hostile threshold: increase it (make it harder to be hostile). Friendly threshold: decrease it (easier to be friendly).
                    # Example: bias_value = relationship_value / 10.
                    # final_hostile_threshold = base_hostile_threshold + bias_value
                    # final_friendly_threshold = base_friendly_threshold - bias_value

                    # Using the example hostility_threshold_modifier_formula: "-(relationship_value / 10)"
                    # If rel_value = 50 (friendly), adjustment = -(50/10) = -5
                    # final_hostile_threshold = -50 + (-5) = -55 (harder to meet hostile threshold)
                    # final_friendly_threshold = 50 - (-5) = 55 (easier to meet friendly threshold)
                    # This interpretation seems more consistent: positive relationship makes NPC less hostile / more friendly.

                    # Let's use the direct output of the formula as the adjustment.
                    # The formula "-(relationship_value / X)" means positive rel_value leads to negative adjustment.
                    # Hostile threshold: base_hostile_threshold + adjustment (e.g., -50 + (-5) = -55)
                    # Friendly threshold: base_friendly_threshold - adjustment (e.g., 50 - (-5) = 55)

                    hostility_bias_mod = int(eval(formula, {"__builtins__": {}}, {"relationship_value": relationship_val}))
                    final_hostile_threshold += hostility_bias_mod
                    final_friendly_threshold -= hostility_bias_mod # Higher positive relationship makes friendly threshold lower (easier to be friendly)
                                                                  # and hostile threshold more negative (harder to be hostile)

                except Exception as e:
                    # Log error in evaluating formula
                    pass # Use base thresholds

        if relationship_val <= final_hostile_threshold:
            return True
        if relationship_val >= final_friendly_threshold:
            return False # Explicitly friendly

    # 2. Faction check (if both are NPCs and have factions)
    if actor_faction and target_faction and actor_faction == target_faction:
        # Same faction: generally not hostile unless specific rules override
        if hostility_config.get("same_faction_is_friendly", True):
            return False

    # TODO: Implement more complex faction hostility rules (e.g., enemy faction list)
    # faction_relationships = await get_rule(session, guild_id, f"factions:{actor_faction}:relationships", {})
    # if target_faction in faction_relationships.get("enemies", []): return True
    # if target_faction in faction_relationships.get("allies", []): return False

    # 3. Default rule application
    if default_hostility_rule == "attack_players_and_hostile_npcs":
        if target_participant_info["type"] == EntityType.PLAYER.value:
            return True
        # For NPCs, hostility might need to be explicitly defined or fall back to faction/relationship checks.
        # If an NPC is not explicitly friendly and not same faction (if that rule applies), consider hostile by default in combat.
        if target_participant_info["type"] == EntityType.NPC.value:
            # This is a simplification; real system might need more nuance or rely on combat setup.
            return True
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
        if participant_info.get("id") == actor_npc.id and participant_info.get("type") == EntityType.NPC.value:
            continue

        # Skip defeated participants (current HP is in participant_info)
        if participant_info.get("hp", 0) <= 0:
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
    target_entity_model = target_info.get("entity")
    target_combat_data = target_info.get("combat_data")

    if not isinstance(target_entity_model, (Player, GeneratedNpc)):
        # Log error or handle appropriately
        # This addresses potential type confusion for target_entity_model
        return 0.0 # Return a neutral score or handle error

    if not isinstance(target_combat_data, dict):
        return 0.0 # Return a neutral score or handle error


    score = 0.0

    if priority_metric == "lowest_hp_percentage":
        current_hp = target_combat_data.get("hp", 0)
        max_hp = 1 # Default to 1 to avoid division by zero if not found
        if isinstance(target_entity_model, GeneratedNpc):
            target_props = target_entity_model.properties_json or {}
            base_stats = target_props.get("stats", {})
            max_hp = base_stats.get("hp", current_hp if current_hp > 0 else 1)
        elif isinstance(target_entity_model, Player):
            max_hp = target_combat_data.get("max_hp", current_hp if current_hp > 0 else 1)

        if max_hp <= 0: max_hp = 1
        score = (current_hp / max_hp) * 100 if max_hp > 0 else 0
        return score # Lower is better

    elif priority_metric == "highest_hp_percentage":
        current_hp = target_combat_data.get("hp", 0)
        max_hp = 1
        if isinstance(target_entity_model, GeneratedNpc):
            target_props = target_entity_model.properties_json or {}
            base_stats = target_props.get("stats", {})
            max_hp = base_stats.get("hp", current_hp if current_hp > 0 else 1)
        elif isinstance(target_entity_model, Player):
            max_hp = target_combat_data.get("max_hp", current_hp if current_hp > 0 else 1)

        if max_hp <= 0: max_hp = 1
        score = (current_hp / max_hp) * 100 if max_hp > 0 else 0
        return score # Higher is better

    elif priority_metric == "lowest_absolute_hp":
        score = target_combat_data.get("hp", 0)
        return score # Lower is better

    elif priority_metric == "highest_absolute_hp":
        score = target_combat_data.get("hp", 0)
        return score # Higher is better

    elif priority_metric == "highest_threat_score":
        threat = 0.0
        threat_factors = ai_rules.get("target_selection", {}).get("threat_factors", {})
        threat += target_combat_data.get("threat_generated_towards_actor", 0.0) * threat_factors.get("damage_dealt_to_self_factor", 1.0)

        if isinstance(target_entity_model, GeneratedNpc):
            target_props = target_entity_model.properties_json or {}
            target_roles = target_props.get("roles", [])
            if "healer" in target_roles and threat_factors.get("is_healer_factor"):
                threat += 100 * threat_factors.get("is_healer_factor")

        if threat_factors.get("low_hp_target_bonus"):
            current_hp = target_combat_data.get("hp", 0)
            max_hp = 1
            if isinstance(target_entity_model, GeneratedNpc):
                target_props = target_entity_model.properties_json or {}
                target_stats = target_props.get("stats", {})
                max_hp = target_stats.get("hp", current_hp if current_hp > 0 else 1)
            elif isinstance(target_entity_model, Player):
                max_hp = target_combat_data.get("max_hp", current_hp if current_hp > 0 else 1)

            if max_hp <=0: max_hp = 1
            hp_percent = (current_hp / max_hp) if max_hp > 0 else 0
            if hp_percent < 0.3:
                threat += 50 * threat_factors.get("low_hp_target_bonus")

        # Relationship influence on threat (negative relationship increases perceived threat)
        relationship_val = await _get_relationship_value(
            session, guild_id,
            EntityType.NPC, actor_npc.id,
            EntityType(target_combat_data["type"]), target_combat_data["id"]
        )
        if relationship_val is not None:
            # Apply general target_score_modifier_formula from relationship_influence rules
            rel_influence_config = ai_rules.get("relationship_influence", {}).get("npc_combat", {}).get("behavior", {})
            if rel_influence_config.get("enabled", False):
                formula = rel_influence_config.get("target_score_modifier_formula")
                if formula and isinstance(formula, str):
                    try:
                        # Formula like "(relationship_value * 0.5)"
                        # Positive relationship_value (friendly) should decrease threat score (if formula results in negative adjustment)
                        # Negative relationship_value (hostile) should increase threat score (if formula results in positive adjustment)
                        # Example: formula = "-(relationship_value * 0.2)" -> rel=50 (friend) -> -(10) -> threat decreases by 10
                        #          formula = "-(relationship_value * 0.2)" -> rel=-50 (enemy) -> -(-10) -> threat increases by 10
                        adjustment = float(eval(formula, {"__builtins__": {}}, {"relationship_value": relationship_val}))
                        threat += adjustment
                    except Exception as e:
                        # Log error
                        pass
            # Legacy/Specific threat factor (can be kept for fine-tuning or removed if formula is preferred)
            elif threat_factors.get("relationship_threat_modifier"): # Check this only if general formula not applied
                # Simplified: if very hostile, add some threat based on old logic
                if relationship_val < -50 : # Arbitrary threshold for "very hostile"
                     threat += 75 * threat_factors.get("relationship_threat_modifier", 0.1) # This factor could be deprecated

        return threat # Higher is better

    # TODO: Implement other metrics like "closest_target", "random", "specific_role_focus"

    return score


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
    """
    available_abilities = []
    actor_props = actor_npc.properties_json or {}
    npc_abilities = actor_props.get("abilities", [])
    if not npc_abilities: # npc_abilities will be [] if properties_json is None or "abilities" key is missing
        return []

    current_resources = actor_combat_data.get("resources", {}) # e.g., {"mana": 50, "stamina": 100}
    active_cooldowns = actor_combat_data.get("cooldowns", {}) # e.g., {"fireball_static_id": 2 (turns remaining)}

    for ability_props in npc_abilities:
        ability_static_id = ability_props.get("static_id")
        if not ability_static_id:
            continue # Skip abilities without static_id for tracking

        # Check cooldown
        if ability_static_id in active_cooldowns and active_cooldowns[ability_static_id] > 0:
            continue

        # Check resource costs
        cost = ability_props.get("cost", {}) # e.g., {"mana": 10}
        can_afford = True
        for resource_type, amount_needed in cost.items():
            if current_resources.get(resource_type, 0) < amount_needed:
                can_afford = False
                break
        if not can_afford:
            continue

        # TODO: Check other conditions if any (e.g. target requirements, self status requirements)
        # conditions = ability_props.get("conditions", {})
        # meets_conditions = True
        # if meets_conditions:
        available_abilities.append(ability_props)

    return available_abilities

async def _simulate_action_outcome(
    session: AsyncSession,
    guild_id: int,
    actor_npc: GeneratedNpc,
    actor_combat_data: Dict[str, Any],
    target_info: Dict[str, Union[Player, GeneratedNpc, Dict[str, Any]]],
    action_details: Dict[str, Any], # e.g. {"type": "attack" or "ability", "ability_props": {}}
    ai_rules: Dict[str, Any],
    combat_engine_api: Any # Mock or actual CombatEngine process_combat_action or a dedicated simulation part
) -> Dict[str, Any]:
    """
    Simulates the outcome of an action to estimate its effectiveness.
    This is a complex function and might involve calling parts of the combat engine.
    Returns a dictionary with simulation results like { 'hit_chance': float, 'expected_damage': float, 'applied_statuses': [] }

    For now, this will be a very simplified placeholder.
    A real version would need to:
    1. Determine check type, actor attribute, target attribute, DC based on action_details and rules.
    2. Call resolve_check.
    3. Estimate damage based on weapon/ability damage formula and resolve_check outcome.
    4. Estimate status application probability.
    """
    # This is a placeholder. A real implementation is significantly more complex.
    # It might need access to a simplified version of `process_combat_action` or `resolve_check`.

    sim_config = ai_rules.get("simulation", {})
    if not sim_config.get("enabled", False):
        # If simulation is disabled in rules, return high confidence to not penalize actions.
        return {"hit_chance": 1.0, "expected_damage": 10.0, "critical_chance": 0.05, "applied_statuses": []}

    # Extremely simplified simulation:
    hit_chance = 0.7 # Base hit chance
    expected_damage = 0
    crit_chance = 0.05

    actor_props = actor_npc.properties_json or {}
    actor_stats = actor_props.get("stats", {})

    if action_details["type"] == "attack":
        # Simulate basic attack
        # TODO: Get weapon damage from actor_props.get("equipment", {})
        expected_damage = actor_stats.get("base_attack_damage", 5)
    elif action_details["type"] == "ability":
        ability_props = action_details.get("ability_props", {})
        # TODO: Parse ability_props for effects (damage, healing, status)
        # For a damage effect:
        damage_effect = next((eff for eff in ability_props.get("effects", []) if eff.get("type") == "damage"), None)
        if damage_effect:
            # Simplified: "1d6+strength_modifier" -> extract base, ignore dice for now
            dmg_formula = damage_effect.get("value", "5") # e.g. "1d6+5" or just "10"
            if isinstance(dmg_formula, str) and 'd' in dmg_formula:
                parts = dmg_formula.split('d') # "1d6" -> parts[1] = "6"
                try:
                    dice_face = int(parts[1].split('+')[0].split('-')[0])
                    num_dice = int(parts[0])
                    expected_damage = num_dice * (dice_face / 2 + 0.5) # Avg roll
                    # Add modifiers if any
                    if '+' in dmg_formula: expected_damage += int(dmg_formula.split('+')[-1])
                    elif '-' in dmg_formula: expected_damage -= int(dmg_formula.split('-')[-1])
                except:
                    expected_damage = 5 # fallback
            else:
                try:
                    expected_damage = int(dmg_formula)
                except:
                    expected_damage = 5 # fallback for non-parsable direct damage
        else:
            expected_damage = 2 # Default for non-damaging abilities or unparsed

    # TODO: Consider target defenses (armor, resistances) from target_info["entity"].properties_json.stats
    # target_defense = target_info["entity"].properties_json.get("stats", {}).get("defense", 0)
    # expected_damage = max(1, expected_damage - target_defense)


    return {
        "hit_chance": hit_chance,
        "expected_damage": expected_damage,
        "critical_chance": crit_chance,
        "applied_statuses": [] # TODO: Simulate status application
    }


async def _evaluate_action_effectiveness(
    session: AsyncSession,
    guild_id: int,
    actor_npc: GeneratedNpc,
    actor_combat_data: Dict[str, Any],
    target_info: Dict[str, Union[Player, GeneratedNpc, Dict[str, Any]]],
    action_details: Dict[str, Any], # e.g. {"type": "attack" or "ability", "ability_props": {}}
    ai_rules: Dict[str, Any]
    # combat_engine_api: Any # Potentially pass a combat engine simulation interface
) -> float:
    """
    Evaluates the 'effectiveness' or 'attractiveness' of a given action against a target.
    Returns a score, where higher is generally better.
    """
    effectiveness_score = 0.0

    # 1. Simulate basic outcome (hit chance, damage)
    # For a real system, combat_engine_api would be used here.
    sim_results = await _simulate_action_outcome(session, guild_id, actor_npc, actor_combat_data, target_info, action_details, ai_rules, None)

    # 2. Basic damage contribution
    # Consider hit chance: effective_damage = expected_damage * hit_chance
    # Consider crit chance: crit_bonus_damage = expected_damage * crit_multiplier * crit_chance
    # For simplicity now:
    effective_damage = sim_results["expected_damage"] * sim_results["hit_chance"]
    effectiveness_score += effective_damage

    # 3. Factor in action type preferences from rules (e.g. prefer abilities that exploit weakness)
    if action_details["type"] == "ability":
        effectiveness_score *= ai_rules.get("action_selection",{}).get("ability_base_effectiveness_multiplier", 1.1) # Slight preference for abilities
        # TODO: Check for target weaknesses / resistances against ability damage type / effects
        # ability_props = action_details.get("ability_props", {})
        # damage_type = ability_props.get("damage_type")
        # target_resistances = target_info["entity"].properties_json.get("resistances", {})
        # if damage_type in target_resistances: effectiveness_score *= (1 - target_resistances[damage_type])

    # 4. Factor in strategic value (e.g. applying a crucial debuff, healing self/ally)
    # This is highly dependent on ability effects and AI rules.
    # Example: if ability applies 'stun' and target is not immune, add significant value.
    if action_details["type"] == "ability":
        ability_props = action_details.get("ability_props", {})
        for effect in ability_props.get("effects", []):
            if effect.get("type") == "apply_status":
                status_static_id = effect.get("status_static_id")
                # TODO: Check target immunity to this status
                # TODO: Get strategic value of this status from ai_rules
                status_value = ai_rules.get("action_selection", {}).get("status_strategic_value", {}).get(status_static_id, 0)
                effectiveness_score += status_value
            elif effect.get("type") == "heal": # Self-heal or ally heal (if NPC can target allies)
                # Healing value could be based on amount healed and current HP deficit
                heal_amount = 0 # parse effect.value
                try:
                    heal_formula = effect.get("value", "5")
                    if isinstance(heal_formula, str) and 'd' in heal_formula: # Simplified dice parsing
                         parts = heal_formula.split('d'); dice_face = int(parts[1].split('+')[0]); num_dice = int(parts[0])
                         heal_amount = num_dice * (dice_face / 2 + 0.5)
                         if '+' in heal_formula: heal_amount += int(heal_formula.split('+')[-1])
                    else: heal_amount = int(heal_formula)
                except: heal_amount = 5

                # Value healing more if actor is low HP
                actor_props = actor_npc.properties_json or {}
                actor_stats = actor_props.get("stats", {})
                actor_max_hp = actor_stats.get("hp",1)
                actor_current_hp = actor_combat_data.get("hp", actor_max_hp)
                hp_deficit_ratio = 1 - (actor_current_hp / actor_max_hp if actor_max_hp > 0 else 1)
                effectiveness_score += heal_amount * (1 + hp_deficit_ratio * ai_rules.get("action_selection",{}).get("low_hp_heal_urgency_multiplier", 2.0))


    # 5. Check against simulation thresholds from rules
    sim_thresholds = ai_rules.get("simulation", {})
    if sim_thresholds.get("enabled", False):
        if sim_results["hit_chance"] < sim_thresholds.get("required_hit_chance_threshold", 0.0):
            return -1.0 # Action is too unreliable

        target_current_hp = target_info["combat_data"].get("hp", 1)
        if target_current_hp <= 0: target_current_hp = 1
        damage_ratio_vs_target_hp = sim_results["expected_damage"] / target_current_hp
        if damage_ratio_vs_target_hp < sim_thresholds.get("min_expected_damage_ratio_vs_target_hp", 0.0):
             # If action is damaging and doesn't do enough relative damage
            if sim_results["expected_damage"] > 0 :
                 return -1.0 # Not impactful enough

    return effectiveness_score


async def _choose_action(
    session: AsyncSession,
    guild_id: int,
    actor_npc: GeneratedNpc,
    actor_combat_data: Dict[str, Any], # Actor's current state in combat
    target_info: Dict[str, Union[Player, GeneratedNpc, Dict[str, Any]]], # Selected target's entity and combat_data
    ai_rules: Dict[str, Any],
    combat_encounter: CombatEncounter # For context
) -> Dict[str, Any]: # Returns a dict describing the chosen action, e.g. {"type": "attack", "source_npc_id": ...}
    """
    Chooses the best action for the actor_npc to take against the target_info.
    """
    possible_actions = []

    # 1. Consider basic attack
    basic_attack_action = {"type": "attack", "name": "Basic Attack"}
    # We always evaluate basic attack, but its effectiveness score will determine if it's chosen.

    # 2. Consider available abilities
    available_abilities = _get_available_abilities(actor_npc, actor_combat_data, ai_rules)
    for ability_prop in available_abilities:
        # TODO: Filter abilities based on target type, range, etc. if applicable
        # For now, assume all available abilities can target the selected_target
        possible_actions.append({"type": "ability", "name": ability_prop.get("name", "Unknown Ability"), "ability_props": ability_prop})

    # Always add basic attack to the list of considerations
    possible_actions.append(basic_attack_action)

    if not possible_actions:
        return {"type": "idle", "reason": "No actions available"} # Should at least have basic attack

    # 3. Evaluate effectiveness of each possible action
    action_evaluations = []
    for action in possible_actions:
        effectiveness = await _evaluate_action_effectiveness(
            session, guild_id, actor_npc, actor_combat_data, target_info, action, ai_rules
        )
        if effectiveness >= 0: # Only consider actions that pass basic simulation checks (not -1.0)
            action_evaluations.append({"action": action, "score": effectiveness})

    if not action_evaluations:
         # If all actions were deemed too ineffective by simulation, fallback to basic attack if possible, or idle.
        # This check is important if _evaluate_action_effectiveness can return very low scores for bad actions.
        # Re-evaluate basic attack with minimal thresholds if everything else failed.
        basic_attack_effectiveness = await _evaluate_action_effectiveness(
            session, guild_id, actor_npc, actor_combat_data, target_info, basic_attack_action,
            {**ai_rules, "simulation": {**ai_rules.get("simulation",{}), "enabled":False}} # Force sim off for fallback
        )
        if basic_attack_effectiveness > 0 : # Simple check if it's not completely useless
             return basic_attack_action
        return {"type": "idle", "reason": "All actions deemed ineffective or failed simulation"}

    # 4. Select best action based on scores and AI rules (e.g., offensive_bias)
    # Sort by score descending
    action_evaluations.sort(key=lambda x: x["score"], reverse=True)

    best_evaluated_action = action_evaluations[0] # Highest score

    # TODO: Implement offensive_bias logic (e.g. if score is low and bias is low, maybe choose a defensive/utility action if available, or idle)
    # offensive_bias = ai_rules.get("action_selection", {}).get("offensive_bias", 0.75)
    # if best_evaluated_action["score"] < ai_rules.get("action_selection",{}).get("min_offensive_score_threshold", 5.0) and offensive_bias < 0.5:
    #     # Look for non-offensive actions or idle
    #     pass

    # Modify action scores based on relationship category with the target
    rel_influence_config = ai_rules.get("relationship_influence", {}).get("npc_combat", {}).get("behavior", {})
    if rel_influence_config.get("enabled", False) and "action_choice" in rel_influence_config:
        action_choice_rules = rel_influence_config["action_choice"]
        current_relationship_val = await _get_relationship_value(
            session, guild_id,
            EntityType.NPC, actor_npc.id,
            EntityType(target_info["combat_data"]["type"]), target_info["combat_data"]["id"]
        )

        if current_relationship_val is not None:
            relationship_category = "neutral" # Default
            if current_relationship_val >= action_choice_rules.get("friendly_positive_threshold", 50):
                relationship_category = "friendly"
            elif current_relationship_val <= action_choice_rules.get("hostile_negative_threshold", -50):
                relationship_category = "hostile"

            rules_for_category = action_choice_rules.get(f"actions_if_{relationship_category}", [])
            if rules_for_category:
                for eval_item in action_evaluations: # eval_item is {"action": action, "score": effectiveness}
                    action_type = eval_item["action"]["type"]
                    ability_static_id = eval_item["action"].get("ability_props", {}).get("static_id") if action_type == "ability" else None

                    for rule_mod in rules_for_category:
                        matches_type = (rule_mod.get("action_type") == action_type)
                        matches_id = (not rule_mod.get("ability_static_id") or rule_mod.get("ability_static_id") == ability_static_id)

                        if matches_type and matches_id:
                            weight_multiplier = rule_mod.get("weight_multiplier", 1.0)
                            eval_item["score"] *= weight_multiplier
                            # Add to a log or debug message that score was modified by relationship rule
                            break # Apply first matching rule modification for this action

                # Re-sort after applying multipliers
                action_evaluations.sort(key=lambda x: x["score"], reverse=True)
                if action_evaluations: # Check if list is not empty after potential modifications
                    best_evaluated_action = action_evaluations[0]


    # TODO: Check for special conditions (e.g., NPC low HP -> prioritize healing ability if available and effective)
    actor_props = actor_npc.properties_json or {}
    actor_stats = actor_props.get("stats", {})
    actor_max_hp = actor_stats.get("hp",1)
    actor_current_hp = actor_combat_data.get("hp", actor_max_hp)
    hp_percentage = (actor_current_hp / actor_max_hp) if actor_max_hp > 0 else 1.0

    heal_threshold = ai_rules.get("action_selection",{}).get("resource_thresholds",{}).get("self_hp_below_for_heal_ability")
    if heal_threshold and hp_percentage < heal_threshold:
        healing_actions = []
        for eval_action in action_evaluations:
            action_props = eval_action["action"].get("ability_props",{})
            is_healing = any(effect.get("type") == "heal" and effect.get("target_scope","self") == "self" for effect in action_props.get("effects",[])) # crude check
            if is_healing:
                healing_actions.append(eval_action)

        if healing_actions: # If there are healing actions, pick the best one among them
            healing_actions.sort(key=lambda x: x["score"], reverse=True)
            # print(f"NPC {actor_npc.id} is low HP ({hp_percentage*100}%), choosing heal: {healing_actions[0]['action']}")
            return healing_actions[0]["action"]


    # print(f"NPC {actor_npc.id} chose action: {best_evaluated_action['action']} with score {best_evaluated_action['score']}")
    return best_evaluated_action["action"]


def _format_action_result(
    chosen_action_details: Dict[str, Any], # The output from _choose_action
    target_info: Dict[str, Union[Player, GeneratedNpc, Dict[str, Any]]] # Selected target
) -> Dict[str, Any]:
    """
    Formats the chosen action into the structure expected by the CombatEngine.
    """
    action_type_str = chosen_action_details["type"] # "attack" or "ability"

    # Convert to CombatActionType enum if CombatEngine expects it, or keep as string
    # For now, assume CombatEngine can handle these strings.
    # combat_action_type = CombatActionType.ATTACK if action_type_str == "attack" else CombatActionType.USE_ABILITY

    target_entity_model = target_info.get("entity") # Use .get for safety on target_info itself
    target_combat_data = target_info.get("combat_data")

    if not isinstance(target_entity_model, (Player, GeneratedNpc)):
        # This case should ideally not be reached if upstream logic is correct.
        # Consider logging an error or raising an exception.
        # For now, return an error-like action or handle as per game design.
        # This addresses Pyright's concern about target_info["entity"] potentially being a Dict.
        return {"action_type": "error", "message": "Invalid target entity type in _format_action_result."}

    if not isinstance(target_combat_data, dict):
        return {"action_type": "error", "message": "Invalid target combat data in _format_action_result."}


    formatted_action = {
        "action_type": action_type_str,
        "target_id": target_entity_model.id, # Now using the validated model instance
        # Ensure target_type is the string value from EntityType enum
        "target_type": target_combat_data.get("type") # Use .get on the dict
    }

    if action_type_str == "ability":
        ability_props = chosen_action_details.get("ability_props", {})
        formatted_action["ability_id"] = ability_props.get("static_id")
        if not formatted_action["ability_id"]:
            # This would be an issue, an ability action must have an ability_id
            # Fallback or error
            # For now, let's assume valid abilities always have static_id from _get_available_abilities
            # TODO: Log error if ability_id is missing for an ability action
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
    """
    Determines the action an NPC will take in combat.
    Orchestrates loading data, selecting a target, choosing an action, and formatting the result.
    """
    # 1. Load core data
    actor_npc = await _get_npc_data(session, npc_id, guild_id)
    if not actor_npc:
        # TODO: Log this error
        return {"action_type": "error", "message": f"NPC {npc_id} not found for guild {guild_id}."}

    combat_encounter = await _get_combat_encounter_data(session, combat_instance_id, guild_id)
    if not combat_encounter:
        # TODO: Log this error
        return {"action_type": "error", "message": f"Combat encounter {combat_instance_id} not found for guild {guild_id}."}

    # Find actor's current combat data (HP, resources, cooldowns, etc.)
    participants_list = combat_encounter.participants_json
    if not isinstance(participants_list, list):
        # TODO: Log this error
        return {"action_type": "error", "message": f"Combat encounter {combat_instance_id} has invalid participants_json format."}

    actor_combat_data = next((p for p in participants_list if isinstance(p, dict) and p.get("id") == actor_npc.id and p.get("type") == EntityType.NPC.value), None)
    if not actor_combat_data:
        # TODO: Log this error - actor NPC not found in participant list of the combat encounter
        return {"action_type": "error", "message": f"Actor NPC {npc_id} not found in combat {combat_instance_id} participants."}

    # If actor is defeated
    if actor_combat_data.get("hp", 0) <= 0:
        return {"action_type": "idle", "reason": "Actor is defeated."}

    # 2. Get AI rules
    ai_rules = await _get_npc_ai_rules(session, guild_id, actor_npc, combat_encounter)

    # 3. Get potential targets
    # Pass participants_list to _get_potential_targets to avoid re-accessing combat_encounter.participants_json
    potential_targets = await _get_potential_targets(session, actor_npc, combat_encounter, ai_rules, guild_id, participants_list)
    if not potential_targets:
       return {"action_type": "idle", "reason": "No targets available."}

    # 4. Select a target
    selected_target_info = await _select_target(session, guild_id, actor_npc, potential_targets, ai_rules, combat_encounter)
    if not selected_target_info:
       return {"action_type": "idle", "reason": "Could not select a target."}

    # If selected target is somehow defeated (should be filtered by _get_potential_targets, but as a safeguard)
    if selected_target_info["combat_data"].get("hp", 0) <= 0:
        # Attempt to pick another target if any are left, or idle.
        remaining_targets = [t for t in potential_targets if t["entity"].id != selected_target_info["entity"].id and t["combat_data"].get("hp",0)>0]
        if remaining_targets:
            selected_target_info = await _select_target(session, guild_id, actor_npc, remaining_targets, ai_rules, combat_encounter)
            if not selected_target_info: # Still no valid target
                 return {"action_type": "idle", "reason": "Selected target defeated, no other valid targets."}
        else: # No other targets left
            return {"action_type": "idle", "reason": "Selected target defeated, no other targets."}


    # 5. Choose an action against the selected target
    chosen_action_details = await _choose_action(
        session, guild_id, actor_npc, actor_combat_data, selected_target_info, ai_rules, combat_encounter
    )

    if chosen_action_details.get("type") == "idle": # If _choose_action decided to be idle
        return {"action_type": "idle", "reason": chosen_action_details.get("reason", "No effective action found.")}

    # 6. Format the result for CombatEngine
    formatted_action = _format_action_result(chosen_action_details, selected_target_info)

    # print(f"[NPC Strategy] Guild: {guild_id}, NPC: {actor_npc.id} ({actor_npc.name_i18n.get('en','N/A')}), Action: {formatted_action}")
    return formatted_action
