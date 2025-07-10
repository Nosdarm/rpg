import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { MobileGroupData, MobileGroupPayload } from '../../types/globalEntity';
import { getMobileGroup, updateMobileGroup, createMobileGroup } from '../../services/globalEntityService';
import { useGuild } from '../../contexts';

const MobileGroupDetailPage: React.FC = () => {
  const { groupId } = useParams<{ groupId?: string }>();
  const navigate = useNavigate();
  const isNew = groupId === 'new';
  const [group, setGroup] = useState<Partial<MobileGroupData>>({});
  const [formData, setFormData] = useState<Partial<MobileGroupPayload>>({});
  const [loading, setLoading] = useState<boolean>(!isNew);
  const [error, setError] = useState<string | null>(null);
  const { currentGuildId } = useGuild();

  useEffect(() => {
    if (!isNew && groupId && currentGuildId) {
      const fetchGroup = async () => {
        try {
          setLoading(true);
          const data = await getMobileGroup(parseInt(groupId, 10), currentGuildId);
          setGroup(data);
          setFormData({
            static_id: data.static_id,
            name_i18n_json: JSON.stringify(data.name_i18n || {}),
            description_i18n_json: JSON.stringify(data.description_i18n || {}),
            current_location_id: data.current_location_id || undefined,
            leader_global_npc_id: data.leader_global_npc_id || undefined,
            members_definition_json: JSON.stringify(data.members_definition_json || []),
            behavior_type_i18n_json: JSON.stringify(data.behavior_type_i18n || {}),
            route_json: JSON.stringify(data.route_json || {}),
            properties_json: JSON.stringify(data.properties_json || {}),
          });
          setError(null);
        } catch (err) {
          console.error("Failed to fetch Mobile Group:", err);
          setError("Failed to load Mobile Group details.");
        } finally {
          setLoading(false);
        }
      };
      fetchGroup();
    } else if (isNew) {
      setFormData({
        static_id: '',
        name_i18n_json: JSON.stringify({ en: '' }),
        members_definition_json: JSON.stringify([]),
        properties_json: JSON.stringify({}),
      });
    }
  }, [groupId, isNew, currentGuildId]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
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
      const payload: MobileGroupPayload = { // Construct full payload
        static_id: formData.static_id || '',
        name_i18n_json: formData.name_i18n_json || '{}',
        description_i18n_json: formData.description_i18n_json,
        current_location_id: formData.current_location_id,
        leader_global_npc_id: formData.leader_global_npc_id,
        members_definition_json: formData.members_definition_json,
        behavior_type_i18n_json: formData.behavior_type_i18n_json,
        route_json: formData.route_json,
        properties_json: formData.properties_json,
      };

      let savedGroup;
      if (isNew) {
        savedGroup = await createMobileGroup(payload, currentGuildId);
        navigate(`/global-entities/groups/${savedGroup.id}`);
      } else if (groupId) {
        savedGroup = await updateMobileGroup(parseInt(groupId, 10), payload as MobileGroupData, currentGuildId);
        setGroup(savedGroup);
        alert('Mobile Group updated successfully!');
      }
      setError(null);
    } catch (err) {
      console.error("Failed to save Mobile Group:", err);
      setError("Failed to save Mobile Group. Check console.");
    } finally {
      setLoading(false);
    }
  };

  if (loading && !isNew) return <div>Loading Mobile Group details...</div>;
  if (error) return <div style={{ color: 'red' }}>Error: {error}</div>;
  if (!isNew && !group.id) return <div>Mobile Group not found.</div>;

  return (
    <div>
      <h1>{isNew ? 'Create New Mobile Group' : `Edit Mobile Group: ${group.name_i18n?.en || group.static_id}`}</h1>
      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="static_id">Static ID:</label>
          <input type="text" id="static_id" name="static_id" value={formData.static_id || ''} onChange={handleChange} required />
        </div>
        <div>
          <label htmlFor="name_i18n_json">Name (JSON):</label>
          <textarea id="name_i18n_json" name="name_i18n_json" value={formData.name_i18n_json || ''} onChange={handleChange} rows={2} required />
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
          <label htmlFor="leader_global_npc_id">Leader Global NPC ID:</label>
          <input type="number" id="leader_global_npc_id" name="leader_global_npc_id" value={formData.leader_global_npc_id || ''} onChange={handleChange} />
        </div>
        <div>
          <label htmlFor="members_definition_json">Members Definition (JSON Array):</label>
          <textarea id="members_definition_json" name="members_definition_json" value={formData.members_definition_json || ''} onChange={handleChange} rows={4} />
        </div>
        <div>
          <label htmlFor="behavior_type_i18n_json">Behavior Type (JSON):</label>
          <textarea id="behavior_type_i18n_json" name="behavior_type_i18n_json" value={formData.behavior_type_i18n_json || ''} onChange={handleChange} rows={2} />
        </div>
        <div>
          <label htmlFor="route_json">Route (JSON):</label>
          <textarea id="route_json" name="route_json" value={formData.route_json || ''} onChange={handleChange} rows={3} />
        </div>
        <div>
          <label htmlFor="properties_json">Properties (JSON):</label>
          <textarea id="properties_json" name="properties_json" value={formData.properties_json || ''} onChange={handleChange} rows={3} />
        </div>
        <button type="submit" disabled={loading}>{loading ? 'Saving...' : 'Save Mobile Group'}</button>
      </form>
      {!isNew && <pre>Raw Data: {JSON.stringify(group, null, 2)}</pre>}
    </div>
  );
};

export default MobileGroupDetailPage;
