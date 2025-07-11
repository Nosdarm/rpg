// src/ui/src/components/InventoryView/AddItemToInventoryForm.tsx
import React, { useState, useEffect } from 'react';
import { itemService } from '../../services/itemService';
import { inventoryService } from '../../services/inventoryService';
import { ItemDefinition } from '../../types/items';
import { PaginatedResponse } from '../../types/entities';

interface AddItemToInventoryFormProps {
  guildId: number;
  ownerEntityType: 'PLAYER' | 'GENERATED_NPC';
  ownerEntityId: number;
  onItemAdded: () => void; // Callback to refresh inventory list or give feedback
  onCancel: () => void;
}

const AddItemToInventoryForm: React.FC<AddItemToInventoryFormProps> = ({
  guildId,
  ownerEntityType,
  ownerEntityId,
  onItemAdded,
  onCancel,
}) => {
  const [availableItems, setAvailableItems] = useState<ItemDefinition[]>([]);
  const [selectedItemId, setSelectedItemId] = useState<string>('');
  const [quantity, setQuantity] = useState<string>('1');
  const [equippedStatus, setEquippedStatus] = useState<string>('');
  const [propertiesJson, setPropertiesJson] = useState<string>('{}');

  const [loadingItems, setLoadingItems] = useState<boolean>(true);
  const [loadingSubmit, setLoadingSubmit] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchAllItems = async () => {
      setLoadingItems(true);
      try {
        // Fetch all items - in a real app, this might need pagination/search
        // For simplicity, fetching a large number of items for the dropdown.
        const response: PaginatedResponse<ItemDefinition> = await itemService.listItems(guildId, 1, 200);
        setAvailableItems(response.items);
        if (response.items.length > 0) {
          // setSelectedItemId(response.items[0].id.toString()); // Pre-select first item
        }
      } catch (err: any) {
        setError(`Failed to load available items: ${err.message || 'Unknown error'}`);
      } finally {
        setLoadingItems(false);
      }
    };
    fetchAllItems();
  }, [guildId]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedItemId) {
      setError('Please select an item.');
      return;
    }
    const itemIdNum = parseInt(selectedItemId, 10);
    const quantityNum = parseInt(quantity, 10);

    if (isNaN(itemIdNum) || itemIdNum <= 0) {
      setError('Invalid item selected.');
      return;
    }
    if (isNaN(quantityNum) || quantityNum <= 0) {
      setError('Quantity must be a positive number.');
      return;
    }

    let parsedProperties: Record<string, any> | undefined;
    if (propertiesJson.trim() !== '' && propertiesJson.trim() !== '{}') {
      try {
        parsedProperties = JSON.parse(propertiesJson);
      } catch (e) {
        setError('Invalid JSON format for Instance Properties.');
        return;
      }
    }

    setLoadingSubmit(true);
    setError(null);
    try {
      await inventoryService.addInventoryItem(
        guildId,
        ownerEntityId,
        ownerEntityType,
        itemIdNum,
        quantityNum,
        equippedStatus.trim() === '' ? undefined : equippedStatus.trim(),
        parsedProperties
      );
      onItemAdded(); // Notify parent
    } catch (err: any) {
      setError(`Failed to add item: ${err.message || 'Unknown error'}`);
    } finally {
      setLoadingSubmit(false);
    }
  };

  const getLocalizedValue = (i18nRecord: Record<string, string> | undefined, lang: string = 'en') => {
    if (!i18nRecord) return 'N/A';
    return i18nRecord[lang] || i18nRecord['en'] || Object.values(i18nRecord)[0] || 'N/A';
  };

  if (loadingItems) return <p>Loading available items...</p>;

  return (
    <form onSubmit={handleSubmit} style={{ border: '1px solid #ccc', padding: '15px', marginTop: '15px', borderRadius: '5px' }}>
      <h4>Add New Item to Inventory</h4>
      {error && <p style={{ color: 'red' }}>{error}</p>}

      <div style={{ marginBottom: '10px' }}>
        <label htmlFor="item-select">Item:</label>
        <select
          id="item-select"
          value={selectedItemId}
          onChange={(e) => setSelectedItemId(e.target.value)}
          required
          style={{width: '100%', padding: '8px', boxSizing: 'border-box'}}
        >
          <option value="">-- Select an Item --</option>
          {availableItems.map(item => (
            <option key={item.id} value={item.id.toString()}>
              {getLocalizedValue(item.name_i18n)} (ID: {item.id}, Type: {getLocalizedValue(item.item_type_i18n)})
            </option>
          ))}
        </select>
      </div>

      <div style={{ marginBottom: '10px' }}>
        <label htmlFor="quantity">Quantity:</label>
        <input
          type="number"
          id="quantity"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          min="1"
          required
          style={{width: '100%', padding: '8px', boxSizing: 'border-box'}}
        />
      </div>

      <div style={{ marginBottom: '10px' }}>
        <label htmlFor="equippedStatus">Equipped Status (Optional):</label>
        <input
          type="text"
          id="equippedStatus"
          value={equippedStatus}
          onChange={(e) => setEquippedStatus(e.target.value)}
          placeholder="e.g., Main Hand, Head"
          style={{width: '100%', padding: '8px', boxSizing: 'border-box'}}
        />
      </div>

      <div style={{ marginBottom: '10px' }}>
        <label htmlFor="propertiesJson">Instance Specific Properties (JSON, Optional):</label>
        <textarea
          id="propertiesJson"
          value={propertiesJson}
          onChange={(e) => setPropertiesJson(e.target.value)}
          rows={3}
          placeholder='e.g., {"charge_level": 5, "engraving": "Hero"}'
          style={{ width: '100%', fontFamily: 'monospace', padding: '8px', boxSizing: 'border-box' }}
        />
      </div>

      <div style={{display: 'flex', justifyContent: 'flex-end', gap: '10px'}}>
        <button type="button" onClick={onCancel} disabled={loadingSubmit}>Cancel</button>
        <button type="submit" disabled={loadingSubmit || loadingItems || !selectedItemId}>
          {loadingSubmit ? 'Adding...' : 'Add Item'}
        </button>
      </div>
    </form>
  );
};

export default AddItemToInventoryForm;
