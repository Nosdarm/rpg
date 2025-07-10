// Corresponds to src/models/player.py
export interface Player {
  id: number;
  guild_id: number;
  discord_id: string;
  name: string;
  level: number;
  xp: number;
  unspent_xp: number;
  gold: number;
  current_hp: number | null;
  max_hp: number | null; // This might be calculated or stored if available
  current_status: string; // Corresponds to PlayerStatus enum, e.g., "IDLE", "EXPLORING", "IN_COMBAT"
  selected_language: string | null;
  current_location_id: number | null;
  current_party_id: number | null;
  attributes_json: Record<string, any>; // e.g., {"strength": 10, "dexterity": 12}
  inventory?: EnrichedInventoryItem[]; // Added for inventory details
  created_at: string; // ISO date string
  updated_at: string; // ISO date string
}

// Corresponds to src/models/generated_npc.py
export interface GeneratedNpc {
  id: number;
  guild_id: number;
  static_id: string | null;
  name_i18n: Record<string, string>; // e.g., {"en": "Guard", "ru": "Стражник"}
  description_i18n: Record<string, string>;
  npc_type_i18n: Record<string, string>; // Role or type, e.g., {"en": "Merchant", "ru": "Торговец"}
  faction_id: number | null;
  current_location_id: number | null;
  properties_json: Record<string, any>; // e.g., {"stats": {"hp": 50, "attack": 5}, "role": "merchant", "inventory_template_key": "general_store"}
  inventory?: EnrichedInventoryItem[]; // Added for inventory details
  ai_metadata_json: Record<string, any> | null;
  created_at: string; // ISO date string
  updated_at: string; // ISO date string
}

// For API payloads (Create/Update)
export interface PlayerPayload {
  discord_user_id?: string; // For create
  player_name?: string; // For create
  name?: string; // For update
  level?: number;
  xp?: number;
  unspent_xp?: number;
  gold?: number;
  current_hp?: number | null;
  current_status?: string; // PlayerStatus enum string
  language?: string | null;
  current_location_id?: number | null;
  current_party_id?: number | null;
  attributes_json?: Record<string, any>;
}

export interface GeneratedNpcPayload {
  static_id?: string | null;
  name_i18n_json?: string; // Stringified JSON for command compatibility
  description_i18n_json?: string; // Stringified JSON
  npc_type_i18n_json?: string; // Stringified JSON
  faction_id?: number | null;
  current_location_id?: number | null;
  properties_json?: string; // Stringified JSON
}

// For list responses
// This was moved to items.ts, but if it's used by other entity lists, it can be kept here or in a more global types file.
// For now, assuming items.ts PaginatedResponse will be the primary one.
// If needed elsewhere, ensure consistency or create a global one.
export interface PaginatedResponse<T> {
  items: T[];
  current_page: number; // Ensure this matches what backend list commands actually return
  total_pages: number;  // Or 'pages'
  total_items: number;  // Or 'total'
  limit_per_page: number; // Or 'limit'
}

// Import EnrichedInventoryItem if not already implicitly available through a global import strategy
import { EnrichedInventoryItem } from './items';
