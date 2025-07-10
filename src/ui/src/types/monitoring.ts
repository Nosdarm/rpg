// Based on src/models/enums.py EventType
// It's a large enum, so for brevity in this example, we'll list a few
// and assume the UI team will populate it fully or use a more dynamic way if needed.
export type UIEventType =
  | "player_action"
  | "npc_action"
  | "system_event"
  | "combat_start"
  | "combat_action"
  | "combat_end"
  | "movement"
  | "dialogue_start"
  | "dialogue_line"
  | "dialogue_end"
  | "world_event_quests_generated"
  | "quest_accepted"
  | "quest_step_completed"
  | "quest_completed"
  | "quest_failed"
  | "item_acquired"
  | "item_lost"
  | "item_used"
  | "item_dropped"
  | "trade_initiated"
  | "trade_completed"
  | "trade_item_bought"
  | "trade_item_sold"
  | "level_up"
  | "xp_gained"
  | "relationship_change"
  | "faction_change"
  | "world_state_change"
  | "master_command"
  | "error_event"
  | "ability_used"
  | "status_applied"
  | "status_removed"
  | "ai_generation_triggered"
  | "ai_response_received"
  | "ai_content_validation_success"
  | "ai_content_validation_failed"
  | "ai_content_approved"
  | "ai_content_rejected"
  | "ai_content_edited"
  | "ai_content_saved"
  | "attribute_points_spent"
  | "world_event_location_generated"
  | "master_action_location_added"
  | "master_action_location_removed"
  | "master_action_locations_connected"
  | "master_action_locations_disconnected"
  | "world_event_factions_generated"
  | "world_event_economic_entities_generated"
  | "global_entity_moved"
  | "global_entity_detected_entity"
  | "global_entity_action"
  | "ge_triggered_dialogue_placeholder"
  | "turn_start"
  | "turn_end"
  | string; // Allow any string for future-proofing if the list isn't exhaustive

// Based on src/models/story_log.py StoryLog
export interface UIStoryLogData {
  id: number;
  guild_id: string; // Guild IDs are typically snowflakes (strings)
  timestamp: string; // ISO DateTime string
  event_type: UIEventType;
  location_id?: number | null;
  entity_ids_json?: Record<string, any> | null; // e.g., {"player_ids": [1], "npc_ids": [101]}
  details_json?: Record<string, any> | null; // Event-specific structured data
  narrative_i18n?: Record<string, string> | null; // Raw narrative from AI/system
  turn_number?: number | null;

  // Optional pre-formatted message for display, potentially provided by backend
  // This aligns with "Format log entries (API 47) for display" from Task 64 description
  formatted_message?: string;
  // Or, if i18n formatting happens on UI based on templates:
  // formatted_narrative_i18n?: Record<string, string>;
}

export interface UIStoryLogFilterParams {
  page?: number;
  limit?: number;
  event_type?: UIEventType;
  // Add other potential filters if supported by API:
  // location_id?: number;
  // involved_entity_id?: number; // This would require backend to parse entity_ids_json
  // date_from?: string; // ISO date string
  // date_to?: string; // ISO date string
}

// Re-export PaginatedResponse if common, or define specific if structure varies
// For now, assuming common PaginatedResponse from entities.ts will be used by service
// import { PaginatedResponse } from './entities';
// export type PaginatedStoryLogResponse = PaginatedResponse<UIStoryLogData>;
