import { getLocations, getLocationDetails } from './locationService';
import { apiClient } from './apiClient';
import { PaginatedResponse } from '../types/entities';
import { UILocationData } from '../types/location';

// Mock the apiClient
jest.mock('./apiClient', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(), // if master commands are called via post
  },
}));

const GUILD_ID = 'test-guild-456';

describe('locationService', () => {
  beforeEach(() => {
    (apiClient.get as jest.Mock).mockClear();
    (apiClient.post as jest.Mock).mockClear();
  });

  describe('getLocations', () => {
    it('should fetch locations (mocked)', async () => {
      // Since the service function itself contains the mock logic for now:
      const result = await getLocations(GUILD_ID, { page: 1, limit: 5 });
      expect(result.items.length).toBeGreaterThanOrEqual(0); // Check based on mock service data
      expect(result.current_page).toBe(1);
    });
  });

  describe('getLocationDetails', () => {
    it('should fetch single location details by ID (mocked)', async () => {
      const LOCATION_ID = 1;
      const result = await getLocationDetails(GUILD_ID, LOCATION_ID);
      expect(result.id).toEqual(LOCATION_ID);
      expect(result.name_i18n).toBeDefined();
    });

    it('should fetch single location details by static_id (mocked)', async () => {
        const LOCATION_STATIC_ID = 'town_square_static_id';
        const result = await getLocationDetails(GUILD_ID, LOCATION_STATIC_ID);
        expect(result.static_id).toEqual(LOCATION_STATIC_ID);
        expect(result.name_i18n).toBeDefined();
      });

    it('should reject if location not found (mocked)', async () => {
      await expect(getLocationDetails(GUILD_ID, 'nonexistent_location_static_id')).rejects.toThrow('Location not found');
      await expect(getLocationDetails(GUILD_ID, 99999)).rejects.toThrow('Location not found');
    });
  });
});
