// src/ui/src/services/questService.ts

import {
  PaginatedResponse,
  QuestlineData,
  QuestlinePayload,
  GeneratedQuestData,
  GeneratedQuestPayload,
  QuestStepData,
  QuestStepPayload,
  PlayerQuestProgressData,
  PlayerQuestProgressPayload,
  PlayerQuestProgressUpdatePayload,
  // UIQuestStatus, // Не используется напрямую в вызовах, но полезен для UI
} from '../types/quest';

// Заглушка для API клиента. В реальном приложении это будет реальный HTTP клиент.
const apiClient = {
  async get<T>(endpoint: string, params?: Record<string, any>): Promise<T> {
    console.log(`[STUB] GET ${endpoint} with params:`, params);
    // Имитация ответа сервера в зависимости от эндпоинта
    if (endpoint.includes('/master_quest/questline_list')) {
      return Promise.resolve({
        items: [{ id: 1, guild_id: params?.guildId || '1', static_id: 'main_story', title_i18n: { en: 'Main Story' }, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), is_main_storyline: true }],
        total: 1, page: params?.page || 1, limit: params?.limit || 10, total_pages: 1
      } as any);
    }
    if (endpoint.includes('/master_quest/generated_quest_list')) {
       return Promise.resolve({
        items: [{ id: 101, guild_id: params?.guildId || '1', static_id: 'kill_goblins', title_i18n: { en: 'Kill Goblins' }, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), is_repeatable: false, questline_id: 1 }],
        total: 1, page: params?.page || 1, limit: params?.limit || 10, total_pages: 1
      } as any);
    }
     if (endpoint.includes('/master_quest/quest_step_list')) {
       return Promise.resolve({
        items: [{ id: 201, quest_id: params?.quest_id || 101, step_order:1, title_i18n: { en: 'Slay 5 Goblins' }, description_i18n: {en: '...'}, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }],
        total: 1, page: params?.page || 1, limit: params?.limit || 10, total_pages: 1
      } as any);
    }
    if (endpoint.includes('/master_quest/progress_list')) {
       return Promise.resolve({
        items: [{ id: 301, guild_id: params?.guildId || '1', quest_id: 101, player_id:1, status: 'IN_PROGRESS', created_at: new Date().toISOString(), updated_at: new Date().toISOString() }],
        total: 1, page: params?.page || 1, limit: params?.limit || 10, total_pages: 1
      } as any);
    }
    // Для детальных запросов
    if (endpoint.match(/\/master_quest\/questline_view\/\d+/)) {
        return Promise.resolve({ id: 1, guild_id: '1', static_id: 'main_story', title_i18n: { en: 'Main Story' }, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), is_main_storyline: true } as any);
    }
     if (endpoint.match(/\/master_quest\/generated_quest_view\/\d+/)) {
        return Promise.resolve({ id: 101, guild_id: '1', static_id: 'kill_goblins', title_i18n: { en: 'Kill Goblins' }, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), is_repeatable: false, questline_id: 1 } as any);
    }
    // ... другие эндпоинты для get
    return Promise.reject(new Error(`[STUB] Unknown GET endpoint: ${endpoint}`));
  },

  async post<T>(endpoint: string, data: any): Promise<T> {
    console.log(`[STUB] POST ${endpoint} with data:`, data);
    // Имитация создания и возврата созданного объекта с ID
    return Promise.resolve({ ...data, id: Math.floor(Math.random() * 1000) + 1, created_at: new Date().toISOString(), updated_at: new Date().toISOString() } as any);
  },

  async put<T>(endpoint: string, data: any): Promise<T> {
    console.log(`[STUB] PUT ${endpoint} with data:`, data);
    // Имитация обновления и возврата обновленного объекта
    // В реальном API PUT может возвращать обновленный объект или статус 200/204
    return Promise.resolve({ ...data, updated_at: new Date().toISOString() } as any);
  },

  async delete(endpoint: string): Promise<void> {
    console.log(`[STUB] DELETE ${endpoint}`);
    return Promise.resolve();
  },
};

// --- Questline Services ---

export const getQuestlines = async (
  guildId: string, page?: number, limit?: number
): Promise<PaginatedResponse<QuestlineData>> => {
  return apiClient.get<PaginatedResponse<QuestlineData>>(`/master_command_endpoint/master_quest/questline_list`, { guildId, page, limit });
};

export const getQuestline = async (guildId: string, questlineId: number): Promise<QuestlineData> => {
  return apiClient.get<QuestlineData>(`/master_command_endpoint/master_quest/questline_view/${questlineId}`, { guildId });
};

export const createQuestline = async (guildId: string, payload: QuestlinePayload): Promise<QuestlineData> => {
  return apiClient.post<QuestlineData>(`/master_command_endpoint/master_quest/questline_create`, { guildId, ...payload });
};

export const updateQuestline = async (
  guildId: string, questlineId: number, fieldToUpdate: string, newValue: any // Simplified for stub
): Promise<QuestlineData> => {
  // В реальном API это может быть PATCH или PUT с определенной структурой
  return apiClient.put<QuestlineData>(`/master_command_endpoint/master_quest/questline_update/${questlineId}`, { guildId, field_to_update: fieldToUpdate, new_value: newValue });
};

export const deleteQuestline = async (guildId: string, questlineId: number): Promise<void> => {
  return apiClient.delete(`/master_command_endpoint/master_quest/questline_delete/${questlineId}?guildId=${guildId}`);
};

