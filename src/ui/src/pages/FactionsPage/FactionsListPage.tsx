import React, { useEffect, useState } from 'react';
// import { factionService } from '../../services/factionService';
// import type { Faction, PaginatedResponse } from '../../types/faction';

const FactionsListPage: React.FC = () => {
  // const [factionsResponse, setFactionsResponse] = useState<PaginatedResponse<Faction> | null>(null);
  // const [loading, setLoading] = useState<boolean>(true);
  // const [error, setError] = useState<string | null>(null);
  // const [currentPage, setCurrentPage] = useState<number>(1);
  const guildId = "123"; // Placeholder

  // useEffect(() => {
  //   const fetchFactions = async () => {
  //     try {
  //       setLoading(true);
  //       setError(null);
  //       // const response = await factionService.getFactions(guildId, currentPage);
  //       // setFactionsResponse(response);
  //     } catch (err) {
  //       setError((err as Error).message);
  //     } finally {
  //       setLoading(false);
  //     }
  //   };
  //   fetchFactions();
  // }, [guildId, currentPage]);

  // if (loading) return <div>Loading factions...</div>;
  // if (error) return <div>Error fetching factions: {error}</div>;
  // if (!factionsResponse || factionsResponse.items.length === 0) return <div>No factions found.</div>;

  return (
    <div>
      <h1>Factions</h1>
      <p>Faction list placeholder for Guild ID: {guildId}. Real implementation will show a list of factions.</p>
      {/*
      TODO: Implement actual list rendering, pagination controls, link to detail page, create button
      <ul>
        {factionsResponse.items.map(faction => (
          <li key={faction.id}>
            {faction.name_i18n.en || faction.static_id} (ID: {faction.id})
            {/* <Link to={`/guilds/${guildId}/factions/${faction.id}`}>View</Link> * /}
          </li>
        ))}
      </ul>
      <div>
        <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage === 1}>Previous</button>
        <span>Page {factionsResponse.page} of {Math.ceil(factionsResponse.total / factionsResponse.limit)}</span>
        <button onClick={() => setCurrentPage(p => p + 1)} disabled={currentPage * factionsResponse.limit >= factionsResponse.total}>Next</button>
      </div>
       */}
    </div>
  );
};

export default FactionsListPage;
