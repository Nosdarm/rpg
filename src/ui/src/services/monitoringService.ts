import { apiClient } from './apiClient';
import { PaginatedResponse } from '../types/entities'; // Assuming this is the agreed-upon PaginatedResponse structure
import { RuleConfigEntry } from '../types/ruleconfig';
import { UIStoryLogData, UIStoryLogFilterParams } from '../types/monitoring';

const GUILD_ID_PLACEHOLDER = 'currentGuildId'; // This should be dynamically replaced by the actual guild ID in a real UI

/**
 * Fetches a paginated list of WorldState entries (RuleConfig entries with a specific prefix).
 * @param guildId The ID of the guild.
 * @param params Parameters for pagination and filtering (e.g., prefix).
 */
export const getWorldStateEntries = async (
  guildId: string = GUILD_ID_PLACEHOLDER, // UI should replace this
  params: { page?: number; limit?: number; prefix?: string } = {}
): Promise<PaginatedResponse<RuleConfigEntry>> => {
  // Mocked response structure, ensure it matches PaginatedResponse<RuleConfigEntry>
  // The actual API call would be to a master command like /master_monitor worldstate list
  console.log(`Mock API: Fetching world state entries for guild ${guildId} with params`, params);
  const mockItems: RuleConfigEntry[] = [
    { key: 'worldstate:weather', value_json: { current: 'sunny', forecast: 'cloudy' }, description: 'Current weather' },
    { key: 'worldstate:economy_status', value_json: { trend: 'booming' }, description: 'Economic status' },
  ];
  return Promise.resolve({
    items: mockItems.slice(0, params.limit || 2),
    current_page: params.page || 1,
    total_pages: Math.ceil(mockItems.length / (params.limit || 2)),
    total_items: mockItems.length,
    limit_per_page: params.limit || 2,
  });
  // Example actual call:
  // return apiClient.get(`/guilds/${guildId}/monitoring/worldstate`, { params });
  // Or if calling a generic master command endpoint:
  // return apiClient.post(`/master-command/master_monitor_worldstate_list`, { guild_id: guildId, ...params });
};

/**
 * Fetches a single WorldState entry by its key.
 * @param guildId The ID of the guild.
 * @param key The key of the WorldState entry.
 */
export const getWorldStateEntry = async (
  guildId: string = GUILD_ID_PLACEHOLDER,
  key: string
): Promise<RuleConfigEntry> => {
  console.log(`Mock API: Fetching world state entry for guild ${guildId} with key ${key}`);
  if (key === 'worldstate:weather') {
    return Promise.resolve({ key: 'worldstate:weather', value_json: { current: 'sunny', forecast: 'cloudy' }, description: 'Current weather' });
  }
  return Promise.reject(new Error('WorldState entry not found'));
  // Example actual call:
  // return apiClient.get(`/guilds/${guildId}/monitoring/worldstate/${encodeURIComponent(key)}`);
};

/**
 * Fetches a paginated list of StoryLog entries.
 * @param guildId The ID of the guild.
 * @param params Parameters for pagination and filtering.
 */
export const getStoryLogEntries = async (
  guildId: string = GUILD_ID_PLACEHOLDER,
  params: UIStoryLogFilterParams = {}
): Promise<PaginatedResponse<UIStoryLogData>> => {
  console.log(`Mock API: Fetching story log entries for guild ${guildId} with params`, params);
  const mockItems: UIStoryLogData[] = [
    { id: 1, guild_id: guildId, timestamp: new Date().toISOString(), event_type: 'player_action', details_json: { action: 'moved', to: 'tavern' }, narrative_i18n: { en: 'Player entered the tavern.' }, formatted_message: 'Player entered the tavern.' },
    { id: 2, guild_id: guildId, timestamp: new Date().toISOString(), event_type: 'combat_start', details_json: { participants: [1, 101] }, narrative_i18n: { en: 'Combat started!' }, formatted_message: 'Combat started!' },
  ];
  return Promise.resolve({
    items: mockItems.slice(0, params.limit || 2),
    current_page: params.page || 1,
    total_pages: Math.ceil(mockItems.length / (params.limit || 2)),
    total_items: mockItems.length,
    limit_per_page: params.limit || 2,
  });
  // Example actual call:
  // return apiClient.get(`/guilds/${guildId}/monitoring/storylog`, { params });
};

/**
 * Fetches a single StoryLog entry by its ID.
 * @param guildId The ID of the guild.
 * @param logId The ID of the StoryLog entry.
 */
export const getStoryLogEntry = async (
  guildId: string = GUILD_ID_PLACEHOLDER,
  logId: number
): Promise<UIStoryLogData> => {
  console.log(`Mock API: Fetching story log entry for guild ${guildId} with ID ${logId}`);
  if (logId === 1) {
    return Promise.resolve({ id: 1, guild_id: guildId, timestamp: new Date().toISOString(), event_type: 'player_action', details_json: { action: 'moved', to: 'tavern' }, narrative_i18n: { en: 'Player entered the tavern.' }, formatted_message: 'Player entered the tavern.' });
  }
  return Promise.reject(new Error('StoryLog entry not found'));
  // Example actual call:
  // return apiClient.get(`/guilds/${guildId}/monitoring/storylog/${logId}`);
};
