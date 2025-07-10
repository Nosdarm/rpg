import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { MobileGroupData } from '../../types/globalEntity';
import { getMobileGroups } from '../../services/globalEntityService';
import { useGuild } from '../../contexts';

const MobileGroupListPage: React.FC = () => {
  const [mobileGroups, setMobileGroups] = useState<MobileGroupData[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const { currentGuildId } = useGuild();

  useEffect(() => {
    if (!currentGuildId) {
      setError("Guild ID not selected.");
      setLoading(false);
      return;
    }
    const fetchGroups = async () => {
      try {
        setLoading(true);
        const response = await getMobileGroups(currentGuildId);
        setMobileGroups(response.items);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch mobile groups:", err);
        setError("Failed to load Mobile Groups. Check console.");
      } finally {
        setLoading(false);
      }
    };

    fetchGroups();
  }, [currentGuildId]);

  if (loading) return <div>Loading Mobile Groups...</div>;
  if (error) return <div style={{ color: 'red' }}>Error: {error}</div>;
  if (!mobileGroups.length) return <div>No Mobile Groups found for this guild.</div>;

  return (
    <div>
      <h1>Mobile Group List</h1>
      {/* <Link to="/global-entities/groups/new">Create New Mobile Group</Link> */}
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Static ID</th>
            <th>Name (EN)</th>
            <th>Location ID</th>
            <th>Leader NPC ID</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {mobileGroups.map((group) => (
            <tr key={group.id}>
              <td>{group.id}</td>
              <td>{group.static_id}</td>
              <td>{group.name_i18n?.en || 'N/A'}</td>
              <td>{group.current_location_id || 'N/A'}</td>
              <td>{group.leader_global_npc_id || 'N/A'}</td>
              <td>
                <Link to={`/global-entities/groups/${group.id}`}>View/Edit</Link>
                {/* TODO: Delete button */}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {/* TODO: Pagination */}
    </div>
  );
};

export default MobileGroupListPage;
