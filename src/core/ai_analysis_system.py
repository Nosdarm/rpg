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
                # i18n completeness
                required_langs_rule = await get_rule(session, guild_id, "analysis:common:i18n_completeness", {"required_languages": ["en", "ru"]})
                required_langs = required_langs_rule.get("required_languages", ["en"])
                i18n_fields_to_check = ["name_i18n", "title_i18n", "description_i18n", "summary_i18n", "ideology_i18n", "role_i18n", "descriptions_i18n"]
                if entity_type_lower == "quest" and "steps" in data and isinstance(data["steps"], list):
                    for step_idx, step_data in enumerate(data["steps"]):
                        if isinstance(step_data, dict):
                            for field_name_i18n in ["title_i18n", "description_i18n"]:
                                if field_name_i18n in step_data:
                                    i18n_content = step_data[field_name_i18n]
                                    if isinstance(i18n_content, dict):
                                        for lang_code in required_langs:
                                            if lang_code not in i18n_content or not i18n_content[lang_code]:
                                                report.issues_found.append(f"Quest Step {step_idx+1}: Missing or empty i18n field '{field_name_i18n}' for lang '{lang_code}'.")
                                    else: report.issues_found.append(f"Quest Step {step_idx+1}: Field '{field_name_i18n}' not a valid i18n dict.")

                for field_name_i18n in i18n_fields_to_check:
                    if field_name_i18n in data:
                        i18n_content = data[field_name_i18n]
                        if isinstance(i18n_content, dict):
                            for lang_code in required_langs:
                                if lang_code not in i18n_content or not i18n_content[lang_code]:
                                    report.issues_found.append(f"Missing or empty i18n field '{field_name_i18n}' for lang '{lang_code}'.")
                        else: report.issues_found.append(f"Field '{field_name_i18n}' is not a valid i18n dictionary.")

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

                # Rule 2: Basic NPC health check
                if entity_type_lower == "npc":
                    npc_stats = data.get("properties_json", {}).get("stats", {})
                    if isinstance(npc_stats, dict):
                        health = npc_stats.get("health")
                        if health is not None: # Allow 0 health if explicitly set, but not None or non-numeric
                            if not isinstance(health, (int, float)):
                                report.issues_found.append(f"NPC 'properties_json.stats.health' is not a number (found: {type(health)}).")
                            elif health <= 0: # Changed from >0 to <=0 for issue reporting
                                report.issues_found.append(f"NPC 'properties_json.stats.health' is not positive ({health}). Consider if this is intended for a non-combatant or defeated NPC.")
                        # else: # Health not present, might be okay depending on NPC type
                        #    report.suggestions.append("NPC 'properties_json.stats.health' is not defined. This might be acceptable for non-combat NPCs.")


                # Recalculate balance score based on new checks potentially adding issues
                report.balance_score = 0.75 if not report.issues_found and not report.validation_errors else 0.25

        except Exception as e_outer_loop:
            logger.error(f"Outer loop error during analysis for {entity_type} item {i}: {e_outer_loop}", exc_info=True)
            report.issues_found.append(f"Critical error during processing for item {i}: {str(e_outer_loop)}")

        result.analysis_reports.append(report)

    num_successful_parses = sum(1 for r in result.analysis_reports if r.parsed_entity_data)
    num_total_issues = sum(len(r.issues_found) + len(r.validation_errors or []) for r in result.analysis_reports)
    result.overall_summary = (
        f"Analyzed {target_count} generated instance(s) of type '{entity_type}'. "
        f"Successfully parsed: {num_successful_parses}/{target_count}. "
        f"Total issues/validation errors found: {num_total_issues}."
    )
    return result
