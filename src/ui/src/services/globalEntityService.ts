import { apiClient } from './apiClient'; // Assuming apiClient is set up for mock/real calls
import {
  GlobalNpcData,
  GlobalNpcPayload,
  GlobalNpcUpdatePayload,
  MobileGroupData,
  MobileGroupPayload,
  MobileGroupUpdatePayload,
} from '../types/globalEntity';
import { PaginatedResponse } from '../types/entities';

const GUILD_ID_PLACEHOLDER = 'currentGuildId'; // This should be dynamically obtained in a real app

// === Global NPC Service ===

export const getGlobalNpcs = async (
  guildId: string = GUILD_ID_PLACEHOLDER,
  page: number = 1,
  limit: number = 10
): Promise<PaginatedResponse<GlobalNpcData>> => {
  // MOCK IMPLEMENTATION
  console.log(`Mock API: Fetching Global NPCs for guild ${guildId}, page ${page}, limit ${limit}`);
  // Simulate API call structure for master commands
  // const response = await apiClient.post('/master_command_endpoint', {
  //   command: '/master_global_npc list',
  //   payload: { page, limit, guild_id: guildId },
  // });
  // return response.data; // Assuming response.data is PaginatedResponse<GlobalNpcData>

  // Example Mock Data:
  const mockItems: GlobalNpcData[] = [
    {
      id: 1, guild_id: parseInt(guildId), static_id: 'traveling_merchant_01', name_i18n: { en: 'Traveling Merchant', ru: 'Странствующий торговец' },
      current_location_id: 10, properties_json: { route: { type: 'random_walk' }, current_hp: 50 },
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      base_npc_id: 1, mobile_group_id: null,
    },
    {
      id: 2, guild_id: parseInt(guildId), static_id: 'wandering_scout_01', name_i18n: { en: 'Wandering Scout', ru: 'Бродячий разведчик' },
      current_location_id: 12, properties_json: { goals: ['explore_ruins'], status: 'active' },
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    },
  ];
  return Promise.resolve({
    items: mockItems.slice(0, limit),
    current_page: page,
    total_pages: Math.ceil(mockItems.length / limit),
    total_items: mockItems.length,
    limit_per_page: limit,
  });
};

export const getGlobalNpc = async (
  id: number,
  guildId: string = GUILD_ID_PLACEHOLDER
): Promise<GlobalNpcData> => {
  console.log(`Mock API: Fetching Global NPC ${id} for guild ${guildId}`);
  // const response = await apiClient.post('/master_command_endpoint', {
  //   command: '/master_global_npc view',
  //   payload: { global_npc_id: id, guild_id: guildId },
  // });
  // return response.data;
  return Promise.resolve({
    id, guild_id: parseInt(guildId), static_id: `gnpc_static_${id}`, name_i18n: { en: `Global NPC ${id}` },
    properties_json: { current_hp: 100, status: 'idle' }, created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  });
};

