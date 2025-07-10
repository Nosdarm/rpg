// Corresponds to src/models/relationship.py
// Uses RelationshipEntityType from backend: PLAYER, GENERATED_NPC, GENERATED_FACTION, PARTY, GLOBAL_NPC, MOBILE_GROUP

// For displaying concise entity information in relationship lists/details
export interface RelationshipEntityInfo {
  id: number;
  type: string; // e.g., "PLAYER", "GENERATED_NPC"
  name: string; // Potentially localized or a default identifier
  static_id?: string | null; // If applicable
}

export interface RelationshipData {
  id: number;
  guild_id: number; // Assuming string for guildId in UI context
  entity1_type: string; // from RelationshipEntityType enum
  entity1_id: number;
  entity1_details?: RelationshipEntityInfo; // For UI display

  entity2_type: string; // from RelationshipEntityType enum
  entity2_id: number;
  entity2_details?: RelationshipEntityInfo; // For UI display

  relationship_type: string;
  value: number;
  source_log_id: number | null;

  // Timestamps from Base model (if returned by API, Relationship model does not have them by default)
  // created_at: string; // ISO date string - Currently not on Relationship model
  // updated_at: string; // ISO date string - Currently not on Relationship model
}

// For API payloads (Create/Update)
// These fields correspond to the parameters of /master_relationship create and update
export interface RelationshipPayload {
  entity1_id: number;
  entity1_type: string; // e.g., "PLAYER", "GENERATED_NPC", "GENERATED_FACTION"
  entity2_id: number;
  entity2_type: string; // e.g., "PLAYER", "GENERATED_NPC", "GENERATED_FACTION"
  relationship_type: string;
  value: number;
  source_log_id?: number | null;
}

export interface RelationshipUpdatePayload {
  field_to_update: 'relationship_type' | 'value';
  new_value: string; // For 'value', this will be a string representation of a number
}

// Assuming a generic PaginatedResponse structure exists, e.g.:
// import { PaginatedResponse } from './common'; // or './items'
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  // Adjust based on what your actual list commands return
}
