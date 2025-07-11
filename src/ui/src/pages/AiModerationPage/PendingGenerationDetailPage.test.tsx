// src/ui/src/pages/AiModerationPage/PendingGenerationDetailPage.test.tsx
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import PendingGenerationDetailPage from './PendingGenerationDetailPage';
import { pendingGenerationService } from '../../services/pendingGenerationService';
import { UIPendingGeneration, UIMRModerationStatus, UpdatePendingGenerationPayload } from '../../types/pending_generation';

jest.mock('../../services/pendingGenerationService');
const mockGetById = pendingGenerationService.getPendingGenerationById as jest.MockedFunction<typeof pendingGenerationService.getPendingGenerationById>;
const mockApprove = pendingGenerationService.approvePendingGeneration as jest.MockedFunction<typeof pendingGenerationService.approvePendingGeneration>;
const mockUpdate = pendingGenerationService.updatePendingGeneration as jest.MockedFunction<typeof pendingGenerationService.updatePendingGeneration>;

const guildId = 1;
const createMockItem = (id: number, status: UIMRModerationStatus, notes?: string | null, parsedData?: Record<string, any> | null): UIPendingGeneration => ({
  id,
  guild_id: guildId,
  triggered_by_user_id: 1,
  trigger_context_json: { requested_entity_type: 'npc', theme: 'forest' },
  ai_prompt_text: `Generate a forest NPC for ID ${id}`,
  raw_ai_response_text: `{"name": "Forest Spirit ${id}"}`,
  parsed_validated_data_json: parsedData === undefined ? { name: `Forest Spirit ${id}`, type: 'spirit' } : parsedData,
  validation_issues_json: null,
  status,
  master_id: null,
  master_notes: notes || null,
  created_at: new Date('2023-01-01T10:00:00Z').toISOString(),
  updated_at: new Date('2023-01-01T11:00:00Z').toISOString(),
});

