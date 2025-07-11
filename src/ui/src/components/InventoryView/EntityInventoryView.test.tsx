// src/ui/src/components/InventoryView/EntityInventoryView.test.tsx
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import EntityInventoryView from './EntityInventoryView';
import { EnrichedInventoryItem } from '../../types/items';

const mockInventoryItem = (id: number, name: string, quantity: number, equipped?: string, slot?: string): EnrichedInventoryItem => ({
  inventory_item_id: id,
  item_id: id * 10,
  name_i18n: { en: name, ru: `Имя ${name}` },
  description_i18n: { en: `Description for ${name}` },
  item_type_i18n: { en: 'Generic Item', ru: 'Обычный Предмет' },
  item_category_i18n: { en: 'Miscellaneous', ru: 'Разное' },
  is_stackable: true,
  quantity,
  equipped_status: equipped,
  slot_type: slot,
  instance_specific_properties_json: id === 1 ? { quality: 'Fine' } : undefined,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
});

describe('EntityInventoryView', () => {
  const mockOnSelectItem = jest.fn();
  const mockOnEquipItem = jest.fn();

  beforeEach(() => {
    mockOnSelectItem.mockReset();
    mockOnEquipItem.mockReset();
  });

  test('renders loading state', () => {
    render(<EntityInventoryView isLoading={true} />);
    expect(screen.getByText('Loading inventory...')).toBeInTheDocument();
  });

  test('renders error state', () => {
    render(<EntityInventoryView error="Failed to load data." />);
    expect(screen.getByText('Error loading inventory: Failed to load data.')).toBeInTheDocument();
  });

  test('renders "Inventory is empty" when no items are provided', () => {
    render(<EntityInventoryView inventory={[]} ownerName="Test Owner" />);
    expect(screen.getByText("Test Owner's inventory is empty.")).toBeInTheDocument();
  });

  test('renders "Inventory is empty" (no owner name) when no items are provided', () => {
    render(<EntityInventoryView inventory={[]} />);
    expect(screen.getByText('Inventory is empty.')).toBeInTheDocument();
  });

  test('renders a list of inventory items with details', () => {
    const inventory = [
      mockInventoryItem(1, 'Health Potion', 5, undefined, 'consumable'),
      mockInventoryItem(2, 'Iron Sword', 1, 'Main Hand', 'weapon'),
    ];
    render(<EntityInventoryView inventory={inventory} ownerName="Player" />);

    expect(screen.getByText('Player\'s Inventory')).toBeInTheDocument();

    // Item 1
    expect(screen.getByText('Health Potion (x5)')).toBeInTheDocument();
    expect(screen.getByText(/Instance Properties: {"quality":"Fine"}/i)).toBeInTheDocument();

    // Item 2
    const swordElement = screen.getByText('Iron Sword (x1)');
    expect(swordElement).toBeInTheDocument();
    // Check for equipped status text near the sword element
    const swordListItem = swordElement.closest('li');
    expect(swordListItem).toHaveTextContent('(Main Hand)');
    expect(swordListItem).toHaveTextContent('Equip'); // Since it has a slot_type, equip button should be there
  });

  test('calls onSelectItem when an item name is clicked', () => {
    const item1 = mockInventoryItem(1, 'Clickable Potion', 3);
    const inventory = [item1];
    render(<EntityInventoryView inventory={inventory} onSelectItem={mockOnSelectItem} />);

    const itemNameElement = screen.getByText('Clickable Potion (x3)');
    fireEvent.click(itemNameElement);
    expect(mockOnSelectItem).toHaveBeenCalledWith(item1);
  });

  test('calls onEquipItem when "Equip" button is clicked', () => {
    const itemToEquip = mockInventoryItem(1, 'Equippable Axe', 1, undefined, 'weapon');
    const inventory = [itemToEquip];
    render(<EntityInventoryView inventory={inventory} onEquipItem={mockOnEquipItem} />);

    const equipButton = screen.getByRole('button', { name: 'Equip' });
    fireEvent.click(equipButton);
    expect(mockOnEquipItem).toHaveBeenCalledWith(itemToEquip);
  });

  test('displays "Unequip" button for equipped items and calls onEquipItem', () => {
    const equippedItem = mockInventoryItem(2, 'Equipped Shield', 1, 'Off Hand', 'shield');
    const inventory = [equippedItem];
    render(<EntityInventoryView inventory={inventory} onEquipItem={mockOnEquipItem} />);

    const unequipButton = screen.getByRole('button', { name: 'Unequip' });
    expect(unequipButton).toBeInTheDocument();
    fireEvent.click(unequipButton);
    expect(mockOnEquipItem).toHaveBeenCalledWith(equippedItem);
  });

  test('does not show equip/unequip button if onEquipItem is not provided', () => {
    const inventory = [mockInventoryItem(1, 'Basic Item', 1, undefined, 'ring')];
    render(<EntityInventoryView inventory={inventory} />);
    expect(screen.queryByRole('button', { name: 'Equip' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Unequip' })).not.toBeInTheDocument();
  });

   test('does not show equip/unequip button if item has no slot_type', () => {
    const inventory = [mockInventoryItem(1, 'Slotless Item', 1, undefined, undefined)]; // No slot_type
    render(<EntityInventoryView inventory={inventory} onEquipItem={mockOnEquipItem} />);
    expect(screen.queryByRole('button', { name: 'Equip' })).not.toBeInTheDocument();
  });
});
