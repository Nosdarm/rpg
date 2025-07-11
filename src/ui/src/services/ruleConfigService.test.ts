import { ruleConfigService, RuleConfigCreatePayload, RuleConfigSetPayload } from './ruleConfigService';
import { apiClient, processPaginatedResponse } from './apiClient'; // Mock this
import type { RuleConfigEntry } from 'src/types/ruleconfig';
import type { PaginatedResponse, ApiPaginatedResponse } from 'src/types/entities';

// Mock apiClient
jest.mock('./apiClient', () => ({
  apiClient: {
    post: jest.fn(),
  },
  processPaginatedResponse: jest.fn( (response: ApiPaginatedResponse<any>) => ({ // Simple mock for processPaginatedResponse
    items: response.results || response.items,
    current_page: response.current_page || response.page || 1,
    total_pages: response.total_pages || Math.ceil((response.count || response.total_items || 0) / (response.limit_per_page || 10)),
    total_items: response.count || response.total_items || 0,
    limit_per_page: response.limit_per_page || 10,
  })),
}));

const mockApiClientPost = apiClient.post as jest.Mock;
const mockProcessPaginatedResponse = processPaginatedResponse as jest.Mock;


describe('ruleConfigService', () => {
  const guildId = 'test-guild-123';

  beforeEach(() => {
    // Clear mock call history before each test
    mockApiClientPost.mockClear();
    mockProcessPaginatedResponse.mockClear();
  });

  describe('listRuleConfigEntries', () => {
    it('should call apiClient.post with correct parameters for listing rules', async () => {
      const mockApiResponse: ApiPaginatedResponse<RuleConfigEntry> = { results: [], count: 0, page: 1, total_pages: 0, limit_per_page: 10 };
      mockApiClientPost.mockResolvedValueOnce(mockApiResponse);
      mockProcessPaginatedResponse.mockImplementation(response => response);


      await ruleConfigService.listRuleConfigEntries(guildId, 'test.prefix', 2, 20);

      expect(mockApiClientPost).toHaveBeenCalledWith('/master_ruleconfig', {
        command_name: 'list',
        guild_id: guildId,
        parameters: { prefix: 'test.prefix', page: 2, limit: 20 },
      });
      expect(mockProcessPaginatedResponse).toHaveBeenCalledWith(mockApiResponse);
    });

    it('should call apiClient.post with default pagination if not provided', async () => {
      const mockApiResponse: ApiPaginatedResponse<RuleConfigEntry> = { results: [], count: 0, page: 1, total_pages: 0, limit_per_page: 10 };
       mockApiClientPost.mockResolvedValueOnce(mockApiResponse);
      mockProcessPaginatedResponse.mockImplementation(response => response);

      await ruleConfigService.listRuleConfigEntries(guildId);
      expect(mockApiClientPost).toHaveBeenCalledWith('/master_ruleconfig', {
        command_name: 'list',
        guild_id: guildId,
        parameters: { page: 1, limit: 10 }, // Default prefix is undefined, so not included
      });
    });
  });

  describe('getRuleConfigEntry', () => {
    it('should call apiClient.post with correct parameters for getting a rule', async () => {
      const mockRule: RuleConfigEntry = { key: 'test.key', value_json: { data: 'value' } };
      mockApiClientPost.mockResolvedValueOnce(mockRule);

      const result = await ruleConfigService.getRuleConfigEntry(guildId, 'test.key');

      expect(mockApiClientPost).toHaveBeenCalledWith('/master_ruleconfig', {
        command_name: 'get',
        guild_id: guildId,
        parameters: { key: 'test.key' },
      });
      expect(result).toEqual(mockRule);
    });
  });

  describe('createRuleConfigEntry', () => {
    it('should call apiClient.post for "set" and then for "get"', async () => {
      const payload: RuleConfigCreatePayload = { key: 'new.key', value_json: '{"data":"new_value"}', description: 'A new rule' };
      const mockCreatedRule: RuleConfigEntry = { key: 'new.key', value_json: { data: 'new_value' }, description: 'A new rule' };

      mockApiClientPost
        .mockResolvedValueOnce(undefined) // For the 'set' command
        .mockResolvedValueOnce(mockCreatedRule); // For the subsequent 'get' command

      const result = await ruleConfigService.createRuleConfigEntry(guildId, payload);

      expect(mockApiClientPost).toHaveBeenCalledWith('/master_ruleconfig', {
        command_name: 'set',
        guild_id: guildId,
        parameters: { key: payload.key, value_json: payload.value_json },
      });
      expect(mockApiClientPost).toHaveBeenCalledWith('/master_ruleconfig', {
        command_name: 'get',
        guild_id: guildId,
        parameters: { key: payload.key },
      });
      expect(result).toEqual(mockCreatedRule);
    });
  });

  describe('updateRuleConfigEntry', () => {
    it('should call apiClient.post for "set" and then for "get"', async () => {
      const ruleKey = 'existing.key';
      const payload: RuleConfigSetPayload = { value_json: '{"data":"updated_value"}', description: 'Updated desc' };
      const mockUpdatedRule: RuleConfigEntry = { key: ruleKey, value_json: { data: 'updated_value' }, description: 'Updated desc' };

      mockApiClientPost
        .mockResolvedValueOnce(undefined) // For 'set'
        .mockResolvedValueOnce(mockUpdatedRule); // For 'get'

      const result = await ruleConfigService.updateRuleConfigEntry(guildId, ruleKey, payload);

      expect(mockApiClientPost).toHaveBeenCalledWith('/master_ruleconfig', {
        command_name: 'set',
        guild_id: guildId,
        parameters: { key: ruleKey, value_json: payload.value_json },
      });
      expect(mockApiClientPost).toHaveBeenCalledWith('/master_ruleconfig', {
        command_name: 'get',
        guild_id: guildId,
        parameters: { key: ruleKey },
      });
      expect(result).toEqual(mockUpdatedRule);
    });
  });

  describe('deleteRuleConfigEntry', () => {
    it('should call apiClient.post with correct parameters for deleting a rule', async () => {
      mockApiClientPost.mockResolvedValueOnce(undefined);

      await ruleConfigService.deleteRuleConfigEntry(guildId, 'delete.key');

      expect(mockApiClientPost).toHaveBeenCalledWith('/master_ruleconfig', {
        command_name: 'delete',
        guild_id: guildId,
        parameters: { key: 'delete.key' },
      });
    });
  });
});
