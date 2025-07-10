import { apiClient } from './apiClient';
import type {
  UIPendingGeneration,
  TriggerGenerationPayload,
  UpdatePendingGenerationPayload,
  UIMRModerationStatus
} from 'src/types/pending_generation';
import type { PaginatedResponse } from 'src/types/entities';

const BASE_PATH = (guildId: number | string) => `/guilds/${guildId}/pending_generations`;

export const pendingGenerationService = {
  async triggerGeneration(guildId: number, payload: TriggerGenerationPayload): Promise<UIPendingGeneration> {
    // This corresponds to the new /master_pending_generation trigger command
    const mockResponse: UIPendingGeneration = {
      id: Math.floor(Math.random() * 1000) + 1,
      guild_id: guildId,
      triggered_by_user_id: 1, // Mock master user ID
      trigger_context_json: {
        requested_entity_type: payload.entity_type,
        ...(payload.generation_context_json || {})
      },
      ai_prompt_text: "Mocked AI prompt based on payload...",
      raw_ai_response_text: "Mocked raw AI response...",
      parsed_validated_data_json: { generated_name: `Mock ${payload.entity_type}` },
      validation_issues_json: null,
      status: UIMRModerationStatus.PENDING_MODERATION,
      master_id: null,
      master_notes: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    return apiClient.post<UIPendingGeneration, TriggerGenerationPayload>(`${BASE_PATH(guildId)}/trigger`, payload, mockResponse);
  },

  async listPendingGenerations(
    guildId: number,
    status?: UIMRModerationStatus | string,
    page: number = 1,
    limit: number = 10
  ): Promise<PaginatedResponse<UIPendingGeneration>> {
    const mockItems: UIPendingGeneration[] = Array.from({ length: limit }, (_, i) => ({
      id: (page - 1) * limit + i + 1,
      guild_id: guildId,
      triggered_by_user_id: 1,
      trigger_context_json: { requested_entity_type: "npc" },
      ai_prompt_text: "Short prompt...",
      raw_ai_response_text: "Short response...",
      parsed_validated_data_json: { name_i18n: { en: `Pending NPC ${(page - 1) * limit + i + 1}`}},
      validation_issues_json: null,
      status: status ? (status as UIMRModerationStatus) : UIMRModerationStatus.PENDING_MODERATION,
      master_id: null,
      master_notes: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }));
    const mockResponse: PaginatedResponse<UIPendingGeneration> = {
        items: mockItems,
        current_page: page,
        total_pages: Math.ceil(10 / limit), // Assuming 10 total items for mock
        total_items: 10,
        limit_per_page: limit,
    };
    let path = `${BASE_PATH(guildId)}?page=${page}&limit=${limit}`;
    if (status) {
      path += `&status=${status}`;
    }
    return apiClient.get<PaginatedResponse<UIPendingGeneration>>(path, mockResponse);
  },

  async getPendingGenerationById(guildId: number, pendingId: number): Promise<UIPendingGeneration> {
    const mockResponse: UIPendingGeneration = {
      id: pendingId,
      guild_id: guildId,
      triggered_by_user_id: 1,
      trigger_context_json: { requested_entity_type: "quest", details: "fetch quest" },
      ai_prompt_text: "Full AI prompt for quest generation...",
      raw_ai_response_text: "{\"entity_type\": \"quest\", \"title_i18n\": ...}",
      parsed_validated_data_json: { title_i18n: { en: "The Grand Quest" }, steps: [] },
      validation_issues_json: null,
      status: UIMRModerationStatus.PENDING_MODERATION,
      master_id: null,
      master_notes: "Needs review for balance.",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    return apiClient.get<UIPendingGeneration>(`${BASE_PATH(guildId)}/${pendingId}`, mockResponse);
  },

  async approvePendingGeneration(guildId: number, pendingId: number): Promise<UIPendingGeneration> {
    // This API might return the updated PendingGeneration object or just a success status.
    // Assuming it returns the updated object.
    const mockResponse: UIPendingGeneration = {
      id: pendingId,
      guild_id: guildId,
      triggered_by_user_id: 1,
      trigger_context_json: { requested_entity_type: "item" },
      ai_prompt_text: "Prompt for item...",
      raw_ai_response_text: "Raw response for item...",
      parsed_validated_data_json: { name_i18n: { en: "Approved Item" } },
      validation_issues_json: null,
      status: UIMRModerationStatus.SAVED, // Status after successful approval and save
      master_id: 1, // Master who approved
      master_notes: "Approved by mock service.",
      created_at: new Date(Date.now() - 200000).toISOString(),
      updated_at: new Date().toISOString(),
    };
    return apiClient.post<UIPendingGeneration, {}>(`${BASE_PATH(guildId)}/${pendingId}/approve`, {}, mockResponse);
  },

  async updatePendingGeneration(
    guildId: number,
    pendingId: number,
    payload: UpdatePendingGenerationPayload
  ): Promise<UIPendingGeneration> {
    const mockResponse: UIPendingGeneration = {
      id: pendingId,
      guild_id: guildId,
      triggered_by_user_id: 1,
      trigger_context_json: { requested_entity_type: "location" },
      ai_prompt_text: "Prompt for location...",
      raw_ai_response_text: "Raw response for location...",
      parsed_validated_data_json: payload.new_parsed_data_json || { name_i18n: { en: "Updated Location Data" } },
      validation_issues_json: null,
      status: (payload.new_status as UIMRModerationStatus) || UIMRModerationStatus.EDITED_PENDING_APPROVAL,
      master_id: 1,
      master_notes: payload.master_notes || "Updated by mock service.",
      created_at: new Date(Date.now() - 300000).toISOString(),
      updated_at: new Date().toISOString(),
    };
    return apiClient.patch<UIPendingGeneration, UpdatePendingGenerationPayload>(`${BASE_PATH(guildId)}/${pendingId}`, payload, mockResponse);
  },
};
