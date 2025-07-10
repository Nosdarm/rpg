// Corresponds to src/models/enums.py ModerationStatus
export enum UIMRModerationStatus {
  PENDING_MODERATION = "PENDING_MODERATION",
  VALIDATION_FAILED = "VALIDATION_FAILED",
  APPROVED = "APPROVED",
  REJECTED = "REJECTED",
  SAVED = "SAVED",
  ERROR_ON_SAVE = "ERROR_ON_SAVE",
  EDITED_PENDING_APPROVAL = "EDITED_PENDING_APPROVAL",
}

// Corresponds to src/models/pending_generation.py PendingGeneration
export interface UIPendingGeneration {
  id: number;
  guild_id: number;
  triggered_by_user_id: number | null;
  trigger_context_json: Record<string, any> | null; // e.g., {"requested_entity_type": "npc", "theme": "dark_forest"}
  ai_prompt_text: string | null;
  raw_ai_response_text: string | null;
  parsed_validated_data_json: Record<string, any> | null; // This would contain the actual generated entity data
  validation_issues_json: Record<string, any> | null; // e.g., {"errors": ["Field X is missing"], "warnings": []}
  status: UIMRModerationStatus;
  master_id: number | null; // User ID of the master who reviewed
  master_notes: string | null;
  created_at: string; // ISO date string
  updated_at: string; // ISO date string
}

// Payload for triggering a new generation
export interface TriggerGenerationPayload {
  entity_type: string; // e.g., "location", "npc", "item", "quest", "faction"
  generation_context_json?: Record<string, any> | null; // Specific context for generation
  location_id_context?: number | null;
  player_id_context?: number | null;
}

// Payload for updating a pending generation (e.g., for reject, edit)
export interface UpdatePendingGenerationPayload {
  new_status?: UIMRModerationStatus | string; // Allow string for choice compatibility, backend validates
  new_parsed_data_json?: Record<string, any> | null; // For edits
  master_notes?: string | null;
}

// Response for listing pending generations might use PaginatedResponse<UIPendingGeneration>
// from entities.ts if the API returns pagination in that format.
// Otherwise, define a specific list response type if needed.
// For now, assuming PaginatedResponse will be used.