export const createGlobalNpc = async (
  payload: GlobalNpcPayload,
  guildId: string = GUILD_ID_PLACEHOLDER
): Promise<GlobalNpcData> => {
  console.log(`Mock API: Creating Global NPC for guild ${guildId}`, payload);
  // const response = await apiClient.post('/master_command_endpoint', {
  //   command: '/master_global_npc create',
  //   payload: { ...payload, guild_id: guildId }, // Ensure guild_id is part of the payload if master command needs it explicitly
  // });
  // return response.data;
  const mockCreatedId = Math.floor(Math.random() * 1000) + 3;
  return Promise.resolve({
    id: mockCreatedId,
    guild_id: parseInt(guildId),
    static_id: payload.static_id,
    name_i18n: JSON.parse(payload.name_i18n_json),
    description_i18n: payload.description_i18n_json ? JSON.parse(payload.description_i18n_json) : undefined,
    current_location_id: payload.current_location_id,
    base_npc_id: payload.base_npc_id,
    mobile_group_id: payload.mobile_group_id,
    properties_json: payload.properties_json ? JSON.parse(payload.properties_json) : {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
};

export const updateGlobalNpc = async (
  id: number,
  payload: GlobalNpcUpdatePayload, // Master commands typically take field_to_update and new_value.
                                   // This service might need to make multiple calls or the API gateway handles it.
                                   // For a simple mock, we'll assume the gateway can take a partial update.
  guildId: string = GUILD_ID_PLACEHOLDER
): Promise<GlobalNpcData> => {
  console.log(`Mock API: Updating Global NPC ${id} for guild ${guildId}`, payload);
  // Example for a single field update:
  // const response = await apiClient.post('/master_command_endpoint', {
  //   command: '/master_global_npc update',
  //   payload: { global_npc_id: id, field_to_update: 'static_id', new_value: payload.static_id, guild_id: guildId },
  // });
  // return response.data;
  return Promise.resolve({
    id,
    guild_id: parseInt(guildId),
    static_id: payload.static_id || `gnpc_static_${id}`,
    name_i18n: payload.name_i18n_json ? JSON.parse(payload.name_i18n_json) : { en: `Updated Global NPC ${id}` },
    description_i18n: payload.description_i18n_json ? JSON.parse(payload.description_i18n_json) : undefined,
    current_location_id: payload.current_location_id,
    base_npc_id: payload.base_npc_id,
    mobile_group_id: payload.mobile_group_id,
    properties_json: payload.properties_json ? JSON.parse(payload.properties_json) : { updated: true },
    created_at: "2023-01-01T00:00:00Z", // Should fetch original and only update changed
    updated_at: new Date().toISOString(),
  });
};

export const deleteGlobalNpc = async (
  id: number,
  guildId: string = GUILD_ID_PLACEHOLDER
): Promise<void> => {
  console.log(`Mock API: Deleting Global NPC ${id} for guild ${guildId}`);
  // await apiClient.post('/master_command_endpoint', {
  //   command: '/master_global_npc delete',
  //   payload: { global_npc_id: id, guild_id: guildId },
  // });
  return Promise.resolve();
};


// === Mobile Group Service ===

export const getMobileGroups = async (
  guildId: string = GUILD_ID_PLACEHOLDER,
  page: number = 1,
  limit: number = 10
): Promise<PaginatedResponse<MobileGroupData>> => {
  console.log(`Mock API: Fetching Mobile Groups for guild ${guildId}, page ${page}, limit ${limit}`);
  const mockItems: MobileGroupData[] = [
    {
      id: 1, guild_id: parseInt(guildId), static_id: 'merchant_caravan_a', name_i18n: { en: 'Merchant Caravan Alpha' },
      current_location_id: 5, leader_global_npc_id: 1, members_definition_json: [{ global_npc_static_id: 'traveling_merchant_01', role_i18n: {en: 'Leader'} }],
      route_json: { type: 'fixed', points: [5, 8, 10] }, properties_json: { status: 'traveling' },
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    },
  ];
  return Promise.resolve({
    items: mockItems.slice(0, limit),
    current_page: page,
    total_pages: Math.ceil(mockItems.length / limit),
    total_items: mockItems.length,
    limit_per_page: limit,
  });
};

export const getMobileGroup = async (
  id: number,
  guildId: string = GUILD_ID_PLACEHOLDER
): Promise<MobileGroupData> => {
  console.log(`Mock API: Fetching Mobile Group ${id} for guild ${guildId}`);
  return Promise.resolve({
    id, guild_id: parseInt(guildId), static_id: `mgroup_static_${id}`, name_i18n: { en: `Mobile Group ${id}` },
    members_definition_json: [], properties_json: {}, created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  });
};

export const createMobileGroup = async (
  payload: MobileGroupPayload,
  guildId: string = GUILD_ID_PLACEHOLDER
): Promise<MobileGroupData> => {
  console.log(`Mock API: Creating Mobile Group for guild ${guildId}`, payload);
  const mockCreatedId = Math.floor(Math.random() * 1000) + 3;
  return Promise.resolve({
    id: mockCreatedId,
    guild_id: parseInt(guildId),
    static_id: payload.static_id,
    name_i18n: JSON.parse(payload.name_i18n_json),
    description_i18n: payload.description_i18n_json ? JSON.parse(payload.description_i18n_json) : undefined,
    current_location_id: payload.current_location_id,
    leader_global_npc_id: payload.leader_global_npc_id,
    members_definition_json: payload.members_definition_json ? JSON.parse(payload.members_definition_json) : [],
    behavior_type_i18n: payload.behavior_type_i18n_json ? JSON.parse(payload.behavior_type_i18n_json) : undefined,
    route_json: payload.route_json ? JSON.parse(payload.route_json) : undefined,
    properties_json: payload.properties_json ? JSON.parse(payload.properties_json) : {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
};

export const updateMobileGroup = async (
  id: number,
  payload: MobileGroupUpdatePayload,
  guildId: string = GUILD_ID_PLACEHOLDER
): Promise<MobileGroupData> => {
  console.log(`Mock API: Updating Mobile Group ${id} for guild ${guildId}`, payload);
  return Promise.resolve({
    id,
    guild_id: parseInt(guildId),
    static_id: payload.static_id || `mgroup_static_${id}`,
    name_i18n: payload.name_i18n_json ? JSON.parse(payload.name_i18n_json) : { en: `Updated Mobile Group ${id}` },
    members_definition_json: payload.members_definition_json ? JSON.parse(payload.members_definition_json) : [],
    // ... other fields
    created_at: "2023-01-01T00:00:00Z",
    updated_at: new Date().toISOString(),
  });
};

export const deleteMobileGroup = async (
  id: number,
  guildId: string = GUILD_ID_PLACEHOLDER
): Promise<void> => {
  console.log(`Mock API: Deleting Mobile Group ${id} for guild ${guildId}`);
  return Promise.resolve();
};

// GlobalEvent services would go here if they were being implemented in this step.
