// src/ui/src/pages/ItemManagementPage/ItemManagementDashboard.tsx
import React, { useState } from 'react';
import ItemListPage from './ItemListPage';
import ItemForm from './ItemForm';
import ManageEntityInventory from './ManageEntityInventory';
import { ItemDefinition } from '../../types/items';

const ItemManagementDashboard: React.FC = () => {
  // Предполагаем, что guildId будет получен из контекста или глобального состояния UI
  const guildId = 1; // Моковое значение

  const [view, setView] = useState<'itemList' | 'itemForm' | 'entityInventory'>('itemList');
  const [editingItem, setEditingItem] = useState<ItemDefinition | null>(null);

  const [manageInventoryFor, setManageInventoryFor] = useState<{
    entityType: 'PLAYER' | 'GENERATED_NPC';
    entityId: number;
  } | null>(null);

  // State for manual entity ID input for inventory management
  const [selectedEntityType, setSelectedEntityType] = useState<'PLAYER' | 'GENERATED_NPC'>('PLAYER');
  const [entityIdInput, setEntityIdInput] = useState<string>('');


  const handleAddNewItem = () => {
    setEditingItem(null);
    setView('itemForm');
  };

  const handleEditItemDefinition = (item: ItemDefinition) => {
    setEditingItem(item);
    setView('itemForm');
  };

  const handleFormSuccess = (item: ItemDefinition) => {
    setView('itemList'); // Go back to list after successful save/create
    // Optionally, could add a feedback message here
    alert(`Item Definition "${item.name_i18n.en}" ${editingItem ? 'updated' : 'created'} successfully!`);
    setEditingItem(null);
  };

  const handleFormCancel = () => {
    setView('itemList');
    setEditingItem(null);
  };

  const handleManageEntityInventory = () => {
    const id = parseInt(entityIdInput, 10);
    if (isNaN(id) || id <= 0) {
      alert("Please enter a valid numeric Entity ID.");
      return;
    }
    setManageInventoryFor({ entityType: selectedEntityType, entityId: id });
    setView('entityInventory');
  };

  const handleBackToDashboardFromInventory = () => {
      setManageInventoryFor(null);
      setView('itemList'); // Or a more general dashboard view if it evolves
  }

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      <header style={{ marginBottom: '20px', borderBottom: '1px solid #eee', paddingBottom: '10px' }}>
        <h1 style={{ margin: 0 }}>Item & Inventory Management</h1>
      </header>

      {view !== 'entityInventory' && view !== 'itemForm' && (
        <div style={{ marginBottom: '20px', padding: '10px', border: '1px solid #ddd', borderRadius: '5px' }}>
          <h4>Manage Specific Entity Inventory</h4>
          <select
            value={selectedEntityType}
            onChange={(e) => setSelectedEntityType(e.target.value as 'PLAYER' | 'GENERATED_NPC')}
            style={{marginRight: '10px', padding: '5px'}}
          >
            <option value="PLAYER">Player</option>
            <option value="GENERATED_NPC">NPC</option>
          </select>
          <input
            type="number"
            value={entityIdInput}
            onChange={(e) => setEntityIdInput(e.target.value)}
            placeholder={`Enter ${selectedEntityType} ID`}
            style={{marginRight: '10px', padding: '5px'}}
          />
          <button onClick={handleManageEntityInventory} style={{padding: '5px 10px'}}>Load Inventory</button>
        </div>
      )}


      {view === 'itemList' && (
        <ItemListPage
          guildId={guildId}
          onSelectItem={handleEditItemDefinition}
          onAddNewItem={handleAddNewItem}
        />
      )}
      {view === 'itemForm' && (
        <ItemForm
          guildId={guildId}
          editingItem={editingItem}
          onFormSubmitSuccess={handleFormSuccess}
          onCancel={handleFormCancel}
        />
      )}
      {view === 'entityInventory' && manageInventoryFor && (
        <>
            <button onClick={handleBackToDashboardFromInventory} style={{marginBottom: '10px'}}>
                &larr; Back to Item Definitions / Entity Selection
            </button>
            <ManageEntityInventory
                guildId={guildId}
                ownerEntityType={manageInventoryFor.entityType}
                ownerEntityId={manageInventoryFor.entityId}
            />
        </>
      )}
    </div>
  );
};

export default ItemManagementDashboard;