// --- GeneratedQuest Services ---

export const getGeneratedQuests = async (
  guildId: string, questlineId?: number, page?: number, limit?: number
): Promise<PaginatedResponse<GeneratedQuestData>> => {
  return apiClient.get<PaginatedResponse<GeneratedQuestData>>(`/master_command_endpoint/master_quest/generated_quest_list`, { guildId, questline_id: questlineId, page, limit });
};

export const getGeneratedQuest = async (guildId: string, questId: number): Promise<GeneratedQuestData> => {
  // UI может захотеть также загрузить шаги квеста здесь или отдельным запросом
  return apiClient.get<GeneratedQuestData>(`/master_command_endpoint/master_quest/generated_quest_view/${questId}`, { guildId });
};

export const createGeneratedQuest = async (guildId: string, payload: GeneratedQuestPayload): Promise<GeneratedQuestData> => {
  return apiClient.post<GeneratedQuestData>(`/master_command_endpoint/master_quest/generated_quest_create`, { guildId, ...payload });
};

export const updateGeneratedQuest = async (
  guildId: string, questId: number, fieldToUpdate: string, newValue: any
): Promise<GeneratedQuestData> => {
  return apiClient.put<GeneratedQuestData>(`/master_command_endpoint/master_quest/generated_quest_update/${questId}`, { guildId, field_to_update: fieldToUpdate, new_value: newValue });
};

export const deleteGeneratedQuest = async (guildId: string, questId: number): Promise<void> => {
  return apiClient.delete(`/master_command_endpoint/master_quest/generated_quest_delete/${questId}?guildId=${guildId}`);
};

// --- QuestStep Services ---

export const getQuestSteps = async (
  guildId: string, questId: number, page?: number, limit?: number
): Promise<PaginatedResponse<QuestStepData>> => {
  return apiClient.get<PaginatedResponse<QuestStepData>>(`/master_command_endpoint/master_quest/quest_step_list`, { guildId, quest_id: questId, page, limit });
};

export const getQuestStep = async (guildId: string, questStepId: number): Promise<QuestStepData> => {
  return apiClient.get<QuestStepData>(`/master_command_endpoint/master_quest/quest_step_view/${questStepId}`, { guildId });
};

export const createQuestStep = async (guildId: string, payload: QuestStepPayload): Promise<QuestStepData> => {
  return apiClient.post<QuestStepData>(`/master_command_endpoint/master_quest/quest_step_create`, { guildId, ...payload });
};

export const updateQuestStep = async (
  guildId: string, questStepId: number, fieldToUpdate: string, newValue: any
): Promise<QuestStepData> => {
  return apiClient.put<QuestStepData>(`/master_command_endpoint/master_quest/quest_step_update/${questStepId}`, { guildId, field_to_update: fieldToUpdate, new_value: newValue });
};

export const deleteQuestStep = async (guildId: string, questStepId: number): Promise<void> => {
  return apiClient.delete(`/master_command_endpoint/master_quest/quest_step_delete/${questStepId}?guildId=${guildId}`);
};

// --- PlayerQuestProgress Services ---

export const getPlayerQuestProgressList = async (
  guildId: string, filters: { playerId?: number; partyId?: number; questId?: number; status?: string }, page?: number, limit?: number
): Promise<PaginatedResponse<PlayerQuestProgressData>> => {
  return apiClient.get<PaginatedResponse<PlayerQuestProgressData>>(`/master_command_endpoint/master_quest/progress_list`, {
    guildId,
    player_id: filters.playerId,
    party_id: filters.partyId,
    quest_id: filters.questId,
    status: filters.status,
    page,
    limit,
  });
};

export const getPlayerQuestProgress = async (guildId: string, progressId: number): Promise<PlayerQuestProgressData> => {
  return apiClient.get<PlayerQuestProgressData>(`/master_command_endpoint/master_quest/progress_view/${progressId}`, { guildId });
};

export const createPlayerQuestProgress = async (guildId: string, payload: PlayerQuestProgressPayload): Promise<PlayerQuestProgressData> => {
  return apiClient.post<PlayerQuestProgressData>(`/master_command_endpoint/master_quest/progress_create`, { guildId, ...payload });
};

export const updatePlayerQuestProgress = async (
  guildId: string, progressId: number, payload: PlayerQuestProgressUpdatePayload
): Promise<PlayerQuestProgressData> => {
  return apiClient.put<PlayerQuestProgressData>(`/master_command_endpoint/master_quest/progress_update/${progressId}`, {
    guildId,
    field_to_update: payload.field_to_update,
    new_value: payload.new_value,
  });
};

export const deletePlayerQuestProgress = async (guildId: string, progressId: number): Promise<void> => {
  return apiClient.delete(`/master_command_endpoint/master_quest/progress_delete/${progressId}?guildId=${guildId}`);
};

// TODO: Добавить обработку ошибок, типизацию параметров и ответов API более строго,
//       а также интеграцию с реальным apiClient, когда он будет готов.
//       Эндпоинты `/master_command_endpoint/...` являются плейсхолдерами.
//       Реальные эндпоинты будут зависеть от реализации API шлюза.
//       Для команд update, которые принимают field_to_update и new_value,
//       UI может предпочесть отправлять Partial<EntityPayload> на PATCH эндпоинт,
//       если API шлюз будет это поддерживать. Текущие стабы отражают команды "как есть".
