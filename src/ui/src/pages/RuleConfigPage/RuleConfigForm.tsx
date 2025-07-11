import React, { useState, useEffect } from 'react';
import { ruleConfigService, RuleConfigCreatePayload, RuleConfigSetPayload } from 'src/services/ruleConfigService';
import type { RuleConfigEntry } from 'src/types/ruleconfig';

interface RuleConfigFormProps {
  guildId: string;
  ruleKeyToEdit?: string | null; // If provided, form is in edit mode
  onFormSubmitSuccess: () => void; // Callback to refresh list or navigate
  onCancel: () => void;
  notify: (message: string, type?: 'success' | 'error') => void;
}

const RuleConfigForm: React.FC<RuleConfigFormProps> = ({
  guildId,
  ruleKeyToEdit,
  onFormSubmitSuccess,
  onCancel,
  notify,
}) => {
  const [key, setKey] = useState('');
  const [valueJson, setValueJson] = useState('');
  const [description, setDescription] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const isEditing = !!ruleKeyToEdit;

  useEffect(() => {
    if (isEditing && ruleKeyToEdit) {
      setIsLoading(true);
      ruleConfigService.getRuleConfigEntry(guildId, ruleKeyToEdit)
        .then((rule) => {
          setKey(rule.key);
          setValueJson(typeof rule.value_json === 'string' ? rule.value_json : JSON.stringify(rule.value_json, null, 2));
          setDescription(rule.description || '');
        })
        .catch(err => {
          const msg = err instanceof Error ? err.message : 'Failed to fetch rule details';
          notify(msg, 'error');
          setFormError(msg);
        })
        .finally(() => setIsLoading(false));
    } else {
      // Reset form for creation mode
      setKey('');
      setValueJson('');
      setDescription('');
    }
  }, [guildId, ruleKeyToEdit, isEditing, notify]);

  const validateJson = (jsonString: string): boolean => {
    try {
      JSON.parse(jsonString);
      return true;
    } catch (e) {
      return false;
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(null);

    if (!key.trim()) {
      setFormError('Key cannot be empty.');
      return;
    }
    if (!validateJson(valueJson)) {
      setFormError('Value must be valid JSON.');
      return;
    }

    setIsLoading(true);

    try {
      if (isEditing && ruleKeyToEdit) {
        const payload: RuleConfigSetPayload = { value_json: valueJson, description: description || undefined };
        await ruleConfigService.updateRuleConfigEntry(guildId, ruleKeyToEdit, payload);
        notify(`Rule "${ruleKeyToEdit}" updated successfully.`, 'success');
      } else {
        const payload: RuleConfigCreatePayload = { key, value_json: valueJson, description: description || undefined };
        await ruleConfigService.createRuleConfigEntry(guildId, payload);
        notify(`Rule "${key}" created successfully.`, 'success');
      }
      onFormSubmitSuccess();
    } catch (err) {
      const msg = err instanceof Error ? err.message : (isEditing ? 'Failed to update rule' : 'Failed to create rule');
      notify(msg, 'error');
      setFormError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading && isEditing && !key) return <p>Loading rule details...</p>; // Loading state for edit mode initial fetch

  return (
    <form onSubmit={handleSubmit}>
      <h2>{isEditing ? `Edit Rule: ${ruleKeyToEdit}` : 'Create New RuleConfig'}</h2>

      {formError && <p style={{ color: 'red' }}>Error: {formError}</p>}

      <div>
        <label htmlFor="ruleKey">Key:</label>
        <input
          type="text"
          id="ruleKey"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          readOnly={isEditing}
          required
          style={{width: '100%', boxSizing: 'border-box', marginBottom: '10px'}}
        />
      </div>

      <div>
        <label htmlFor="ruleValueJson">Value (JSON string):</label>
        <textarea
          id="ruleValueJson"
          value={valueJson}
          onChange={(e) => setValueJson(e.target.value)}
          rows={15}
          required
          style={{width: '100%', boxSizing: 'border-box', marginBottom: '10px', fontFamily: 'monospace'}}
        />
      </div>

      <div>
        <label htmlFor="ruleDescription">Description (optional):</label>
        <textarea
          id="ruleDescription"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={5}
          style={{width: '100%', boxSizing: 'border-box', marginBottom: '10px'}}
        />
      </div>

      <div>
        <button type="submit" disabled={isLoading} style={{ marginRight: '10px' }}>
          {isLoading ? 'Saving...' : (isEditing ? 'Save Changes' : 'Create Rule')}
        </button>
        <button type="button" onClick={onCancel} disabled={isLoading}>
          Cancel
        </button>
      </div>
    </form>
  );
};

export default RuleConfigForm;
