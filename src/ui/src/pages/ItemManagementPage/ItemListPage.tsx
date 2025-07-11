// src/ui/src/pages/ItemManagementPage/ItemListPage.tsx
import React, { useEffect, useState, useCallback } from 'react';
import { itemService } from '../../services/itemService';
import { ItemDefinition }
from '../../types/items'; // Assuming PaginatedResponse is from entities
import { PaginatedResponse } from '../../types/entities';

interface ItemListPageProps {
  guildId: number;
  onSelectItem: (item: ItemDefinition) => void; // For editing
  onAddNewItem: () => void; // To open creation form
}

const ITEMS_PER_PAGE = 15;

const ItemListPage: React.FC<ItemListPageProps> = ({ guildId, onSelectItem, onAddNewItem }) => {
  const [response, setResponse] = useState<PaginatedResponse<ItemDefinition> | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  // TODO: Add filter states if needed, e.g., nameFilter, typeFilter

  const fetchItems = useCallback(async (page: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await itemService.listItems(guildId, page, ITEMS_PER_PAGE);
      setResponse(data);
    } catch (err: any) {
      setError(`Failed to load items: ${err.message || 'Unknown error'}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    if (guildId) {
      fetchItems(currentPage);
    }
  }, [guildId, currentPage, fetchItems]);

  const handlePreviousPage = () => {
    if (response && response.current_page > 1) {
      setCurrentPage(response.current_page - 1);
    }
  };

  const handleNextPage = () => {
    if (response && response.current_page < response.total_pages) {
      setCurrentPage(response.current_page + 1);
    }
  };

  const getLocalizedValue = (i18nRecord: Record<string, string> | undefined, lang: string = 'en') => {
    if (!i18nRecord) return 'N/A';
    return i18nRecord[lang] || i18nRecord['en'] || Object.values(i18nRecord)[0] || 'N/A';
  };

  if (loading) return <p>Loading item definitions...</p>;
  if (error) return <p style={{ color: 'red' }}>Error: {error}</p>;

  return (
    <div style={{ padding: '10px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
        <h2>Item Definitions</h2>
        <button onClick={onAddNewItem} style={{padding: '8px 12px'}}>Add New Item</button>
      </div>
      {/* TODO: Add filtering controls here */}

      {!response || response.items.length === 0 ? (
        <p>No item definitions found.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #ddd', textAlign: 'left' }}>
              <th style={{padding: '8px'}}>ID</th>
              <th style={{padding: '8px'}}>Static ID</th>
              <th style={{padding: '8px'}}>Name (en)</th>
              <th style={{padding: '8px'}}>Type (en)</th>
              <th style={{padding: '8px'}}>Value</th>
              <th style={{padding: '8px'}}>Stackable</th>
              <th style={{padding: '8px'}}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {response.items.map(item => (
              <tr key={item.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{padding: '8px'}}>{item.id}</td>
                <td style={{padding: '8px'}}>{item.static_id || 'N/A'}</td>
                <td style={{padding: '8px'}}>{getLocalizedValue(item.name_i18n)}</td>
                <td style={{padding: '8px'}}>{getLocalizedValue(item.item_type_i18n)}</td>
                <td style={{padding: '8px'}}>{item.base_value ?? 'N/A'}</td>
                <td style={{padding: '8px'}}>{item.is_stackable ? 'Yes' : 'No'}</td>
                <td style={{padding: '8px'}}>
                  <button onClick={() => onSelectItem(item)} style={{padding: '5px 10px'}}>Edit</button>
                  {/* TODO: Add delete button with confirmation */}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {response && response.total_pages > 1 && (
        <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <button onClick={handlePreviousPage} disabled={currentPage === 1 || loading} style={{marginRight: '10px'}}>
            Previous
          </button>
          <span>
            Page {response.current_page} of {response.total_pages} (Total items: {response.total_items})
          </span>
          <button onClick={handleNextPage} disabled={currentPage === response.total_pages || loading} style={{marginLeft: '10px'}}>
            Next
          </button>
        </div>
      )}
    </div>
  );
};

export default ItemListPage;
