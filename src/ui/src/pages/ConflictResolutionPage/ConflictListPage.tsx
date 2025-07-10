import React, { useEffect, useState } from 'react';
// import { getPendingConflicts } from '../../services/conflictService';
// import { UIConflictListItem, UIConflictStatus } from '../../types/conflict';
// import { PaginatedResponse } from '../../types/entities';

interface ConflictListPageProps {
  onSelectConflict: (conflictId: number) => void;
  guildId: string; // Assuming guildId is passed as a prop or from context
}

const ConflictListPage: React.FC<ConflictListPageProps> = ({ onSelectConflict, guildId }) => {
  // const [conflicts, setConflicts] = useState<PaginatedResponse<UIConflictListItem> | null>(null);
  // const [loading, setLoading] = useState<boolean>(true);
  // const [error, setError] = useState<string | null>(null);
  // const [currentPage, setCurrentPage] = useState<number>(1);
  // const [statusFilter, setStatusFilter] = useState<UIConflictStatus | undefined>(UIConflictStatus.PENDING_MASTER_RESOLUTION);

  useEffect(() => {
    // const fetchConflicts = async () => {
    //   setLoading(true);
    //   setError(null);
    //   try {
    //     // const response = await getPendingConflicts(guildId, statusFilter, currentPage);
    //     // setConflicts(response);
    //   } catch (err) {
    //     // setError('Failed to fetch conflicts.');
    //     // console.error(err);
    //   } finally {
    //     // setLoading(false);
    //   }
    // };
    // fetchConflicts();
    console.log('Mock: Fetching conflicts for guild:', guildId);
  }, [guildId, currentPage, statusFilter]);

  // if (loading) return <p>Loading conflicts...</p>;
  // if (error) return <p style={{ color: 'red' }}>{error}</p>;
  // if (!conflicts || conflicts.items.length === 0) return <p>No conflicts found.</p>;

  return (
    <div>
      <h2>Pending Conflicts</h2>
      {/* Placeholder for filter controls */}
      {/* Placeholder for pagination controls */}
      {/* <ul>
        {conflicts.items.map(conflict => (
          <li key={conflict.id} onClick={() => onSelectConflict(conflict.id)} style={{ cursor: 'pointer' }}>
            ID: {conflict.id} - Status: {conflict.status} - Summary: {conflict.involved_entities_summary} - Created: {new Date(conflict.created_at).toLocaleString()}
          </li>
        ))}
      </ul> */}
      <p>List of conflicts will be displayed here.</p>
      <button onClick={() => onSelectConflict(1)}>Select Mock Conflict 1</button>
    </div>
  );
};

export default ConflictListPage;
