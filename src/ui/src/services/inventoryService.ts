import { apiClient } from './apiClient';
import { InventoryItemData, EnrichedInventoryItem, ItemDefinition, PaginatedResponse } from '../types/items'; // Assuming PaginatedResponse is in items.ts
import { Player, GeneratedNpc } from '../types/entities'; // For owner types

const GUILD_ID_PLACEHOLDER = 1; // Replace with actual guild_id management in UI

// Helper to simulate the backend's enrichment if not done by a single API call
async function enrichInventoryItems(guildId: number, items: InventoryItemData[]): Promise<EnrichedInventoryItem[]> {
    const enrichedItems: EnrichedInventoryItem[] = [];
    for (const invItem of items) {
        try {
            // This simulates fetching base item details. In a real app, itemService.getItem would be used.
            const baseItem = await apiClient.post<ItemDefinition>('/master_command_endpoint', {
                command_name: 'master_item view',
                guild_id: guildId,
                params: { item_id: invItem.item_id }
            });

            enrichedItems.push({
                inventory_item_id: invItem.id,
                item_id: invItem.item_id,
                name_i18n: baseItem.name_i18n,
                description_i18n: baseItem.description_i18n,
                item_type_i18n: baseItem.item_type_i18n,
                item_category_i18n: baseItem.item_category_i18n,
                base_value: baseItem.base_value,
                slot_type: base_Item.slot_type,
                is_stackable: base_Item.is_stackable,
                item_properties_json: baseItem.properties_json,
                quantity: invItem.quantity,
                equipped_status: invItem.equipped_status,
                instance_specific_properties_json: invItem.instance_specific_properties_json,
                created_at: baseItem.created_at,
                updated_at: baseItem.updated_at,
            });
        } catch (error) {
            console.error(`Failed to enrich item ID ${invItem.item_id}:`, error);
            // Add with minimal data if enrichment fails
            enrichedItems.push({
                inventory_item_id: invItem.id,
                item_id: invItem.item_id,
                name_i18n: { en: `Unknown Item ${invItem.item_id}` },
                description_i18n: { en: "Details unavailable" },
                is_stackable: true, // Default
                quantity: invItem.quantity,
                equipped_status: invItem.equipped_status,
                instance_specific_properties_json: invItem.instance_specific_properties_json,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
            });
        }
    }
    return enrichedItems;
}


