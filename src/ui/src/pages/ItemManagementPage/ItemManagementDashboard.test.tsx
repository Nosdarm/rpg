// src/ui/src/pages/ItemManagementPage/ItemManagementDashboard.test.tsx
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import ItemManagementDashboard from './ItemManagementDashboard';

// Mock child components
jest.mock('./ItemListPage', () => jest.fn(({ onSelectItem, onAddNewItem }) => (
  <div data-testid="item-list-page">
    <span>Item List Page</span>
    <button onClick={() => onAddNewItem()}>Add New Item (from List)</button>
    <button onClick={() => onSelectItem({ id: 1, name_i18n: { en: 'Mock Item' } })}>Edit Item 1 (from List)</button>
  </div>
)));

jest.mock('./ItemForm', () => jest.fn(({ editingItem, onFormSubmitSuccess, onCancel }) => (
  <div data-testid="item-form">
    <span>{editingItem ? `Editing Item: ${editingItem.name_i18n.en}` : 'Creating New Item'}</span>
    <button onClick={() => onFormSubmitSuccess({ id: editingItem?.id || 2, name_i18n: { en: 'Submitted Item' } })}>Submit Form</button>
    <button onClick={onCancel}>Cancel Form</button>
  </div>
)));

jest.mock('./ManageEntityInventory', () => jest.fn(({ ownerEntityType, ownerEntityId }) => (
  <div data-testid="manage-entity-inventory">
    <span>Inventory for {ownerEntityType} ID: {ownerEntityId}</span>
  </div>
)));

// Mock window.alert
const alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});

describe('ItemManagementDashboard', () => {
  beforeEach(() => {
    alertSpy.mockClear();
  });
  afterAll(() => {
    alertSpy.mockRestore();
  });

  test('renders ItemListPage by default', () => {
    render(<ItemManagementDashboard />);
    expect(screen.getByTestId('item-list-page')).toBeInTheDocument();
    expect(screen.getByText('Item List Page')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Item & Inventory Management' })).toBeInTheDocument();
  });

  test('switches to ItemForm when "Add New Item" is clicked', async () => {
    render(<ItemManagementDashboard />);
    fireEvent.click(screen.getByRole('button', { name: 'Add New Item (from List)' }));
    await waitFor(() => {
      expect(screen.getByTestId('item-form')).toBeInTheDocument();
      expect(screen.getByText('Creating New Item')).toBeInTheDocument();
    });
  });

  test('switches to ItemForm for editing when an item is selected', async () => {
    render(<ItemManagementDashboard />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit Item 1 (from List)' }));
    await waitFor(() => {
      expect(screen.getByTestId('item-form')).toBeInTheDocument();
      expect(screen.getByText('Editing Item: Mock Item')).toBeInTheDocument();
    });
  });

  test('returns to ItemListPage after form submission', async () => {
    render(<ItemManagementDashboard />);
    fireEvent.click(screen.getByRole('button', { name: 'Add New Item (from List)' }));
    await waitFor(() => screen.getByTestId('item-form'));

    fireEvent.click(screen.getByRole('button', { name: 'Submit Form' }));
    await waitFor(() => {
      expect(screen.getByTestId('item-list-page')).toBeInTheDocument();
    });
    expect(alertSpy).toHaveBeenCalledWith('Item Definition "Submitted Item" created successfully!');
  });

  test('returns to ItemListPage when form is cancelled', async () => {
    render(<ItemManagementDashboard />);
    fireEvent.click(screen.getByRole('button', { name: 'Add New Item (from List)' }));
    await waitFor(() => screen.getByTestId('item-form'));

    fireEvent.click(screen.getByRole('button', { name: 'Cancel Form' }));
    await waitFor(() => {
      expect(screen.getByTestId('item-list-page')).toBeInTheDocument();
    });
  });

  test('switches to ManageEntityInventory view when "Load Inventory" is clicked with valid ID', async () => {
    render(<ItemManagementDashboard />);

    fireEvent.change(screen.getByPlaceholderText('Enter PLAYER ID'), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Inventory' }));

    await waitFor(() => {
      expect(screen.getByTestId('manage-entity-inventory')).toBeInTheDocument();
      expect(screen.getByText('Inventory for PLAYER ID: 123')).toBeInTheDocument();
    });
  });

  test('shows alert if entity ID is invalid for loading inventory', async () => {
    render(<ItemManagementDashboard />);
    fireEvent.change(screen.getByPlaceholderText('Enter PLAYER ID'), { target: { value: 'abc' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Inventory' }));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Please enter a valid numeric Entity ID.');
    });
    expect(screen.queryByTestId('manage-entity-inventory')).not.toBeInTheDocument();
  });

  test('switches back to ItemListPage from ManageEntityInventory view', async () => {
    render(<ItemManagementDashboard />);
    fireEvent.change(screen.getByPlaceholderText('Enter PLAYER ID'), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Inventory' }));
    await waitFor(() => screen.getByTestId('manage-entity-inventory'));

    fireEvent.click(screen.getByRole('button', { name: '← Back to Item Definitions / Entity Selection' }));
    await waitFor(() => {
        expect(screen.getByTestId('item-list-page')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('manage-entity-inventory')).not.toBeInTheDocument();
  });
});
