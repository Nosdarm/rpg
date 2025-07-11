// src/ui/src/components/InventoryView/AddItemToInventoryForm.test.tsx
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import AddItemToInventoryForm from './AddItemToInventoryForm';
import { itemService } from '../../services/itemService';
import { inventoryService } from '../../services/inventoryService';
import { ItemDefinition } from '../../types/items';
import { PaginatedResponse } from '../../types/entities';

jest.mock('../../services/itemService');
const mockListItems = itemService.listItems as jest.MockedFunction<typeof itemService.listItems>;

jest.mock('../../services/inventoryService');
const mockAddInventoryItem = inventoryService.addInventoryItem as jest.MockedFunction<typeof inventoryService.addInventoryItem>;

const mockGuildId = 1;
const mockOwnerEntityId = 10;
const mockOwnerEntityType = 'PLAYER';

const mockAvailableItems: ItemDefinition[] = [
  { id: 1, static_id: 'sword', name_i18n: { en: 'Sword' }, item_type_i18n: {en: 'Weapon'}, description_i18n:{en:''}, is_stackable: false, created_at: '', updated_at: '', guild_id: mockGuildId },
  { id: 2, static_id: 'potion', name_i18n: { en: 'Potion' }, item_type_i18n: {en: 'Consumable'}, description_i18n:{en:''}, is_stackable: true, created_at: '', updated_at: '', guild_id: mockGuildId },
];

const mockPaginatedItemsResponse: PaginatedResponse<ItemDefinition> = {
  items: mockAvailableItems,
  current_page: 1,
  total_pages: 1,
  total_items: mockAvailableItems.length,
  limit_per_page: 200,
};

describe('AddItemToInventoryForm', () => {
  const mockOnItemAdded = jest.fn();
  const mockOnCancel = jest.fn();

  beforeEach(() => {
    mockListItems.mockReset();
    mockAddInventoryItem.mockReset();
    mockOnItemAdded.mockReset();
    mockOnCancel.mockReset();
    mockListItems.mockResolvedValue(mockPaginatedItemsResponse); // Default mock for item loading
  });

  test('renders loading state for items then the form', async () => {
    mockListItems.mockReturnValue(new Promise(resolve => setTimeout(() => resolve(mockPaginatedItemsResponse), 50)));
    render(
      <AddItemToInventoryForm
        guildId={mockGuildId}
        ownerEntityId={mockOwnerEntityId}
        ownerEntityType={mockOwnerEntityType}
        onItemAdded={mockOnItemAdded}
        onCancel={mockOnCancel}
      />
    );
    expect(screen.getByText('Loading available items...')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText('Item:')).toBeInTheDocument();
    });
  });

  test('populates item select dropdown after items are loaded', async () => {
    render(
      <AddItemToInventoryForm
        guildId={mockGuildId}
        ownerEntityId={mockOwnerEntityId}
        ownerEntityType={mockOwnerEntityType}
        onItemAdded={mockOnItemAdded}
        onCancel={mockOnCancel}
      />
    );
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /Sword \(ID: 1, Type: Weapon\)/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /Potion \(ID: 2, Type: Consumable\)/i })).toBeInTheDocument();
    });
  });

  test('submits form with correct data and calls onItemAdded on success', async () => {
    mockAddInventoryItem.mockResolvedValue({} as any); // Mock successful add
    render(
      <AddItemToInventoryForm
        guildId={mockGuildId}
        ownerEntityId={mockOwnerEntityId}
        ownerEntityType={mockOwnerEntityType}
        onItemAdded={mockOnItemAdded}
        onCancel={mockOnCancel}
      />
    );
    await waitFor(() => screen.getByLabelText('Item:')); // Wait for items to load

    fireEvent.change(screen.getByLabelText('Item:'), { target: { value: '1' } }); // Select Sword
    fireEvent.change(screen.getByLabelText('Quantity:'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('Equipped Status (Optional):'), { target: { value: 'Backpack' } });
    fireEvent.change(screen.getByLabelText('Instance Specific Properties (JSON, Optional):'), { target: { value: '{"condition":"New"}' } });

    fireEvent.click(screen.getByRole('button', { name: 'Add Item' }));

    await waitFor(() => {
      expect(mockAddInventoryItem).toHaveBeenCalledWith(
        mockGuildId,
        mockOwnerEntityId,
        mockOwnerEntityType,
        1, // Item ID for Sword
        3, // Quantity
        'Backpack',
        { condition: 'New' }
      );
      expect(mockOnItemAdded).toHaveBeenCalled();
    });
  });

  test('shows error if item is not selected', async () => {
    render(
      <AddItemToInventoryForm
        guildId={mockGuildId}
        ownerEntityId={mockOwnerEntityId}
        ownerEntityType={mockOwnerEntityType}
        onItemAdded={mockOnItemAdded}
        onCancel={mockOnCancel}
      />
    );
    await waitFor(() => screen.getByLabelText('Item:'));
    fireEvent.click(screen.getByRole('button', { name: 'Add Item' }));
    await waitFor(() => {
        expect(screen.getByText('Error: Please select an item.')).toBeInTheDocument();
    });
    expect(mockAddInventoryItem).not.toHaveBeenCalled();
  });

  test('shows error if quantity is invalid', async () => {
    render(
      <AddItemToInventoryForm
        guildId={mockGuildId}
        ownerEntityId={mockOwnerEntityId}
        ownerEntityType={mockOwnerEntityType}
        onItemAdded={mockOnItemAdded}
        onCancel={mockOnCancel}
      />
    );
    await waitFor(() => screen.getByLabelText('Item:'));
    fireEvent.change(screen.getByLabelText('Item:'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Quantity:'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add Item' }));
    await waitFor(() => {
        expect(screen.getByText('Error: Quantity must be a positive number.')).toBeInTheDocument();
    });
  });

  test('shows error if properties JSON is invalid', async () => {
    render(
      <AddItemToInventoryForm
        guildId={mockGuildId}
        ownerEntityId={mockOwnerEntityId}
        ownerEntityType={mockOwnerEntityType}
        onItemAdded={mockOnItemAdded}
        onCancel={mockOnCancel}
      />
    );
    await waitFor(() => screen.getByLabelText('Item:'));
    fireEvent.change(screen.getByLabelText('Item:'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Instance Specific Properties (JSON, Optional):'), { target: { value: '{"bad:"json"' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add Item' }));
    await waitFor(() => {
        expect(screen.getByText('Error: Invalid JSON format for Instance Properties.')).toBeInTheDocument();
    });
  });

  test('calls onCancel when cancel button is clicked', async () => {
    render(
      <AddItemToInventoryForm
        guildId={mockGuildId}
        ownerEntityId={mockOwnerEntityId}
        ownerEntityType={mockOwnerEntityType}
        onItemAdded={mockOnItemAdded}
        onCancel={mockOnCancel}
      />
    );
    await waitFor(() => screen.getByLabelText('Item:'));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mockOnCancel).toHaveBeenCalled();
  });
});
