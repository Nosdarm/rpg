import { getWorldStateEntries, getWorldStateEntry, getStoryLogEntries, getStoryLogEntry } from './monitoringService';
import { apiClient } from './apiClient';
import { PaginatedResponse } from '../types/entities';
import { RuleConfigEntry } from '../types/ruleconfig';
import { UIStoryLogData } from '../types/monitoring';

// Mock the apiClient
jest.mock('./apiClient', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(), // if master commands are called via post
  },
}));

const GUILD_ID = 'test-guild-123';

describe('monitoringService', () => {
  beforeEach(() => {
    // Clear all instances and calls to constructor and all methods:
    (apiClient.get as jest.Mock).mockClear();
    (apiClient.post as jest.Mock).mockClear();
  });

  describe('getWorldStateEntries', () => {
    it('should fetch world state entries (mocked)', async () => {
      const mockRuleConfigEntry: RuleConfigEntry = { key: 'ws:test', value_json: { data: 'test' } };
      const mockResponse: PaginatedResponse<RuleConfigEntry> = {
        items: [mockRuleConfigEntry],
        current_page: 1,
        total_pages: 1,
        total_items: 1,
        limit_per_page: 10,
      };
      // For this test, we are testing the mock implementation within the service itself
      // In a real scenario with apiClient making actual calls, you'd mock apiClient.get here.
      // Since the service function itself contains the mock logic:
      const result = await getWorldStateEntries(GUILD_ID, { page: 1, limit: 5, prefix: 'worldstate:' });
      expect(result.items.length).toBeGreaterThanOrEqual(0); // Check based on mock service data
      expect(result.current_page).toBe(1);
    });
  });

  describe('getWorldStateEntry', () => {
    it('should fetch a single world state entry (mocked)', async () => {
      const KEY = 'worldstate:weather';
      const result = await getWorldStateEntry(GUILD_ID, KEY);
      expect(result.key).toEqual(KEY);
      expect(result.value_json).toBeDefined();
    });

    it('should reject if world state entry not found (mocked)', async () => {
      await expect(getWorldStateEntry(GUILD_ID, 'nonexistentkey')).rejects.toThrow('WorldState entry not found');
    });
  });

  describe('getStoryLogEntries', () => {
    it('should fetch story log entries (mocked)', async () => {
      const result = await getStoryLogEntries(GUILD_ID, { page: 1, limit: 5 });
      expect(result.items.length).toBeGreaterThanOrEqual(0); // Check based on mock service data
      expect(result.current_page).toBe(1);
    });
  });

  describe('getStoryLogEntry', () => {
    it('should fetch a single story log entry (mocked)', async () => {
      const LOG_ID = 1;
      const result = await getStoryLogEntry(GUILD_ID, LOG_ID);
      expect(result.id).toEqual(LOG_ID);
    });

    it('should reject if story log entry not found (mocked)', async () => {
      await expect(getStoryLogEntry(GUILD_ID, 9999)).rejects.toThrow('StoryLog entry not found');
    });
  });
});
