// src/ui/src/pages/ItemManagementPage/ItemForm.tsx
import React, { useState, useEffect, useMemo } from 'react';
import { ItemDefinition, ItemPayload } from '../../types/items';
import { itemService } from '../../services/itemService';

interface ItemFormProps {
  guildId: number;
  editingItem?: ItemDefinition | null; // Item to edit, or null/undefined for new item
  onFormSubmitSuccess: (item: ItemDefinition) => void; // Callback on successful submit
  onCancel: () => void;
}

// Example supported languages, could come from a global config or context
const SUPPORTED_LANGUAGES = ['en', 'ru'];

const ItemForm: React.FC<ItemFormProps> = ({ guildId, editingItem, onFormSubmitSuccess, onCancel }) => {
  const isEditMode = !!editingItem;

  const initialNameI18n = useMemo(() => SUPPORTED_LANGUAGES.reduce((acc, lang) => ({ ...acc, [lang]: '' }), {}), []);
  const initialDescriptionI18n = useMemo(() => SUPPORTED_LANGUAGES.reduce((acc, lang) => ({ ...acc, [lang]: '' }), {}), []);
  const initialItemTypeI18n = useMemo(() => SUPPORTED_LANGUAGES.reduce((acc, lang) => ({ ...acc, [lang]: '' }), {}), []);
  const initialCategoryI18n = useMemo(() => SUPPORTED_LANGUAGES.reduce((acc, lang) => ({ ...acc, [lang]: '' }), {}), []);

  const [staticId, setStaticId] = useState<string>('');
  const [nameI18n, setNameI18n] = useState<Record<string, string>>(initialNameI18n);
  const [descriptionI18n, setDescriptionI18n] = useState<Record<string, string>>(initialDescriptionI18n);
  const [itemTypeI18n, setItemTypeI18n] = useState<Record<string, string>>(initialItemTypeI18n);
  const [categoryI18n, setCategoryI18n] = useState<Record<string, string>>(initialCategoryI18n);
  const [baseValue, setBaseValue] = useState<string>(''); // string for input field
  const [propertiesJson, setPropertiesJson] = useState<string>('{}');
  const [slotType, setSlotType] = useState<string>('');
  const [isStackable, setIsStackable] = useState<boolean>(true);

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (editingItem) {
      setStaticId(editingItem.static_id || '');
      setNameI18n(editingItem.name_i18n || initialNameI18n);
      setDescriptionI18n(editingItem.description_i18n || initialDescriptionI18n);
      setItemTypeI18n(editingItem.item_type_i18n || initialItemTypeI18n);
      setCategoryI18n(editingItem.item_category_i18n || initialCategoryI18n);
      setBaseValue(editingItem.base_value?.toString() || '');
      setPropertiesJson(JSON.stringify(editingItem.properties_json || {}, null, 2));
      setSlotType(editingItem.slot_type || '');
      setIsStackable(editingItem.is_stackable !== undefined ? editingItem.is_stackable : true);
    } else {
      // Reset for new item form
      setStaticId('');
      setNameI18n(initialNameI18n);
      setDescriptionI18n(initialDescriptionI18n);
      setItemTypeI18n(initialItemTypeI18n);
      setCategoryI18n(initialCategoryI18n);
      setBaseValue('');
      setPropertiesJson('{}');
      setSlotType('');
      setIsStackable(true);
    }
  }, [editingItem, initialCategoryI18n, initialDescriptionI18n, initialItemTypeI18n, initialNameI18n]);

  const handleI18nChange = (
    lang: string,
    value: string,
    setter: React.Dispatch<React.SetStateAction<Record<string, string>>>
  ) => {
    setter(prev => ({ ...prev, [lang]: value }));
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);

    let parsedPropertiesJson: Record<string, any> | undefined;
    try {
      parsedPropertiesJson = propertiesJson.trim() === '' ? {} : JSON.parse(propertiesJson);
    } catch (e) {
      setError('Invalid JSON format for Properties JSON.');
      setLoading(false);
      return;
    }

    const payload: ItemPayload = {
      static_id: staticId.trim() === '' ? undefined : staticId.trim(), // static_id is optional for ItemPayload if backend generates it
      name_i18n: nameI18n,
      item_type_i18n: itemTypeI18n, // Required for creation
      description_i18n: descriptionI18n,
      item_category_i18n: categoryI18n,
      base_value: baseValue.trim() === '' ? undefined : parseInt(baseValue, 10),
      properties_json: parsedPropertiesJson,
      slot_type: slotType.trim() === '' ? undefined : slotType.trim(),
      is_stackable: isStackable,
    };

    // Basic validation for required fields
    if (!payload.static_id && !isEditMode) { // static_id might be required for create by command
        setError('Static ID is required for new items.');
        setLoading(false);
        return;
    }
    if (Object.values(payload.name_i18n).every(name => name.trim() === '')) {
        setError('Name (at least for one language) is required.');
        setLoading(false);
        return;
    }
     if (Object.values(payload.item_type_i18n).every(type => type.trim() === '')) {
        setError('Item Type (at least for one language) is required.');
        setLoading(false);
        return;
    }


    try {
      let result: ItemDefinition;
      if (isEditMode && editingItem) {
        // For update, the backend /master_item update command expects data_json
        // So the payload should be Partial<ItemPayload>
        const updatePayload: Partial<ItemPayload> = {};
        if (staticId !== editingItem.static_id) updatePayload.static_id = staticId;
        if (JSON.stringify(nameI18n) !== JSON.stringify(editingItem.name_i18n)) updatePayload.name_i18n = nameI18n;
        if (JSON.stringify(descriptionI18n) !== JSON.stringify(editingItem.description_i18n)) updatePayload.description_i18n = descriptionI18n;
        if (JSON.stringify(itemTypeI18n) !== JSON.stringify(editingItem.item_type_i18n)) updatePayload.item_type_i18n = itemTypeI18n;
        if (JSON.stringify(categoryI18n) !== JSON.stringify(editingItem.item_category_i18n)) updatePayload.item_category_i18n = categoryI18n;
        if (baseValue !== (editingItem.base_value?.toString() || '')) updatePayload.base_value = baseValue === '' ? undefined : parseInt(baseValue, 10);
        if (propertiesJson !== JSON.stringify(editingItem.properties_json || {}, null, 2)) updatePayload.properties_json = parsedPropertiesJson;
        if (slotType !== (editingItem.slot_type || '')) updatePayload.slot_type = slotType;
        if (isStackable !== editingItem.is_stackable) updatePayload.is_stackable = isStackable;

        result = await itemService.updateItem(guildId, editingItem.id, updatePayload);
      } else {
        result = await itemService.createItem(guildId, payload as ItemPayload); // Cast as full payload for create
      }
      onFormSubmitSuccess(result);
    } catch (err: any) {
      setError(`Operation failed: ${err.message || 'Unknown error'}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const renderI18nFields = (
    label: string,
    state: Record<string, string>,
    handler: (lang: string, value: string, setter: React.Dispatch<React.SetStateAction<Record<string, string>>>) => void,
    setter: React.Dispatch<React.SetStateAction<Record<string, string>>>,
    isTextarea: boolean = false
  ) => (
    <div>
      <label style={{display: 'block', fontWeight: 'bold', marginBottom: '5px'}}>{label}:</label>
      {SUPPORTED_LANGUAGES.map(lang => (
        <div key={lang} style={{marginBottom: '5px'}}>
          <label htmlFor={`${label}-${lang}`} style={{marginRight: '5px', textTransform: 'uppercase'}}>{lang}:</label>
          {isTextarea ? (
            <textarea
              id={`${label}-${lang}`}
              value={state[lang] || ''}
              onChange={(e) => handler(lang, e.target.value, setter)}
              rows={2}
              style={{width: 'calc(100% - 30px)', padding: '5px'}}
              disabled={loading}
            />
          ) : (
            <input
              type="text"
              id={`${label}-${lang}`}
              value={state[lang] || ''}
              onChange={(e) => handler(lang, e.target.value, setter)}
              style={{width: 'calc(100% - 30px)', padding: '5px'}}
              disabled={loading}
            />
          )}
        </div>
      ))}
    </div>
  );


  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '15px', padding: '20px', border: '1px solid #ccc', borderRadius: '8px', backgroundColor: '#f9f9f9' }}>
      <h3>{isEditMode ? `Edit Item ID: ${editingItem?.id}` : 'Create New Item Definition'}</h3>

      <div>
        <label htmlFor="staticId" style={{display: 'block', marginBottom: '5px'}}>Static ID:</label>
        <input type="text" id="staticId" value={staticId} onChange={(e) => setStaticId(e.target.value)} required={!isEditMode} disabled={loading} style={{width: '100%', padding: '8px', boxSizing: 'border-box'}} />
      </div>

      {renderI18nFields("Name", nameI18n, handleI18nChange, setNameI18n)}
      {renderI18nFields("Description", descriptionI18n, handleI18nChange, setDescriptionI18n, true)}
      {renderI18nFields("Item Type", itemTypeI18n, handleI18nChange, setItemTypeI18n)}
      {renderI18nFields("Category", categoryI18n, handleI18nChange, setCategoryI18n)}

      <div>
        <label htmlFor="baseValue" style={{display: 'block', marginBottom: '5px'}}>Base Value:</label>
        <input type="number" id="baseValue" value={baseValue} onChange={(e) => setBaseValue(e.target.value)} disabled={loading} style={{width: '100%', padding: '8px', boxSizing: 'border-box'}} />
      </div>

      <div>
        <label htmlFor="slotType" style={{display: 'block', marginBottom: '5px'}}>Slot Type (e.g., weapon, head, chest):</label>
        <input type="text" id="slotType" value={slotType} onChange={(e) => setSlotType(e.target.value)} disabled={loading} style={{width: '100%', padding: '8px', boxSizing: 'border-box'}} />
      </div>

      <div>
        <label htmlFor="propertiesJson" style={{display: 'block', marginBottom: '5px'}}>Properties (JSON):</label>
        <textarea
          id="propertiesJson"
          value={propertiesJson}
          onChange={(e) => setPropertiesJson(e.target.value)}
          rows={5}
          style={{ width: '100%', fontFamily: 'monospace', padding: '8px', boxSizing: 'border-box' }}
          disabled={loading}
        />
      </div>

      <div style={{display: 'flex', alignItems: 'center'}}>
        <input type="checkbox" id="isStackable" checked={isStackable} onChange={(e) => setIsStackable(e.target.checked)} disabled={loading} style={{marginRight: '5px'}} />
        <label htmlFor="isStackable">Is Stackable</label>
      </div>

      {error && <p style={{ color: 'red', marginTop: '10px' }}>Error: {error}</p>}

      <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
        <button type="button" onClick={onCancel} disabled={loading} style={{padding: '10px 15px'}}>Cancel</button>
        <button type="submit" disabled={loading} style={{padding: '10px 15px', backgroundColor: '#007bff', color: 'white'}}>
          {loading ? 'Saving...' : (isEditMode ? 'Save Changes' : 'Create Item')}
        </button>
      </div>
    </form>
  );
};

export default ItemForm;
