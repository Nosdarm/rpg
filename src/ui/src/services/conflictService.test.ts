import {
  getPendingConflicts,
  getConflictDetails,
  getConflictResolutionOutcomeOptions,
  resolveConflict,
} from './conflictService';
import { UIConflictStatus, UIResolveConflictPayload } from '../types/conflict';

// Mock global console.log to avoid polluting test output if services use it
// global.console = { ...console, log: jest.fn() };

describe('conflictService', () => {
  const mockGuildId = 'guildTest123';

  describe('getPendingConflicts', () => {
    it('should return a paginated list of conflict list items', async () => {
      const response = await getPendingConflicts(mockGuildId, UIConflictStatus.PENDING_MASTER_RESOLUTION, 1, 5);
      expect(response).toHaveProperty('items');
      expect(response).toHaveProperty('current_page', 1);
      expect(response).toHaveProperty('limit_per_page', 5);
      expect(response).toHaveProperty('total_items');
      expect(response).toHaveProperty('total_pages');
      if (response.items.length > 0) {
        expect(response.items[0]).toHaveProperty('id');
        expect(response.items[0]).toHaveProperty('status');
        expect(response.items[0]).toHaveProperty('created_at');
        expect(response.items[0]).toHaveProperty('involved_entities_summary');
      }
    });

    it('should filter by status if provided', async () => {
      // This test relies on the mock implementation filtering correctly.
      // For a real API, you'd mock the fetch call and verify query params.
      const response = await getPendingConflicts(mockGuildId, UIConflictStatus.RESOLVED_BY_MASTER_DISMISS, 1, 5);
      response.items.forEach(item => {
        expect(item.status).toBe(UIConflictStatus.RESOLVED_BY_MASTER_DISMISS);
      });
    });
  });

  describe('getConflictDetails', () => {
    it('should return conflict details for a given ID', async () => {
      const conflictId = 1;
      const response = await getConflictDetails(mockGuildId, conflictId);
      expect(response).toHaveProperty('id', conflictId);
      expect(response).toHaveProperty('guild_id', mockGuildId);
      expect(response).toHaveProperty('status');
      expect(response).toHaveProperty('involved_entities');
      expect(response).toHaveProperty('conflicting_actions');
      expect(response.involved_entities[0]).toHaveProperty('actor');
      expect(response.involved_entities[0]).toHaveProperty('action');
    });
  });

  describe('getConflictResolutionOutcomeOptions', () => {
    it('should return a list of master outcome options', async () => {
      const response = await getConflictResolutionOutcomeOptions(mockGuildId);
      expect(Array.isArray(response)).toBe(true);
      expect(response.length).toBeGreaterThan(0);
      if (response.length > 0) {
        expect(response[0]).toHaveProperty('id');
        expect(response[0]).toHaveProperty('name_key');
      }
      // Check for specific expected outcomes
      const outcomeIds = response.map(opt => opt.id);
      expect(outcomeIds).toContain(UIConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION1);
      expect(outcomeIds).toContain(UIConflictStatus.RESOLVED_BY_MASTER_DISMISS);
    });
  });

  describe('resolveConflict', () => {
    it('should return a success response when resolving a conflict', async () => {
      const conflictId = 1;
      const payload: UIResolveConflictPayload = {
        outcome_status: UIConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION1,
        notes: 'Master resolved this.',
      };
      const response = await resolveConflict(mockGuildId, conflictId, payload);
      expect(response).toHaveProperty('success', true);
      expect(response).toHaveProperty('message');
      expect(response.message).toContain(`Conflict ${conflictId} resolved`);
      expect(response.message).toContain(payload.outcome_status);
      expect(response.message).toContain(payload.notes);
    });

    it('should return a failure response if outcome_status is missing', async () => {
        const conflictId = 2;
        const payload = { notes: 'Missing outcome' } as UIResolveConflictPayload; // Type assertion
        const response = await resolveConflict(mockGuildId, conflictId, payload);
        expect(response.success).toBe(false);
        expect(response.message).toBe('Outcome status is required.');
      });
  });
});
