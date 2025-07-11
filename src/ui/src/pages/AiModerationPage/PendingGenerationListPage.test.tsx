// src/ui/src/pages/AiModerationPage/PendingGenerationListPage.test.tsx
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import PendingGenerationListPage from './PendingGenerationListPage';
import { pendingGenerationService } from '../../services/pendingGenerationService';
import { UIPendingGeneration, UIMRModerationStatus } from '../../types/pending_generation';
import { PaginatedResponse } from '../../types/entities';

jest.mock('../../services/pendingGenerationService');
const mockListPendingGenerations = pendingGenerationService.listPendingGenerations as jest.MockedFunction<typeof pendingGenerationService.listPendingGenerations>;

const mockGuildId = 123;

const createMockPendingItem = (id: number, status: UIMRModerationStatus, notes?: string | null): UIPendingGeneration => ({
  id,
  guild_id: mockGuildId,
  triggered_by_user_id: 1,
  trigger_context_json: { requested_entity_type: 'npc' },
  ai_prompt_text: `Prompt for ${id}`,
  raw_ai_response_text: `Raw response for ${id}`,
  parsed_validated_data_json: { name: `NPC ${id}` },
  validation_issues_json: null,
  status,
  master_id: null,
  master_notes: notes || null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
});

describe('PendingGenerationListPage', () => {
  beforeEach(() => {
    mockListPendingGenerations.mockReset();
  });

  test('renders loading state initially', () => {
    mockListPendingGenerations.mockReturnValue(new Promise(() => {})); // Non-resolving promise
    render(<PendingGenerationListPage guildId={mockGuildId} onSelectPendingItem={jest.fn()} />);
    expect(screen.getByText('Loading pending generations...')).toBeInTheDocument();
  });

  test('renders error state if fetching fails', async () => {
    mockListPendingGenerations.mockRejectedValue(new Error('API Error'));
    render(<PendingGenerationListPage guildId={mockGuildId} onSelectPendingItem={jest.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('Error: Failed to load pending generations: API Error')).toBeInTheDocument();
    });
  });

  test('renders "No pending generations found" when list is empty and shows filter', async () => {
    const mockEmptyResponse: PaginatedResponse<UIPendingGeneration> = {
      items: [], current_page: 1, total_pages: 0, total_items: 0, limit_per_page: 10
    };
    mockListPendingGenerations.mockResolvedValue(mockEmptyResponse);
    render(<PendingGenerationListPage guildId={mockGuildId} onSelectPendingItem={jest.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('No pending generations found for the current filter.')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Filter by Status:')).toBeInTheDocument();
  });

  test('renders a list of pending generations with details and pagination', async () => {
    const items = [
      createMockPendingItem(1, UIMRModerationStatus.PENDING_MODERATION, 'Needs review'),
      createMockPendingItem(2, UIMRModerationStatus.VALIDATION_FAILED),
    ];
    const mockResponse: PaginatedResponse<UIPendingGeneration> = {
      items, current_page: 1, total_pages: 2, total_items: 12, limit_per_page: 2
    };
    mockListPendingGenerations.mockResolvedValue(mockResponse);
    render(<PendingGenerationListPage guildId={mockGuildId} onSelectPendingItem={jest.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('ID: 1')).toBeInTheDocument();
      expect(screen.getByText('Pending Moderation')).toBeInTheDocument(); // Formatted status
      expect(screen.getByText('Type: npc')).toBeInTheDocument();
      expect(screen.getByText('Notes:')).toBeInTheDocument();
      expect(screen.getByText('Needs review')).toBeInTheDocument();

      expect(screen.getByText('ID: 2')).toBeInTheDocument();
      expect(screen.getByText('Validation Failed')).toBeInTheDocument(); // Formatted status

      expect(screen.getByText('Page 1 of 2 (Total: 12)')).toBeInTheDocument();
    });
  });

  test('calls onSelectPendingItem when a list item is clicked', async () => {
    const mockSelectItem = jest.fn();
    const items = [createMockPendingItem(101, UIMRModerationStatus.PENDING_MODERATION)];
    const mockResponse: PaginatedResponse<UIPendingGeneration> = {
      items, current_page: 1, total_pages: 1, total_items: 1, limit_per_page: 10
    };
    mockListPendingGenerations.mockResolvedValue(mockResponse);
    render(<PendingGenerationListPage guildId={mockGuildId} onSelectPendingItem={mockSelectItem} />);

    await waitFor(() => {
      // Find by role 'button' is more specific than just text if the whole li is clickable
      const listItem = screen.getByRole('listitem', { name: /ID: 101/i }); // Use a regex or more specific selector
      fireEvent.click(listItem);
      expect(mockSelectItem).toHaveBeenCalledWith(101);
    });
  });

  test('calls onSelectPendingItem when Enter key is pressed on a focused list item', async () => {
    const mockSelectItem = jest.fn();
    const items = [createMockPendingItem(102, UIMRModerationStatus.PENDING_MODERATION)];
    const mockResponse: PaginatedResponse<UIPendingGeneration> = {
      items, current_page: 1, total_pages: 1, total_items: 1, limit_per_page: 10
    };
    mockListPendingGenerations.mockResolvedValue(mockResponse);
    render(<PendingGenerationListPage guildId={mockGuildId} onSelectPendingItem={mockSelectItem} />);

    await waitFor(() => {
      const listItem = screen.getByRole('listitem', { name: /ID: 102/i });
      listItem.focus(); // Ensure the item is focusable by having tabIndex={0}
      fireEvent.keyPress(listItem, { key: 'Enter', code: 'Enter', charCode: 13 });
      expect(mockSelectItem).toHaveBeenCalledWith(102);
    });
  });


  test('fetches next/previous page on pagination button click', async () => {
    const itemsPage1 = [createMockPendingItem(1, UIMRModerationStatus.PENDING_MODERATION)];
    const itemsPage2 = [createMockPendingItem(2, UIMRModerationStatus.PENDING_MODERATION)];
    const mockResponsePage1: PaginatedResponse<UIPendingGeneration> = {
      items: itemsPage1, current_page: 1, total_pages: 2, total_items: 2, limit_per_page: 1
    };
    const mockResponsePage2: PaginatedResponse<UIPendingGeneration> = {
      items: itemsPage2, current_page: 2, total_pages: 2, total_items: 2, limit_per_page: 1
    };

    mockListPendingGenerations.mockResolvedValueOnce(mockResponsePage1);
    render(<PendingGenerationListPage guildId={mockGuildId} onSelectPendingItem={jest.fn()} />);

    await waitFor(() => expect(screen.getByText('ID: 1')).toBeInTheDocument());

    mockListPendingGenerations.mockResolvedValueOnce(mockResponsePage2);
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() => expect(screen.getByText('ID: 2')).toBeInTheDocument());
    expect(mockListPendingGenerations).toHaveBeenCalledTimes(2);
    expect(mockListPendingGenerations).toHaveBeenNthCalledWith(2, mockGuildId, undefined, 2, 10); // guildId, statusFilter, page, ITEMS_PER_PAGE

    mockListPendingGenerations.mockResolvedValueOnce(mockResponsePage1);
    fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
    await waitFor(() => expect(screen.getByText('ID: 1')).toBeInTheDocument());
    expect(mockListPendingGenerations).toHaveBeenCalledTimes(3);
    expect(mockListPendingGenerations).toHaveBeenNthCalledWith(3, mockGuildId, undefined, 1, 10);
  });

  test('refetches data and resets to page 1 when status filter changes', async () => {
    const mockInitialResponse: PaginatedResponse<UIPendingGeneration> = {
      items: [createMockPendingItem(1, UIMRModerationStatus.PENDING_MODERATION)],
      current_page: 1, total_pages: 1, total_items: 1, limit_per_page: 10
    };
    const mockFilteredResponse: PaginatedResponse<UIPendingGeneration> = {
      items: [createMockPendingItem(2, UIMRModerationStatus.APPROVED)],
      current_page: 1, total_pages: 1, total_items: 1, limit_per_page: 10
    };
    mockListPendingGenerations.mockResolvedValueOnce(mockInitialResponse);
    render(<PendingGenerationListPage guildId={mockGuildId} onSelectPendingItem={jest.fn()} />);

    await waitFor(() => expect(screen.getByText('ID: 1')).toBeInTheDocument());

    mockListPendingGenerations.mockResolvedValueOnce(mockFilteredResponse);
    const filterSelect = screen.getByLabelText('Filter by Status:');
    fireEvent.change(filterSelect, { target: { value: UIMRModerationStatus.APPROVED } });

    await waitFor(() => expect(screen.getByText('ID: 2')).toBeInTheDocument());
    expect(mockListPendingGenerations).toHaveBeenCalledTimes(2);
    // First call is (guildId, undefined, 1, 10)
    // Second call is (guildId, 'APPROVED', 1, 10)
    expect(mockListPendingGenerations).toHaveBeenNthCalledWith(2, mockGuildId, UIMRModerationStatus.APPROVED, 1, 10);
  });
});
