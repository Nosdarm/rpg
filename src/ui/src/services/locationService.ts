import { apiClient } from './apiClient';
import { PaginatedResponse } from '../types/entities';
import { UILocationData, UILocationFilterParams } from '../types/location';

const GUILD_ID_PLACEHOLDER = 'currentGuildId'; // This should be dynamically replaced

/**
 * Fetches a paginated list of locations for the map.
 * @param guildId The ID of the guild.
 * @param params Parameters for pagination and filtering.
 */
export const getLocations = async (
  guildId: string = GUILD_ID_PLACEHOLDER,
  params: UILocationFilterParams = {}
): Promise<PaginatedResponse<UILocationData>> => {
  console.log(`Mock API: Fetching locations for guild ${guildId} with params`, params);
  const mockItems: UILocationData[] = [
    { id: 1, guild_id: guildId, name_i18n: { en: 'Town Square' }, descriptions_i18n: { en: 'A bustling square.'}, type: 'town', coordinates_json: { x: 0, y: 0 } },
    { id: 2, guild_id: guildId, name_i18n: { en: 'Dark Forest' }, descriptions_i18n: { en: 'A spooky forest.'}, type: 'forest', coordinates_json: { x: 1, y: 0 } },
  ];
  return Promise.resolve({
    items: mockItems.slice(0, params.limit || 2),
    current_page: params.page || 1,
    total_pages: Math.ceil(mockItems.length / (params.limit || 2)),
    total_items: mockItems.length,
    limit_per_page: params.limit || 2,
  });
  // Example actual call:
  // return apiClient.get(`/guilds/${guildId}/map/locations`, { params });
  // Or if calling a generic master command endpoint:
  // return apiClient.post(`/master-command/master_monitor_map_list_locations`, { guild_id: guildId, ...params });
};

/**
 * Fetches details for a single location by its ID or static_id.
 * @param guildId The ID of the guild.
 * @param identifier The ID (number) or static_id (string) of the location.
 */
export const getLocationDetails = async (
  guildId: string = GUILD_ID_PLACEHOLDER,
  identifier: string | number
): Promise<UILocationData> => {
  console.log(`Mock API: Fetching location details for guild ${guildId} with identifier ${identifier}`);
  if (identifier === 1 || identifier === 'town_square_static_id') {
    return Promise.resolve({
      id: 1,
      guild_id: guildId,
      static_id: 'town_square_static_id',
      name_i18n: { en: 'Town Square', ru: 'Городская площадь' },
      descriptions_i18n: { en: 'A bustling square at the heart of the town.', ru: 'Шумная площадь в сердце города.' },
      type: 'town',
      coordinates_json: { x: 0, y: 0, map_id: 'main_map' },
      neighbor_locations_json: {
        "north": "market_street_static_id",
        "east": 202 // Example ID for another location
      },
      generated_details_json: { population_density: "high", notable_features: ["fountain", "statue"] }
    });
  }
  return Promise.reject(new Error('Location not found'));
  // Example actual call:
  // return apiClient.get(`/guilds/${guildId}/map/locations/${identifier}`);
};
