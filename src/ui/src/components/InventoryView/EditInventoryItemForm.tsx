// src/ui/src/components/InventoryView/EditInventoryItemForm.tsx
import React, { useState, useEffect } from 'react';
import { inventoryService } from '../../services/inventoryService';
import { EnrichedInventoryItem, InventoryItemData } from '../../types/items';

interface EditInventoryItemFormProps {
  guildId: number;
  item: EnrichedInventoryItem; // The item being edited
  onItemUpdated: (updatedItem: InventoryItemData) => void; // Callback on successful update
  onCancel: () => void;
}

const EditInventoryItemForm: React.FC<EditInventoryItemFormProps> = ({
  guildId,
  item,
  onItemUpdated,
  onCancel,
}) => {
  const [quantity, setQuantity] = useState<string>(item.quantity.toString());
  const [propertiesJson, setPropertiesJson] = useState<string>(
    JSON.stringify(item.instance_specific_properties_json || {}, null, 2)
  );
  // equipped_status is handled by a separate mechanism in ManageEntityInventory usually

  const [loadingSubmit, setLoadingSubmit] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const getLocalizedValue = (i18nRecord: Record<string, string> | undefined, lang: string = 'en') => {
    if (!i18nRecord) return 'N/A';
    return i18nRecord[lang] || i18nRecord['en'] || Object.values(i18nRecord)[0] || 'N/A';
  };

  useEffect(() => {
    setQuantity(item.quantity.toString());
    setPropertiesJson(JSON.stringify(item.instance_specific_properties_json || {}, null, 2));
  }, [item]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const quantityNum = parseInt(quantity, 10);
    if (isNaN(quantityNum) || quantityNum < 0) { // Allow 0 for potential deletion via quantity update
      setError('Quantity must be a non-negative number.');
      return;
    }

    let parsedProperties: Record<string, any> | undefined;
    if (propertiesJson.trim() !== '' && propertiesJson.trim() !== '{}') {
      try {
        parsedProperties = JSON.parse(propertiesJson);
      } catch (e) {
        setError('Invalid JSON format for Instance Specific Properties.');
        return;
      }
    } else if (propertiesJson.trim() === '{}') {
        parsedProperties = {};
    }


    setLoadingSubmit(true);
    setError(null);
    try {
      // The backend /master_inventory_item update is field-by-field.
      // This form focuses on quantity and properties_json.
      // We might need to make two separate calls if both changed, or enhance backend.
      // For now, assume we can send them if changed.
      // A more robust solution would compare initial values to current values and only send changed fields.

      const updates: { quantity?: number; properties_json?: Record<string, any> | null } = {};
      let hasChanges = false;

      if (quantityNum !== item.quantity) {
        updates.quantity = quantityNum;
        hasChanges = true;
      }

      const currentPropsString = JSON.stringify(item.instance_specific_properties_json || {}, null, 2);
      if (propertiesJson !== currentPropsString) {
        updates.properties_json = parsedProperties; // Send parsed object, or null if it was cleared
        hasChanges = true;
      }

      if (!hasChanges) {
        setError("No changes detected.");
        setLoadingSubmit(false);
        return;
      }

      // If quantity is 0, it implies deletion by the backend command.
      // Otherwise, it's an update.
      if (updates.quantity === 0) {
         // This will delete the item if quantity is set to 0 by backend logic
        const updatedItemData = await inventoryService.updateInventoryItem(guildId, item.inventory_item_id, { quantity: 0 });
        onItemUpdated(updatedItemData);
      } else {
        const updatedItemData = await inventoryService.updateInventoryItem(guildId, item.inventory_item_id, updates);
        onItemUpdated(updatedItemData);
      }

    } catch (err: any) {
      setError(`Failed to update item: ${err.message || 'Unknown error'}`);
    } finally {
      setLoadingSubmit(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ border: '1px solid #007bff', padding: '20px', marginTop: '15px', borderRadius: '5px', backgroundColor: '#f0f8ff' }}>
      <h4>Edit Inventory Item: {getLocalizedValue(item.name_i18n)} (ID: {item.inventory_item_id})</h4>
      {error && <p style={{ color: 'red' }}>{error}</p>}

      <div style={{ marginBottom: '10px' }}>
        <label htmlFor="edit-quantity">Quantity:</label>
        <input
          type="number"
          id="edit-quantity"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          min="0" // Allow 0 for deletion via quantity update
          required
          style={{width: '100%', padding: '8px', boxSizing: 'border-box'}}
          disabled={loadingSubmit}
        />
      </div>

      <div style={{ marginBottom: '10px' }}>
        <label htmlFor="edit-propertiesJson">Instance Specific Properties (JSON):</label>
        <textarea
          id="edit-propertiesJson"
          value={propertiesJson}
          onChange={(e) => setPropertiesJson(e.target.value)}
          rows={4}
          style={{ width: '100%', fontFamily: 'monospace', padding: '8px', boxSizing: 'border-box' }}
          disabled={loadingSubmit}
        />
      </div>

      <div style={{display: 'flex', justifyContent: 'flex-end', gap: '10px'}}>
        <button type="button" onClick={onCancel} disabled={loadingSubmit}>Cancel</button>
        <button type="submit" disabled={loadingSubmit}>
          {loadingSubmit ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </form>
  );
};

export default EditInventoryItemForm;
