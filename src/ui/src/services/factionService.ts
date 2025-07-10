import { apiClient } from './apiClient';
import type { Faction, FactionPayload, FactionUpdatePayload, PaginatedResponse } from '../types/faction';

const BASE_PATH = '/master_faction'; // Conceptual path, will depend on actual API gateway

// Mock data for now
const MOCK_FACTIONS: Faction[] = [
  {
    id: 1,
    guild_id: 123, // Changed to number to match Faction interface
    static_id: 'knights_of_dawn',
    name_i18n: { en: 'Knights of Dawn', ru: 'Рыцари Рассвета' },
    description_i18n: { en: 'A noble order of knights.', ru: 'Благородный орден рыцарей.' },
    ideology_i18n: { en: 'Justice and Honor', ru: 'Справедливость и Честь' },
    leader_npc_id: 101,
    leader_npc_details: { id: 101, name: 'Sir Reginald', static_id: 'npc_reginald' },
    resources_json: { gold: 10000, influence: 75 },
    ai_metadata_json: { theme: 'chivalry' },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 2,
    guild_id: 123, // Changed to number
    static_id: 'shadow_syndicate',
    name_i18n: { en: 'Shadow Syndicate', ru: 'Теневой Синдикат' },
    description_i18n: { en: 'A mysterious organization operating in the shadows.', ru: 'Таинственная организация, действующая в тени.' },
    ideology_i18n: null,
    leader_npc_id: null,
    leader_npc_details: null,
    resources_json: { wealth: 50000, spies: 20 },
    ai_metadata_json: { operations: ['smuggling', 'espionage'] },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

export const factionService = {
  async getFactions(guildId: string, page: number = 1, limit: number = 10): Promise<PaginatedResponse<Faction>> {
    // In a real app, guildId would be part of the path or query params
    // Path might be /guilds/{guildId}/factions or /factions?guild_id={guildId}
    // For master commands, it's often implicit from the session/context on backend.
    // Here, we assume the API client or gateway handles guild context.
    console.log(`factionService.getFactions called for guild ${guildId}, page ${page}, limit ${limit}`);

    // Mocking pagination
    const start = (page - 1) * limit;
    const end = start + limit;
    const paginatedItems = MOCK_FACTIONS.slice(start, end);

    return apiClient.get<PaginatedResponse<Faction>>(
      `${BASE_PATH}/list?page=${page}&limit=${limit}`, // Mocking the command structure
      {
        items: paginatedItems,
        total: MOCK_FACTIONS.length,
        page,
        limit,
      }
    );
  },

  async getFaction(guildId: string, factionId: number): Promise<Faction> {
    console.log(`factionService.getFaction called for guild ${guildId}, faction ${factionId}`);
    const faction = MOCK_FACTIONS.find(f => f.id === factionId);
    return apiClient.get<Faction>(
      `${BASE_PATH}/view?faction_id=${factionId}`, // Mocking command
      faction || MOCK_FACTIONS[0] // Return found or first as fallback for mock
    );
  },

  async createFaction(guildId: string, payload: FactionPayload): Promise<Faction> {
    console.log(`factionService.createFaction called for guild ${guildId}`, payload);
    // Mock: create a new faction object and add to list
    const newFaction: Faction = {
      id: Math.max(0, ...MOCK_FACTIONS.map(f => f.id)) + 1,
      guild_id: parseInt(guildId), // Assuming guildId is a string in UI context
      static_id: payload.static_id,
      name_i18n: JSON.parse(payload.name_i18n_json),
      description_i18n: payload.description_i18n_json ? JSON.parse(payload.description_i18n_json) : {},
      ideology_i18n: payload.ideology_i18n_json ? JSON.parse(payload.ideology_i18n_json) : null,
      leader_npc_id: null, // Needs resolving from leader_npc_static_id
      resources_json: payload.resources_json ? JSON.parse(payload.resources_json) : null,
      ai_metadata_json: payload.ai_metadata_json ? JSON.parse(payload.ai_metadata_json) : null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    // MOCK_FACTIONS.push(newFaction); // In a real scenario, this would be handled by backend
    return apiClient.post<Faction, FactionPayload>(
      `${BASE_PATH}/create`, // Mocking command
      payload,
      newFaction
    );
  },

  async updateFaction(guildId: string, factionId: number, payload: FactionUpdatePayload): Promise<Faction> {
    console.log(`factionService.updateFaction called for guild ${guildId}, faction ${factionId}`, payload);
    // Mock: find faction and update
    const factionIndex = MOCK_FACTIONS.findIndex(f => f.id === factionId);
    let updatedFaction = MOCK_FACTIONS[factionIndex];
    if (updatedFaction) {
      // This is a simplified mock. Real update logic would be more complex.
      updatedFaction = { ...updatedFaction, /* apply changes based on payload */ updated_at: new Date().toISOString() };
      // MOCK_FACTIONS[factionIndex] = updatedFaction;
    }
    return apiClient.patch<Faction, FactionUpdatePayload>( // Using PATCH for partial updates
      `${BASE_PATH}/update?faction_id=${factionId}`, // Mocking command
      payload,
      updatedFaction || MOCK_FACTIONS[0]
    );
  },

  async deleteFaction(guildId: string, factionId: number): Promise<void> {
    console.log(`factionService.deleteFaction called for guild ${guildId}, faction ${factionId}`);
    // Mock: remove faction from list
    // const factionIndex = MOCK_FACTIONS.findIndex(f => f.id === factionId);
    // if (factionIndex > -1) {
    //   MOCK_FACTIONS.splice(factionIndex, 1);
    // }
    return apiClient.delete<void>(
      `${BASE_PATH}/delete?faction_id=${factionId}` // Mocking command
    );
  },
};
