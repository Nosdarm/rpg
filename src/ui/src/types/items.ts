export interface ItemDefinition {
    id: number;
    guild_id: number;
    static_id?: string;
    name_i18n: Record<string, string>;
    description_i18n: Record<string, string>;
    item_type_i18n?: Record<string, string>;
    item_category_i18n?: Record<string, string>;
    base_value?: number;
    properties_json?: Record<string, any>;
    slot_type?: string;
    is_stackable: boolean;
    created_at: string;
    updated_at: string;
}

export interface ItemPayload { // Общий для создания и data_json при обновлении
    static_id: string;
    name_i18n: Record<string, string>;
    item_type_i18n: Record<string, string>; // Обязательно при создании
    description_i18n?: Record<string, string>;
    properties_json?: Record<string, any>;
    base_value?: number;
    slot_type?: string;
    is_stackable?: boolean;
    item_category_i18n?: Record<string, string>;
}

export interface InventoryItemData {
    id: number; // InventoryItem instance ID
    guild_id: number;
    owner_entity_type: string; // "PLAYER" | "GENERATED_NPC"
    owner_entity_id: number;
    item_id: number; // Base ItemDefinition ID
    quantity: number;
    equipped_status?: string;
    instance_specific_properties_json?: Record<string, any>;
    // Поля базового ItemDefinition могут быть здесь, если API возвращает их сразу
    // Либо UI должен будет их дозагружать.
    // Для обогащенного ответа, см. EnrichedInventoryItem ниже.
}

// Используется, когда API возвращает инвентарь с уже включенными деталями предметов
export interface EnrichedInventoryItem {
    inventory_item_id: number; // Instance ID
    item_id: number; // Base Item ID
    name_i18n: Record<string, string>;
    description_i18n: Record<string, string>;
    item_type_i18n?: Record<string, string>;
    item_category_i18n?: Record<string, string>;
    base_value?: number;
    slot_type?: string;
    is_stackable: boolean;
    item_properties_json?: Record<string, any>; // From Item model (base definition)
    quantity: number;
    equipped_status?: string;
    instance_specific_properties_json?: Record<string, any>; // From InventoryItem model
    created_at: string; // from ItemDefinition
    updated_at: string; // from ItemDefinition
}

// PaginatedResponse is now typically imported from a shared types file like 'entities.ts'
// or a global types definition if available.
// For example: import { PaginatedResponse } from './entities';
// If it's specific to items and different, it can remain.
// Assuming for now it's intended to be shared, so this local one might be redundant.
// Keeping it here for now if item-specific pagination differs, but likely should be centralized.
// Based on analysis, it's better to use the one from entities.ts or a global one.
// This local definition will be removed.
