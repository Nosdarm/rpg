import { PaginatedResponse } from './entities'; // Assuming PaginatedResponse is suitable

// Corresponds to src/models/global_npc.py GlobalNpc
export interface GlobalNpcData {
  id: number;
  guild_id: number;
  static_id: string;
  name_i18n: Record<string, string>;
  description_i18n?: Record<string, string> | null;
  current_location_id?: number | null;
  base_npc_id?: number | null; // Refers to GeneratedNpc.id
  mobile_group_id?: number | null;
  properties_json: Record<string, any>; // For route, goals, status, current_hp etc.
  // ai_metadata_json is likely backend-internal, not directly managed by user via simple CRUD
  created_at: string; // ISO date string
  updated_at: string; // ISO date string

  // Optional enriched data
  current_location_name?: string; // If resolved by UI/API Gateway
  base_npc_name?: string; // If resolved
  mobile_group_name?: string; // If resolved
}

export interface GlobalNpcPayload {
  static_id: string;
  name_i18n_json: string; // JSON string for Record<string, string>
  description_i18n_json?: string | null; // JSON string
  current_location_id?: number | null;
  base_npc_id?: number | null;
  mobile_group_id?: number | null;
  properties_json?: string | null; // JSON string for Record<string, any>
                                 // e.g., {"route": {...}, "current_hp": 100, "status": "patrolling"}
}

// For partial updates, similar to how master commands work (field_to_update, new_value)
// However, a more RESTful approach would be Partial<GlobalNpcPayload>
// For now, let's define a more flexible update payload if the API supports bulk field updates.
// If API is strictly field by field, this might need to be different or handled in the service.
export interface GlobalNpcUpdatePayload {
  static_id?: string;
  name_i18n_json?: string;
  description_i18n_json?: string | null;
  current_location_id?: number | null;
  base_npc_id?: number | null;
  mobile_group_id?: number | null; // Can be null to remove from group
  properties_json?: string | null;
}


// Corresponds to src/models/mobile_group.py MobileGroup
export interface MobileGroupData {
  id: number;
  guild_id: number;
  static_id: string;
  name_i18n: Record<string, string>;
  description_i18n?: Record<string, string> | null;
  current_location_id?: number | null;
  leader_global_npc_id?: number | null;
  members_definition_json: Record<string, any>[]; // List of member definitions
  behavior_type_i18n?: Record<string, string> | null;
  route_json?: Record<string, any> | null;
  properties_json?: Record<string, any> | null; // For status, goals etc.
  // ai_metadata_json not typically user-managed in simple CRUD
  created_at: string; // ISO date string
  updated_at: string; // ISO date string

  // Optional enriched data
  current_location_name?: string;
  leader_global_npc_name?: string;
  member_details?: GlobalNpcData[]; // List of full GlobalNpcData for members
}

export interface MobileGroupPayload {
  static_id: string;
  name_i18n_json: string; // JSON string
  description_i18n_json?: string | null; // JSON string
  current_location_id?: number | null;
  leader_global_npc_id?: number | null;
  members_definition_json?: string | null; // JSON string for List<Record<string, any>>
                                         // e.g., [{"global_npc_static_id": "guard1", "role_i18n": {"en":"Guard"}}]
  behavior_type_i18n_json?: string | null; // JSON string
  route_json?: string | null; // JSON string
  properties_json?: string | null; // JSON string
}

export interface MobileGroupUpdatePayload {
  static_id?: string;
  name_i18n_json?: string;
  description_i18n_json?: string | null;
  current_location_id?: number | null;
  leader_global_npc_id?: number | null;
  members_definition_json?: string | null;
  behavior_type_i18n_json?: string | null;
  route_json?: string | null;
  properties_json?: string | null;
}

// GlobalEvent - Deferred due to lack of master commands for now
/*
export interface GlobalEventData {
  id: number;
  guild_id: number;
  static_id: string;
  name_i18n: Record<string, string>;
  description_i18n: Record<string, string>;
  event_type: string;
  location_id?: number | null;
  trigger_time?: string | null; // ISO date string
  expiration_time?: string | null; // ISO date string
  status: string; // e.g., "pending", "active", "expired", "completed"
  properties_json: Record<string, any>;
  created_at: string;
  updated_at: string;

  location_name?: string;
}

export interface GlobalEventPayload {
  static_id: string;
  name_i18n_json: string;
  description_i18n_json: string;
  event_type: string;
  location_id?: number | null;
  trigger_time_iso?: string | null;
  expiration_time_iso?: string | null;
  status?: string;
  properties_json?: string | null;
}

export interface GlobalEventUpdatePayload {
  static_id?: string;
  name_i18n_json?: string;
  description_i18n_json?: string;
  event_type?: string;
  location_id?: number | null;
  trigger_time_iso?: string | null;
  expiration_time_iso?: string | null;
  status?: string;
  properties_json?: string | null;
}
*/

// Re-export PaginatedResponse if it's not globally available or for clarity
// export { PaginatedResponse } from './entities'; // Already imported above
