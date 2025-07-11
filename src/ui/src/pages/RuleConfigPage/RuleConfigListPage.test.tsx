import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import RuleConfigListPage from './RuleConfigListPage';
import { ruleConfigService } from 'src/services/ruleConfigService';
import type { PaginatedResponse, RuleConfigEntry } from 'src/types';

jest.mock('src/services/ruleConfigService');
const mockRuleConfigService = ruleConfigService as jest.Mocked<typeof ruleConfigService>;

const mockNotify = jest.fn();
const mockOnEditRule = jest.fn();
const mockOnCreateRule = jest.fn();

const mockRulesPage1: PaginatedResponse<RuleConfigEntry> = {
  items: [
    { key: 'rule1', value_json: { data: 'value1' }, description: 'First rule' },
    { key: 'rule2', value_json: { data: 'value2' }, description: 'Second rule' },
  ],
  current_page: 1,
  total_pages: 2,
  total_items: 4,
  limit_per_page: 2,
};

const mockRulesPage2: PaginatedResponse<RuleConfigEntry> = {
  items: [
    { key: 'rule3', value_json: { data: 'value3' } },
    { key: 'rule4', value_json: { data: 'value4' } },
  ],
  current_page: 2,
  total_pages: 2,
  total_items: 4,
  limit_per_page: 2,
};

const mockEmptyRules: PaginatedResponse<RuleConfigEntry> = {
    items: [],
    current_page: 1,
    total_pages: 0,
    total_items: 0,
    limit_per_page: 2,
  };


