// src/ui/src/types/simulation.ts

// --- Common Enum for Actor/Target Types ---
export enum UIRelationshipEntityType {
  PLAYER = "player",
  GENERATED_NPC = "generated_npc",
  ITEM = "item", // If items can be actors/targets in checks
  LOCATION = "location", // If locations can be actors/targets
  // Add other relevant types from src/models/enums.py RelationshipEntityType
  UNKNOWN = "unknown",
  PARTY = "party",
  GLOBAL_NPC = "global_npc",
  MOBILE_GROUP = "mobile_group",
  FACTION = "faction",
  OBJECT = "object", // For generic world objects if applicable in checks
}

// --- Interfaces for Simulate Check ---

export interface IModifierDetail {
  source: string;
  value: number;
  description?: string | null;
}

export interface ICheckOutcome {
  status: string; // e.g., "success", "failure", "critical_success"
  description?: string | null;
}

export interface IUICheckResult {
  guild_id: number;
  check_type: string;
  entity_doing_check_id: number;
  entity_doing_check_type: string; // Consider UIRelationshipEntityType
  target_entity_id?: number | null;
  target_entity_type?: string | null; // Consider UIRelationshipEntityType
  difficulty_class?: number | null;
  dice_notation: string;
  raw_rolls: number[];
  roll_used: number;
  total_modifier: number;
  modifier_details: IModifierDetail[];
  final_value: number;
  outcome: ICheckOutcome;
  rule_config_snapshot?: Record<string, any> | null;
  check_context_provided?: Record<string, any> | null;
}

export interface UISimulateCheckParams {
  check_type: string;
  actor_id: number;
  actor_type: string; // Should map to UIRelationshipEntityType values
  target_id?: number;
  target_type?: string; // Should map to UIRelationshipEntityType values
  difficulty_dc?: number;
  json_context?: string; // JSON string
}

// --- Interfaces for Simulate Combat Action ---

export interface UICombatActionResult {
  success: boolean;
  action_type: string;
  actor_id: number;
  actor_type: string; // "player" or "npc"
  target_id?: number | null;
  target_type?: string | null; // "player" or "npc"
  damage_dealt?: number | null;
  healing_done?: number | null;
  status_effects_applied?: Array<Record<string, any>> | null;
  status_effects_removed?: Array<Record<string, any>> | null;
  check_result?: IUICheckResult | null;
  description_i18n?: Record<string, string> | null;
  costs_paid?: Array<Record<string, any>> | null;
  additional_details?: Record<string, any> | null;
  // This field is added based on the command output showing participant states
  participants_json_post_action?: { entities: Array<Record<string, any>> } | null;
}

export interface UISimulateCombatActionParams {
  combat_encounter_id: number;
  actor_id: number;
  actor_type: string; // "player" or "generated_npc"
  action_json_data: string; // JSON string for the action
  dry_run?: boolean;
}

// --- Interfaces for Simulate Conflict ---

export interface UIActionEntity {
  type: string;
  value: string;
  // confidence?: number | null; // Based on ParsedAction, but optional in command
  // source?: string | null;     // Based on ParsedAction, but optional in command
}

export interface UIInputParsedAction {
  raw_text: string;
  intent: string;
  entities: UIActionEntity[];
  // guild_id?: number | null; // Not needed from UI as it's context
  // player_id?: number | null; // Not needed from UI as actor_id is primary
}

export interface UIInputConflictAction {
  actor_id: number;
  actor_type: string; // "player" or "generated_npc"
  parsed_action: UIInputParsedAction;
}

export interface UISimulateConflictParams {
  actions_json: string; // JSON string of List<UIInputConflictAction>
}

export interface UIPydanticConflictForSim {
  guild_id: number;
  conflict_type: string;
  status: string; // From ConflictStatus enum
  involved_entities_json: Array<{
    entity_id: number;
    entity_type: string;
    action_intent: string;
    action_text: string;
    action_entities: UIActionEntity[]; // Added this based on command output
  }>;
  resolution_details_json: Record<string, any>;
  turn_number: number;
  conflicting_actions_json?: Array<Record<string, any>> | null;
}

// --- Interfaces for Analyze AI Generation ---

export enum UIAnalyzableEntityType {
  NPC = "npc",
  ITEM = "item",
  QUEST = "quest",
  LOCATION = "location",
  FACTION = "faction",
}

export interface UIAnalyzeAiGenerationParams {
  entity_type: UIAnalyzableEntityType | string; // Allow string for flexibility if enum not strictly enforced by input
  generation_context_json?: string; // JSON string
  target_count: number;
  use_real_ai?: boolean;
}

export interface UIEntityAnalysisReport {
  entity_index: number;
  entity_data_preview: Record<string, any>;
  raw_ai_response?: string | null;
  parsed_entity_data?: Record<string, any> | null;
  issues_found: string[];
  suggestions: string[];
  balance_score?: number | null;
  validation_errors?: string[] | null; // Assuming stringified JSON from backend
  balance_score_details: Record<string, number>;
  lore_score_details: Record<string, number>;
  quality_score_details: Record<string, number>;
}

export interface UIAiAnalysisResult {
  requested_entity_type: string;
  requested_target_count: number;
  used_real_ai: boolean;
  generation_context_provided?: Record<string, any> | null;
  analysis_reports: UIEntityAnalysisReport[];
  overall_summary: string;
}

// Log that the file is defined
console.log("src/ui/src/types/simulation.ts defined");
export {}; // Make this a module
