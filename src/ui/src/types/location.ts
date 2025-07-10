// Based on src/models/location.py LocationType
export type UILocationType =
  | "generic"
  | "town"
  | "city"
  | "village"
  | "forest"
  | "mountain"
  | "cave"
  | "dungeon"
  | "shop"
  | "tavern"
  | "road"
  | "port"
  | string; // Allow any string for future-proofing or custom types

// Based on src/models/location.py Location model
export interface UILocationData {
  id: number;
  guild_id: string; // Guild IDs are typically snowflakes (strings)
  parent_location_id?: number | null;
  static_id?: string | null;
  name_i18n: Record<string, string>; // e.g., {"en": "The Prancing Pony", "ru": "Гарцующий Пони"}
  descriptions_i18n: Record<string, string>;
  type: UILocationType;
  coordinates_json?: Record<string, any> | null; // e.g., {"x": 10, "y": 20, "map_id": "world"}

  // Example structure for neighbor_locations_json:
  // {"north": "forest_path_1_static_id", "east": 203 }
  // OR [{"direction": "north", "target_static_id": "forest_path_1", "target_id": 203, "details_i18n": {"en": "A dark path"}}]
  neighbor_locations_json?: Record<string, number | string> | Array<{
    direction: string;
    target_id?: number;
    target_static_id?: string;
    details_i18n?: Record<string, string>;
  }> | null;

  generated_details_json?: Record<string, any> | null; // Other AI generated details
  // ai_metadata_json is likely backend-internal

  // Optional: Fields that might be populated for map display
  // players_present_ids?: number[];
  // npcs_present_ids?: number[];
  // global_entities_present_ids?: number[];
}

export interface UILocationFilterParams {
  page?: number;
  limit?: number;
  // name_contains?: string; // Example filter, if API supports
  // type?: UILocationType; // Example filter
}

// Re-export PaginatedResponse if common, or define specific if structure varies
// For now, assuming common PaginatedResponse from entities.ts will be used by service
// import { PaginatedResponse } from './entities';
// export type PaginatedLocationResponse = PaginatedResponse<UILocationData>;
