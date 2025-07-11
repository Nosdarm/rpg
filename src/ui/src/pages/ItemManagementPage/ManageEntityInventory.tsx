// src/ui/src/pages/ItemManagementPage/ManageEntityInventory.tsx
import React, { useState, useEffect, useCallback } from 'react';
import { EnrichedInventoryItem, InventoryItemData } from '../../types/items';
import { Player, GeneratedNpc } from '../../types/entities';
import { playerService } from '../../services/playerService';
import { npcService } from '../../services/npcService';
import { inventoryService } from '../../services/inventoryService';
import EntityInventoryView from '../../components/InventoryView/EntityInventoryView';
import AddItemToInventoryForm from '../../components/InventoryView/AddItemToInventoryForm';
import EditInventoryItemForm from '../../components/InventoryView/EditInventoryItemForm';

interface ManageEntityInventoryProps {
  guildId: number;
  ownerEntityType: 'PLAYER' | 'GENERATED_NPC';
  ownerEntityId: number;
}

const ManageEntityInventory: React.FC<ManageEntityInventoryProps> = ({
  guildId,
  ownerEntityType,
  ownerEntityId,
}) => {
  const [owner, setOwner] = useState<Player | GeneratedNpc | null>(null);
  const [inventory, setInventory] = useState<EnrichedInventoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddItemForm, setShowAddItemForm] = useState<boolean>(false);
  const [editingInventoryItem, setEditingInventoryItem] = useState<EnrichedInventoryItem | null>(null);

  const fetchOwnerAndInventory = useCallback(async (showLoading: boolean = true) => {
    if(showLoading) setLoading(true);
    setError(null);
    try {
      let ownerData;
      if (ownerEntityType === 'PLAYER') {
        ownerData = await playerService.getPlayerById(guildId, ownerEntityId, true);
      } else {
        ownerData = await npcService.getNpcById(guildId, ownerEntityId, true);
      }
      setOwner(ownerData);
      setInventory(ownerData.inventory || []);
    } catch (err: any) {
      setError(`Failed to load owner or inventory: ${err.message || 'Unknown error'}`);
      console.error(err);
    } finally {
      if(showLoading) setLoading(false);
    }
  }, [guildId, ownerEntityType, ownerEntityId]);

  useEffect(() => {
    fetchOwnerAndInventory();
  }, [fetchOwnerAndInventory]);

  const handleItemAdded = () => {
    setShowAddItemForm(false);
    fetchOwnerAndInventory(false); // Refresh inventory without full page loading spinner
    alert('Item added to inventory successfully!');
  };

  const handleEditItem = (item: EnrichedInventoryItem) => {
    setEditingInventoryItem(item);
    setShowAddItemForm(false); // Close add form if open
  };

  const handleItemUpdated = (updatedItemData: InventoryItemData) => {
    setEditingInventoryItem(null);
    fetchOwnerAndInventory(false);
    alert(`Inventory item ID ${updatedItemData.id} updated successfully!`);
  };

  const handleDeleteItem = async (item: EnrichedInventoryItem) => {
    if (window.confirm(`Are you sure you want to delete "${item.name_i18n.en}" (x${item.quantity}) from the inventory?`)) {
      setLoading(true); // Use general loading for this action for simplicity
      setError(null);
      try {
        await inventoryService.deleteInventoryItem(guildId, item.inventory_item_id);
        fetchOwnerAndInventory(false);
        alert('Item deleted from inventory.');
      } catch (err: any) {
        setError(`Failed to delete item: ${err.message || 'Unknown error'}`);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleEquipItem = async (item: EnrichedInventoryItem) => {
    if (!owner) return;
    const newEquippedStatus = item.equipped_status ? null : item.slot_type; // Toggle logic
    setLoading(true);
    setError(null);
    try {
      await inventoryService.updateInventoryItem(guildId, item.inventory_item_id, {
        equipped_status: newEquippedStatus,
      });
      fetchOwnerAndInventory(false);
      alert(`Item ${newEquippedStatus ? `equipped to ${newEquippedStatus}` : 'unequipped'}.`);
    } catch (err:any) {
      setError(`Failed to ${newEquippedStatus ? 'equip' : 'unequip'} item: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  if (loading && !owner && !editingInventoryItem && !showAddItemForm) return <p>Loading entity and inventory details...</p>;
  if (error && !owner) return <p style={{ color: 'red' }}>Error: {error}</p>;
  if (!owner) return <p>Entity not found.</p>;

  const ownerName = ownerEntityType === 'PLAYER' ? (owner as Player).name : (owner as GeneratedNpc).name_i18n.en;

  return (
    <div>
      <h3>Manage Inventory for {ownerEntityType}: {ownerName} (ID: {ownerEntityId})</h3>
      {error && <p style={{ color: 'red' }}>{error}</p>}

      {!editingInventoryItem && (
        <button
          onClick={() => {setShowAddItemForm(!showAddItemForm); setEditingInventoryItem(null);}}
          style={{ marginBottom: '15px' }}
          disabled={loading}
        >
          {showAddItemForm ? 'Cancel Add Item' : 'Add Item to Inventory'}
        </button>
      )}

      {showAddItemForm && !editingInventoryItem && (
        <AddItemToInventoryForm
          guildId={guildId}
          ownerEntityId={ownerEntityId}
          ownerEntityType={ownerEntityType}
          onItemAdded={handleItemAdded}
          onCancel={() => setShowAddItemForm(false)}
        />
      )}

      {editingInventoryItem && (
        <EditInventoryItemForm
          guildId={guildId}
          item={editingInventoryItem}
          onItemUpdated={handleItemUpdated}
          onCancel={() => setEditingInventoryItem(null)}
        />
      )}

      {!showAddItemForm && !editingInventoryItem && (
        <EntityInventoryView
          inventory={inventory}
          ownerName={ownerName}
          isLoading={loading}
          // error prop is handled globally for the page for simplicity here
          onEditItem={handleEditItem}
          onDeleteItem={handleDeleteItem}
          onEquipItem={handleEquipItem}
        />
      )}
    </div>
  );
};

export default ManageEntityInventory;
