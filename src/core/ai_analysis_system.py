import logging
import json
from typing import List, Dict, Any, Optional, Union

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_prompt_builder import (
    prepare_quest_generation_prompt,
    prepare_economic_entity_generation_prompt,
    prepare_faction_relationship_generation_prompt,
    prepare_ai_prompt as prepare_general_location_content_prompt,
    _get_entity_schema_terms
)
from src.core.ai_response_parser import parse_and_validate_ai_response, BaseGeneratedEntity, CustomValidationError, ParsedAiData # Added CustomValidationError, ParsedAiData
from src.core.rules import get_rule
from src.core.ai_orchestrator import make_real_ai_call # Import the new function

logger = logging.getLogger(__name__)

class EntityAnalysisReport(BaseModel):
    entity_index: int
    entity_data_preview: Dict[str, Any]
    raw_ai_response: Optional[str] = None
    parsed_entity_data: Optional[Dict[str, Any]] = None
    issues_found: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    balance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    validation_errors: Optional[List[str]] = Field(default_factory=list)
    # New granular scores
    balance_score_details: Dict[str, float] = Field(default_factory=dict)
    lore_score_details: Dict[str, float] = Field(default_factory=dict)
    quality_score_details: Dict[str, float] = Field(default_factory=dict)

class AIAnalysisResult(BaseModel):
    requested_entity_type: str
    requested_target_count: int
    used_real_ai: bool
    generation_context_provided: Optional[Dict[str, Any]] = None
    analysis_reports: List[EntityAnalysisReport] = Field(default_factory=list)
    overall_summary: str = "Analysis complete."

