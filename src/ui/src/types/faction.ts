// Corresponds to src/models/generated_faction.py

// For displaying faction leader information concisely
export interface FactionLeaderInfo {
  id: number;
  name: string; // Potentially localized
  static_id: string | null;
}

export interface Faction {
  id: number;
  guild_id: number; // Assuming string for guildId in UI context, adjust if needed
  static_id: string | null;
  name_i18n: Record<string, string>;
  description_i18n: Record<string, string>;
  ideology_i18n: Record<string, string> | null;
  leader_npc_id: number | null;
  leader_npc_details?: FactionLeaderInfo | null; // For UI display
  resources_json: Record<string, any> | null;
  ai_metadata_json: Record<string, any> | null;
  // Timestamps from Base model (if returned by API)
  created_at: string; // ISO date string
  updated_at: string; // ISO date string
  // members_count?: number; // Example of additional info UI might want
}

// For API payloads (Create/Update)
// These fields correspond to the parameters of /master_faction create and /master_faction update
export interface FactionPayload {
  static_id: string; // Required for create
  name_i18n_json: string; // Stringified JSON: Record<string, string>
  description_i18n_json?: string; // Stringified JSON: Record<string, string>
  ideology_i18n_json?: string; // Stringified JSON: Record<string, string> | null
  leader_npc_static_id?: string | null; // Static ID of NPC, or null to remove
  resources_json?: string; // Stringified JSON: Record<string, any> | null
  ai_metadata_json?: string; // Stringified JSON: Record<string, any> | null
}

// For the update operation, which takes a field name and a new value
export interface FactionUpdatePayload {
  field_to_update: 'static_id' | 'name_i18n_json' | 'description_i18n_json' | 'ideology_i18n_json' | 'leader_npc_static_id' | 'resources_json' | 'ai_metadata_json';
  new_value: string; // The new value, will be string for JSON fields, static_id, or 'None'
}

// Re-using PaginatedResponse from items.ts or entities.ts if it's generic enough
// Assuming a generic PaginatedResponse structure exists, e.g.:
// import { PaginatedResponse } from './common'; // or './items'
// If not, define it here or ensure it's defined globally
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  // Adjust based on what your actual list commands return, e.g., total_pages
}
