import React from 'react';
// import { relationshipService } from '../../services/relationshipService';
// import type { RelationshipData, PaginatedResponse } from '../../types/relationship';

const RelationshipsListPage: React.FC = () => {
  const guildId = "123"; // Placeholder

  // TODO: Fetch relationships using relationshipService.getRelationships(guildId, filters, page)
  // TODO: Implement filtering UI
  // TODO: Implement list rendering, pagination, link to detail/edit, create button
  // TODO: Handle loading and error states

  return (
    <div>
      <h1>Relationships</h1>
      <p>Relationship list placeholder for Guild ID: {guildId}.</p>
      <p>This page will display a list of relationships with filtering options.</p>
      {/*
      Placeholder for filters:
      <input type="text" placeholder="Entity 1 ID" />
      <input type="text" placeholder="Entity 1 Type" />
      ...
      */}
      {/* Placeholder for list */}
      <ul>
        <li>Player 1 (Friendly) Faction Alpha - View/Edit</li>
        <li>Faction Alpha (Hostile) Faction Beta - View/Edit</li>
      </ul>
    </div>
  );
};

export default RelationshipsListPage;
