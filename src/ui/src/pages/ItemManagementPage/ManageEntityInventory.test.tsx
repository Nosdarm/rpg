// src/ui/src/pages/ItemManagementPage/ManageEntityInventory.test.tsx
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import ManageEntityInventory from './ManageEntityInventory';
import { playerService } from '../../services/playerService';
import { npcService } from '../../services/npcService';
import { inventoryService } from '../../services/inventoryService';
import { itemService } from '../../services/itemService';
import { Player, GeneratedNpc } from '../../types/entities';
import { EnrichedInventoryItem, ItemDefinition, InventoryItemData } from '../../types/items';
import { PaginatedResponse } from '../../types/entities';

// Mock services
jest.mock('../../services/playerService');
jest.mock('../../services/npcService');
jest.mock('../../services/inventoryService');
jest.mock('../../services/itemService');

const mockPlayerService = playerService as jest.Mocked<typeof playerService>;
const mockNpcService = npcService as jest.Mocked<typeof npcService>;
const mockInventoryService = inventoryService as jest.Mocked<typeof inventoryService>;
const mockItemService = itemService as jest.Mocked<typeof itemService>;


const mockGuildId = 1;
const mockPlayerId = 10;

const mockSwordItem: EnrichedInventoryItem = {
  inventory_item_id: 1, item_id: 101, guild_id: mockGuildId, name_i18n: { en: 'Steel Sword' }, quantity: 1,
  description_i18n: {en: 'A basic steel sword.'}, item_type_i18n: {en:'Weapon'}, is_stackable: false,
  created_at: new Date().toISOString(), updated_at: new Date().toISOString(), slot_type: 'weapon'
};
const mockPotionItem: EnrichedInventoryItem = {
  inventory_item_id: 2, item_id: 102, guild_id: mockGuildId, name_i18n: { en: 'Health Potion' }, quantity: 5,
  description_i18n: {en: 'Restores health.'}, item_type_i18n: {en:'Consumable'}, is_stackable: true,
  created_at: new Date().toISOString(), updated_at: new Date().toISOString(), slot_type: 'consumable'
};

const mockPlayerData: Player = {
  id: mockPlayerId, guild_id: mockGuildId, discord_id: 'player_discord_123', name: 'Hero Player', level: 5, xp: 100, gold: 50, current_hp: 100, max_hp:100, current_status:'IDLE', unspent_xp: 0, selected_language: 'en', current_location_id:1, current_party_id: null, attributes_json:{},
  inventory: [mockSwordItem, mockPotionItem],
  created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
};

const mockAvailableItemsForForm: ItemDefinition[] = [
  { id: 101, static_id: 'sword', name_i18n: { en: 'Steel Sword' }, item_type_i18n: {en:'Weapon'}, description_i18n:{en:''}, is_stackable: false, created_at: '', updated_at: '', guild_id: mockGuildId},
  { id: 102, static_id: 'potion', name_i18n: { en: 'Health Potion' }, item_type_i18n: {en:'Potion'}, description_i18n:{en:''}, is_stackable: true, created_at: '', updated_at: '', guild_id: mockGuildId },
  { id: 103, static_id: 'helmet', name_i18n: { en: 'Iron Helmet' }, item_type_i18n: {en:'Armor'}, description_i18n:{en:''}, is_stackable: false, created_at: '', updated_at: '', guild_id: mockGuildId },
];
const mockPaginatedItemsResponse: PaginatedResponse<ItemDefinition> = {
  items: mockAvailableItemsForForm, current_page: 1, total_pages: 1, total_items: 3, limit_per_page: 200,
};

// Mock EditInventoryItemForm to verify it's called
jest.mock('../../components/InventoryView/EditInventoryItemForm', () => {
  return jest.fn(({ item, onItemUpdated, onCancel }) => (
    <div data-testid="edit-inventory-item-form">
      <span>Editing: {item.name_i18n.en}</span>
      <button onClick={() => onItemUpdated({ ...item, quantity: item.quantity + 1 } as InventoryItemData)}>Mock Save</button>
      <button onClick={onCancel}>Mock Cancel Edit</button>
    </div>
  ));
});


