import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { GlobalNpcData } from '../../types/globalEntity';
import { getGlobalNpcs } from '../../services/globalEntityService';
import { /*useLanguage,*/ useGuild } from '../../contexts'; // Assuming context for lang/guild

const GlobalNpcListPage: React.FC = () => {
  const [globalNpcs, setGlobalNpcs] = useState<GlobalNpcData[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  // const { currentLanguage } = useLanguage(); // Example context usage
  const { currentGuildId } = useGuild(); // Example context usage

  useEffect(() => {
    if (!currentGuildId) {
      setError("Guild ID not selected.");
      setLoading(false);
      return;
    }
    const fetchNpcs = async () => {
      try {
        setLoading(true);
        // TODO: Add pagination controls and pass page/limit
        const response = await getGlobalNpcs(currentGuildId);
        setGlobalNpcs(response.items);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch global NPCs:", err);
        setError("Failed to load Global NPCs. Check console for details.");
      } finally {
        setLoading(false);
      }
    };

    fetchNpcs();
  }, [currentGuildId]);

  if (loading) return <div>Loading Global NPCs...</div>;
  if (error) return <div style={{ color: 'red' }}>Error: {error}</div>;
  if (!globalNpcs.length) return <div>No Global NPCs found for this guild.</div>;

  return (
    <div>
      <h1>Global NPC List</h1>
      {/* TODO: Add Link to Create New Global NPC page */}
      {/* <Link to="/global-entities/npcs/new">Create New Global NPC</Link> */}
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Static ID</th>
            <th>Name (EN/Current Lang)</th>
            <th>Location ID</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {globalNpcs.map((npc) => (
            <tr key={npc.id}>
              <td>{npc.id}</td>
              <td>{npc.static_id}</td>
              <td>{npc.name_i18n?.en || 'N/A'} {/* Basic display, improve with lang context */}</td>
              <td>{npc.current_location_id || 'N/A'}</td>
              <td>
                <Link to={`/global-entities/npcs/${npc.id}`}>View/Edit</Link>
                {/* TODO: Add delete button with confirmation */}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {/* TODO: Add pagination component */}
    </div>
  );
};

export default GlobalNpcListPage;
