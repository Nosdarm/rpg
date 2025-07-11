// src/ui/src/pages/AiModerationPage/TriggerAiGenerationForm.tsx
import React, { useState } from 'react';
import { pendingGenerationService } from '../../services/pendingGenerationService';
import { TriggerGenerationPayload, UIPendingGeneration } from '../../types/pending_generation';

interface TriggerAiGenerationFormProps {
  guildId: number;
  onGenerationTriggered?: (response: UIPendingGeneration) => void;
}

const entityTypes = ["location", "npc", "item", "quest", "faction", "world_event", "lore_entry"];

const TriggerAiGenerationForm: React.FC<TriggerAiGenerationFormProps> = ({ guildId, onGenerationTriggered }) => {
  const [entityType, setEntityType] = useState<string>(entityTypes[0]);
  const [generationContextJson, setGenerationContextJson] = useState<string>('{}');
  const [locationIdContext, setLocationIdContext] = useState<string>('');
  const [playerIdContext, setPlayerIdContext] = useState<string>('');

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setSuccessMessage(null);

    let parsedContextJson: Record<string, any> | undefined = undefined;
    if (generationContextJson.trim() !== '' && generationContextJson.trim() !== '{}') {
      try {
        parsedContextJson = JSON.parse(generationContextJson);
      } catch (e) {
        setError('Invalid JSON format for Generation Context. Please provide valid JSON or an empty object {}.');
        setLoading(false);
        return;
      }
    } else if (generationContextJson.trim() === '{}') {
        parsedContextJson = {};
    }


    const payload: TriggerGenerationPayload = {
      entity_type: entityType,
    };

    if (parsedContextJson !== undefined) {
        payload.generation_context_json = parsedContextJson;
    }
    if (locationIdContext) {
        const locId = parseInt(locationIdContext, 10);
        if (!isNaN(locId)) {
            payload.location_id_context = locId;
        } else {
            setError('Location ID Context must be a valid number.');
            setLoading(false);
            return;
        }
    }
    if (playerIdContext) {
        const pId = parseInt(playerIdContext, 10);
        if (!isNaN(pId)) {
            payload.player_id_context = pId;
        } else {
            setError('Player ID Context must be a valid number.');
            setLoading(false);
            return;
        }
    }


    try {
      // Используем guildId из props
      const response = await pendingGenerationService.triggerGeneration(guildId, payload);
      setSuccessMessage(`Generation triggered successfully! Pending ID: ${response.id}, Status: ${response.status}`);
      if (onGenerationTriggered) {
        onGenerationTriggered(response);
      }
      // Сброс формы после успешной отправки
      setEntityType(entityTypes[0]);
      setGenerationContextJson('{}');
      setLocationIdContext('');
      setPlayerIdContext('');
    } catch (err: any) {
      setError(`Failed to trigger generation: ${err.message || 'Unknown error'}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '15px', padding: '15px', border: '1px solid #ddd', borderRadius: '8px' }}>
      <h3>Trigger New AI Content Generation</h3>

      <div>
        <label htmlFor="entityType" style={{display: 'block', marginBottom: '5px'}}>Entity Type: </label>
        <select
          id="entityType"
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
          required
          style={{width: '100%', padding: '8px', boxSizing: 'border-box'}}
        >
          {entityTypes.map(type => (
            <option key={type} value={type}>{type.charAt(0).toUpperCase() + type.slice(1)}</option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="generationContextJson" style={{display: 'block', marginBottom: '5px'}}>Generation Context (JSON): </label>
        <textarea
          id="generationContextJson"
          value={generationContextJson}
          onChange={(e) => setGenerationContextJson(e.target.value)}
          rows={6}
          placeholder='e.g., {"theme": "dark_fantasy", "keywords": ["undead", "cursed"]}'
          style={{ width: '100%', fontFamily: 'monospace', padding: '8px', boxSizing: 'border-box', minHeight: '80px' }}
        />
        <small>Enter valid JSON or leave as '{{}}' for default/no specific context.</small>
      </div>

      <div>
        <label htmlFor="locationIdContext" style={{display: 'block', marginBottom: '5px'}}>Location ID Context (Optional): </label>
        <input
          id="locationIdContext"
          type="number"
          value={locationIdContext}
          onChange={(e) => setLocationIdContext(e.target.value)}
          placeholder="Enter location ID"
          style={{width: '100%', padding: '8px', boxSizing: 'border-box'}}
        />
      </div>

      <div>
        <label htmlFor="playerIdContext" style={{display: 'block', marginBottom: '5px'}}>Player ID Context (Optional): </label>
        <input
          id="playerIdContext"
          type="number"
          value={playerIdContext}
          onChange={(e) => setPlayerIdContext(e.target.value)}
          placeholder="Enter player ID"
          style={{width: '100%', padding: '8px', boxSizing: 'border-box'}}
        />
      </div>

      <button type="submit" disabled={loading} style={{padding: '10px 15px', cursor: loading? 'not-allowed' : 'pointer'}}>
        {loading ? 'Triggering...' : 'Trigger Generation'}
      </button>

      {error && <p style={{ color: 'red', marginTop: '10px' }}>Error: {error}</p>}
      {successMessage && <p style={{ color: 'green', marginTop: '10px' }}>{successMessage}</p>}
    </form>
  );
};

export default TriggerAiGenerationForm;
