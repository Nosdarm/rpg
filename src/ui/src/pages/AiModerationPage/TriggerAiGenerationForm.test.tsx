// src/ui/src/pages/AiModerationPage/TriggerAiGenerationForm.test.tsx
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import TriggerAiGenerationForm from './TriggerAiGenerationForm';
import { pendingGenerationService } from '../../services/pendingGenerationService';
import { UIPendingGeneration, UIMRModerationStatus, TriggerGenerationPayload } from '../../types/pending_generation';

jest.mock('../../services/pendingGenerationService');
const mockTriggerGeneration = pendingGenerationService.triggerGeneration as jest.MockedFunction<typeof pendingGenerationService.triggerGeneration>;

const guildId = 1;
const entityTypes = ["location", "npc", "item", "quest", "faction", "world_event", "lore_entry"];


describe('TriggerAiGenerationForm', () => {
  beforeEach(() => {
    mockTriggerGeneration.mockReset();
  });

  test('renders the form with default values', () => {
    render(<TriggerAiGenerationForm guildId={guildId} />);
    expect(screen.getByLabelText('Entity Type:')).toHaveValue(entityTypes[0]);
    expect(screen.getByLabelText('Generation Context (JSON):')).toHaveValue('{}');
    expect(screen.getByLabelText('Location ID Context (Optional):')).toHaveValue('');
    expect(screen.getByLabelText('Player ID Context (Optional):')).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Trigger Generation' })).toBeInTheDocument();
  });

  test('updates form fields on user input', () => {
    render(<TriggerAiGenerationForm guildId={guildId} />);

    const entityTypeSelect = screen.getByLabelText('Entity Type:');
    fireEvent.change(entityTypeSelect, { target: { value: 'npc' } });
    expect(entityTypeSelect).toHaveValue('npc');

    const contextTextarea = screen.getByLabelText('Generation Context (JSON):');
    fireEvent.change(contextTextarea, { target: { value: '{"difficulty":"hard"}' } });
    expect(contextTextarea).toHaveValue('{"difficulty":"hard"}');

    const locationInput = screen.getByLabelText('Location ID Context (Optional):');
    fireEvent.change(locationInput, { target: { value: '101' } });
    expect(locationInput).toHaveValue(101);

    const playerInput = screen.getByLabelText('Player ID Context (Optional):');
    fireEvent.change(playerInput, { target: { value: '303' } });
    expect(playerInput).toHaveValue(303);
  });

  test('submits the form with all fields and shows success, then resets form', async () => {
    const mockSuccessResponse: UIPendingGeneration = {
      id: 99, status: UIMRModerationStatus.PENDING_MODERATION, guild_id: guildId,
      triggered_by_user_id: null, trigger_context_json: {}, ai_prompt_text: null, raw_ai_response_text: null,
      parsed_validated_data_json: null, validation_issues_json: null, master_id: null, master_notes: null,
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    };
    mockTriggerGeneration.mockResolvedValue(mockSuccessResponse);
    const handleTriggered = jest.fn();

    render(<TriggerAiGenerationForm guildId={guildId} onGenerationTriggered={handleTriggered} />);

    fireEvent.change(screen.getByLabelText('Entity Type:'), { target: { value: 'item' } });
    fireEvent.change(screen.getByLabelText('Generation Context (JSON):'), { target: { value: '{"material":"gold"}' } });
    fireEvent.change(screen.getByLabelText('Location ID Context (Optional):'), { target: { value: '202' } });
    fireEvent.change(screen.getByLabelText('Player ID Context (Optional):'), { target: { value: '404' } });

    fireEvent.click(screen.getByRole('button', { name: 'Trigger Generation' }));

    await waitFor(() => {
      expect(mockTriggerGeneration).toHaveBeenCalledWith(guildId, {
        entity_type: 'item',
        generation_context_json: { material: 'gold' },
        location_id_context: 202,
        player_id_context: 404,
      });
      expect(screen.getByText('Generation triggered successfully! Pending ID: 99, Status: PENDING_MODERATION')).toBeInTheDocument();
      expect(handleTriggered).toHaveBeenCalledWith(mockSuccessResponse);
    });

    // Check form reset
    expect(screen.getByLabelText('Entity Type:')).toHaveValue(entityTypes[0]);
    expect(screen.getByLabelText('Generation Context (JSON):')).toHaveValue('{}');
    expect(screen.getByLabelText('Location ID Context (Optional):')).toHaveValue('');
    expect(screen.getByLabelText('Player ID Context (Optional):')).toHaveValue('');
  });

  test('submits with empty context JSON (uses default {}), location and player IDs', async () => {
    mockTriggerGeneration.mockResolvedValue({ id: 100, status: UIMRModerationStatus.PENDING_MODERATION } as UIPendingGeneration);
    render(<TriggerAiGenerationForm guildId={guildId} />);

    fireEvent.change(screen.getByLabelText('Entity Type:'), { target: { value: 'quest' } });
    fireEvent.change(screen.getByLabelText('Generation Context (JSON):'), { target: { value: '   {}   ' } }); // Empty or whitespace around {}
    fireEvent.change(screen.getByLabelText('Location ID Context (Optional):'), { target: { value: '500' } });
    fireEvent.change(screen.getByLabelText('Player ID Context (Optional):'), { target: { value: '600' } });


    fireEvent.click(screen.getByRole('button', { name: 'Trigger Generation' }));

    await waitFor(() => {
      expect(mockTriggerGeneration).toHaveBeenCalledWith(guildId, {
        entity_type: 'quest',
        generation_context_json: {}, // Should be parsed to empty object
        location_id_context: 500,
        player_id_context: 600,
      });
    });
  });

  test('submits with no optional fields (empty strings for IDs, default JSON)', async () => {
    mockTriggerGeneration.mockResolvedValue({ id: 101, status: UIMRModerationStatus.PENDING_MODERATION } as UIPendingGeneration);
    render(<TriggerAiGenerationForm guildId={guildId} />);

    fireEvent.change(screen.getByLabelText('Entity Type:'), { target: { value: 'faction' } });
    // generationContextJson defaults to '{}'
    // locationIdContext defaults to ''
    // playerIdContext defaults to ''

    fireEvent.click(screen.getByRole('button', { name: 'Trigger Generation' }));

    await waitFor(() => {
      expect(mockTriggerGeneration).toHaveBeenCalledWith(guildId, {
        entity_type: 'faction',
        generation_context_json: {}, // Default empty object
        location_id_context: undefined, // Empty string should become undefined
        player_id_context: undefined,   // Empty string should become undefined
      });
    });
  });


  test('shows error message if generation context JSON is invalid', async () => {
    render(<TriggerAiGenerationForm guildId={guildId} />);
    fireEvent.change(screen.getByLabelText('Generation Context (JSON):'), { target: { value: '{"invalid_json"' } });
    fireEvent.click(screen.getByRole('button', { name: 'Trigger Generation' }));

    await waitFor(() => {
      expect(screen.getByText('Error: Invalid JSON format for Generation Context. Please provide valid JSON or an empty object {}.')).toBeInTheDocument();
    });
    expect(mockTriggerGeneration).not.toHaveBeenCalled();
  });

  test('shows error message if location ID is not a number', async () => {
    render(<TriggerAiGenerationForm guildId={guildId} />);
    fireEvent.change(screen.getByLabelText('Location ID Context (Optional):'), { target: { value: 'abc' } });
    fireEvent.click(screen.getByRole('button', { name: 'Trigger Generation' }));

    await waitFor(() => {
      expect(screen.getByText('Error: Location ID Context must be a valid number.')).toBeInTheDocument();
    });
    expect(mockTriggerGeneration).not.toHaveBeenCalled();
  });

  test('shows error message if player ID is not a number', async () => {
    render(<TriggerAiGenerationForm guildId={guildId} />);
    fireEvent.change(screen.getByLabelText('Player ID Context (Optional):'), { target: { value: 'xyz' } });
    fireEvent.click(screen.getByRole('button', { name: 'Trigger Generation' }));

    await waitFor(() => {
      expect(screen.getByText('Error: Player ID Context must be a valid number.')).toBeInTheDocument();
    });
    expect(mockTriggerGeneration).not.toHaveBeenCalled();
  });

  test('shows error message if service call fails', async () => {
    mockTriggerGeneration.mockRejectedValue(new Error('Network Error'));
    render(<TriggerAiGenerationForm guildId={guildId} />);
    fireEvent.change(screen.getByLabelText('Entity Type:'), { target: { value: 'quest' } });
    fireEvent.click(screen.getByRole('button', { name: 'Trigger Generation' }));

    await waitFor(() => {
      expect(screen.getByText('Error: Failed to trigger generation: Network Error')).toBeInTheDocument();
    });
  });

  test('disables submit button while loading', async () => {
    mockTriggerGeneration.mockImplementation(() => new Promise(resolve => setTimeout(() => resolve({id: 1, status: UIMRModerationStatus.PENDING_MODERATION} as UIPendingGeneration), 100)));
    render(<TriggerAiGenerationForm guildId={guildId} />);

    const submitButton = screen.getByRole('button', { name: 'Trigger Generation' });
    fireEvent.click(submitButton);

    expect(submitButton).toBeDisabled();
    expect(screen.getByText('Triggering...')).toBeInTheDocument();

    await waitFor(() => expect(submitButton).not.toBeDisabled());
  });
});
