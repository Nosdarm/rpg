// src/ui/src/services/pendingGenerationService.test.ts
import { pendingGenerationService } from './pendingGenerationService';
import { TriggerGenerationPayload, UIMRModerationStatus, UpdatePendingGenerationPayload, UIPendingGeneration } from '../types/pending_generation';
import { PaginatedResponse } from '../types/entities';

// Если бы apiClient использовался для реальных вызовов, его нужно было бы мокировать так:
// jest.mock('./apiClient', () => ({
//   apiClient: { // Убедитесь, что имя совпадает с экспортируемым объектом
//     get: jest.fn(),
//     post: jest.fn(),
//     patch: jest.fn(),
//   }
// }));
// const mockedApiClient = apiClient as jest.Mocked<typeof apiClient>;


describe('pendingGenerationService', () => {
  const guildId = 1;

  // Перед каждым тестом можно сбрасывать моки, если apiClient мокируется глобально
  // beforeEach(() => {
  //   if (jest.isMockFunction(apiClient.get)) mockedApiClient.get.mockReset();
  //   if (jest.isMockFunction(apiClient.post)) mockedApiClient.post.mockReset();
  //   if (jest.isMockFunction(apiClient.patch)) mockedApiClient.patch.mockReset();
  // });

  describe('triggerGeneration', () => {
    it('should return a mock pending generation object based on payload', async () => {
      const payload: TriggerGenerationPayload = {
        entity_type: 'npc',
        generation_context_json: { theme: 'desert' }
      };
      // Поскольку сервис сейчас возвращает моковые данные напрямую, мы тестируем эту моковую логику.
      const result = await pendingGenerationService.triggerGeneration(guildId, payload);

      expect(result).toBeDefined();
      expect(result.id).toEqual(expect.any(Number));
      expect(result.status).toBe(UIMRModerationStatus.PENDING_MODERATION);
      expect(result.guild_id).toBe(guildId);
      expect(result.trigger_context_json?.requested_entity_type).toBe('npc');
      expect(result.trigger_context_json?.theme).toBe('desert');
      expect(result.parsed_validated_data_json?.generated_name).toBe('Mock npc');
    });
  });

  describe('listPendingGenerations', () => {
    it('should return a paginated list of mock pending generations', async () => {
      const result = await pendingGenerationService.listPendingGenerations(guildId, UIMRModerationStatus.PENDING_MODERATION, 1, 5);
      expect(result).toBeDefined();
      expect(result.items).toBeInstanceOf(Array);
      expect(result.items.length).toBe(5); // Мок должен возвращать запрошенный limit
      if (result.items.length > 0) {
        expect(result.items[0].status).toBe(UIMRModerationStatus.PENDING_MODERATION);
      }
      expect(result.current_page).toBe(1);
      expect(result.limit_per_page).toBe(5);
      expect(result.total_items).toBe(10); // Согласно моку
      expect(result.total_pages).toBe(Math.ceil(10 / 5));
    });
  });

  describe('getPendingGenerationById', () => {
    it('should return a mock pending generation object for a given ID', async () => {
      const pendingId = 123;
      const result = await pendingGenerationService.getPendingGenerationById(guildId, pendingId);
      expect(result).toBeDefined();
      expect(result.id).toBe(pendingId);
      expect(result.trigger_context_json?.requested_entity_type).toBe('quest'); // Из мока
      expect(result.master_notes).toBe('Needs review for balance.'); // Из мока
    });
  });

  describe('approvePendingGeneration', () => {
    it('should return an updated mock pending generation with SAVED status', async () => {
      const pendingId = 456;
      const result = await pendingGenerationService.approvePendingGeneration(guildId, pendingId);
      expect(result).toBeDefined();
      expect(result.id).toBe(pendingId);
      expect(result.status).toBe(UIMRModerationStatus.SAVED);
      expect(result.master_id).toBe(1);
      expect(result.master_notes).toBe("Approved by mock service.");
    });
  });

  describe('updatePendingGeneration', () => {
    it('should return an updated mock pending generation reflecting the payload', async () => {
      const pendingId = 789;
      const payload: UpdatePendingGenerationPayload = {
        new_status: UIMRModerationStatus.REJECTED,
        master_notes: 'This content is not suitable.',
      };
      const result = await pendingGenerationService.updatePendingGeneration(guildId, pendingId, payload);
      expect(result).toBeDefined();
      expect(result.id).toBe(pendingId);
      expect(result.status).toBe(UIMRModerationStatus.REJECTED);
      expect(result.master_notes).toBe('This content is not suitable.');
    });

    it('should set status to EDITED_PENDING_APPROVAL if new_parsed_data_json is provided without explicit new_status', async () => {
      const pendingId = 790;
      const payload: UpdatePendingGenerationPayload = {
        new_parsed_data_json: { name: "Edited Name" },
        master_notes: "User edited data.",
      };
      const result = await pendingGenerationService.updatePendingGeneration(guildId, pendingId, payload);
      expect(result.status).toBe(UIMRModerationStatus.EDITED_PENDING_APPROVAL);
      expect(result.parsed_validated_data_json).toEqual({ name: "Edited Name" });
      expect(result.master_notes).toBe("User edited data.");
    });
  });
});
