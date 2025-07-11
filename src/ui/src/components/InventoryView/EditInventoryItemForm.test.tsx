// src/ui/src/components/InventoryView/EditInventoryItemForm.test.tsx
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import EditInventoryItemForm from './EditInventoryItemForm';
import { inventoryService } from '../../services/inventoryService';
import { EnrichedInventoryItem, InventoryItemData } from '../../types/items';

jest.mock('../../services/inventoryService');
const mockUpdateInventoryItem = inventoryService.updateInventoryItem as jest.MockedFunction<typeof inventoryService.updateInventoryItem>;

const mockGuildId = 1;
const mockItemToEdit: EnrichedInventoryItem = {
  inventory_item_id: 5,
  item_id: 105,
  guild_id: mockGuildId,
  name_i18n: { en: 'Old Amulet', ru: 'Старый Амулет' },
  description_i18n: { en: 'An ancient amulet.'},
  item_type_i18n: { en: 'Accessory'},
  is_stackable: false,
  quantity: 1,
  instance_specific_properties_json: { "power": 5, "curse": "minor_luck" },
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

describe('EditInventoryItemForm', () => {
  const mockOnItemUpdated = jest.fn();
  const mockOnCancel = jest.fn();

  beforeEach(() => {
    mockUpdateInventoryItem.mockReset();
    mockOnItemUpdated.mockReset();
    mockOnCancel.mockReset();
  });

  test('renders form with pre-filled data from the item', () => {
    render(
      <EditInventoryItemForm
        guildId={mockGuildId}
        item={mockItemToEdit}
        onItemUpdated={mockOnItemUpdated}
        onCancel={mockOnCancel}
      />
    );
    expect(screen.getByRole('heading', { name: /Edit Inventory Item: Old Amulet \(ID: 5\)/i })).toBeInTheDocument();
    expect(screen.getByLabelText('Quantity:')).toHaveValue(mockItemToEdit.quantity);
    expect(screen.getByLabelText('Instance Specific Properties (JSON):'))
      .toHaveValue(JSON.stringify(mockItemToEdit.instance_specific_properties_json, null, 2));
  });

  test('updates quantity and properties and submits successfully', async () => {
    const updatedQuantity = 2; // Note: item is_stackable: false, but form allows editing quantity. Backend should handle logic.
    const updatedProperties = { power: 7, description: "Polished" };
    mockUpdateInventoryItem.mockResolvedValue({
        ...mockItemToEdit,
        quantity: updatedQuantity,
        instance_specific_properties_json: updatedProperties
    } as InventoryItemData);

    render(
      <EditInventoryItemForm
        guildId={mockGuildId}
        item={mockItemToEdit}
        onItemUpdated={mockOnItemUpdated}
        onCancel={mockOnCancel}
      />
    );

    fireEvent.change(screen.getByLabelText('Quantity:'), { target: { value: updatedQuantity.toString() } });
    fireEvent.change(screen.getByLabelText('Instance Specific Properties (JSON):'), {
      target: { value: JSON.stringify(updatedProperties, null, 2) }
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() => {
      expect(mockUpdateInventoryItem).toHaveBeenCalledWith(
        mockGuildId,
        mockItemToEdit.inventory_item_id,
        {
          quantity: updatedQuantity,
          properties_json: updatedProperties,
        }
      );
      expect(mockOnItemUpdated).toHaveBeenCalledWith(
        expect.objectContaining({
            quantity: updatedQuantity,
            instance_specific_properties_json: updatedProperties
        })
      );
    });
  });

  test('submits with quantity set to 0 (for potential deletion by backend)', async () => {
    mockUpdateInventoryItem.mockResolvedValue({ ...mockItemToEdit, quantity: 0 } as InventoryItemData);
     render(
      <EditInventoryItemForm
        guildId={mockGuildId}
        item={mockItemToEdit}
        onItemUpdated={mockOnItemUpdated}
        onCancel={mockOnCancel}
      />
    );
    fireEvent.change(screen.getByLabelText('Quantity:'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() => {
      expect(mockUpdateInventoryItem).toHaveBeenCalledWith(
        mockGuildId,
        mockItemToEdit.inventory_item_id,
        expect.objectContaining({ quantity: 0 })
      );
      expect(mockOnItemUpdated).toHaveBeenCalled();
    });
  });


  test('shows error if quantity is invalid', async () => {
    render(
      <EditInventoryItemForm
        guildId={mockGuildId}
        item={mockItemToEdit}
        onItemUpdated={mockOnItemUpdated}
        onCancel={mockOnCancel}
      />
    );
    fireEvent.change(screen.getByLabelText('Quantity:'), { target: { value: '-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => {
      expect(screen.getByText('Error: Quantity must be a non-negative number.')).toBeInTheDocument();
    });
    expect(mockUpdateInventoryItem).not.toHaveBeenCalled();
  });

  test('shows error if properties JSON is invalid', async () => {
     render(
      <EditInventoryItemForm
        guildId={mockGuildId}
        item={mockItemToEdit}
        onItemUpdated={mockOnItemUpdated}
        onCancel={mockOnCancel}
      />
    );
    fireEvent.change(screen.getByLabelText('Instance Specific Properties (JSON):'), { target: { value: '{"bad:"json"' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => {
      expect(screen.getByText('Error: Invalid JSON format for Instance Specific Properties.')).toBeInTheDocument();
    });
  });

  test('shows "No changes detected" if form submitted without changes', async () => {
    render(
      <EditInventoryItemForm
        guildId={mockGuildId}
        item={mockItemToEdit} // Initial data
        onItemUpdated={mockOnItemUpdated}
        onCancel={mockOnCancel}
      />
    );
    // Submit without any changes
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => {
      expect(screen.getByText('Error: No changes detected.')).toBeInTheDocument();
    });
    expect(mockUpdateInventoryItem).not.toHaveBeenCalled();
  });

  test('calls onCancel when cancel button is clicked', () => {
     render(
      <EditInventoryItemForm
        guildId={mockGuildId}
        item={mockItemToEdit}
        onItemUpdated={mockOnItemUpdated}
        onCancel={mockOnCancel}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mockOnCancel).toHaveBeenCalled();
  });
});
