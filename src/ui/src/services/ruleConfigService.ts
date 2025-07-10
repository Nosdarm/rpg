import { apiClient } from './apiClient';
import type { RuleConfigEntry, RuleConfigMap, RuleConfigUpdatePayload } from 'src/types/ruleconfig';
import type { PaginatedResponse } from 'src/types/entities'; // Assuming RuleConfig list might be paginated

const BASE_PATH = (guildId: number | string) => `/guilds/${guildId}/ruleconfig`;

export const ruleConfigService = {
  async getRule(guildId: number, key: string): Promise<RuleConfigEntry> {
    // The backend /master_ruleconfig get returns the value directly.
    // For UI consistency, this service might wrap it in a RuleConfigEntry structure.
    const mockValue = { data: `value for ${key}`, timestamp: Date.now() }; // Example value
    const mockEntry: RuleConfigEntry = {
        key: key,
        value_json: mockValue
    };
    // Or, if API returns the value directly:
    // const value = await apiClient.get<any>(`${BASE_PATH(guildId)}/${encodeURIComponent(key)}`);
    // return { key, value_json: value };
    return apiClient.get<RuleConfigEntry>(`${BASE_PATH(guildId)}/${encodeURIComponent(key)}`, mockEntry);
  },

  async setRule(guildId: number, key: string, payload: RuleConfigUpdatePayload): Promise<void> {
    // Backend /master_ruleconfig set expects value_json (stringified).
    // API would take actual JSON.
    return apiClient.put<void, RuleConfigUpdatePayload>(`${BASE_PATH(guildId)}/${encodeURIComponent(key)}`, payload);
  },

  async listRules(
    guildId: number,
    page: number = 1,
    limit: number = 10,
    prefix?: string
  ): Promise<PaginatedResponse<RuleConfigEntry>> {
    // The backend /master_ruleconfig list returns a paginated list of all rules.
    // A more advanced UI might want prefix filtering.
    const mockRules: RuleConfigEntry[] = Array.from({ length: limit }, (_, i) => ({
      key: `${prefix || 'rule'}_${(page - 1) * limit + i + 1}`,
      value_json: { detail: `Mock rule value ${(page - 1) * limit + i + 1}` },
    }));
    const mockPaginatedResponse: PaginatedResponse<RuleConfigEntry> = {
        items: mockRules,
        current_page: page,
        total_pages: Math.ceil(50 / limit), // Assuming 50 total rules for mock
        total_items: 50,
        limit_per_page: limit
    };
    let path = `${BASE_PATH(guildId)}?page=${page}&limit=${limit}`;
    if (prefix) {
      path += `&prefix=${encodeURIComponent(prefix)}`;
    }
    return apiClient.get<PaginatedResponse<RuleConfigEntry>>(path, mockPaginatedResponse);
  },

  async getAllRulesAsMap(guildId: number): Promise<RuleConfigMap> {
    // This is a helper if UI wants to build a tree and needs all rules.
    // The backend /master_ruleconfig list could be used with a very high limit,
    // or a dedicated endpoint could provide all rules.
    const mockMap: RuleConfigMap = {
        "system:feature_x_enabled": true,
        "worldstate:quest_alpha:status": "COMPLETED",
        "ai:generation:npc:default_prompt": "Generate a standard NPC..."
    };
    // This would likely call listRules with a high limit or a specific endpoint.
    return apiClient.get<RuleConfigMap>(`${BASE_PATH(guildId)}?all=true`, mockMap);
  },

  async deleteRule(guildId: number, key: string): Promise<void> {
    return apiClient.delete<void>(`${BASE_PATH(guildId)}/${encodeURIComponent(key)}`);
  },
};