describe('ManageEntityInventory', () => {
  let alertSpy: jest.SpyInstance;

  beforeEach(() => {
    mockPlayerService.getPlayerById.mockReset();
    mockNpcService.getNpcById.mockReset();
    mockInventoryService.addInventoryItem.mockReset();
    mockInventoryService.updateInventoryItem.mockReset();
    mockInventoryService.deleteInventoryItem.mockReset();
    mockItemService.listItems.mockResolvedValue(mockPaginatedItemsResponse);
    alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});
    jest.spyOn(window, 'confirm').mockReturnValue(true); // Auto-confirm deletions
  });

  afterEach(() => {
    alertSpy.mockRestore();
    jest.restoreAllMocks();
  });

  test('loads and displays player inventory', async () => {
    mockPlayerService.getPlayerById.mockResolvedValue(mockPlayerData);
    render(<ManageEntityInventory guildId={mockGuildId} ownerEntityType="PLAYER" ownerEntityId={mockPlayerId} />);
    await waitFor(() => expect(screen.getByText('Steel Sword (x1)')).toBeInTheDocument());
  });

  test('toggles AddItemToInventoryForm and EditInventoryItemForm correctly', async () => {
    mockPlayerService.getPlayerById.mockResolvedValue(mockPlayerData);
    render(<ManageEntityInventory guildId={mockGuildId} ownerEntityType="PLAYER" ownerEntityId={mockPlayerId} />);
    await waitFor(() => screen.getByText('Add Item to Inventory'));

    // Open Add form
    fireEvent.click(screen.getByText('Add Item to Inventory'));
    await waitFor(() => expect(screen.getByRole('heading', {name: 'Add New Item to Inventory'})).toBeInTheDocument());
    expect(screen.queryByTestId('edit-inventory-item-form')).not.toBeInTheDocument();

    // Close Add form
    fireEvent.click(screen.getByText('Cancel Add Item'));
    await waitFor(() => expect(screen.queryByRole('heading', {name: 'Add New Item to Inventory'})).not.toBeInTheDocument());

    // Click Edit on an item (assuming EntityInventoryView renders Edit buttons)
    const editButtons = await screen.findAllByRole('button', { name: 'Edit' });
    fireEvent.click(editButtons[0]); // Click edit for the first item (Steel Sword)

    await waitFor(() => {
      expect(screen.getByTestId('edit-inventory-item-form')).toBeInTheDocument();
      expect(screen.getByText('Editing: Steel Sword')).toBeInTheDocument();
    });
    expect(screen.queryByText('Add Item to Inventory')).not.toBeInTheDocument(); // Button should hide

     // Close Edit form via its cancel
    fireEvent.click(screen.getByRole('button', {name: 'Mock Cancel Edit'}));
    await waitFor(() => expect(screen.queryByTestId('edit-inventory-item-form')).not.toBeInTheDocument());
    expect(screen.getByText('Add Item to Inventory')).toBeInTheDocument(); // Button should reappear
  });

  test('handles item deletion and refreshes inventory', async () => {
    mockPlayerService.getPlayerById.mockResolvedValue(mockPlayerData);
    mockInventoryService.deleteInventoryItem.mockResolvedValue(undefined);

    const refreshedPlayerData = { ...mockPlayerData, inventory: [mockPotionItem] }; // Sword removed
    mockPlayerService.getPlayerById.mockResolvedValueOnce(mockPlayerData).mockResolvedValueOnce(refreshedPlayerData);

    render(<ManageEntityInventory guildId={mockGuildId} ownerEntityType="PLAYER" ownerEntityId={mockPlayerId} />);
    await waitFor(() => screen.getByText('Steel Sword (x1)'));

    const deleteButtons = await screen.findAllByRole('button', { name: 'Delete' });
    fireEvent.click(deleteButtons[0]); // Delete Steel Sword

    await waitFor(() => {
      expect(mockInventoryService.deleteInventoryItem).toHaveBeenCalledWith(mockGuildId, mockSwordItem.inventory_item_id);
      expect(mockPlayerService.getPlayerById).toHaveBeenCalledTimes(2); // Initial + refresh
      expect(screen.queryByText('Steel Sword (x1)')).not.toBeInTheDocument();
      expect(screen.getByText('Health Potion (x5)')).toBeInTheDocument();
    });
    expect(window.alert).toHaveBeenCalledWith('Item deleted from inventory.');
  });

  test('handles item update from EditInventoryItemForm and refreshes', async () => {
    mockPlayerService.getPlayerById.mockResolvedValue(mockPlayerData);
    // Mock what updateInventoryItem would return if called by EditInventoryItemForm
    // For this test, we just need to ensure the refresh logic in ManageEntityInventory is called.
    // The actual call to inventoryService.updateInventoryItem is mocked within EditInventoryItemForm's own tests.

    const updatedSword = { ...mockSwordItem, quantity: 2 };
    const refreshedPlayerDataWithUpdate = { ...mockPlayerData, inventory: [updatedSword, mockPotionItem] };
    mockPlayerService.getPlayerById.mockResolvedValueOnce(mockPlayerData).mockResolvedValueOnce(refreshedPlayerDataWithUpdate);


    render(<ManageEntityInventory guildId={mockGuildId} ownerEntityType="PLAYER" ownerEntityId={mockPlayerId} />);
    await waitFor(() => screen.getByText('Steel Sword (x1)'));

    const editButtons = await screen.findAllByRole('button', { name: 'Edit' });
    fireEvent.click(editButtons[0]); // Open edit form for Steel Sword

    await waitFor(() => screen.getByTestId('edit-inventory-item-form'));

    // Simulate the EditInventoryItemForm calling its onItemUpdated prop
    const mockSaveButtonInEditForm = screen.getByRole('button', { name: 'Mock Save' });
    fireEvent.click(mockSaveButtonInEditForm);


    await waitFor(() => {
      expect(mockPlayerService.getPlayerById).toHaveBeenCalledTimes(2); // Initial + refresh after update
      expect(screen.getByText('Steel Sword (x2)')).toBeInTheDocument(); // Check if quantity updated
    });
    expect(window.alert).toHaveBeenCalledWith(`Inventory item ID ${mockSwordItem.inventory_item_id} updated successfully!`);
  });

});
