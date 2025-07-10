import React from 'react';
// import { useParams } from 'react-router-dom'; // If using react-router

const FactionDetailPage: React.FC = () => {
  // const { guildId, factionId } = useParams<{ guildId: string, factionId: string }>(); // Example with react-router
  const guildId = "123"; // Placeholder
  const factionId = "1"; // Placeholder

  // TODO: Fetch faction details using factionService.getFaction(guildId, factionId)
  // TODO: Implement form for editing faction details
  // TODO: Handle loading and error states

  return (
    <div>
      <h1>Faction Details</h1>
      <p>Details for Faction ID: {factionId} in Guild ID: {guildId}.</p>
      <p>This page will display faction details and provide forms for editing.</p>
      {/* Placeholder for form elements */}
      <form>
        <div>
          <label htmlFor="factionName">Faction Name (en):</label>
          <input type="text" id="factionName" name="factionName" defaultValue="Placeholder Name" />
        </div>
        {/* Add more fields for static_id, description_i18n, etc. */}
        <button type="submit">Save Changes (Placeholder)</button>
      </form>
    </div>
  );
};

export default FactionDetailPage;