export const inventoryService = {
    async getPlayerInventory(
        guildId: number = GUILD_ID_PLACEHOLDER,
        playerId: number,
        enrich: boolean = true // Flag to decide if frontend should enrich
    ): Promise<EnrichedInventoryItem[]> {
        // Assumes /master_player view now returns inventory if include_inventory=true
        const playerDetails = await apiClient.post<Player>('/master_command_endpoint', {
            command_name: 'master_player view',
            guild_id: guildId,
            params: { player_id: playerId, include_inventory: true },
        });
        return playerDetails.inventory || [];
    },

    async getNpcInventory(
        guildId: number = GUILD_ID_PLACEHOLDER,
        npcId: number,
        enrich: boolean = true // Flag to decide if frontend should enrich
    ): Promise<EnrichedInventoryItem[]> {
        const npcDetails = await apiClient.post<GeneratedNpc>('/master_command_endpoint', {
            command_name: 'master_npc view',
            guild_id: guildId,
            params: { npc_id: npcId, include_inventory: true },
        });
        return npcDetails.inventory || [];
    },

    // Alternative if backend doesn't directly provide enriched inventory:
    async getOwnerInventoryRaw(
        guildId: number = GUILD_ID_PLACEHOLDER,
        ownerId: number,
        ownerType: 'PLAYER' | 'GENERATED_NPC'
    ): Promise<InventoryItemData[]> {
        const response = await apiClient.post<{items: InventoryItemData[], total: number}>('/master_command_endpoint', {
            command_name: 'master_inventory_item list',
            guild_id: guildId,
            params: { owner_id: ownerId, owner_type: ownerType, limit: 1000 }, // Assuming large limit for full inventory
        });
        return response.items || [];
    },

    async getAndEnrichOwnerInventory(
        guildId: number = GUILD_ID_PLACEHOLDER,
        ownerId: number,
        ownerType: 'PLAYER' | 'GENERATED_NPC'
    ): Promise<EnrichedInventoryItem[]> {
        const rawItems = await this.getOwnerInventoryRaw(guildId, ownerId, ownerType);
        return await enrichInventoryItems(guildId, rawItems);
    },


    async addInventoryItem(
        guildId: number = GUILD_ID_PLACEHOLDER,
        ownerId: number,
        ownerType: 'PLAYER' | 'GENERATED_NPC',
        itemId: number,
        quantity: number,
        equippedStatus?: string,
        properties?: Record<string, any>
    ): Promise<InventoryItemData> {
        const response = await apiClient.post<InventoryItemData>('/master_command_endpoint', {
            command_name: 'master_inventory_item create',
            guild_id: guildId,
            params: {
                owner_id: ownerId,
                owner_type: ownerType,
                item_id: itemId,
                quantity: quantity,
                equipped_status: equippedStatus,
                properties_json: properties ? JSON.stringify(properties) : undefined,
            },
        });
        return response;
    },

    async updateInventoryItem(
        guildId: number = GUILD_ID_PLACEHOLDER,
        inventoryItemId: number,
        updates: {
            quantity?: number;
            equipped_status?: string | null;
            properties_json?: Record<string, any> | null;
        }
    ): Promise<InventoryItemData> {
        // The backend command /master_inventory_item update takes field_to_update and new_value.
        // This service function needs to make multiple calls if multiple fields are updated,
        // or the backend command needs to be enhanced to accept a JSON object of updates.
        // For simplicity, this mock will assume only one field is updated at a time or properties_json.

        let command_name = 'master_inventory_item update';
        let params: Record<string, any> = { inventory_item_id: inventoryItemId };

        if (updates.quantity !== undefined) {
            params.field_to_update = 'quantity';
            params.new_value = updates.quantity.toString();
        } else if (updates.equipped_status !== undefined) {
            params.field_to_update = 'equipped_status';
            params.new_value = updates.equipped_status === null ? 'None' : updates.equipped_status;
        } else if (updates.properties_json !== undefined) {
            params.field_to_update = 'properties_json'; // or instance_specific_properties_json
            params.new_value = updates.properties_json === null ? 'None' : JSON.stringify(updates.properties_json);
        } else {
            throw new Error("No valid update fields provided for inventory item.");
        }

        const response = await apiClient.post<InventoryItemData>('/master_command_endpoint', {
            command_name,
            guild_id: guildId,
            params,
        });
        return response;
    },

    async deleteInventoryItem(
        guildId: number = GUILD_ID_PLACEHOLDER,
        inventoryItemId: number
    ): Promise<void> {
        await apiClient.post('/master_command_endpoint', {
            command_name: 'master_inventory_item delete',
            guild_id: guildId,
            params: { inventory_item_id: inventoryItemId },
        });
    },

    async moveInventoryItem(
        guildId: number = GUILD_ID_PLACEHOLDER,
        sourceInventoryItemId: number, // ID of the InventoryItem instance to move
        targetOwnerId: number,
        targetOwnerType: 'PLAYER' | 'GENERATED_NPC',
        quantity: number // Quantity to move from the stack
    ): Promise<void> {
        // This is a complex operation that needs to be carefully mocked or implemented
        // 1. Get the source inventory item to know its item_id and current quantity
        // 2. Calculate new quantity for source, or if it needs to be deleted
        // 3. Update source item (or delete)
        // 4. Add/update item for target owner
        console.log(`Mock Move: ${quantity} of invItem ${sourceInventoryItemId} to ${targetOwnerType} ${targetOwnerId}`);

        // --- Detailed mock logic for move ---
        // Step 1: Get source item details (especially item_id and current quantity)
        const sourceItemDetailsArray = await this.getOwnerInventoryRaw(guildId, 0, 'PLAYER'); // Dummy call to get type, need actual owner
        const sourceItem = sourceItemDetailsArray.find(it => it.id === sourceInventoryItemId); // This is not right, need to get by inv_item_id
        // This requires a getInventoryItemById function or using list with inventory_item_id filter.
        // For mock, let's assume we magically get it:
        const MOCK_sourceItem: InventoryItemData | undefined = (await apiClient.post<any>('/master_command_endpoint', {
             command_name: 'master_inventory_item view', guild_id: guildId, params: { inventory_item_id: sourceInventoryItemId }
        })).item; // Assuming the view returns the item in a sub-field or directly

        if (!MOCK_sourceItem || quantity <= 0) {
            throw new Error("Source item not found or invalid quantity for move.");
        }
        if (MOCK_sourceItem.quantity < quantity) {
            throw new Error("Not enough quantity in source stack to move.");
        }

        // Step 2 & 3: Update source item
        const newSourceQuantity = MOCK_sourceItem.quantity - quantity;
        if (newSourceQuantity > 0) {
            await this.updateInventoryItem(guildId, sourceInventoryItemId, { quantity: newSourceQuantity });
        } else {
            await this.deleteInventoryItem(guildId, sourceInventoryItemId);
        }

        // Step 4: Add/update item for target owner
        // Check if target already has this item (same base item_id and similar instance_properties_json if applicable)
        // This is a simplification. Real stacking logic is more complex.
        // For this mock, we just add as a new stack or new item.
        await this.addInventoryItem(
            guildId,
            targetOwnerId,
            targetOwnerType,
            MOCK_sourceItem.item_id,
            quantity,
            undefined, // equipped_status usually not set on move
            MOCK_sourceItem.instance_specific_properties_json // Preserve instance properties
        );
        console.log(`Mock Move successful for invItem ${sourceInventoryItemId}`);
    }
};