describe('PendingGenerationDetailPage', () => {
  let alertSpy: jest.SpyInstance;

  beforeEach(() => {
    mockGetById.mockReset();
    mockApprove.mockReset();
    mockUpdate.mockReset();
    alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});
  });

  afterEach(() => {
    alertSpy.mockRestore();
  });

  const mockItemPending = createMockItem(123, UIMRModerationStatus.PENDING_MODERATION, 'Initial review needed.');

  test('renders loading state then item details correctly', async () => {
    mockGetById.mockResolvedValue(mockItemPending);
    render(<PendingGenerationDetailPage pendingId={123} guildId={guildId} onBackToList={() => {}} />);

    expect(screen.getByText('Loading details for item ID 123...')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Details for Pending Generation ID: 123')).toBeInTheDocument();
      expect(screen.getByText((content, node) => node?.textContent === 'Status: Pending Moderation')).toBeInTheDocument();
      expect(screen.getByText((content, node) => node?.textContent === 'Requested Type: npc')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Initial review needed.')).toBeInTheDocument(); // Master Notes
      // Check for collapsible sections (titles)
      expect(screen.getByText((content, node) => content.includes('AI Prompt:'))).toBeInTheDocument();
      expect(screen.getByText((content, node) => content.includes('Raw AI Response:'))).toBeInTheDocument();
      expect(screen.getByText((content, node) => content.includes('Parsed/Validated Data:'))).toBeInTheDocument();
      expect(screen.getByText((content, node) => content.includes('Validation Issues:'))).toBeInTheDocument();
    });
  });

  test('shows error if loading details fails and no item is loaded', async () => {
    mockGetById.mockRejectedValue(new Error('Failed to fetch'));
    render(<PendingGenerationDetailPage pendingId={123} guildId={guildId} onBackToList={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Error: Failed to load details for item ID 123: Failed to fetch')).toBeInTheDocument();
    });
  });

  test('shows "Select an item" if pendingId is null', () => {
    render(<PendingGenerationDetailPage pendingId={null} guildId={guildId} onBackToList={() => {}} />);
    expect(screen.getByText('Select an item from the list to see details.')).toBeInTheDocument();
  });

  test('calls approve service, onActionSuccess, and onBackToList on approve button click', async () => {
    mockGetById.mockResolvedValue(mockItemPending);
    mockApprove.mockResolvedValue({ ...mockItemPending, status: UIMRModerationStatus.APPROVED });
    const handleActionSuccess = jest.fn();
    const handleBackToList = jest.fn();

    render(
      <PendingGenerationDetailPage
        pendingId={123}
        guildId={guildId}
        onBackToList={handleBackToList}
        onActionSuccess={handleActionSuccess}
      />
    );
    await waitFor(() => screen.getByText('Details for Pending Generation ID: 123'));

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(mockApprove).toHaveBeenCalledWith(guildId, 123));
    expect(handleActionSuccess).toHaveBeenCalledWith('Generation approved and save process initiated!');
    expect(handleBackToList).toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalledWith('Generation approved and save process initiated!');
  });

  test('calls update service with REJECTED status and notes on reject button click', async () => {
    mockGetById.mockResolvedValue(mockItemPending);
    const updatedNotes = 'Rejected by test';
    mockUpdate.mockResolvedValue({ ...mockItemPending, status: UIMRModerationStatus.REJECTED, master_notes: updatedNotes });
    const handleActionSuccess = jest.fn();
    render(
      <PendingGenerationDetailPage
        pendingId={123}
        guildId={guildId}
        onBackToList={() => {}}
        onActionSuccess={handleActionSuccess}
      />
    );
    await waitFor(() => screen.getByText('Details for Pending Generation ID: 123'));

    const notesTextarea = screen.getByPlaceholderText('Enter moderation notes here...');
    fireEvent.change(notesTextarea, { target: { value: updatedNotes } });

    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));

    const expectedPayload: UpdatePendingGenerationPayload = {
      master_notes: updatedNotes,
      new_status: UIMRModerationStatus.REJECTED,
    };
    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith(guildId, 123, expect.objectContaining(expectedPayload)));
    expect(handleActionSuccess).toHaveBeenCalledWith('Generation updated successfully!');
    expect(alertSpy).toHaveBeenCalledWith('Generation updated successfully!');
  });

  test('allows editing parsed data, calls update, and sets EDITED_PENDING_APPROVAL status on save', async () => {
    mockGetById.mockResolvedValue(mockItemPending);
    const newParsedData = { name: "Edited Forest Spirit", type: "spirit", power: 10 };
    const newNotes = "Data edited by user.";

    mockUpdate.mockResolvedValue({
      ...mockItemPending,
      parsed_validated_data_json: newParsedData,
      master_notes: newNotes,
      status: UIMRModerationStatus.EDITED_PENDING_APPROVAL
    });
    const handleActionSuccess = jest.fn();
    render(
      <PendingGenerationDetailPage
        pendingId={123}
        guildId={guildId}
        onBackToList={() => {}}
        onActionSuccess={handleActionSuccess}
      />
    );
    await waitFor(() => screen.getByText('Details for Pending Generation ID: 123'));

    fireEvent.click(screen.getByRole('button', { name: 'Edit Parsed Data' }));
    const dataTextarea = screen.getByDisplayValue(JSON.stringify(mockItemPending.parsed_validated_data_json || {}, null, 2));
    fireEvent.change(dataTextarea, { target: { value: JSON.stringify(newParsedData, null, 2) } });

    const notesTextarea = screen.getByPlaceholderText('Enter moderation notes here...');
    fireEvent.change(notesTextarea, { target: { value: newNotes } });

    fireEvent.click(screen.getByRole('button', { name: 'Save Edits & Notes' }));

    const expectedPayload: UpdatePendingGenerationPayload = {
      master_notes: newNotes,
      new_parsed_data_json: newParsedData,
      new_status: UIMRModerationStatus.EDITED_PENDING_APPROVAL,
    };
    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith(guildId, 123, expect.objectContaining(expectedPayload)));
    expect(handleActionSuccess).toHaveBeenCalledWith('Generation updated successfully!');
    expect(alertSpy).toHaveBeenCalledWith('Generation updated successfully!');
    // Check if edit mode is exited
    expect(screen.getByRole('button', { name: 'Edit Parsed Data' })).toBeInTheDocument();
  });

  test('handles invalid JSON in edited data', async () => {
    mockGetById.mockResolvedValue(mockItemPending);
    render(<PendingGenerationDetailPage pendingId={123} guildId={guildId} onBackToList={() => {}} />);
    await waitFor(() => screen.getByText('Details for Pending Generation ID: 123'));

    fireEvent.click(screen.getByRole('button', { name: 'Edit Parsed Data' }));
    const dataTextarea = screen.getByDisplayValue(JSON.stringify(mockItemPending.parsed_validated_data_json || {}, null, 2));
    fireEvent.change(dataTextarea, { target: { value: '{"invalid_json"' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save Edits & Notes' }));

    await waitFor(() => {
      expect(screen.getByText((content, node) => content.startsWith('Error: Invalid JSON format for edited data:'))).toBeInTheDocument();
    });
    expect(mockUpdate).not.toHaveBeenCalled();
  });
});