describe('RuleConfigListPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRuleConfigService.listRuleConfigEntries.mockResolvedValue(mockRulesPage1);
    mockRuleConfigService.deleteRuleConfigEntry.mockResolvedValue(undefined);
  });

  const renderComponent = () =>
    render(
      <RuleConfigListPage
        guildId="test-guild"
        onEditRule={mockOnEditRule}
        onCreateRule={mockOnCreateRule}
        notify={mockNotify}
      />
    );

  it('renders loading state initially', () => {
    mockRuleConfigService.listRuleConfigEntries.mockImplementationOnce(() => new Promise(() => {})); // Never resolves
    renderComponent();
    expect(screen.getByText('Loading rules...')).toBeInTheDocument();
  });

  it('renders list of rules on successful fetch', async () => {
    renderComponent();
    await waitFor(() => expect(screen.getByText('rule1')).toBeInTheDocument());
    expect(screen.getByText('rule2')).toBeInTheDocument();
    expect(screen.getByText('First rule')).toBeInTheDocument(); // Description
  });

  it('handles error state on fetch failure', async () => {
    mockRuleConfigService.listRuleConfigEntries.mockRejectedValueOnce(new Error('Fetch failed'));
    renderComponent();
    await waitFor(() => expect(screen.getByText('Error fetching rules: Fetch failed')).toBeInTheDocument());
    expect(mockNotify).toHaveBeenCalledWith('Fetch failed', 'error');
  });

  it('calls onCreateRule when "Add New Rule" button is clicked', async () => {
    renderComponent();
    await waitFor(() => expect(screen.getByText('rule1')).toBeInTheDocument()); // Wait for load
    fireEvent.click(screen.getByRole('button', { name: 'Add New Rule' }));
    expect(mockOnCreateRule).toHaveBeenCalled();
  });

  it('calls onEditRule with rule key when "Edit" button is clicked', async () => {
    renderComponent();
    await waitFor(() => expect(screen.getByText('rule1')).toBeInTheDocument());
    const editButtons = screen.getAllByRole('button', { name: 'Edit' });
    fireEvent.click(editButtons[0]); // Click edit for rule1
    expect(mockOnEditRule).toHaveBeenCalledWith('rule1');
  });

  it('calls deleteRuleConfigEntry and refreshes list on delete confirmation', async () => {
    window.confirm = jest.fn(() => true); // Mock confirm dialog
    renderComponent();
    await waitFor(() => expect(screen.getByText('rule1')).toBeInTheDocument());

    const deleteButtons = screen.getAllByRole('button', { name: 'Delete' });
    fireEvent.click(deleteButtons[0]); // Click delete for rule1

    expect(window.confirm).toHaveBeenCalledWith('Are you sure you want to delete the rule "rule1"?');
    await waitFor(() => expect(mockRuleConfigService.deleteRuleConfigEntry).toHaveBeenCalledWith('test-guild', 'rule1'));
    expect(mockNotify).toHaveBeenCalledWith('Rule "rule1" deleted successfully.', 'success');
    expect(mockRuleConfigService.listRuleConfigEntries).toHaveBeenCalledTimes(2); // Initial fetch + refresh
  });

  it('does not call deleteRuleConfigEntry if delete is cancelled', async () => {
    window.confirm = jest.fn(() => false); // Mock confirm dialog
    renderComponent();
    await waitFor(() => expect(screen.getByText('rule1')).toBeInTheDocument());

    const deleteButtons = screen.getAllByRole('button', { name: 'Delete' });
    fireEvent.click(deleteButtons[0]);

    expect(window.confirm).toHaveBeenCalled();
    expect(mockRuleConfigService.deleteRuleConfigEntry).not.toHaveBeenCalled();
  });

  it('handles pagination: clicking Next and Previous', async () => {
    renderComponent();
    await waitFor(() => expect(screen.getByText('rule1')).toBeInTheDocument()); // Page 1 loaded

    // Click Next
    mockRuleConfigService.listRuleConfigEntries.mockResolvedValueOnce(mockRulesPage2);
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(screen.getByText('rule3')).toBeInTheDocument());
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
    expect(mockRuleConfigService.listRuleConfigEntries).toHaveBeenCalledWith('test-guild', undefined, 2, 10);


    // Click Previous
    mockRuleConfigService.listRuleConfigEntries.mockResolvedValueOnce(mockRulesPage1);
    fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
    await waitFor(() => expect(screen.getByText('rule1')).toBeInTheDocument());
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();
    expect(mockRuleConfigService.listRuleConfigEntries).toHaveBeenCalledWith('test-guild', undefined, 1, 10);
  });

  it('handles client-side prefix filtering', async () => {
    const specificMockResponse: PaginatedResponse<RuleConfigEntry> = {
        items: [ { key: 'test.one', value_json: {} }, { key: 'test.two', value_json: {} }, { key: 'other.key', value_json: {} } ],
        current_page: 1, total_pages: 1, total_items: 3, limit_per_page: 10,
    };
    mockRuleConfigService.listRuleConfigEntries.mockResolvedValue(specificMockResponse);
    renderComponent();

    await waitFor(() => expect(screen.getByText('test.one')).toBeInTheDocument());

    const filterInput = screen.getByPlaceholderText('Filter by key prefix...');
    fireEvent.change(filterInput, { target: { value: 'test.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Filter' }));

    // The service is called without prefix, then client-side filtering happens
    await waitFor(() => {
        expect(screen.getByText('test.one')).toBeInTheDocument();
        expect(screen.getByText('test.two')).toBeInTheDocument();
        expect(screen.queryByText('other.key')).not.toBeInTheDocument();
    });
    // Check that listRuleConfigEntries was called (potentially multiple times due to useEffect structure)
    // The last relevant call for filtering would be for page 1 without backend prefix
    expect(mockRuleConfigService.listRuleConfigEntries).toHaveBeenCalledWith('test-guild', undefined, 1, 10);
  });

  it('displays "No rules found" when items array is empty', async () => {
    mockRuleConfigService.listRuleConfigEntries.mockResolvedValue(mockEmptyRules);
    renderComponent();
    await waitFor(() => expect(screen.getByText('No rules found')).toBeInTheDocument());
  });

  it('changes limit per page and refreshes', async () => {
    renderComponent();
    await waitFor(() => expect(screen.getByText('rule1')).toBeInTheDocument());

    const limitSelect = screen.getByRole('combobox');
    fireEvent.change(limitSelect, { target: { value: '20' } });

    await waitFor(() => expect(mockRuleConfigService.listRuleConfigEntries).toHaveBeenCalledWith('test-guild', undefined, 1, 20));
  });

});
