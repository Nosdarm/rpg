import { apiClient } from './apiClient';
import { ItemDefinition, ItemPayload, PaginatedResponse } from '../types/items'; // Assuming PaginatedResponse is now in items.ts

const GUILD_ID_PLACEHOLDER = 1; // Replace with actual guild_id management in UI

export const itemService = {
    async listItems(
        guildId: number = GUILD_ID_PLACEHOLDER,
        page: number = 1,
        limit: number = 10
    ): Promise<PaginatedResponse<ItemDefinition>> {
        // In a real scenario, guildId would come from UI state/context
        const response = await apiClient.post<any>('/master_command_endpoint', { // Endpoint is conceptual
            command_name: 'master_item list',
            guild_id: guildId,
            params: { page, limit },
        });
        // Adapt mock/real response to PaginatedResponse<ItemDefinition>
        // This is a simplified mock structure based on typical list command output
        return {
            items: response.items || [], // Assuming the command cog returns an 'items' array
            total: response.total_items || response.items?.length || 0,
            page: response.current_page || page,
            limit: response.limit_per_page || limit,
            // total_pages: response.total_pages, // If backend provides it
        } as PaginatedResponse<ItemDefinition>;
    },

    async getItem(
        guildId: number = GUILD_ID_PLACEHOLDER,
        itemId: number
    ): Promise<ItemDefinition> {
        const response = await apiClient.post<ItemDefinition>('/master_command_endpoint', {
            command_name: 'master_item view',
            guild_id: guildId,
            params: { item_id: itemId },
        });
        return response; // Assuming the command cog returns the ItemDefinition directly
    },

    async createItem(
        guildId: number = GUILD_ID_PLACEHOLDER,
        payload: ItemPayload
    ): Promise<ItemDefinition> {
        // Master command expects JSON fields as strings
        const commandPayload = {
            static_id: payload.static_id,
            name_i18n_json: JSON.stringify(payload.name_i18n),
            item_type_i18n_json: JSON.stringify(payload.item_type_i18n),
            description_i18n_json: payload.description_i18n ? JSON.stringify(payload.description_i18n) : undefined,
            properties_json: payload.properties_json ? JSON.stringify(payload.properties_json) : undefined,
            base_value: payload.base_value,
            slot_type: payload.slot_type,
            is_stackable: payload.is_stackable,
            item_category_i18n_json: payload.item_category_i18n ? JSON.stringify(payload.item_category_i18n) : undefined,
        };

        const response = await apiClient.post<ItemDefinition>('/master_command_endpoint', {
            command_name: 'master_item create',
            guild_id: guildId,
            params: commandPayload,
        });
        return response; // Assuming the command cog returns the created ItemDefinition
    },

    async updateItem(
        guildId: number = GUILD_ID_PLACEHOLDER,
        itemId: number,
        payload: Partial<ItemPayload> // Using Partial for flexibility with data_json
    ): Promise<ItemDefinition> {
        // Using the data_json parameter for /master_item update
        const response = await apiClient.post<ItemDefinition>('/master_command_endpoint', {
            command_name: 'master_item update',
            guild_id: guildId,
            params: {
                item_id: itemId,
                data_json: JSON.stringify(payload),
            },
        });
        return response;
    },

    async deleteItem(
        guildId: number = GUILD_ID_PLACEHOLDER,
        itemId: number
    ): Promise<void> {
        await apiClient.post('/master_command_endpoint', {
            command_name: 'master_item delete',
            guild_id: guildId,
            params: { item_id: itemId },
        });
        // No explicit return, successful call implies success
    },
};
