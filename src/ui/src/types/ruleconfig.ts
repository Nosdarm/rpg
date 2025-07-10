export interface RuleConfigEntry {
  key: string;
  value_json: any; // The value can be any valid JSON type
  description?: string | null; // Optional description if provided by API
  // Timestamps might not be directly relevant for UI display of rules themselves
  // created_at: string;
  // updated_at: string;
}

// For listing rules, the API might return a dictionary or an array of entries
// If it's a dictionary:
export type RuleConfigMap = Record<string, any>;

// If it's an array (e.g., for paginated list or prefix search):
// Use PaginatedResponse<RuleConfigEntry> from entities.ts if applicable

// For updating a rule
export interface RuleConfigUpdatePayload {
  value_json: any; // The new JSON value for the rule
}
