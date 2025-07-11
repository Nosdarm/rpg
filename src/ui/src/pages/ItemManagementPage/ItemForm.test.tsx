// src/ui/src/pages/ItemManagementPage/ItemForm.test.tsx
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import ItemForm from './ItemForm';
import { itemService } from '../../services/itemService';
import { ItemDefinition, ItemPayload } from '../../types/items';

jest.mock('../../services/itemService');
const mockCreateItem = itemService.createItem as jest.MockedFunction<typeof itemService.createItem>;
const mockUpdateItem = itemService.updateItem as jest.MockedFunction<typeof itemService.updateItem>;

const mockGuildId = 1;
const mockLanguages = ['en', 'ru']; // Should match ItemForm's SUPPORTED_LANGUAGES

const mockItemDefinition: ItemDefinition = {
  id: 1,
  guild_id: mockGuildId,
  static_id: 'test_sword',
  name_i18n: { en: 'Test Sword', ru: 'Тестовый Меч' },
  description_i18n: { en: 'A sword for testing.', ru: 'Меч для тестов.' },
  item_type_i18n: { en: 'Weapon', ru: 'Оружие' },
  item_category_i18n: { en: 'Melee', ru: 'Ближний бой'},
  base_value: 100,
  properties_json: { damage: '1d6', material: 'steel' },
  slot_type: 'main_hand',
  is_stackable: false,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

describe('ItemForm', () => {
  const mockOnSubmitSuccess = jest.fn();
  const mockOnCancel = jest.fn();

  beforeEach(() => {
    mockCreateItem.mockReset();
    mockUpdateItem.mockReset();
    mockOnSubmitSuccess.mockReset();
    mockOnCancel.mockReset();
  });

  describe('Create Mode', () => {
    test('renders form with empty default fields for new item', () => {
      render(<ItemForm guildId={mockGuildId} onFormSubmitSuccess={mockOnSubmitSuccess} onCancel={mockOnCancel} />);
      expect(screen.getByRole('heading', { name: 'Create New Item Definition' })).toBeInTheDocument();
      expect(screen.getByLabelText('Static ID:')).toHaveValue('');
      expect(screen.getByLabelText('EN:', { selector: 'input[id="Name-en"]'})).toHaveValue('');
      expect(screen.getByLabelText('RU:', { selector: 'input[id="Name-ru"]'})).toHaveValue('');
      expect(screen.getByLabelText('Properties (JSON):')).toHaveValue('{}');
      expect(screen.getByLabelText('Is Stackable')).toBeChecked();
    });

    test('submits correct payload for new item creation', async () => {
      mockCreateItem.mockResolvedValue(mockItemDefinition); // Assume create returns the created item
      render(<ItemForm guildId={mockGuildId} onFormSubmitSuccess={mockOnSubmitSuccess} onCancel={mockOnCancel} />);

      fireEvent.change(screen.getByLabelText('Static ID:'), { target: { value: 'new_item_01' } });
      fireEvent.change(screen.getByLabelText('EN:', { selector: 'input[id="Name-en"]'}), { target: { value: 'New Awesome Item' } });
      fireEvent.change(screen.getByLabelText('EN:', { selector: 'input[id="Item Type-en"]'}), { target: { value: 'Generic' } });
      fireEvent.change(screen.getByLabelText('Base Value:'), { target: { value: '50' } });
      fireEvent.change(screen.getByLabelText('Properties (JSON):'), { target: { value: '{"effect":"healing"}' } });
      fireEvent.click(screen.getByLabelText('Is Stackable')); // Uncheck

      fireEvent.click(screen.getByRole('button', { name: 'Create Item' }));

      await waitFor(() => {
        expect(mockCreateItem).toHaveBeenCalledWith(
          mockGuildId,
          expect.objectContaining({
            static_id: 'new_item_01',
            name_i18n: expect.objectContaining({ en: 'New Awesome Item' }),
            item_type_i18n: expect.objectContaining({ en: 'Generic' }),
            base_value: 50,
            properties_json: { effect: 'healing' },
            is_stackable: false,
          })
        );
        expect(mockOnSubmitSuccess).toHaveBeenCalledWith(mockItemDefinition);
      });
    });

    test('shows error if required fields are missing for new item', async () => {
      render(<ItemForm guildId={mockGuildId} onFormSubmitSuccess={mockOnSubmitSuccess} onCancel={mockOnCancel} />);
      fireEvent.click(screen.getByRole('button', { name: 'Create Item' }));
      await waitFor(() => {
        expect(screen.getByText('Error: Static ID is required for new items.')).toBeInTheDocument();
      });
      expect(mockCreateItem).not.toHaveBeenCalled();
    });
  });

  describe('Edit Mode', () => {
    test('renders form pre-filled with editingItem data', () => {
      render(<ItemForm guildId={mockGuildId} editingItem={mockItemDefinition} onFormSubmitSuccess={mockOnSubmitSuccess} onCancel={mockOnCancel} />);
      expect(screen.getByRole('heading', { name: `Edit Item ID: ${mockItemDefinition.id}` })).toBeInTheDocument();
      expect(screen.getByLabelText('Static ID:')).toHaveValue(mockItemDefinition.static_id);
      expect(screen.getByLabelText('EN:', { selector: 'input[id="Name-en"]'})).toHaveValue(mockItemDefinition.name_i18n.en);
      expect(screen.getByLabelText('RU:', { selector: 'input[id="Name-ru"]'})).toHaveValue(mockItemDefinition.name_i18n.ru);
      expect(screen.getByLabelText('Properties (JSON):')).toHaveValue(JSON.stringify(mockItemDefinition.properties_json, null, 2));
      expect(screen.getByLabelText('Is Stackable')).not.toBeChecked();
    });

    test('submits correct partial payload for item update', async () => {
      mockUpdateItem.mockResolvedValue({ ...mockItemDefinition, name_i18n: { en: 'Updated Sword', ru: 'Обновленный Меч'} });
      render(<ItemForm guildId={mockGuildId} editingItem={mockItemDefinition} onFormSubmitSuccess={mockOnSubmitSuccess} onCancel={mockOnCancel} />);

      fireEvent.change(screen.getByLabelText('EN:', { selector: 'input[id="Name-en"]'}), { target: { value: 'Updated Sword' } });
      fireEvent.change(screen.getByLabelText('RU:', { selector: 'input[id="Name-ru"]'}), { target: { value: 'Обновленный Меч' } });
      fireEvent.change(screen.getByLabelText('Base Value:'), { target: { value: '120' } });

      fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

      await waitFor(() => {
        expect(mockUpdateItem).toHaveBeenCalledWith(
          mockGuildId,
          mockItemDefinition.id,
          expect.objectContaining({
            name_i18n: { en: 'Updated Sword', ru: 'Обновленный Меч' },
            base_value: 120,
          })
        );
        // Check that unchanged fields are not in the partial payload sent for update
        const SUT_payload = mockUpdateItem.mock.calls[0][2];
        expect(SUT_payload.static_id).toBeUndefined();
        expect(SUT_payload.is_stackable).toBeUndefined();


        expect(mockOnSubmitSuccess).toHaveBeenCalledWith(
          expect.objectContaining({ name_i18n: { en: 'Updated Sword', ru: 'Обновленный Меч' } })
        );
      });
    });
  });

  test('shows error if JSON for properties is invalid on submit', async () => {
    render(<ItemForm guildId={mockGuildId} onFormSubmitSuccess={mockOnSubmitSuccess} onCancel={mockOnCancel} />);
    fireEvent.change(screen.getByLabelText('Static ID:'), { target: { value: 'test_item' } });
    fireEvent.change(screen.getByLabelText('EN:', { selector: 'input[id="Name-en"]'}), { target: { value: 'Test' } });
     fireEvent.change(screen.getByLabelText('EN:', { selector: 'input[id="Item Type-en"]'}), { target: { value: 'Test Type' } });
    fireEvent.change(screen.getByLabelText('Properties (JSON):'), { target: { value: '{"invalid_json: true"' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create Item' }));

    await waitFor(() => {
      expect(screen.getByText('Error: Invalid JSON format for Properties JSON.')).toBeInTheDocument();
    });
    expect(mockCreateItem).not.toHaveBeenCalled();
  });

  test('calls onCancel when cancel button is clicked', () => {
    render(<ItemForm guildId={mockGuildId} onFormSubmitSuccess={mockOnSubmitSuccess} onCancel={mockOnCancel} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mockOnCancel).toHaveBeenCalled();
  });
});
