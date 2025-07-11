// src/ui/src/pages/AiModerationPage/AiModerationDashboardPage.test.tsx
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import AiModerationDashboardPage from './AiModerationDashboardPage';
// We need to mock the actual child components to test interactions
// For simplicity, we'll assume they render some identifiable text or data-testid

const mockGuildId = 1;

// Mock child components
jest.mock('./PendingGenerationListPage', () => {
  return jest.fn(({ onSelectPendingItem }) => (
    <div data-testid="pending-list-page">
      <span>Pending List Page Content</span>
      <button onClick={() => onSelectPendingItem(123)}>Select Item 123</button>
      <button onClick={() => onSelectPendingItem(456)}>Select Item 456</button>
    </div>
  ));
});

jest.mock('./PendingGenerationDetailPage', () => {
  return jest.fn(({ pendingId, onBackToList, onActionSuccess }) => (
    <div data-testid="pending-detail-page">
      <span>Detail Page for Item ID: {pendingId}</span>
      <button onClick={onBackToList}>Back to List (from Detail)</button>
      <button onClick={() => onActionSuccess?.('Detail Action Successful!')}>Perform Detail Action</button>
    </div>
  ));
});

jest.mock('./TriggerAiGenerationForm', () => {
    return jest.fn(({ onGenerationTriggered }) => (
      <div data-testid="trigger-form-page">
        <span>Trigger Form Page Content</span>
        <button onClick={() => onGenerationTriggered?.({ id: 789, status: 'PENDING_MODERATION' })}>
          Mock Trigger
        </button>
      </div>
    ));
  });


describe('AiModerationDashboardPage', () => {
  test('renders dashboard title and navigation buttons', () => {
    render(<AiModerationDashboardPage />);
    expect(screen.getByText('AI Generation & Moderation Dashboard')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Moderation List' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Trigger New Generation' })).toBeInTheDocument();
  });

  test('defaults to "Moderation List" view and shows PendingGenerationListPage', () => {
    render(<AiModerationDashboardPage />);
    expect(screen.getByTestId('pending-list-page')).toBeInTheDocument();
    expect(screen.getByText('Pending List Page Content')).toBeInTheDocument();
    expect(screen.queryByTestId('trigger-form-page')).not.toBeInTheDocument();
    expect(screen.queryByTestId('pending-detail-page')).not.toBeInTheDocument();
  });

  test('switches to "Trigger New Generation" view on button click', () => {
    render(<AiModerationDashboardPage />);
    const triggerTabButton = screen.getByRole('button', { name: 'Trigger New Generation' });
    fireEvent.click(triggerTabButton);

    expect(screen.getByTestId('trigger-form-page')).toBeInTheDocument();
    expect(screen.getByText('Trigger Form Page Content')).toBeInTheDocument();
    expect(screen.queryByTestId('pending-list-page')).not.toBeInTheDocument();
  });

  test('switches to "Detail" view when an item is selected from the list', async () => {
    render(<AiModerationDashboardPage />);
    // Ensure list is visible first
    expect(screen.getByTestId('pending-list-page')).toBeInTheDocument();

    const selectItemButton = screen.getByRole('button', { name: 'Select Item 123' });
    fireEvent.click(selectItemButton);

    await waitFor(() => {
      expect(screen.getByTestId('pending-detail-page')).toBeInTheDocument();
      expect(screen.getByText('Detail Page for Item ID: 123')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('pending-list-page')).not.toBeInTheDocument();
  });

  test('switches back to "Moderation List" view from "Detail" view', async () => {
    render(<AiModerationDashboardPage />);
    // Go to detail view first
    const selectItemButton = screen.getByRole('button', { name: 'Select Item 123' });
    fireEvent.click(selectItemButton);
    await waitFor(() => expect(screen.getByTestId('pending-detail-page')).toBeInTheDocument());

    // Click "Back to List" button within the mocked detail page
    const backButton = screen.getByRole('button', { name: 'Back to List (from Detail)' });
    fireEvent.click(backButton);

    await waitFor(() => {
      expect(screen.getByTestId('pending-list-page')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('pending-detail-page')).not.toBeInTheDocument();
  });

  test('displays feedback message from TriggerAiGenerationForm', async () => {
    render(<AiModerationDashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Trigger New Generation' }));

    await waitFor(() => expect(screen.getByTestId('trigger-form-page')).toBeInTheDocument());

    const mockTriggerButton = screen.getByRole('button', {name: 'Mock Trigger'});
    fireEvent.click(mockTriggerButton);

    await waitFor(() => {
        expect(screen.getByText("Successfully triggered generation ID: 789. It's now PENDING_MODERATION.")).toBeInTheDocument();
    });
  });

  test('displays feedback message from PendingGenerationDetailPage after an action', async () => {
    render(<AiModerationDashboardPage />);
    // Navigate to detail page
    const selectItemButton = screen.getByRole('button', { name: 'Select Item 456' });
    fireEvent.click(selectItemButton);
    await waitFor(() => expect(screen.getByTestId('pending-detail-page')).toBeInTheDocument());

    // Simulate an action in the detail page
    const detailActionButton = screen.getByRole('button', { name: 'Perform Detail Action' });
    fireEvent.click(detailActionButton);

    await waitFor(() => {
        expect(screen.getByText('Detail Action Successful!')).toBeInTheDocument();
    });
  });

  test('clears feedback message when switching views', async () => {
    render(<AiModerationDashboardPage />);
    // Trigger feedback from form
    fireEvent.click(screen.getByRole('button', { name: 'Trigger New Generation' }));
    await waitFor(() => expect(screen.getByTestId('trigger-form-page')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', {name: 'Mock Trigger'}));
    await waitFor(() => expect(screen.getByText("Successfully triggered generation ID: 789. It's now PENDING_MODERATION.")).toBeInTheDocument());

    // Switch to list view
    fireEvent.click(screen.getByRole('button', { name: 'Moderation List' }));
    await waitFor(() => expect(screen.getByTestId('pending-list-page')).toBeInTheDocument());
    expect(screen.queryByText("Successfully triggered generation ID: 789. It's now PENDING_MODERATION.")).not.toBeInTheDocument();
  });
});
