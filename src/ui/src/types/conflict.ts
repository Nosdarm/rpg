// Corresponds to src/models/enums.py -> ConflictStatus
export enum UIConflictStatus {
  PENDING_MASTER_RESOLUTION = "pending_master_resolution",
  RESOLVED_AUTOMATICALLY_CONTINUE = "resolved_automatically_continue",
  RESOLVED_AUTOMATICALLY_REJECT = "resolved_automatically_reject",
  RESOLVED_BY_MASTER_APPROVED = "resolved_by_master_approved",
  RESOLVED_BY_MASTER_REJECTED = "resolved_by_master_rejected",
  RESOLVED_BY_MASTER_DISMISS = "resolved_by_master_dismiss",
  RESOLVED_BY_MASTER_FAVOR_ACTION1 = "resolved_by_master_favor_action1",
  RESOLVED_BY_MASTER_FAVOR_ACTION2 = "resolved_by_master_favor_action2",
  RESOLVED_BY_MASTER_CUSTOM_ACTION = "resolved_by_master_custom_action",
  EXPIRED = "expired",
  SIMULATED_INTERNAL_CONFLICT = "simulated_internal_conflict",
}

export interface UIConflictListItem {
  id: number;
  status: UIConflictStatus;
  created_at: string; // ISO date string
  involved_entities_summary: string; // e.g., "Player1 vs Player2" or "Actions of 3 players"
}

export interface UIConflictActionEntity {
  type: "player" | "generated_npc" | "party" | "global_npc" | "mobile_group" | "unknown"; // From RelationshipEntityType & others
  id: number;
  name?: string; // Optional: if available from backend or resolved by UI
}

export interface UIConflictParsedAction {
  raw_text?: string; // Optional, as it might not always be present or relevant for UI
  intent: string;
  entities: UIConflictActionEntity[];
  confidence?: number;
  // details_json could be used to store specific parameters of the action,
  // e.g., {"item_id": 123, "target_id": 456} for a "use_item" intent.
  // For UI, it's often better to have more structured fields if known,
  // but Record<string, any> provides flexibility.
  details_json?: Record<string, any>;
}

// Represents one of the conflicting actions/actors in involved_entities_json or conflicting_actions_json
export interface UIConflictInvolvedUnit {
  actor: UIConflictActionEntity;
  action: UIConflictParsedAction;
  // conflicting_actions_json may also contain original_action_id from PlayerActionQueue
  original_action_id?: number;
}

export interface UIConflictDetails {
  id: number;
  guild_id: string;
  // involved_entities_json on backend is List[Dict], where each dict has 'actor' and 'action'.
  // conflicting_actions_json on backend is List[Dict] similar to involved_entities_json.
  // For UI, we'll type them as UIConflictInvolvedUnit[]
  involved_entities: UIConflictInvolvedUnit[];
  conflicting_actions: UIConflictInvolvedUnit[]; // This might be redundant if involved_entities covers all conflicting parties
  status: UIConflictStatus;
  resolution_notes?: string;
  // resolved_action_json on backend is a single ParsedAction (as dict)
  resolved_action?: UIConflictParsedAction;
  created_at: string; // ISO date string
  resolved_at?: string; // ISO date string
}

export interface UIMasterOutcomeOption {
  id: string; // e.g., "RESOLVED_BY_MASTER_FAVOR_ACTION1", corresponds to ConflictStatus enum member name
  name_key: string; // Key for localization, e.g., "conflict_resolution:outcome_favor_action1"
}

export interface UIResolveConflictPayload {
  outcome_status: string; // The id from UIMasterOutcomeOption
  notes?: string;
}

// Re-using PaginatedResponse from entities.ts
// import { PaginatedResponse } from "./entities";
// If PaginatedResponse is not globally available, it should be imported here.
// For now, assuming it's accessible or will be made so.
// No, explicit import is better.
// However, to avoid circular dependencies if entities.ts also imports from conflict.ts (unlikely here),
// it's often placed in a general types file or PaginatedResponse is defined in each file needing it.
// For this task, we'll assume it can be imported.
// If entities.ts is small and stable, direct import is fine.
// import { PaginatedResponse } from './entities'; // Let's assume this will work.
// If it causes issues, one might define a local PaginatedResponse<UIConflictListItem> here.
// For AGENTS.md, I'll note it uses the existing PaginatedResponse.
// The actual import line will be added to the file by the UI dev or if issues arise.
// For now, the type conflictService.ts will correctly reference PaginatedResponse<UIConflictListItem>.

// Placeholder for PaginatedResponse if it's not imported, to make this file self-contained for review.
// This would be removed if the import from './entities' works.
// export interface PaginatedResponse<T> {
//   items: T[];
//   current_page: number;
//   total_pages: number;
//   total_items: number;
//   limit_per_page: number;
// }
// No, I will rely on the existing PaginatedResponse from entities.ts as stated in the plan.
// The UI dev would add `import { PaginatedResponse } from "./entities";` at the top.
