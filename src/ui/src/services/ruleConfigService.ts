import { apiClient, processPaginatedResponse } from './apiClient'; // Assuming processPaginatedResponse exists
import type { RuleConfigEntry, RuleConfigUpdatePayload } from 'src/types/ruleconfig';
import type { PaginatedResponse, ApiPaginatedResponse } from 'src/types/entities';

// Define a payload for creating a rule, which might include description
export interface RuleConfigCreatePayload {
  key: string;
  value_json: string; // Expecting stringified JSON for the master command
  description?: string;
}

// Define a payload for updating, which based on /master_ruleconfig set, primarily targets value_json
// If description update is separate, a different payload/method might be needed.
// For now, aligning with `set` command.
export interface RuleConfigSetPayload {
  value_json: string; // Expecting stringified JSON
  description?: string; // If the API gateway can pass this to a more robust update/set
}


const RULECONFIG_API_BASE_PATH = '/master_ruleconfig'; // Conceptual base path for master commands

export const ruleConfigService = {
  async listRuleConfigEntries(
    guildId: string, // Assuming guildId will be handled by apiClient or injected by a wrapper
    prefix?: string,
    page: number = 1,
    limit: number = 10,
  ): Promise<PaginatedResponse<RuleConfigEntry>> {
    const params: Record<string, string | number> = {
      page,
      limit,
      // guild_id: guildId, // Master commands get guild_id from interaction context
    };
    if (prefix) {
      params.prefix = prefix; // The backend /master_ruleconfig list does not support prefix.
                              // This implies the API gateway would need to handle it, or it's client-side.
                              // For now, we pass it, assuming gateway might use it.
    }
    // The actual response from /master_ruleconfig list is an embed.
    // The API gateway needs to transform this into a JSON PaginatedResponse<RuleConfigEntry>.
    // For now, we assume the apiClient handles the command mapping and response transformation.
    const response = await apiClient.post<ApiPaginatedResponse<RuleConfigEntry>>(RULECONFIG_API_BASE_PATH, {
      command_name: 'list',
      guild_id: guildId, // Pass guild_id in the body for the conceptual API gateway
      parameters: params,
    });
    return processPaginatedResponse(response);
  },

  async getRuleConfigEntry(guildId: string, key: string): Promise<RuleConfigEntry> {
    // /master_ruleconfig get <key>
    // API gateway needs to return RuleConfigEntry structure.
    return apiClient.post<RuleConfigEntry>(RULECONFIG_API_BASE_PATH, {
      command_name: 'get',
      guild_id: guildId,
      parameters: { key },
    });
  },

  async createRuleConfigEntry(guildId: string, payload: RuleConfigCreatePayload): Promise<RuleConfigEntry> {
    // /master_ruleconfig set <key> <value_json>
    // The 'set' command creates if not exists.
    // The description handling needs clarification: master command doesn't take it.
    // Assuming API gateway might handle it or it's set via a generic update later.
    // For now, sending it, but backend command will only use key and value_json.
    await apiClient.post<void>(RULECONFIG_API_BASE_PATH, {
      command_name: 'set',
      guild_id: guildId,
      parameters: { key: payload.key, value_json: payload.value_json }, // description not directly used by current 'set'
    });
    // After creation, fetch the entry to return it, as 'set' doesn't return the object
    return this.getRuleConfigEntry(guildId, payload.key);
  },

  async updateRuleConfigEntry(guildId: string, key: string, payload: RuleConfigSetPayload): Promise<RuleConfigEntry> {
    // /master_ruleconfig set <key> <value_json>
    // This will update the value. If description needs separate update, it's an issue with current commands.
    await apiClient.post<void>(RULECONFIG_API_BASE_PATH, {
      command_name: 'set',
      guild_id: guildId,
      parameters: { key, value_json: payload.value_json }, // description not directly used
    });
    // After update, fetch the entry to return it
    return this.getRuleConfigEntry(guildId, key);
  },

  async deleteRuleConfigEntry(guildId: string, key: string): Promise<void> {
    // /master_ruleconfig delete <key>
    return apiClient.post<void>(RULECONFIG_API_BASE_PATH, {
      command_name: 'delete',
      guild_id: guildId,
      parameters: { key },
    });
  },
};
