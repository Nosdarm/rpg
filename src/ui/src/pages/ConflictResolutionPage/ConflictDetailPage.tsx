import React, { useEffect, useState } from 'react';
// import { getConflictDetails, resolveConflict, getConflictResolutionOutcomeOptions } from '../../services/conflictService';
// import { UIConflictDetails, UIMasterOutcomeOption, UIResolveConflictPayload, UIConflictStatus } from '../../types/conflict';

interface ConflictDetailPageProps {
  conflictId: number;
  guildId: string; // Assuming guildId is passed as a prop or from context
  onConflictResolved?: () => void; // Optional: Callback to refresh list or notify parent
}

const ConflictDetailPage: React.FC<ConflictDetailPageProps> = ({ conflictId, guildId, onConflictResolved }) => {
  // const [conflict, setConflict] = useState<UIConflictDetails | null>(null);
  // const [loading, setLoading] = useState<boolean>(true);
  // const [error, setError] = useState<string | null>(null);
  // const [resolutionOptions, setResolutionOptions] = useState<UIMasterOutcomeOption[]>([]);
  // const [selectedOutcome, setSelectedOutcome] = useState<string>('');
  // const [resolutionNotes, setResolutionNotes] = useState<string>('');
  // const [isResolving, setIsResolving] = useState<boolean>(false);

  useEffect(() => {
    // const fetchDetails = async () => {
    //   setLoading(true);
    //   setError(null);
    //   try {
    //     // const details = await getConflictDetails(guildId, conflictId);
    //     // setConflict(details);
    //     // if (details.status === UIConflictStatus.PENDING_MASTER_RESOLUTION) {
    //     //   const options = await getConflictResolutionOutcomeOptions(guildId);
    //     //   setResolutionOptions(options);
    //     //   if (options.length > 0) setSelectedOutcome(options[0].id);
    //     // }
    //   } catch (err) {
    //     // setError(`Failed to fetch conflict details for ID ${conflictId}.`);
    //     // console.error(err);
    //   } finally {
    //     // setLoading(false);
    //   }
    // };
    // fetchDetails();
    console.log('Mock: Fetching conflict details for guild:', guildId, 'conflict ID:', conflictId);
  }, [guildId, conflictId]);

  // const handleResolve = async () => {
  //   if (!selectedOutcome) {
  //     alert('Please select a resolution outcome.');
  //     return;
  //   }
  //   setIsResolving(true);
  //   setError(null);
  //   try {
  //     const payload: UIResolveConflictPayload = {
  //       outcome_status: selectedOutcome,
  //       notes: resolutionNotes,
  //     };
  //     // const result = await resolveConflict(guildId, conflictId, payload);
  //     // if (result.success) {
  //     //   alert(`Conflict resolved successfully: ${result.message}`);
  //     //   onConflictResolved?.(); // Notify parent to refresh or update
  //         // Re-fetch details to show updated status (or parent handles this)
  //     // } else {
  //     //   setError(result.message || 'Failed to resolve conflict.');
  //     // }
  //   } catch (err) {
  //     // setError('An error occurred while resolving the conflict.');
  //     // console.error(err);
  //   } finally {
  //     // setIsResolving(false);
  //   }
  // };

  // if (loading) return <p>Loading conflict details...</p>;
  // if (error) return <p style={{ color: 'red' }}>{error}</p>;
  // if (!conflict) return <p>No conflict data available.</p>;

  return (
    <div>
      <h3>Conflict Details (ID: {conflictId})</h3>
      {/* <pre>{JSON.stringify(conflict, null, 2)}</pre> */}
      <p>Status: Mock Status</p>
      <p>Created At: {new Date().toLocaleString()}</p>
      <p>Involved Entities: Mock summary</p>
      <p>Conflicting Actions: Mock summary</p>

      {/* {conflict.status === UIConflictStatus.PENDING_MASTER_RESOLUTION && (
        <div>
          <h4>Resolve Conflict</h4>
          <div>
            <label htmlFor="resolutionOutcome">Outcome:</label>
            <select
              id="resolutionOutcome"
              value={selectedOutcome}
              onChange={(e) => setSelectedOutcome(e.target.value)}
              disabled={isResolving}
            >
              {resolutionOptions.map(opt => (
                <option key={opt.id} value={opt.id}>{opt.name_key}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="resolutionNotes">Notes:</label>
            <textarea
              id="resolutionNotes"
              value={resolutionNotes}
              onChange={(e) => setResolutionNotes(e.target.value)}
              disabled={isResolving}
              rows={3}
            />
          </div>
          <button onClick={handleResolve} disabled={isResolving}>
            {isResolving ? 'Resolving...' : 'Resolve Conflict'}
          </button>
        </div>
      )}
      {conflict.status !== UIConflictStatus.PENDING_MASTER_RESOLUTION && (
        <div>
          <p><strong>Resolution Notes:</strong> {conflict.resolution_notes || 'N/A'}</p>
          {conflict.resolved_action && <pre>Resolved Action: {JSON.stringify(conflict.resolved_action, null, 2)}</pre>}
          {conflict.resolved_at && <p><strong>Resolved At:</strong> {new Date(conflict.resolved_at).toLocaleString()}</p>}
        </div>
      )} */}
      <p>Resolution form/details will be displayed here.</p>
    </div>
  );
};

export default ConflictDetailPage;
