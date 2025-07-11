import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import RuleConfigDashboardPage from './RuleConfigDashboardPage';

// Mock child components to simplify testing the dashboard's orchestration logic
jest.mock('./RuleConfigListPage', () => ({
  __esModule: true,
  default: jest.fn(({ onCreateRule, onEditRule }) => (
    <div>
      Mock RuleConfigListPage
      <button onClick={onCreateRule}>Mock Create Rule</button>
      <button onClick={() => onEditRule('mock.key')}>Mock Edit Rule</button>
    </div>
  )),
}));

jest.mock('./RuleConfigForm', () => ({
  __esModule: true,
  default: jest.fn(({ ruleKeyToEdit, onFormSubmitSuccess, onCancel }) => (
    <div>
      Mock RuleConfigForm {ruleKeyToEdit ? `Editing: ${ruleKeyToEdit}` : 'Creating New'}
      <button onClick={onFormSubmitSuccess}>Mock Submit Form</button>
      <button onClick={onCancel}>Mock Cancel Form</button>
    </div>
  )),
}));


describe('RuleConfigDashboardPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Reset window.setTimeout to its original implementation
    jest.useRealTimers();
  });

  it('renders the dashboard title and initially shows the list view', () => {
    render(<RuleConfigDashboardPage />);
    expect(screen.getByText('RuleConfig Management')).toBeInTheDocument();
    expect(screen.getByText('Mock RuleConfigListPage')).toBeInTheDocument();
    expect(screen.queryByText(/Mock RuleConfigForm/)).not.toBeInTheDocument();
  });

  it('switches to form view when "Create Rule" is triggered from list page', () => {
    render(<RuleConfigDashboardPage />);
    expect(screen.getByText('Mock RuleConfigListPage')).toBeInTheDocument(); // Ensure list is there

    fireEvent.click(screen.getByRole('button', { name: 'Mock Create Rule' }));

    expect(screen.queryByText('Mock RuleConfigListPage')).not.toBeInTheDocument();
    expect(screen.getByText('Mock RuleConfigForm Creating New')).toBeInTheDocument();
  });

  it('switches to form view with ruleKey when "Edit Rule" is triggered from list page', () => {
    render(<RuleConfigDashboardPage />);
    expect(screen.getByText('Mock RuleConfigListPage')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Mock Edit Rule' }));

    expect(screen.queryByText('Mock RuleConfigListPage')).not.toBeInTheDocument();
    expect(screen.getByText('Mock RuleConfigForm Editing: mock.key')).toBeInTheDocument();
  });

  it('switches back to list view when form is submitted successfully', () => {
    render(<RuleConfigDashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Mock Create Rule' })); // Go to form view
    expect(screen.getByText('Mock RuleConfigForm Creating New')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Mock Submit Form' }));

    expect(screen.getByText('Mock RuleConfigListPage')).toBeInTheDocument();
    expect(screen.queryByText(/Mock RuleConfigForm/)).not.toBeInTheDocument();
  });

  it('switches back to list view when form is cancelled', () => {
    render(<RuleConfigDashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Mock Create Rule' })); // Go to form view
    expect(screen.getByText('Mock RuleConfigForm Creating New')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Mock Cancel Form' }));

    expect(screen.getByText('Mock RuleConfigListPage')).toBeInTheDocument();
    expect(screen.queryByText(/Mock RuleConfigForm/)).not.toBeInTheDocument();
  });

  it('displays and dismisses notifications', async () => {
    jest.useFakeTimers(); // Use fake timers for setTimeout
    render(<RuleConfigDashboardPage />);

    // Simulate a notification being triggered (e.g., by a child component calling notify)
    // We can't directly call the notify prop of children here easily without more complex mocking.
    // Instead, we'll test the notification component directly if needed or assume child calls it.
    // For this test, let's imagine the dashboard itself triggers one for some reason.

    // To test the notification display logic within the dashboard, we'd need to
    // simulate a child component calling the `showNotification` callback.
    // This is typically done by finding the component and invoking the prop.
    // Since child components are mocked, we can't do that directly.
    // A more integrated test would be needed or we trust the prop passing.

    // Let's assume the notification is shown by some action.
    // We can manually trigger the state change that showNotification would cause.
    const { rerender } = render(<RuleConfigDashboardPage />);

    // Simulate a notification
    // This is a bit of a hack for testing the dashboard's notification state directly
    // In a real scenario, this would be triggered by a child's action.
    act(() => {
      const setNotification = screen.getByText('RuleConfig Management'); // Get any element to access context if needed, not really here
      // Manually trigger a notification for testing purposes
      // This is not ideal but works for this test structure with mocked children
      // A better way would be to find the mock child and invoke its notify prop
    });

    // For simplicity, let's assume notify is called by a child.
    // We'll test the notification rendering and dismissal part.
    // Directly manipulate state for test (not best practice but works for isolated test)
    const instance = screen.getByText('RuleConfig Management').closest('div'); // Get top div

    // Simulate a notification being set
    // This is tricky without exposing setNotification or having a test utility.
    // Let's assume a notification appears

    // If RuleConfigListPage calls notify:
    const MockRuleConfigListPage = require('./RuleConfigListPage').default;
    MockRuleConfigListPage.mockImplementationOnce(({ notify }) => {
      React.useEffect(() => {
        notify('Test success notification', 'success');
      // eslint-disable-next-line react-hooks/exhaustive-deps
      }, []);
      return <div>Mock List Page Triggering Notify</div>;
    });

    rerender(<RuleConfigDashboardPage />);

    await waitFor(() => {
      expect(screen.getByText('Test success notification')).toBeInTheDocument();
    });

    // Test auto-dismissal
    jest.advanceTimersByTime(5000);
    await waitFor(() => {
      expect(screen.queryByText('Test success notification')).not.toBeInTheDocument();
    });

    // Test manual dismissal
     MockRuleConfigListPage.mockImplementationOnce(({ notify }) => {
      React.useEffect(() => {
        notify('Another notification', 'error');
      // eslint-disable-next-line react-hooks/exhaustive-deps
      }, []);
      return <div>Mock List Page Triggering Notify</div>;
    });
    rerender(<RuleConfigDashboardPage />);

    let closeButton;
    await waitFor(() => {
      closeButton = screen.getByRole('button', { name: '×' }); // Close button in Notification component
      expect(screen.getByText('Another notification')).toBeInTheDocument();
    });

    if (closeButton) fireEvent.click(closeButton);

    await waitFor(() => {
      expect(screen.queryByText('Another notification')).not.toBeInTheDocument();
    });

    jest.useRealTimers(); // Restore real timers
  });
});

// Minimal act utility if not available from testing library
// (usually @testing-library/react provides it implicitly with fireEvent/waitFor)
import { act as rtlAct } from '@testing-library/react';
const act = (callback: () => void) => {
  rtlAct(() => {
    callback();
  });
};
