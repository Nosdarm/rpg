import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import RuleConfigForm from './RuleConfigForm';
import { ruleConfigService } from 'src/services/ruleConfigService';
import type { RuleConfigEntry } from 'src/types';

jest.mock('src/services/ruleConfigService');
const mockRuleConfigService = ruleConfigService as jest.Mocked<typeof ruleConfigService>;

const mockNotify = jest.fn();
const mockOnFormSubmitSuccess = jest.fn();
const mockOnCancel = jest.fn();

const guildId = 'test-guild';

describe('RuleConfigForm', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Create Mode', () => {
    const props = {
      guildId,
      onFormSubmitSuccess: mockOnFormSubmitSuccess,
      onCancel: mockOnCancel,
      notify: mockNotify,
    };

    it('renders create form with empty fields', () => {
      render(<RuleConfigForm {...props} />);
      expect(screen.getByText('Create New RuleConfig')).toBeInTheDocument();
      expect(screen.getByLabelText('Key:')).toHaveValue('');
      expect(screen.getByLabelText('Value (JSON string):')).toHaveValue('');
      expect(screen.getByLabelText('Description (optional):')).toHaveValue('');
      expect(screen.getByRole('button', { name: 'Create Rule' })).toBeInTheDocument();
    });

    it('submits valid data for creation', async () => {
      const mockCreatedRule: RuleConfigEntry = { key: 'new.key', value_json: { data: 'new value' }, description: 'New desc' };
      mockRuleConfigService.createRuleConfigEntry.mockResolvedValue(mockCreatedRule);

      render(<RuleConfigForm {...props} />);

      fireEvent.change(screen.getByLabelText('Key:'), { target: { value: 'new.key' } });
      fireEvent.change(screen.getByLabelText('Value (JSON string):'), { target: { value: '{"data":"new value"}' } });
      fireEvent.change(screen.getByLabelText('Description (optional):'), { target: { value: 'New desc' } });
      fireEvent.click(screen.getByRole('button', { name: 'Create Rule' }));

      await waitFor(() => {
        expect(mockRuleConfigService.createRuleConfigEntry).toHaveBeenCalledWith(guildId, {
          key: 'new.key',
          value_json: '{"data":"new value"}',
          description: 'New desc',
        });
        expect(mockNotify).toHaveBeenCalledWith('Rule "new.key" created successfully.', 'success');
        expect(mockOnFormSubmitSuccess).toHaveBeenCalled();
      });
    });

    it('shows error if key is empty', async () => {
        render(<RuleConfigForm {...props} />);
        fireEvent.change(screen.getByLabelText('Value (JSON string):'), { target: { value: '{"data":"value"}' } });
        fireEvent.click(screen.getByRole('button', { name: 'Create Rule' }));

        await waitFor(() => {
          expect(screen.getByText('Error: Key cannot be empty.')).toBeInTheDocument();
          expect(mockRuleConfigService.createRuleConfigEntry).not.toHaveBeenCalled();
        });
      });

    it('shows error for invalid JSON in value field', async () => {
      render(<RuleConfigForm {...props} />);
      fireEvent.change(screen.getByLabelText('Key:'), { target: { value: 'test.key' } });
      fireEvent.change(screen.getByLabelText('Value (JSON string):'), { target: { value: 'invalid json' } });
      fireEvent.click(screen.getByRole('button', { name: 'Create Rule' }));

      await waitFor(() => {
        expect(screen.getByText('Error: Value must be valid JSON.')).toBeInTheDocument();
        expect(mockRuleConfigService.createRuleConfigEntry).not.toHaveBeenCalled();
      });
    });

    it('handles API error on creation', async () => {
        mockRuleConfigService.createRuleConfigEntry.mockRejectedValueOnce(new Error('Create failed'));
        render(<RuleConfigForm {...props} />);
        fireEvent.change(screen.getByLabelText('Key:'), { target: { value: 'fail.key' } });
        fireEvent.change(screen.getByLabelText('Value (JSON string):'), { target: { value: '{"data":"fail"}' } });
        fireEvent.click(screen.getByRole('button', { name: 'Create Rule' }));

        await waitFor(() => {
          expect(mockNotify).toHaveBeenCalledWith('Create failed', 'error');
          expect(screen.getByText('Error: Create failed')).toBeInTheDocument();
        });
      });
  });

  describe('Edit Mode', () => {
    const ruleKeyToEdit = 'edit.key';
    const mockExistingRule: RuleConfigEntry = {
      key: ruleKeyToEdit,
      value_json: { data: 'initial value' },
      description: 'Initial description',
    };
    const props = {
      guildId,
      ruleKeyToEdit,
      onFormSubmitSuccess: mockOnFormSubmitSuccess,
      onCancel: mockOnCancel,
      notify: mockNotify,
    };

    it('renders edit form and loads initial data', async () => {
      mockRuleConfigService.getRuleConfigEntry.mockResolvedValue(mockExistingRule);
      render(<RuleConfigForm {...props} />);

      expect(screen.getByText('Loading rule details...')).toBeInTheDocument(); // Initial loading
      await waitFor(() => {
        expect(screen.getByText(`Edit Rule: ${ruleKeyToEdit}`)).toBeInTheDocument();
        expect(screen.getByLabelText('Key:')).toHaveValue(ruleKeyToEdit);
        expect(screen.getByLabelText('Key:')).toBeDisabled(); // Key is readOnly in edit mode
        expect(screen.getByLabelText('Value (JSON string):')).toHaveValue(JSON.stringify(mockExistingRule.value_json, null, 2));
        expect(screen.getByLabelText('Description (optional):')).toHaveValue(mockExistingRule.description!);
        expect(screen.getByRole('button', { name: 'Save Changes' })).toBeInTheDocument();
      });
    });

    it('submits valid updated data', async () => {
        mockRuleConfigService.getRuleConfigEntry.mockResolvedValue(mockExistingRule);
        const mockUpdatedRule: RuleConfigEntry = { ...mockExistingRule, value_json: {data: "updated value"}, description: "Updated description" };
        mockRuleConfigService.updateRuleConfigEntry.mockResolvedValue(mockUpdatedRule);

        render(<RuleConfigForm {...props} />);
        await waitFor(() => expect(screen.getByLabelText('Key:')).toHaveValue(ruleKeyToEdit)); // Wait for load

        fireEvent.change(screen.getByLabelText('Value (JSON string):'), { target: { value: '{"data":"updated value"}' } });
        fireEvent.change(screen.getByLabelText('Description (optional):'), { target: { value: 'Updated description' } });
        fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

        await waitFor(() => {
            expect(mockRuleConfigService.updateRuleConfigEntry).toHaveBeenCalledWith(guildId, ruleKeyToEdit, {
                value_json: '{"data":"updated value"}',
                description: 'Updated description',
            });
            expect(mockNotify).toHaveBeenCalledWith(`Rule "${ruleKeyToEdit}" updated successfully.`, 'success');
            expect(mockOnFormSubmitSuccess).toHaveBeenCalled();
        });
    });

    it('handles error when fetching initial data for edit', async () => {
        mockRuleConfigService.getRuleConfigEntry.mockRejectedValueOnce(new Error('Fetch details failed'));
        render(<RuleConfigForm {...props} />);
        await waitFor(() => {
            expect(mockNotify).toHaveBeenCalledWith('Fetch details failed', 'error');
            expect(screen.getByText('Error: Fetch details failed')).toBeInTheDocument(); // Error shown in form
        });
    });
  });

  it('calls onCancel when cancel button is clicked', () => {
    render(
      <RuleConfigForm
        guildId={guildId}
        onFormSubmitSuccess={mockOnFormSubmitSuccess}
        onCancel={mockOnCancel}
        notify={mockNotify}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mockOnCancel).toHaveBeenCalled();
  });
});
