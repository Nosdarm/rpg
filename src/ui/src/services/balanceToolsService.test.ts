// src/ui/src/services/balanceToolsService.test.ts
import {
  simulateCheck,
  simulateCombatAction,
  simulateConflict,
  analyzeAiGeneration,
} from './balanceToolsService';
import apiClient from './apiClient';
import type { IUICheckResult, UICombatActionResult, UIPydanticConflictForSim, UIAiAnalysisResult, UISimulateCheckParams, UISimulateCombatActionParams, UISimulateConflictParams, UIAnalyzeAiGenerationParams, UIAnalyzableEntityType } from '../types/simulation';

// Mock apiClient
jest.mock('./apiClient', () => ({
  post: jest.fn(),
}));

const mockGuildId = 'test-guild-123';

describe('balanceToolsService', () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('simulateCheck', () => {
    it('should call apiClient.post with correct parameters and return data', async () => {
      const params: UISimulateCheckParams = {
        check_type: 'perception',
        actor_id: 1,
        actor_type: 'player',
      };
      const mockResponseData: IUICheckResult = {} as IUICheckResult; // Populate with mock data if needed
      (apiClient.post as jest.Mock).mockResolvedValueOnce({ data: mockResponseData });

      const result = await simulateCheck(mockGuildId, params);

      expect(apiClient.post).toHaveBeenCalledWith('/master_command_endpoint', {
        command_name: 'master_simulate check',
        guild_id: mockGuildId,
        parameters: params,
      });
      expect(result).toEqual(mockResponseData);
    });
  });

  describe('simulateCombatAction', () => {
    it('should call apiClient.post with correct parameters and return data', async () => {
      const params: UISimulateCombatActionParams = {
        combat_encounter_id: 10,
        actor_id: 1,
        actor_type: 'player',
        action_json_data: '{}',
        dry_run: true,
      };
      const mockResponseData: UICombatActionResult = {} as UICombatActionResult;
      (apiClient.post as jest.Mock).mockResolvedValueOnce({ data: mockResponseData });

      const result = await simulateCombatAction(mockGuildId, params);

      expect(apiClient.post).toHaveBeenCalledWith('/master_command_endpoint', {
        command_name: 'master_simulate combat_action',
        guild_id: mockGuildId,
        parameters: params,
      });
      expect(result).toEqual(mockResponseData);
    });
  });

  describe('simulateConflict', () => {
    it('should call apiClient.post with correct parameters and return data', async () => {
      const params: UISimulateConflictParams = {
        actions_json: '[]',
      };
      const mockResponseData: UIPydanticConflictForSim[] = [];
      (apiClient.post as jest.Mock).mockResolvedValueOnce({ data: mockResponseData });

      const result = await simulateConflict(mockGuildId, params);

      expect(apiClient.post).toHaveBeenCalledWith('/master_command_endpoint', {
        command_name: 'master_simulate conflict',
        guild_id: mockGuildId,
        parameters: params,
      });
      expect(result).toEqual(mockResponseData);
    });
  });

  describe('analyzeAiGeneration', () => {
    it('should call apiClient.post with correct parameters and return data', async () => {
      const params: UIAnalyzeAiGenerationParams = {
        entity_type: UIAnalyzableEntityType.NPC,
        target_count: 1,
        use_real_ai: false,
      };
      const mockResponseData: UIAiAnalysisResult = {} as UIAiAnalysisResult;
      (apiClient.post as jest.Mock).mockResolvedValueOnce({ data: mockResponseData });

      const result = await analyzeAiGeneration(mockGuildId, params);

      expect(apiClient.post).toHaveBeenCalledWith('/master_command_endpoint', {
        command_name: 'master_analyze ai_generation',
        guild_id: mockGuildId,
        parameters: params,
      });
      expect(result).toEqual(mockResponseData);
    });
  });
});

console.log("src/ui/src/services/balanceToolsService.test.ts defined");
