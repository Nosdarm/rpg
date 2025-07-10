import { apiClient } from './apiClient';
import type { GeneratedNpc, GeneratedNpcPayload, PaginatedResponse } from 'src/types/entities';

const BASE_PATH = (guildId: number | string) => `/guilds/${guildId}/npcs`;

export const npcService = {
  async getNpcs(guildId: number, page: number = 1, limit: number = 10): Promise<PaginatedResponse<GeneratedNpc>> {
    const mockNpcs: GeneratedNpc[] = Array.from({ length: limit }, (_, i) => ({
      id: (page - 1) * limit + i + 1,
      guild_id: guildId,
      static_id: `npc_static_${(page - 1) * limit + i + 1}`,
      name_i18n: { en: `NPC Name ${(page - 1) * limit + i + 1}`, ru: `Имя NPC ${(page - 1) * limit + i + 1}` },
      description_i18n: { en: "A mock NPC description.", ru: "Моковое описание NPC." },
      npc_type_i18n: { en: "Merchant", ru: "Торговец" },
      faction_id: null,
      current_location_id: 1,
      properties_json: { stats: { hp: 50 } },
      ai_metadata_json: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }));
     const mockPaginatedResponse: PaginatedResponse<GeneratedNpc> = {
        items: mockNpcs,
        current_page: page,
        total_pages: Math.ceil(15 / limit), // Assuming 15 total items for mock
        total_items: 15,
        limit_per_page: limit
    };
    return apiClient.get<PaginatedResponse<GeneratedNpc>>(`${BASE_PATH(guildId)}?page=${page}&limit=${limit}`, mockPaginatedResponse);
  },

  async getNpcById(
    guildId: number,
    npcId: number,
    includeInventory: boolean = false // New parameter
  ): Promise<GeneratedNpc> {
    const endpoint = `${BASE_PATH(guildId)}/${npcId}${includeInventory ? '?include_inventory=true' : ''}`;
    const mockNpc: GeneratedNpc = {
      id: npcId,
      guild_id: guildId,
      static_id: `npc_static_${npcId}`,
      name_i18n: { en: `NPC Name ${npcId}`, ru: `Имя NPC ${npcId}` },
      description_i18n: { en: "A detailed mock NPC description.", ru: "Детальное моковое описание NPC." },
      npc_type_i18n: { en: "Guard", ru: "Стражник" },
      faction_id: 1,
      current_location_id: 2,
      properties_json: { stats: { hp: 100, attack: 10 }, dialog_key: "guard_dialogue" },
      inventory: includeInventory ? [ // Mock inventory data if requested
        {
          inventory_item_id: 201, item_id: 2, name_i18n: { en: "Rusty Dagger" },
          description_i18n: {en: "A rusty dagger, likely dropped by a goblin."}, is_stackable: false, quantity: 1,
          item_properties_json: { "damage": "1d4" },
          created_at: new Date().toISOString(), updated_at: new Date().toISOString()
          // Fill other EnrichedInventoryItem fields as needed for mock
        }
      ] : undefined,
      ai_metadata_json: { source_prompt_hash: "abc123xyz" },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    // If using apiClient.post for commands:
    // return apiClient.post<GeneratedNpc>('/master_command_endpoint', {
    // command_name: 'master_npc view',
    // guild_id: guildId,
    // params: { npc_id: npcId, include_inventory: includeInventory },
    // }, mockNpc);
    return apiClient.get<GeneratedNpc>(endpoint, mockNpc); // Assuming GET for this service structure
  },

  async createNpc(guildId: number, payload: GeneratedNpcPayload): Promise<GeneratedNpc> {
    // The backend /master_npc create expects name_i18n_json (stringified json).
    // For a direct API, it might accept actual JSON for name_i18n.
    // This stub assumes the payload matches what a direct JSON API would expect.
    // If UI forms provide stringified JSON, that's fine too.
    const mockCreatedNpc: GeneratedNpc = {
      id: Math.floor(Math.random() * 1000) + 1,
      guild_id: guildId,
      static_id: payload.static_id || `new_npc_${Date.now()}`,
      name_i18n: payload.name_i18n_json ? JSON.parse(payload.name_i18n_json) : { en: "New NPC" },
      description_i18n: payload.description_i18n_json ? JSON.parse(payload.description_i18n_json) : { en: "Description" },
      npc_type_i18n: payload.npc_type_i18n_json ? JSON.parse(payload.npc_type_i18n_json) : { en: "Commoner" },
      faction_id: payload.faction_id || null,
      current_location_id: payload.current_location_id || null,
      properties_json: payload.properties_json ? JSON.parse(payload.properties_json) : {},
      ai_metadata_json: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    return apiClient.post<GeneratedNpc, GeneratedNpcPayload>(`${BASE_PATH(guildId)}`, payload, mockCreatedNpc);
  },

  async updateNpc(guildId: number, npcId: number, payload: Partial<GeneratedNpcPayload>): Promise<GeneratedNpc> {
    // Similar to player update, this assumes a PATCH API.
    const mockUpdatedNpc: GeneratedNpc = {
        id: npcId,
        guild_id: guildId,
        static_id: payload.static_id || `npc_static_${npcId}`,
        name_i18n: payload.name_i18n_json ? JSON.parse(payload.name_i18n_json) : { en: `Updated NPC ${npcId}` },
        description_i18n: payload.description_i18n_json ? JSON.parse(payload.description_i18n_json) : { en: "Updated Description" },
        npc_type_i18n: payload.npc_type_i18n_json ? JSON.parse(payload.npc_type_i18n_json) : { en: "Special" },
        faction_id: payload.faction_id === undefined ? 1 : payload.faction_id, // Example: keep if undefined, else update
        current_location_id: payload.current_location_id === undefined ? 1 : payload.current_location_id,
        properties_json: payload.properties_json ? JSON.parse(payload.properties_json) : { updated_stat: true },
        ai_metadata_json: null,
        created_at: new Date(Date.now() - 100000).toISOString(),
        updated_at: new Date().toISOString(),
    };
    return apiClient.patch<GeneratedNpc, Partial<GeneratedNpcPayload>>(`${BASE_PATH(guildId)}/${npcId}`, payload, mockUpdatedNpc);
  },

  async deleteNpc(guildId: number, npcId: number): Promise<void> {
    return apiClient.delete<void>(`${BASE_PATH(guildId)}/${npcId}`);
  },
};
