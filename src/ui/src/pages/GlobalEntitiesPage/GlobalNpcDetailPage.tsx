import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { GlobalNpcData, GlobalNpcPayload } from '../../types/globalEntity'; // Assuming UpdatePayload is similar or handled by fields
import { getGlobalNpc, updateGlobalNpc, createGlobalNpc } from '../../services/globalEntityService';
import { useGuild } from '../../contexts';

const GlobalNpcDetailPage: React.FC = () => {
  const { npcId } = useParams<{ npcId?: string }>();
  const navigate = useNavigate();
  const isNew = npcId === 'new';
  const [npc, setNpc] = useState<Partial<GlobalNpcData>>({});
  const [formData, setFormData] = useState<Partial<GlobalNpcPayload>>({});
  const [loading, setLoading] = useState<boolean>(!isNew);
  const [error, setError] = useState<string | null>(null);
  const { currentGuildId } = useGuild();

  useEffect(() => {
    if (!isNew && npcId && currentGuildId) {
      const fetchNpc = async () => {
        try {
          setLoading(true);
          const data = await getGlobalNpc(parseInt(npcId, 10), currentGuildId);
          setNpc(data);
          // Initialize form data from fetched NPC data
          setFormData({
            static_id: data.static_id,
            name_i18n_json: JSON.stringify(data.name_i18n || {}),
            description_i18n_json: JSON.stringify(data.description_i18n || {}),
            current_location_id: data.current_location_id || undefined,
            base_npc_id: data.base_npc_id || undefined,
            mobile_group_id: data.mobile_group_id || undefined,
            properties_json: JSON.stringify(data.properties_json || {}),
          });
          setError(null);
        } catch (err) {
          console.error("Failed to fetch Global NPC:", err);
          setError("Failed to load Global NPC details.");
        } finally {
          setLoading(false);
        }
      };
      fetchNpc();
    } else if (isNew) {
      // Initialize form for new NPC
      setFormData({
        static_id: '',
        name_i18n_json: JSON.stringify({ en: ''}),
        description_i18n_json: JSON.stringify({ en: ''}),
        properties_json: JSON.stringify({}),
      });
    }
  }, [npcId, isNew, currentGuildId]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    // @ts-ignore
    const isNumber = e.target.type === 'number';
    setFormData(prev => ({ ...prev, [name]: isNumber ? (value ? parseInt(value,10) : null) : value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentGuildId) {
      setError("Guild ID is missing.");
      return;
    }
    try {
      setLoading(true);
      let savedNpc;
      const payload: GlobalNpcPayload = { // Construct full payload
        static_id: formData.static_id || '',
        name_i18n_json: formData.name_i18n_json || '{}',
        description_i18n_json: formData.description_i18n_json,
        current_location_id: formData.current_location_id,
        base_npc_id: formData.base_npc_id,
        mobile_group_id: formData.mobile_group_id,
        properties_json: formData.properties_json,
      };

      if (isNew) {
        savedNpc = await createGlobalNpc(payload, currentGuildId);
        navigate(`/global-entities/npcs/${savedNpc.id}`); // Navigate to the new NPC's detail page
      } else if (npcId) {
        // For update, the service might need specific field_to_update logic
        // or accept a partial payload. This mock assumes a partial payload works.
        savedNpc = await updateGlobalNpc(parseInt(npcId, 10), payload as GlobalNpcData, currentGuildId);
        setNpc(savedNpc); // Update local state
        alert('Global NPC updated successfully!');
      }
      setError(null);
    } catch (err) {
      console.error("Failed to save Global NPC:", err);
      setError("Failed to save Global NPC. Check console.");
    } finally {
      setLoading(false);
    }
  };

  if (loading && !isNew) return <div>Loading Global NPC details...</div>;
  if (error) return <div style={{ color: 'red' }}>Error: {error}</div>;
  if (!isNew && !npc.id) return <div>Global NPC not found.</div>;

  return (
    <div>
      <h1>{isNew ? 'Create New Global NPC' : `Edit Global NPC: ${npc.name_i18n?.en || npc.static_id}`}</h1>
      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="static_id">Static ID:</label>
          <input type="text" id="static_id" name="static_id" value={formData.static_id || ''} onChange={handleChange} required />
        </div>
        <div>
          <label htmlFor="name_i18n_json">Name (JSON):</label>
          <textarea id="name_i18n_json" name="name_i18n_json" value={formData.name_i18n_json || ''} onChange={handleChange} rows={3} required />
        </div>
        <div>
          <label htmlFor="description_i18n_json">Description (JSON):</label>
          <textarea id="description_i18n_json" name="description_i18n_json" value={formData.description_i18n_json || ''} onChange={handleChange} rows={3} />
        </div>
        <div>
          <label htmlFor="current_location_id">Current Location ID:</label>
          <input type="number" id="current_location_id" name="current_location_id" value={formData.current_location_id || ''} onChange={handleChange} />
        </div>
         <div>
          <label htmlFor="base_npc_id">Base NPC ID (Template):</label>
          <input type="number" id="base_npc_id" name="base_npc_id" value={formData.base_npc_id || ''} onChange={handleChange} />
        </div>
         <div>
          <label htmlFor="mobile_group_id">Mobile Group ID:</label>
          <input type="number" id="mobile_group_id" name="mobile_group_id" value={formData.mobile_group_id || ''} onChange={handleChange} />
        </div>
        <div>
          <label htmlFor="properties_json">Properties (JSON):</label>
          <textarea id="properties_json" name="properties_json" value={formData.properties_json || ''} onChange={handleChange} rows={5} />
        </div>
        <button type="submit" disabled={loading}>{loading ? 'Saving...' : 'Save Global NPC'}</button>
      </form>
      {!isNew && <pre>Raw Data: {JSON.stringify(npc, null, 2)}</pre>}
    </div>
  );
};

export default GlobalNpcDetailPage;
