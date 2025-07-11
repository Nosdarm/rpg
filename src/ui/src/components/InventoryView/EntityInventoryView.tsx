// src/ui/src/components/InventoryView/EntityInventoryView.tsx
import React from 'react';
import { EnrichedInventoryItem } from '../../types/items';

interface EntityInventoryViewProps {
  inventory?: EnrichedInventoryItem[];
  ownerName?: string; // Optional name of the inventory owner for display
  isLoading?: boolean;
  error?: string | null;
  onSelectItem?: (item: EnrichedInventoryItem) => void;
  onEquipItem?: (item: EnrichedInventoryItem) => void;
  onEditItem?: (item: EnrichedInventoryItem) => void; // For editing InventoryItem instance
  onDeleteItem?: (item: EnrichedInventoryItem) => void; // For deleting InventoryItem instance
}

const getLocalizedValue = (i18nRecord: Record<string, string> | undefined, lang: string = 'en') => {
  if (!i18nRecord) return 'N/A';
  return i18nRecord[lang] || i18nRecord['en'] || Object.values(i18nRecord)[0] || 'N/A';
};

const EntityInventoryView: React.FC<EntityInventoryViewProps> = ({
  inventory,
  ownerName,
  isLoading,
  error,
  onSelectItem,
  onEquipItem,
  onEditItem,
  onDeleteItem
}) => {
  if (isLoading) {
    return <p>Loading inventory...</p>;
  }

  if (error) {
    return <p style={{ color: 'red' }}>Error loading inventory: {error}</p>;
  }

  if (!inventory || inventory.length === 0) {
    return <p>{ownerName ? `${ownerName}'s inventory` : 'Inventory'} is empty.</p>;
  }

  return (
    <div style={{ border: '1px solid #e0e0e0', borderRadius: '8px', padding: '15px' }}>
      {ownerName && <h4 style={{ marginTop: 0, marginBottom: '15px' }}>{ownerName}'s Inventory</h4>}
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {inventory.map((item) => (
          <li
            key={item.inventory_item_id}
            style={{
              borderBottom: '1px solid #f0f0f0',
              padding: '10px 0',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}
          >
            <div>
              <strong onClick={onSelectItem ? () => onSelectItem(item) : undefined} style={{cursor: onSelectItem ? 'pointer' : 'default', color: onSelectItem ? '#007bff' : 'inherit'}}>
                {getLocalizedValue(item.name_i18n)} (x{item.quantity})
              </strong>
              {item.equipped_status && <em style={{ marginLeft: '8px', fontSize: '0.9em', color: '#28a745' }}> ({item.equipped_status})</em>}
              <p style={{ fontSize: '0.85em', color: '#555', margin: '4px 0 0 0' }}>
                <em>{getLocalizedValue(item.item_type_i18n)} - {getLocalizedValue(item.item_category_i18n)}</em>
              </p>
              {item.instance_specific_properties_json && Object.keys(item.instance_specific_properties_json).length > 0 && (
                 <p style={{ fontSize: '0.8em', color: '#777', margin: '4px 0 0 0' }}>
                    Instance Properties: {JSON.stringify(item.instance_specific_properties_json)}
                 </p>
              )}
            </div>
            <div>
              {onEquipItem && item.slot_type && (
                 <button
                    onClick={() => onEquipItem(item)}
                    style={{marginLeft: '5px', padding: '5px 8px', fontSize: '0.9em', cursor: 'pointer'}}
                    title={item.equipped_status ? `Unequip from ${item.equipped_status}` : `Equip to ${item.slot_type}`}
                  >
                  {item.equipped_status ? 'Unequip' : 'Equip'}
                </button>
              )}
              {onEditItem && (
                <button
                  onClick={() => onEditItem(item)}
                  style={{marginLeft: '5px', padding: '5px 8px', fontSize: '0.9em', cursor: 'pointer', backgroundColor: '#ffc107'}}
                >
                  Edit
                </button>
              )}
              {onDeleteItem && (
                <button
                  onClick={() => onDeleteItem(item)}
                  style={{marginLeft: '5px', padding: '5px 8px', fontSize: '0.9em', cursor: 'pointer', backgroundColor: '#dc3545', color: 'white'}}
                >
                  Delete
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default EntityInventoryView;
