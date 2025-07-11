// src/ui/src/pages/ItemManagementPage/ItemListPage.test.tsx
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import ItemListPage from './ItemListPage';
import { itemService } from '../../services/itemService';
import { ItemDefinition } from '../../types/items';
import { PaginatedResponse } from '../../types/entities';

jest.mock('../../services/itemService');
const mockListItems = itemService.listItems as jest.MockedFunction<typeof itemService.listItems>;

const mockGuildId = 1;

const createMockItem = (id: number, name: string, type: string): ItemDefinition => ({
  id,
  guild_id: mockGuildId,
  static_id: `item_static_${id}`,
  name_i18n: { en: name, ru: `Имя ${name}` },
  description_i18n: { en: `Description for ${name}` },
  item_type_i18n: { en: type, ru: `Тип ${type}` },
  base_value: id * 10,
  is_stackable: id % 2 === 0,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
});

describe('ItemListPage', () => {
  const mockOnSelectItem = jest.fn();
  const mockOnAddNewItem = jest.fn();

  beforeEach(() => {
    mockListItems.mockReset();
    mockOnSelectItem.mockReset();
    mockOnAddNewItem.mockReset();
  });

  test('renders loading state initially', () => {
    mockListItems.mockReturnValue(new Promise(() => {}));
    render(<ItemListPage guildId={mockGuildId} onSelectItem={mockOnSelectItem} onAddNewItem={mockOnAddNewItem} />);
    expect(screen.getByText('Loading item definitions...')).toBeInTheDocument();
  });

  test('renders error message if fetching items fails', async () => {
    mockListItems.mockRejectedValue(new Error('Failed to fetch items'));
    render(<ItemListPage guildId={mockGuildId} onSelectItem={mockOnSelectItem} onAddNewItem={mockOnAddNewItem} />);
    await waitFor(() => {
      expect(screen.getByText('Error: Failed to load items: Failed to fetch items')).toBeInTheDocument();
    });
  });

  test('renders "No item definitions found" when no items are returned', async () => {
    const emptyResponse: PaginatedResponse<ItemDefinition> = {
      items: [], total_items: 0, current_page: 1, total_pages: 0, limit_per_page: 10
    };
    mockListItems.mockResolvedValue(emptyResponse);
    render(<ItemListPage guildId={mockGuildId} onSelectItem={mockOnSelectItem} onAddNewItem={mockOnAddNewItem} />);
    await waitFor(() => {
      expect(screen.getByText('No item definitions found.')).toBeInTheDocument();
    });
  });

  test('renders a list of items with details and action buttons', async () => {
    const items = [
      createMockItem(1, 'Sword', 'Weapon'),
      createMockItem(2, 'Health Potion', 'Potion'),
    ];
    const mockResponse: PaginatedResponse<ItemDefinition> = {
      items, total_items: 2, current_page: 1, total_pages: 1, limit_per_page: 10
    };
    mockListItems.mockResolvedValue(mockResponse);
    render(<ItemListPage guildId={mockGuildId} onSelectItem={mockOnSelectItem} onAddNewItem={mockOnAddNewItem} />);

    await waitFor(() => {
      expect(screen.getByText('Sword')).toBeInTheDocument();
      expect(screen.getByText('Weapon')).toBeInTheDocument();
      expect(screen.getByText('10')).toBeInTheDocument(); // Base value
      expect(screen.getByText('No')).toBeInTheDocument(); // is_stackable for item 1

      expect(screen.getByText('Health Potion')).toBeInTheDocument();
      expect(screen.getByText('Potion')).toBeInTheDocument(); // Type
      expect(screen.getByText('20')).toBeInTheDocument(); // Base value
      expect(screen.getByText('Yes')).toBeInTheDocument(); // is_stackable for item 2
    });

    const editButtons = screen.getAllByRole('button', { name: 'Edit' });
    expect(editButtons).toHaveLength(2);
    fireEvent.click(editButtons[0]);
    expect(mockOnSelectItem).toHaveBeenCalledWith(items[0]);
  });

  test('calls onAddNewItem when "Add New Item" button is clicked', async () => {
    mockListItems.mockResolvedValue({ items: [], total_items: 0, current_page: 1, total_pages: 0, limit_per_page: 10 });
    render(<ItemListPage guildId={mockGuildId} onSelectItem={mockOnSelectItem} onAddNewItem={mockOnAddNewItem} />);
    await waitFor(() => screen.getByText('Add New Item')); // Ensure page is loaded

    fireEvent.click(screen.getByRole('button', { name: 'Add New Item' }));
    expect(mockOnAddNewItem).toHaveBeenCalled();
  });

  test('handles pagination correctly', async () => {
    const page1Items = [createMockItem(1, 'Item A', 'Type A')];
    const page2Items = [createMockItem(2, 'Item B', 'Type B')];
    const mockResponsePage1: PaginatedResponse<ItemDefinition> = {
      items: page1Items, total_items: 2, current_page: 1, total_pages: 2, limit_per_page: 1
    };
     const mockResponsePage2: PaginatedResponse<ItemDefinition> = {
      items: page2Items, total_items: 2, current_page: 2, total_pages: 2, limit_per_page: 1
    };

    mockListItems.mockResolvedValueOnce(mockResponsePage1);
    render(<ItemListPage guildId={mockGuildId} onSelectItem={mockOnSelectItem} onAddNewItem={mockOnAddNewItem} />);

    await waitFor(() => expect(screen.getByText('Item A')).toBeInTheDocument());
    expect(screen.queryByText('Item B')).not.toBeInTheDocument();
    expect(screen.getByText('Page 1 of 2 (Total items: 2)')).toBeInTheDocument();

    mockListItems.mockResolvedValueOnce(mockResponsePage2);
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() => expect(screen.getByText('Item B')).toBeInTheDocument());
    expect(screen.queryByText('Item A')).not.toBeInTheDocument();
    expect(screen.getByText('Page 2 of 2 (Total items: 2)')).toBeInTheDocument();
    expect(mockListItems).toHaveBeenCalledTimes(2);
    expect(mockListItems).toHaveBeenNthCalledWith(2, mockGuildId, 2, 15); // page 2, default ITEMS_PER_PAGE
  });
});
