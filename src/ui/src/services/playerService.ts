import { apiClient } from './apiClient';
import type { Player, PlayerPayload, PaginatedResponse } from 'src/types/entities';

const BASE_PATH = (guildId: number | string) => `/guilds/${guildId}/players`;

export const playerService = {
  async getPlayers(guildId: number, page: number = 1, limit: number = 10): Promise<PaginatedResponse<Player>> {
    // Mock response structure, actual API would return this
    const mockPlayers: Player[] = Array.from({ length: limit }, (_, i) => ({
      id: (page - 1) * limit + i + 1,
      guild_id: guildId,
      discord_id: `discord_user_${(page - 1) * limit + i + 1}`,
      name: `Player Name ${(page - 1) * limit + i + 1}`,
      level: Math.floor(Math.random() * 10) + 1,
      xp: Math.floor(Math.random() * 1000),
      unspent_xp: Math.floor(Math.random() * 100),
      gold: Math.floor(Math.random() * 500),
      current_hp: 50,
      max_hp: 100,
      current_status: "IDLE",
      selected_language: "en",
      current_location_id: 1,
      current_party_id: null,
      attributes_json: { strength: 10, dexterity: 10 },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }));
    const mockPaginatedResponse: PaginatedResponse<Player> = {
        items: mockPlayers,
        current_page: page,
        total_pages: Math.ceil(25 / limit), // Assuming 25 total items for mock
        total_items: 25,
        limit_per_page: limit
    };
    return apiClient.get<PaginatedResponse<Player>>(`${BASE_PATH(guildId)}?page=${page}&limit=${limit}`, mockPaginatedResponse);
  },

  async getPlayerById(
    guildId: number,
    playerId: number,
    includeInventory: boolean = false // New parameter
  ): Promise<Player> {
    // Adjust the mock and API call if includeInventory is true
    const endpoint = `${BASE_PATH(guildId)}/${playerId}${includeInventory ? '?include_inventory=true' : ''}`;

    const mockPlayer: Player = {
      id: playerId,
      guild_id: guildId,
      discord_id: `discord_user_${playerId}`,
      name: `Player Name ${playerId}`,
      level: 5,
      xp: 500,
      unspent_xp: 50,
      gold: 200,
      current_hp: 75,
      max_hp: 100,
      current_status: "EXPLORING",
      selected_language: "en",
      current_location_id: 2,
      current_party_id: 1,
      attributes_json: { strength: 12, intelligence: 8 },
      inventory: includeInventory ? [ // Mock inventory data if requested
        {
          inventory_item_id: 101, item_id: 1, name_i18n: { en: "Mock Sword" },
          description_i18n: {en: "A trusty mock sword."}, is_stackable: false, quantity: 1,
          created_at: new Date().toISOString(), updated_at: new Date().toISOString()
          // Fill other EnrichedInventoryItem fields as needed for mock
        }
      ] : undefined,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    // The actual API call (if it were real) would pass include_inventory to the backend.
    // For the mock, we adjust the mock response based on it.
    // If using apiClient.post for commands:
    // return apiClient.post<Player>('/master_command_endpoint', {
    // command_name: 'master_player view',
    // guild_id: guildId,
    // params: { player_id: playerId, include_inventory: includeInventory },
    // }, mockPlayer); // Pass mockPlayer for apiClient to return if it's a mock wrapper
    return apiClient.get<Player>(endpoint, mockPlayer); // Assuming GET for this service structure
  },

  async createPlayer(guildId: number, payload: PlayerPayload): Promise<Player> {
    // The backend /master_player create expects discord_user (discord.User object) and player_name.
    // For a direct API, it would be discord_user_id (string).
    // The PlayerPayload should reflect what the direct API expects.
    // Assuming payload contains discord_user_id as string.
    const mockCreatedPlayer: Player = {
      id: Math.floor(Math.random() * 1000) + 1,
      guild_id: guildId,
      discord_id: payload.discord_user_id || `new_discord_user_${Date.now()}`,
      name: payload.player_name || payload.name || "New Player",
      level: payload.level || 1,
      xp: payload.xp || 0,
      unspent_xp: payload.unspent_xp || 0,
      gold: payload.gold || 0,
      current_hp: payload.current_hp || 100,
      max_hp: 100, // Should be determined by rules/attributes
      current_status: payload.current_status || "IDLE",
      selected_language: payload.language || "en",
      current_location_id: payload.current_location_id || null,
      current_party_id: payload.current_party_id || null,
      attributes_json: payload.attributes_json || {}, // This is for the mock Player object
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    // Prepare payload for actual API call (master command expects JSON string for attributes_json)
    const apiPayload = { ...payload };
    if (payload.attributes_json && typeof payload.attributes_json === 'object') {
      apiPayload.attributes_json = JSON.stringify(payload.attributes_json) as any; // Cast because TS expects Record
    }

    // Assuming apiClient.post is a wrapper that will eventually call the master command
    // The conceptual /guilds/{guildId}/players endpoint might be a direct REST API
    // If it's a pass-through to master commands, then stringified JSON is correct.
    return apiClient.post<Player, PlayerPayload>(`${BASE_PATH(guildId)}`, apiPayload, mockCreatedPlayer);
  },

  async updatePlayer(guildId: number, playerId: number, payload: Partial<PlayerPayload>): Promise<Player> {
    // Prepare payload for actual API call
    const apiPayload = { ...payload };
    if (payload.attributes_json && typeof payload.attributes_json === 'object') {
      apiPayload.attributes_json = JSON.stringify(payload.attributes_json) as any; // Cast for the API call
    }

    // This stub assumes a PATCH API. If it's calling a field-by-field master_player update,
    // this service would need to make multiple calls or be redesigned.
    // For now, proceeding with assumption that a single call with partial payload is possible
    // OR that the attributes_json is the only JSON field being updated this way.
    const mockUpdatedPlayer: Player = {
        id: playerId,
        guild_id: guildId,
        discord_id: `discord_user_${playerId}`,
        name: payload.name || `Player Name ${playerId}`,
        level: payload.level || 5,
        xp: payload.xp || 500,
        unspent_xp: payload.unspent_xp || 50,
        gold: payload.gold || 200,
        current_hp: payload.current_hp || 75,
        max_hp: 100,
        current_status: payload.current_status || "EXPLORING",
        selected_language: payload.language || "en",
        current_location_id: payload.current_location_id || 2,
        current_party_id: payload.current_party_id || 1,
        attributes_json: typeof apiPayload.attributes_json === 'string' ? JSON.parse(apiPayload.attributes_json) : apiPayload.attributes_json || { strength: 12, intelligence: 8 },
        created_at: new Date(Date.now() - 100000).toISOString(),
        updated_at: new Date().toISOString(),
      };
    return apiClient.patch<Player, Partial<PlayerPayload>>(`${BASE_PATH(guildId)}/${playerId}`, apiPayload, mockUpdatedPlayer);
  },

  async deletePlayer(guildId: number, playerId: number): Promise<void> {
    return apiClient.delete<void>(`${BASE_PATH(guildId)}/${playerId}`);
  },
};
