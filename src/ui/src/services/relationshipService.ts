import { apiClient } from './apiClient';
import type { RelationshipData, RelationshipPayload, RelationshipUpdatePayload, PaginatedResponse } from '../types/relationship';

const BASE_PATH = '/master_relationship'; // Conceptual path

// Mock data for now
const MOCK_RELATIONSHIPS: RelationshipData[] = [
  {
    id: 1,
    guild_id: 123, // Changed to number
    entity1_type: 'PLAYER',
    entity1_id: 1,
    entity1_details: { id: 1, type: 'PLAYER', name: 'PlayerOne' },
    entity2_type: 'GENERATED_FACTION',
    entity2_id: 1,
    entity2_details: { id: 1, type: 'GENERATED_FACTION', name: 'Knights of Dawn', static_id: 'knights_of_dawn'},
    relationship_type: 'member_of',
    value: 100, // Assuming value indicates status like "trusted member"
    source_log_id: null,
    // created_at: new Date().toISOString(), // Not on model
    // updated_at: new Date().toISOString(), // Not on model
  },
  {
    id: 2,
    guild_id: 123, // Changed to number
    entity1_type: 'GENERATED_FACTION',
    entity1_id: 1,
    entity1_details: { id: 1, type: 'GENERATED_FACTION', name: 'Knights of Dawn', static_id: 'knights_of_dawn'},
    entity2_type: 'GENERATED_FACTION',
    entity2_id: 2,
    entity2_details: { id: 2, type: 'GENERATED_FACTION', name: 'Shadow Syndicate', static_id: 'shadow_syndicate'},
    relationship_type: 'faction_standing',
    value: -50, // Hostile
    source_log_id: 1234,
  },
];

export const relationshipService = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getRelationships(guildId: string, filters: any = {}, page: number = 1, limit: number = 10): Promise<PaginatedResponse<RelationshipData>> {
    console.log(`relationshipService.getRelationships called for guild ${guildId}`, { filters, page, limit });

    // Mocking filtering and pagination
    // This is a very basic mock filter
    const filteredItems = MOCK_RELATIONSHIPS.filter(rel => {
      let match = true;
      if (filters.entity1_id && rel.entity1_id !== parseInt(filters.entity1_id)) match = false;
      if (filters.entity1_type && rel.entity1_type !== filters.entity1_type) match = false;
      // Add more filters as needed
      return match;
    });

    const start = (page - 1) * limit;
    const end = start + limit;
    const paginatedItems = filteredItems.slice(start, end);

    // Construct query parameters from filters object
    const queryParams = new URLSearchParams();
    queryParams.append('page', page.toString());
    queryParams.append('limit', limit.toString());
    for (const key in filters) {
      if (Object.prototype.hasOwnProperty.call(filters, key) && filters[key] !== undefined && filters[key] !== null) {
        queryParams.append(key, filters[key].toString());
      }
    }

    return apiClient.get<PaginatedResponse<RelationshipData>>(
      `${BASE_PATH}/list?${queryParams.toString()}`,
      {
        items: paginatedItems,
        total: filteredItems.length,
        page,
        limit,
      }
    );
  },

  async getRelationship(guildId: string, relationshipId: number): Promise<RelationshipData> {
    console.log(`relationshipService.getRelationship called for guild ${guildId}, relationship ${relationshipId}`);
    const relationship = MOCK_RELATIONSHIPS.find(r => r.id === relationshipId);
    return apiClient.get<RelationshipData>(
      `${BASE_PATH}/view?relationship_id=${relationshipId}`,
      relationship || MOCK_RELATIONSHIPS[0]
    );
  },

  async createRelationship(guildId: string, payload: RelationshipPayload): Promise<RelationshipData> {
    console.log(`relationshipService.createRelationship called for guild ${guildId}`, payload);
    const newRelationship: RelationshipData = {
      id: Math.max(0, ...MOCK_RELATIONSHIPS.map(r => r.id)) + 1,
      guild_id: parseInt(guildId), // Assuming guildId is string in UI context
      ...payload,
      source_log_id: payload.source_log_id ?? null,
      // entity1_details and entity2_details would typically be resolved by backend or a subsequent fetch
    };
    return apiClient.post<RelationshipData, RelationshipPayload>(
      `${BASE_PATH}/create`,
      payload,
      newRelationship
    );
  },

  async updateRelationship(guildId: string, relationshipId: number, payload: RelationshipUpdatePayload): Promise<RelationshipData> {
    console.log(`relationshipService.updateRelationship called for guild ${guildId}, relationship ${relationshipId}`, payload);
    const relIndex = MOCK_RELATIONSHIPS.findIndex(r => r.id === relationshipId);
    let updatedRelationship = MOCK_RELATIONSHIPS[relIndex];
     if (updatedRelationship) {
      // This is a simplified mock. Real update logic would be more complex.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (updatedRelationship as any)[payload.field_to_update] = payload.field_to_update === 'value' ? parseInt(payload.new_value) : payload.new_value;
      // updatedRelationship.updated_at = new Date().toISOString(); // If model had it
    }
    return apiClient.patch<RelationshipData, RelationshipUpdatePayload>( // Using PATCH
      `${BASE_PATH}/update?relationship_id=${relationshipId}`,
      payload,
      updatedRelationship || MOCK_RELATIONSHIPS[0]
    );
  },

  async deleteRelationship(guildId: string, relationshipId: number): Promise<void> {
    console.log(`relationshipService.deleteRelationship called for guild ${guildId}, relationship ${relationshipId}`);
    return apiClient.delete<void>(
      `${BASE_PATH}/delete?relationship_id=${relationshipId}`
    );
  },
};