async def analyze_generated_content(
    session: AsyncSession,
    guild_id: int,
    entity_type: str,
    generation_context_json: Optional[str] = None,
    target_count: int = 1,
    use_real_ai: bool = False,
) -> AIAnalysisResult:

    # --- Helper functions for new analysis types ---

    async def _analyze_item_balance(item_data: Dict[str, Any], report: EntityAnalysisReport, session: AsyncSession, guild_id: int):
        """Analyzes balance for a single item."""
        item_type = item_data.get("item_type", "unknown")
        properties = item_data.get("properties_json", {})
        base_value = item_data.get("base_value")

        # 1. Base Value vs. Properties/Rarity
        if base_value is not None and isinstance(base_value, int):
            expected_value_factors = []
            rarity = properties.get("rarity", "common").lower()
            rarity_multiplier_rule = await get_rule(session, guild_id, f"analysis:item:balance:rarity_value_modifier:{rarity}", {"multiplier": 1.0})
            expected_value_factors.append(rarity_multiplier_rule.get("multiplier", 1.0))

            if item_type == "weapon" and isinstance(properties.get("damage"), str):
                # Simplified: Assume higher damage string (e.g. "2d6" > "1d6") means higher value
                # This needs a robust dice string parser for real value comparison.
                # For now, a placeholder:
                damage_value_factor_rule = await get_rule(session, guild_id, "analysis:item:balance:base_value_factors:weapon_damage", {"factor_per_d6_equivalent": 50})
                # Placeholder logic for damage factor
                if "d" in properties["damage"]:
                    try:
                        num_dice, dice_type = map(int, properties["damage"].split('d')[:2])
                        expected_value_factors.append((num_dice * (dice_type / 6.0)) * damage_value_factor_rule.get("factor_per_d6_equivalent", 50))
                    except ValueError:
                        pass # Invalid format

            elif item_type == "armor" and isinstance(properties.get("armor_value"), int):
                ac_factor_rule = await get_rule(session, guild_id, "analysis:item:balance:base_value_factors:armor_ac", {"factor_per_ac_point": 20})
                expected_value_factors.append(properties["armor_value"] * ac_factor_rule.get("factor_per_ac_point", 20))

            if expected_value_factors:
                # Rough calculation: sum of factors scaled by rarity. Min value 1.
                calculated_expected_value = max(1, int(sum(expected_value_factors) * rarity_multiplier_rule.get("multiplier", 1.0)))
                allowed_variance_rule = await get_rule(session, guild_id, "analysis:item:balance:base_value_allowed_variance_percent", {"percentage": 50})
                variance = allowed_variance_rule.get("percentage", 50) / 100.0
                lower_bound = calculated_expected_value * (1 - variance)
                upper_bound = calculated_expected_value * (1 + variance)

                if not (lower_bound <= base_value <= upper_bound):
                    report.issues_found.append(f"Item base_value ({base_value}) seems unbalanced. Expected around {calculated_expected_value} (range {lower_bound:.0f}-{upper_bound:.0f}) based on properties and rarity.")
                    report.balance_score_details["base_value_vs_properties"] = 0.3
                else:
                    report.balance_score_details["base_value_vs_properties"] = 0.8
            else:
                report.balance_score_details["base_value_vs_properties"] = 0.5 # Not enough data to judge

        # 2. Overpowered/Underpowered Properties
        if item_type == "weapon" and isinstance(properties.get("damage"), str):
            # Example: Max average damage for a weapon
            # This would require a dice parser to get average damage from "1d6", "2d8+2" etc.
            # Placeholder: rule for max number of dice
            max_dice_count_rule = await get_rule(session, guild_id, "analysis:item:balance:max_weapon_dice_count", {"count": 3})
            if "d" in properties["damage"]:
                try:
                    num_dice = int(properties["damage"].split('d')[0])
                    if num_dice > max_dice_count_rule.get("count", 3):
                        report.issues_found.append(f"Weapon damage '{properties['damage']}' might be too high (max dice count rule: {max_dice_count_rule.get('count', 3)}).")
                        report.balance_score_details["weapon_damage_cap"] = 0.2
                    else:
                        report.balance_score_details["weapon_damage_cap"] = 0.9
                except ValueError:
                    report.balance_score_details["weapon_damage_cap"] = 0.4 # Malformed

        if item_type == "consumable" and isinstance(properties.get("effect"), str) and "heal" in properties["effect"].lower():
            # Example: Max healing amount for a potion
            # Requires parsing effect string like "heal_2d4+5"
            max_heal_amount_rule = await get_rule(session, guild_id, "analysis:item:balance:max_potion_heal_avg_amount", {"amount": 50})
            # Placeholder: if effect string contains "heal_large" or "heal_critical"
            if "heal_massive" in properties["effect"].lower() or "heal_full" in properties["effect"].lower(): # Simplified
                 report.issues_found.append(f"Potion effect '{properties['effect']}' might be too strong (max heal rule: ~{max_heal_amount_rule.get('amount',50)} avg).")
                 report.balance_score_details["potion_heal_cap"] = 0.2
            else:
                 report.balance_score_details["potion_heal_cap"] = 0.8
        # Add more property checks here...

    async def _analyze_npc_balance(npc_data: Dict[str, Any], report: EntityAnalysisReport, session: AsyncSession, guild_id: int):
        """Analyzes balance for a single NPC."""
        level = npc_data.get("level")
        stats = npc_data.get("properties_json", {}).get("stats", {})

        if level is not None and isinstance(level, int) and isinstance(stats, dict):
            # HP vs Level
            expected_hp_per_level_rule = await get_rule(session, guild_id, "analysis:npc:balance:avg_hp_per_level", {"value": 10})
            hp_variance_rule = await get_rule(session, guild_id, "analysis:npc:balance:hp_variance_percent", {"value": 30})

            npc_hp = stats.get("health")
            if npc_hp is not None and isinstance(npc_hp, (int, float)):
                expected_hp = expected_hp_per_level_rule.get("value", 10) * level
                variance = hp_variance_rule.get("value", 30) / 100.0
                lower_bound_hp = expected_hp * (1 - variance)
                upper_bound_hp = expected_hp * (1 + variance)
                if not (lower_bound_hp <= npc_hp <= upper_bound_hp):
                    report.issues_found.append(f"NPC health ({npc_hp}) seems unbalanced for level {level}. Expected around {expected_hp:.0f} (range {lower_bound_hp:.0f}-{upper_bound_hp:.0f}).")
                    report.balance_score_details["hp_vs_level"] = 0.3
                else:
                    report.balance_score_details["hp_vs_level"] = 0.8
            else:
                report.balance_score_details["hp_vs_level"] = 0.4 # HP not defined or not numeric

            # Attack vs Level (simplified: assuming an 'attack_bonus' or 'avg_damage_output' stat)
            # This needs more definition on how NPC attack capabilities are stored.
            # Placeholder:
            avg_attack_per_level_rule = await get_rule(session, guild_id, "analysis:npc:balance:avg_attack_per_level", {"value": 2}) # e.g. attack bonus
            attack_stat = stats.get("attack_bonus") # or some derived damage stat
            if attack_stat is not None and isinstance(attack_stat, (int, float)):
                expected_attack = avg_attack_per_level_rule.get("value",2) * level
                # Similar variance logic as HP could be applied
                if abs(attack_stat - expected_attack) > (expected_attack * 0.5): # Example: 50% variance allowed
                    report.issues_found.append(f"NPC attack stat ({attack_stat}) seems unbalanced for level {level}. Expected around {expected_attack:.0f}.")
                    report.balance_score_details["attack_vs_level"] = 0.3
                else:
                    report.balance_score_details["attack_vs_level"] = 0.8
            else:
                report.balance_score_details["attack_vs_level"] = 0.5 # Attack stat not clearly defined for analysis

    async def _analyze_quest_balance(quest_data: Dict[str, Any], report: EntityAnalysisReport, session: AsyncSession, guild_id: int):
        """Analyzes balance for a single quest."""
        min_level = quest_data.get("min_level")
        rewards = quest_data.get("rewards_json", {})
        steps = quest_data.get("steps", [])

        if not isinstance(rewards, dict): rewards = {} # Ensure rewards is a dict
        if not isinstance(steps, list): steps = []     # Ensure steps is a list

        # 1. Rewards vs. Level/Complexity
        if min_level is not None and isinstance(min_level, int):
            # XP Reward
            xp_reward = rewards.get("xp")
            if xp_reward is not None and isinstance(xp_reward, int):
                expected_xp_per_level_rule = await get_rule(session, guild_id, "analysis:quest:balance:xp_per_level_point", {"value": 100})
                xp_variance_rule = await get_rule(session, guild_id, "analysis:quest:balance:xp_variance_percent", {"value": 40})

                expected_xp = expected_xp_per_level_rule.get("value", 100) * min_level
                variance_xp = xp_variance_rule.get("value", 40) / 100.0
                lower_bound_xp = expected_xp * (1 - variance_xp)
                upper_bound_xp = expected_xp * (1 + variance_xp)

                if not (lower_bound_xp <= xp_reward <= upper_bound_xp):
                    report.issues_found.append(f"Quest XP reward ({xp_reward}) seems unbalanced for min_level {min_level}. Expected around {expected_xp:.0f} (range {lower_bound_xp:.0f}-{upper_bound_xp:.0f}).")
                    report.balance_score_details["xp_vs_level"] = 0.3
                else:
                    report.balance_score_details["xp_vs_level"] = 0.8
            else:
                report.balance_score_details["xp_vs_level"] = 0.4 # XP reward not defined or not numeric

            # Item Rewards Value (very simplified for now)
            # This would require fetching item data for each item_static_id to get its base_value.
            # For now, let's just count number of items as a proxy for value.
            item_rewards = rewards.get("item_static_ids", [])
            if isinstance(item_rewards, list):
                num_item_rewards = len(item_rewards)
                expected_items_per_level_rule = await get_rule(session, guild_id, "analysis:quest:balance:items_per_level_range", {"max_low_level": 1, "max_mid_level": 2}) # Example rule

                expected_max_items = expected_items_per_level_rule.get("max_mid_level", 2)
                if min_level <= 5: # Example threshold for low level
                    expected_max_items = expected_items_per_level_rule.get("max_low_level", 1)

                if num_item_rewards > expected_max_items:
                    report.issues_found.append(f"Quest offers {num_item_rewards} item rewards, which might be too many for min_level {min_level} (expected max {expected_max_items}).")
                    report.balance_score_details["item_rewards_vs_level"] = 0.3
                elif num_item_rewards > 0 : # some items
                    report.balance_score_details["item_rewards_vs_level"] = 0.7
                else: # no items
                    report.balance_score_details["item_rewards_vs_level"] = 0.5


        # 2. Complexity vs. Level (using number of steps as a proxy)
        num_steps = len(steps)
        if min_level is not None and isinstance(min_level, int):
            max_steps_per_level_rule = await get_rule(session, guild_id, "analysis:quest:balance:max_steps_per_level", {"base": 2, "per_level_add": 0.5})
            expected_max_steps = max_steps_per_level_rule.get("base",2) + int(min_level * max_steps_per_level_rule.get("per_level_add", 0.5))

            if num_steps == 0:
                report.issues_found.append(f"Quest has no steps defined.") # Already caught by Pydantic validator for steps list, but good to have score impact
                report.balance_score_details["steps_complexity"] = 0.1
            elif num_steps > expected_max_steps:
                report.issues_found.append(f"Quest has {num_steps} steps, which might be too complex for min_level {min_level} (expected max ~{expected_max_steps}).")
                report.balance_score_details["steps_complexity"] = 0.3
            else:
                report.balance_score_details["steps_complexity"] = 0.8
        elif num_steps == 0: # No min_level but also no steps
             report.balance_score_details["steps_complexity"] = 0.1

    async def _analyze_text_content_lore(
        text_content: Union[str, Dict[str, str]],
        field_name: str, # e.g., "name_i18n", "description_i18n.en"
        report: EntityAnalysisReport,
        session: AsyncSession,
        guild_id: int,
        entity_type_for_rules: str
    ):
        """Analyzes a text field or i18n dict for lore consistency, restricted words, etc."""
        if not text_content:
            return

        texts_to_check: List[tuple[str, str]] = [] # list of (text, lang_or_field_path)
        if isinstance(text_content, dict):
            for lang, text_val in text_content.items():
                if isinstance(text_val, str) and text_val.strip():
                    texts_to_check.append((text_val, f"{field_name}.{lang}"))
        elif isinstance(text_content, str) and text_content.strip():
            texts_to_check.append((text_content, field_name))

        if not texts_to_check:
            return

        # Rule: Restricted Keywords
        restricted_keywords_global_rule = await get_rule(session, guild_id, "analysis:common:lore:restricted_keywords:global", {"keywords": []})
        restricted_keywords_entity_rule = await get_rule(session, guild_id, f"analysis:{entity_type_for_rules}:lore:restricted_keywords:{field_name.split('.')[0]}", {"keywords": []}) # e.g. analysis:npc:lore:restricted_keywords:description_i18n

        all_restricted_keywords = set(k.lower() for k in restricted_keywords_global_rule.get("keywords", []))
        all_restricted_keywords.update(k.lower() for k in restricted_keywords_entity_rule.get("keywords", []))

        # Rule: Style Keywords (Positive/Negative Indicators)
        # For simplicity, we'll just use one list of "lore-breaking" style words for now.
        lore_style_breaking_rule = await get_rule(session, guild_id, "analysis:common:lore:style_breaking_keywords", {"keywords": ["internet", "computer", "laser gun"]})
        all_restricted_keywords.update(k.lower() for k in lore_style_breaking_rule.get("keywords", []))


        for text, path_info in texts_to_check:
            text_lower = text.lower()
            found_issues_for_text = False
            for keyword in all_restricted_keywords:
                if keyword in text_lower:
                    report.issues_found.append(f"Potentially problematic keyword '{keyword}' found in '{path_info}'.")
                    found_issues_for_text = True

            if found_issues_for_text:
                report.lore_score_details[f"{path_info}_restricted"] = 0.2
            else:
                report.lore_score_details[f"{path_info}_restricted"] = 0.9

    async def _analyze_properties_json_structure(
        properties_data: Optional[Dict[str, Any]],
        report: EntityAnalysisReport,
        session: AsyncSession,
        guild_id: int,
        entity_type_for_rules: str # e.g., "item", "npc"
    ):
        """Analyzes the structure of properties_json based on RuleConfig."""
        if not isinstance(properties_data, dict):
            # report.issues_found.append(f"'{entity_type_for_rules}' properties_json is missing or not a dictionary.")
            # This is usually caught by Pydantic if properties_json is defined as Dict in the model.
            # If it's Any, then this check is useful. For now, assume it's a dict if present.
            report.quality_score_details[f"properties_json_structure_overall"] = 0.3
            return

        # Rule: Required keys in properties_json (can be nested, e.g., "stats.health")
        # Example RuleConfig: "analysis:npc:structure:required_properties_keys": ["stats", "stats.health", "role"]
        required_keys_rule = await get_rule(session, guild_id, f"analysis:{entity_type_for_rules}:structure:required_properties_keys", {"keys": []})
        required_keys = required_keys_rule.get("keys", [])

        all_present = True
        for key_path_str in required_keys:
            path_parts = key_path_str.split('.')
            current_level_data = properties_data
            key_found = True
            for part_idx, key_part in enumerate(path_parts):
                if isinstance(current_level_data, dict) and key_part in current_level_data:
                    if part_idx == len(path_parts) - 1: # Last part, key exists
                        break
                    current_level_data = current_level_data[key_part]
                else: # Key part not found or current_level_data is not a dict to traverse further
                    key_found = False
                    break

            if not key_found:
                report.issues_found.append(f"Missing required key path '{key_path_str}' in '{entity_type_for_rules}.properties_json'.")
                all_present = False

        if not required_keys: # No keys defined to check
             report.quality_score_details[f"properties_json_structure_required"] = 0.7 # Neutral score if no rules
        elif all_present:
            report.quality_score_details[f"properties_json_structure_required"] = 0.9
        else:
            report.quality_score_details[f"properties_json_structure_required"] = 0.2

        # Add more structural checks for properties_json if needed (e.g., type checks for specific keys)


    # --- End of new helper functions ---

    generation_context: Optional[Dict[str, Any]] = None
    if generation_context_json:
        try:
            generation_context = json.loads(generation_context_json)
        except Exception as e:
            logger.warning(f"Could not parse generation_context_json: {e}")

    result = AIAnalysisResult(
        requested_entity_type=entity_type,
        requested_target_count=target_count,
        used_real_ai=use_real_ai,
        generation_context_provided=generation_context if generation_context else {}
    )

    for i in range(target_count):
        report = EntityAnalysisReport(entity_index=i, entity_data_preview={})
        prompt = ""
        try:
            entity_type_lower = entity_type.lower()
            active_generation_context = generation_context or {}

            if entity_type_lower == "quest":
                player_id_ctx = active_generation_context.get("player_id_context")
                location_id_ctx = active_generation_context.get("location_id_context")
                prompt = await prepare_quest_generation_prompt(session, guild_id, player_id_context=player_id_ctx, location_id_context=location_id_ctx)
            elif entity_type_lower == "item":
                prompt = await prepare_economic_entity_generation_prompt(session, guild_id)
            elif entity_type_lower == "npc":
                location_id_ctx = active_generation_context.get("location_id")
                player_id_ctx = active_generation_context.get("player_id")
                party_id_ctx = active_generation_context.get("party_id")
                if location_id_ctx:
                    prompt = await prepare_general_location_content_prompt(session, guild_id, location_id=location_id_ctx, player_id=player_id_ctx, party_id=party_id_ctx)
                else:
                    npc_schema_desc = _get_entity_schema_terms().get("npc_schema", {"description": "Generate an NPC."})
                    prompt = f"Generate one NPC. Context: {active_generation_context}. Schema: {json.dumps(npc_schema_desc)}"
            elif entity_type_lower == "faction":
                prompt = await prepare_faction_relationship_generation_prompt(session, guild_id)
            elif entity_type_lower == "location":
                location_schema_desc = _get_entity_schema_terms().get("location_schema", {"description": "Generate a new game location."})
                prompt = f"Generate a new game location. Context: {active_generation_context}. Schema: {json.dumps(location_schema_desc)}"
            else:
                error_msg = f"Entity type '{entity_type}' is not supported for AI generation analysis via specific prompt builder."
                report.issues_found.append(error_msg)
                result.analysis_reports.append(report)
                if i == 0: result.overall_summary = error_msg
                continue

            raw_response_text = ""
            if use_real_ai:
                # report.issues_found.append("Real AI call functionality is NOT YET IMPLEMENTED in this system.")
                # raw_response_text = f"SKIPPED: Real AI call for {entity_type} {i+1}."
                logger.info(f"Attempting real AI call for {entity_type} {i+1} with prompt (first 100 chars): {prompt[:100]}...")
                raw_response_text = await make_real_ai_call(prompt)
                if raw_response_text.startswith("Error:"):
                    report.issues_found.append(f"Real AI call failed: {raw_response_text}")
                    logger.warning(f"Real AI call for {entity_type} {i+1} failed: {raw_response_text}")
                else:
                    logger.info(f"Real AI call for {entity_type} {i+1} successful. Response length: {len(raw_response_text)}")
            else:
                mock_entity_data = {}
                if entity_type_lower == "npc":
                    mock_entity_data = {
                        "entity_type": "npc", "static_id": f"mock_npc_{i+1}",
                        "name_i18n": {"en": f"Mock NPC {i+1}", "ru": f"Тестовый NPC {i+1}"},
                        "description_i18n": {"en": "A brave mock warrior of the realm.", "ru": "Храбрый тестовый воин королевства."},
                        "level": 5 + i, "properties_json": {"role": "guard", "stats": {"health": 50 + (i*10)}}
                    }
                elif entity_type_lower == "item":
                    mock_entity_data = {
                        "entity_type": "item", "static_id": f"mock_item_{i+1}",
                        "name_i18n": {"en": f"Mock Item {i+1}", "ru": f"Тестовый Предмет {i+1}"},
                        "description_i18n": {"en": "A shiny mock trinket, good for testing various conditions and lengths."},
                        "item_type": "trinket", "base_value": (i+1)*20,
                        "properties_json": {"weight": 10 + i, "rarity": "common" if i % 2 == 0 else "uncommon"}
                    }
                elif entity_type_lower == "quest":
                    mock_entity_data = {
                        "entity_type": "quest", "static_id": f"mock_quest_{i+1}",
                        "title_i18n": {"en": f"Mock Quest {i+1}", "ru": f"Тестовый Квест {i+1}"},
                        "summary_i18n": {"en": "Retrieve the mock artifact for great justice.", "ru": "Добудьте макетный артефакт во имя справедливости."},
                        "steps": [{"step_order":1, "title_i18n": {"en": "S1"}, "description_i18n": {"en": "Desc1"}}, {"step_order":2, "title_i18n": {"en": "S2"}, "description_i18n": {"en":"Desc2"}}],
                        "min_level": 3 + i
                    }
                elif entity_type_lower == "faction":
                    mock_entity_data = {
                        "entity_type": "faction", "static_id": f"mock_faction_{i+1}",
                        "name_i18n": {"en": f"Mock Faction {i+1}", "ru": f"Тестовая Фракция {i+1}"},
                        "description_i18n": {"en": "A test faction with a moderately long description."},
                        "ideology_i18n": {"en": "Testology"}
                    }
                elif entity_type_lower == "location":
                     mock_entity_data = {
                         "entity_type": "location", "static_id": f"mock_loc_{i+1}",
                         "name_i18n": {"en": f"Mock Location {i+1}", "ru": f"Тестовая Локация {i+1}"},
                         "descriptions_i18n": {"en": "A place of mock wonders and tests."},
                         "type": "settlement"
                     }
                else:
                    mock_entity_data = {"error": f"unknown mock type for analysis: {entity_type_lower}"}
                raw_response_text = json.dumps([mock_entity_data])

            report.raw_ai_response = raw_response_text

            # Corrected call to parse_and_validate_ai_response
            parsed_or_error_response = await parse_and_validate_ai_response(
                raw_ai_output_text=raw_response_text,
                guild_id=guild_id
            )

            if isinstance(parsed_or_error_response, CustomValidationError):
                logger.error(f"Validation error for {entity_type} {i+1}: {parsed_or_error_response.message}")
                report.issues_found.append(f"AI Response Validation Error: {parsed_or_error_response.message}")
                if parsed_or_error_response.details:
                    report.validation_errors = [json.dumps(detail) for detail in parsed_or_error_response.details] # Store details as strings
            elif isinstance(parsed_or_error_response, ParsedAiData):
                # Filter for the expected entity type from the parsed data
                filtered_parsed_data = [p for p in parsed_or_error_response.generated_entities if p.entity_type == entity_type_lower]
                if entity_type_lower == "npc" and not filtered_parsed_data: # Special case for npc_trader
                     filtered_parsed_data = [p for p in parsed_or_error_response.generated_entities if p.entity_type == "npc_trader"]

                if filtered_parsed_data:
                    main_parsed_entity = filtered_parsed_data[0]
                    report.parsed_entity_data = main_parsed_entity.model_dump(mode="json")
                    preview_name_en = getattr(main_parsed_entity, 'name_i18n', {}).get('en') or \
                                      getattr(main_parsed_entity, 'title_i18n', {}).get('en')
                    report.entity_data_preview = {"name": preview_name_en or f"Parsed {entity_type} {i+1}",
                                                  "static_id": getattr(main_parsed_entity, 'static_id', 'N/A')}
                else:
                    report.issues_found.append(f"AI response parsed, but no entities of type '{entity_type_lower}' found after filtering.")
            else: # Should not happen if types are correct
                logger.error(f"Unexpected return type from parse_and_validate_ai_response: {type(parsed_or_error_response)}")
                report.issues_found.append("Internal error: Unexpected data type from AI parser.")


            # The following try-except block for e_parse is now less likely to be hit for Pydantic ValidationErrors
            # as they are caught by the CustomValidationError handling above.
            # It might still catch other unexpected errors if parse_and_validate_ai_response raises something else.
            # For safety, keep it, but the specific handling for .errors() might be redundant now.
            # Consider removing or simplifying the specific .errors() attribute check here if CustomValidationError handles it.
            # For now, let's assume CustomValidationError contains the necessary details.
            # The previous `except Exception as e_parse:` block is now effectively part of the CustomValidationError handling.
            # The PydanticNativeValidationError is caught inside parse_and_validate_ai_response and converted.

            if report.parsed_entity_data:
                data = report.parsed_entity_data
                # i18n completeness (Improved to use GuildConfig)
                from src.core.crud import guild_crud as guild_config_crud # Use alias for existing guild_crud
                guild_config = await guild_config_crud.get(session, id=guild_id)
                default_supported_langs = ["en", "ru"] # Fallback if guild_config or supported_languages is not set

                if guild_config and guild_config.supported_languages_json:
                    # Ensure supported_languages_json is a list of strings
                    if isinstance(guild_config.supported_languages_json, list) and \
                       all(isinstance(lang, str) for lang in guild_config.supported_languages_json):
                        required_langs = guild_config.supported_languages_json
                        if not required_langs: # If list is empty, fallback
                             required_langs = default_supported_langs
                    else: # Malformed or not a list
                        logger.warning(f"GuildConfig.supported_languages_json for guild {guild_id} is malformed: {guild_config.supported_languages_json}. Falling back to defaults.")
                        required_langs = default_supported_langs
                else: # No guild_config or no supported_languages_json field
                    required_langs_rule = await get_rule(session, guild_id, "analysis:common:i18n_completeness", {"required_languages": default_supported_langs})
                    required_langs = required_langs_rule.get("required_languages", default_supported_langs)

                i18n_fields_to_check = ["name_i18n", "title_i18n", "description_i18n", "summary_i18n", "ideology_i18n", "role_i18n", "descriptions_i18n"]

                # Check main entity i18n fields
                for field_name_i18n in i18n_fields_to_check:
                    if field_name_i18n in data:
                        i18n_content = data[field_name_i18n]
                        if isinstance(i18n_content, dict):
                            for lang_code in required_langs:
                                if lang_code not in i18n_content or not i18n_content[lang_code]:
                                    report.issues_found.append(f"Missing or empty i18n field '{field_name_i18n}' for required lang '{lang_code}'.")
                                    report.quality_score_details[f"{field_name_i18n}_completeness"] = 0.2
                                else:
                                    report.quality_score_details[f"{field_name_i18n}_completeness_{lang_code}"] = 1.0
                        else:
                            report.issues_found.append(f"Field '{field_name_i18n}' is not a valid i18n dictionary.")
                            report.quality_score_details[f"{field_name_i18n}_completeness"] = 0.1

                # Check quest steps i18n fields
                if entity_type_lower == "quest" and "steps" in data and isinstance(data["steps"], list):
                    for step_idx, step_data in enumerate(data["steps"]):
                        if isinstance(step_data, dict):
                            for field_name_i18n_step in ["title_i18n", "description_i18n"]:
                                if field_name_i18n_step in step_data:
                                    i18n_content_step = step_data[field_name_i18n_step]
                                    step_field_id = f"steps[{step_idx}].{field_name_i18n_step}"
                                    if isinstance(i18n_content_step, dict):
                                        for lang_code in required_langs:
                                            if lang_code not in i18n_content_step or not i18n_content_step[lang_code]:
                                                report.issues_found.append(f"Quest Step {step_idx+1}: Missing or empty i18n field '{field_name_i18n_step}' for lang '{lang_code}'.")
                                                report.quality_score_details[f"{step_field_id}_completeness"] = 0.2
                                            else:
                                                report.quality_score_details[f"{step_field_id}_completeness_{lang_code}"] = 1.0
                                    else:
                                        report.issues_found.append(f"Quest Step {step_idx+1}: Field '{field_name_i18n_step}' not a valid i18n dict.")
                                        report.quality_score_details[f"{step_field_id}_completeness"] = 0.1


                # Description length
                desc_field_key = "descriptions_i18n" if entity_type_lower == "location" else "description_i18n"
                desc_content_dict = data.get(desc_field_key, data.get("summary_i18n", {}))
                if isinstance(desc_content_dict, dict):
                    desc_len_rule = await get_rule(session, guild_id, f"analysis:common:description_length:{entity_type_lower}", {"min": 10, "max": 1000})
                    for lang, text_val in desc_content_dict.items():
                        if isinstance(text_val, str):
                            if not (desc_len_rule.get("min", 0) <= len(text_val) <= desc_len_rule.get("max", float('inf'))):
                                report.issues_found.append(f"Desc/Summary ({lang}) length ({len(text_val)}) outside range [{desc_len_rule.get('min')}-{desc_len_rule.get('max')}].")

                # Key fields & Range checks
                if entity_type_lower == "item":
                    for kf in ["static_id", "name_i18n", "item_type"]:
                        if kf not in data or not data[kf]: report.issues_found.append(f"Item missing key field: '{kf}'.")
                    if "base_value" in data and isinstance(data["base_value"], int):
                        rule = await get_rule(session, guild_id, "analysis:item:field_range:base_value", {"min": 1, "max": 10000})
                        if not (rule.get("min",0) <= data["base_value"] <= rule.get("max", float('inf'))):
                             report.issues_found.append(f"Item base_value ({data['base_value']}) outside range [{rule.get('min')}-{rule.get('max')}].")
                elif entity_type_lower == "npc":
                    for kf in ["static_id", "name_i18n", "description_i18n", "level"]: # Assuming level is top-level
                        if kf not in data or (data[kf] is None and kf !="level"): # level can be 0 but not None for this check
                             report.issues_found.append(f"NPC missing key field: '{kf}'.")
                    if "level" in data and isinstance(data["level"], int):
                        rule = await get_rule(session, guild_id, "analysis:npc:field_range:level", {"min": 1, "max": 100})
                        if not (rule.get("min",0) <= data["level"] <= rule.get("max", float('inf'))):
                             report.issues_found.append(f"NPC level ({data['level']}) outside range [{rule.get('min')}-{rule.get('max')}].")
                elif entity_type_lower == "quest":
                    for kf in ["static_id", "title_i18n", "summary_i18n", "steps"]:
                        if kf not in data or not data[kf]: report.issues_found.append(f"Quest missing key field: '{kf}'.")
                    if "steps" in data and not isinstance(data["steps"], list) or not data["steps"]:
                        report.issues_found.append("Quest 'steps' field is missing, not a list, or empty.")
                    elif "steps" in data:
                        for step_idx, step_data in enumerate(data["steps"]):
                             if not isinstance(step_data, dict) or not all(k in step_data for k in ["step_order", "title_i18n", "description_i18n"]):
                                report.issues_found.append(f"Quest Step {step_idx+1} is malformed or missing key fields (step_order, title_i18n, description_i18n).")
                # Add more for faction, location...

                if not report.issues_found and not report.validation_errors:
                    report.suggestions.append("No obvious issues found based on current basic analysis rules.")

                # Rule 1: Check for placeholder text in i18n fields
                placeholder_texts_rule = await get_rule(session, guild_id, "analysis:common:placeholder_texts", {"placeholders": ["todo", "fixme", "[description needed]", "...", "placeholder", "tbd"]})
                placeholders_to_check = [ph.lower() for ph in placeholder_texts_rule.get("placeholders", [])]

                fields_for_placeholder_check = list(set(i18n_fields_to_check + ["text_i18n"])) # Add any other relevant text fields

                for field_name in fields_for_placeholder_check:
                    if field_name in data:
                        content = data[field_name]
                        if isinstance(content, dict): # i18n dict
                            for lang, text_val in content.items():
                                if isinstance(text_val, str):
                                    for ph in placeholders_to_check:
                                        if ph in text_val.lower():
                                            report.issues_found.append(f"Potential placeholder text '{ph}' found in '{field_name}.{lang}'.")
                        elif isinstance(content, str): # Simple string field
                             for ph in placeholders_to_check:
                                if ph in content.lower():
                                    report.issues_found.append(f"Potential placeholder text '{ph}' found in field '{field_name}'.")

                if entity_type_lower == "quest" and "steps" in data and isinstance(data["steps"], list):
                    for step_idx, step_data in enumerate(data["steps"]):
                        if isinstance(step_data, dict):
                            for field_name_i18n in ["title_i18n", "description_i18n"]:
                                if field_name_i18n in step_data:
                                    i18n_content = step_data[field_name_i18n]
                                    if isinstance(i18n_content, dict):
                                        for lang_code_step, text_val_step in i18n_content.items():
                                            if isinstance(text_val_step, str):
                                                for ph in placeholders_to_check:
                                                    if ph in text_val_step.lower():
                                                        report.issues_found.append(f"Quest Step {step_idx+1}: Placeholder '{ph}' in '{field_name_i18n}.{lang_code_step}'.")
                                    # else: report.issues_found.append(f"Quest Step {step_idx+1}: Field '{field_name_i18n}' not a valid i18n dict for placeholder check.") # Already checked above

                # Rule 2: Basic NPC health check (now partially covered by _analyze_npc_balance)
                if entity_type_lower == "npc":
                    # Existing check for non-positive health
                    npc_stats_original = data.get("properties_json", {}).get("stats", {})
                    if isinstance(npc_stats_original, dict):
                        health_original = npc_stats_original.get("health")
                        if health_original is not None:
                            if not isinstance(health_original, (int, float)):
                                # This specific check for type might be redundant if Pydantic models are strict enough,
                                # but good for robustness if properties_json is very flexible.
                                if "NPC 'properties_json.stats.health' is not a number" not in " ".join(report.issues_found): # Avoid duplicate
                                    report.issues_found.append(f"NPC 'properties_json.stats.health' is not a number (found: {type(health_original)}).")
                            elif health_original <= 0:
                                if "NPC 'properties_json.stats.health' is not positive" not in " ".join(report.issues_found): # Avoid duplicate
                                    report.issues_found.append(f"NPC 'properties_json.stats.health' is not positive ({health_original}). Consider if this is intended for a non-combatant or defeated NPC.")
                    # Call new balance analysis for NPC
                    await _analyze_npc_balance(data, report, session, guild_id)

                elif entity_type_lower == "item":
                    await _analyze_item_balance(data, report, session, guild_id)
                elif entity_type_lower == "quest":
                    await _analyze_quest_balance(data, report, session, guild_id)
                # Add calls to other specific analyzers here (e.g., faction, location)

                # --- Call properties_json structure analyzer ---
                if entity_type_lower in ["item", "npc"]: # Extend to other types if they use properties_json extensively
                    await _analyze_properties_json_structure(data.get("properties_json"), report, session, guild_id, entity_type_lower)

                # --- Call Lore/Text Analyzer for relevant fields ---
                fields_to_check_lore = []
                if entity_type_lower in ["npc", "item", "faction", "location"]:
                    fields_to_check_lore.extend(["name_i18n", "description_i18n"])
                    if entity_type_lower == "faction":
                        fields_to_check_lore.append("ideology_i18n")
                    if entity_type_lower == "location": # Location uses descriptions_i18n
                        fields_to_check_lore.remove("description_i18n")
                        fields_to_check_lore.append("descriptions_i18n")
                elif entity_type_lower == "quest":
                    fields_to_check_lore.extend(["title_i18n", "summary_i18n"])
                    if "steps" in data and isinstance(data["steps"], list):
                        for step_idx, step_data_lore in enumerate(data["steps"]):
                            if isinstance(step_data_lore, dict):
                                await _analyze_text_content_lore(step_data_lore.get("title_i18n"), f"steps[{step_idx}].title_i18n", report, session, guild_id, entity_type_lower)
                                await _analyze_text_content_lore(step_data_lore.get("description_i18n"), f"steps[{step_idx}].description_i18n", report, session, guild_id, entity_type_lower)

                for field_name_lore in fields_to_check_lore:
                    if field_name_lore in data: # Ensure field exists before passing
                        await _analyze_text_content_lore(data[field_name_lore], field_name_lore, report, session, guild_id, entity_type_lower)


                # --- Recalculate overall balance score based on details ---
                if report.balance_score_details:
                    total_score = sum(report.balance_score_details.values())
                    num_scores = len(report.balance_score_details)
                    report.balance_score = (total_score / num_scores) if num_scores > 0 else 0.5 # Default if no specific scores
                elif not report.issues_found and not report.validation_errors : # Fallback to old logic if no details
                    report.balance_score = 0.75
                else:
                    report.balance_score = 0.25


        except Exception as e_outer_loop:
            logger.error(f"Outer loop error during analysis for {entity_type} item {i}: {e_outer_loop}", exc_info=True)
            report.issues_found.append(f"Critical error during processing for item {i}: {str(e_outer_loop)}")

        result.analysis_reports.append(report)

    # --- Post-loop analysis (e.g., uniqueness across generated entities) ---
    all_generated_static_ids: Dict[str, int] = {} # static_id -> entity_index
    all_generated_names_i18n: Dict[str, Dict[str, int]] = {} # lang -> {name_text -> entity_index}

    for report_item in result.analysis_reports:
        if report_item.parsed_entity_data:
            p_data = report_item.parsed_entity_data
            static_id = p_data.get("static_id")
            if static_id:
                if static_id in all_generated_static_ids:
                    original_index = all_generated_static_ids[static_id]
                    current_index = report_item.entity_index
                    issue_msg = f"Duplicate static_id '{static_id}' found across generated entities (indices {original_index} and {current_index})."
                    result.analysis_reports[original_index].issues_found.append(issue_msg)
                    result.analysis_reports[current_index].issues_found.append(issue_msg)
                    result.analysis_reports[original_index].quality_score_details["batch_static_id_uniqueness"] = 0.1
                    result.analysis_reports[current_index].quality_score_details["batch_static_id_uniqueness"] = 0.1
                else:
                    all_generated_static_ids[static_id] = report_item.entity_index
                    report_item.quality_score_details["batch_static_id_uniqueness"] = 1.0 # Mark as unique initially

            name_field = p_data.get("name_i18n") or p_data.get("title_i18n")
            if isinstance(name_field, dict):
                for lang, name_text in name_field.items():
                    if isinstance(name_text, str) and name_text:
                        if lang not in all_generated_names_i18n:
                            all_generated_names_i18n[lang] = {}

                        if name_text in all_generated_names_i18n[lang]:
                            original_index_name = all_generated_names_i18n[lang][name_text]
                            current_index_name = report_item.entity_index
                            name_issue_msg = f"Duplicate name/title '{name_text}' (lang: {lang}) found across generated entities (indices {original_index_name} and {current_index_name})."
                            result.analysis_reports[original_index_name].issues_found.append(name_issue_msg)
                            result.analysis_reports[current_index_name].issues_found.append(name_issue_msg)
                            result.analysis_reports[original_index_name].quality_score_details[f"batch_name_uniqueness_{lang}"] = 0.1
                            result.analysis_reports[current_index_name].quality_score_details[f"batch_name_uniqueness_{lang}"] = 0.1
                        else:
                            all_generated_names_i18n[lang][name_text] = report_item.entity_index
                            report_item.quality_score_details[f"batch_name_uniqueness_{lang}"] = 1.0


    # --- Finalize scores and summary ---
    for report_item_final in result.analysis_reports:
        # Aggregate quality_score_details
        if report_item_final.quality_score_details:
            q_total = sum(report_item_final.quality_score_details.values())
            q_num = len(report_item_final.quality_score_details)
            report_item_final.quality_score_details["overall_quality_avg"] = (q_total / q_num) if q_num > 0 else 0.5

        # Aggregate lore_score_details
        if report_item_final.lore_score_details:
            l_total = sum(report_item_final.lore_score_details.values())
            l_num = len(report_item_final.lore_score_details)
            report_item_final.lore_score_details["overall_lore_avg"] = (l_total / l_num) if l_num > 0 else 0.5

        # Balance score already calculated per entity

    num_successful_parses = sum(1 for r in result.analysis_reports if r.parsed_entity_data)
    num_total_issues = sum(len(r.issues_found) + len(r.validation_errors or []) for r in result.analysis_reports)
    result.overall_summary = (
        f"Analyzed {target_count} generated instance(s) of type '{entity_type}'. "
        f"Successfully parsed: {num_successful_parses}/{target_count}. "
        f"Total issues/validation errors found: {num_total_issues}."
    )
    return result
