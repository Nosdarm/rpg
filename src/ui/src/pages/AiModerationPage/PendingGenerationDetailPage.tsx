// src/ui/src/pages/AiModerationPage/PendingGenerationDetailPage.tsx
import React, { useEffect, useState, useCallback } from 'react';
import { UIPendingGeneration, UIMRModerationStatus, UpdatePendingGenerationPayload } from '../../types/pending_generation';
import { pendingGenerationService } from '../../services/pendingGenerationService';

interface PendingGenerationDetailPageProps {
  pendingId: number | null;
  guildId: number;
  onBackToList: () => void;
  onActionSuccess?: (message: string) => void; // Pass a message for feedback
}

const PendingGenerationDetailPage: React.FC<PendingGenerationDetailPageProps> = ({
  pendingId,
  guildId,
  onBackToList,
  onActionSuccess,
}) => {
  const [item, setItem] = useState<UIPendingGeneration | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [actionInProgress, setActionInProgress] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState<boolean>(false);
  const [editedData, setEditedData] = useState<string>('');
  const [masterNotes, setMasterNotes] = useState<string>('');

  const loadDetails = useCallback(async () => {
    if (!pendingId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await pendingGenerationService.getPendingGenerationById(guildId, pendingId);
      setItem(data);
      setEditedData(JSON.stringify(data.parsed_validated_data_json || {}, null, 2));
      setMasterNotes(data.master_notes || '');
    } catch (err: any) {
      setError(`Failed to load details for item ID ${pendingId}: ${err.message || 'Unknown error'}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [pendingId, guildId]);

  useEffect(() => {
    if (pendingId) {
      loadDetails();
    } else {
      setItem(null);
    }
  }, [pendingId, loadDetails]);

  const handleApprove = async () => {
    if (!item || actionInProgress) return;
    setActionInProgress(true);
    setError(null);
    try {
      await pendingGenerationService.approvePendingGeneration(guildId, item.id);
      onActionSuccess?.('Generation approved and save process initiated!');
      onBackToList();
    } catch (err: any) {
      setError(`Failed to approve generation: ${err.message || 'Unknown error'}`);
      console.error(err);
    } finally {
      setActionInProgress(false);
    }
  };

  const handleUpdate = async (newStatus?: UIMRModerationStatus) => {
    if (!item || actionInProgress) return;
    setActionInProgress(true);
    setError(null);

    let parsedEditedData: Record<string, any> | null = item.parsed_validated_data_json; // Keep original if not in edit mode or error
    if (editMode) {
      try {
        if (editedData.trim() === "") { // Handle empty textarea as null or empty object
            parsedEditedData = null;
        } else {
            parsedEditedData = JSON.parse(editedData);
        }
      } catch (jsonError: any) {
        setError(`Invalid JSON format for edited data: ${jsonError.message}`);
        setActionInProgress(false);
        return;
      }
    }

    const payload: UpdatePendingGenerationPayload = {
      master_notes: masterNotes.trim() === "" ? null : masterNotes, // Send null if notes are empty
    };

    if (newStatus) {
      payload.new_status = newStatus;
    }

    // Only include new_parsed_data_json if it was actually edited or intended to be cleared
    if (editMode) {
      payload.new_parsed_data_json = parsedEditedData;
      // If data is edited and no explicit newStatus is REJECTED, it becomes EDITED_PENDING_APPROVAL
      if (newStatus !== UIMRModerationStatus.REJECTED) {
        payload.new_status = UIMRModerationStatus.EDITED_PENDING_APPROVAL;
      }
    }

    try {
      const updatedItem = await pendingGenerationService.updatePendingGeneration(guildId, item.id, payload);
      setItem(updatedItem); // Refresh local state with response from service
      setEditedData(JSON.stringify(updatedItem.parsed_validated_data_json || {}, null, 2));
      setMasterNotes(updatedItem.master_notes || '');
      setEditMode(false);
      onActionSuccess?.('Generation updated successfully!');
    } catch (err: any) {
      setError(`Failed to update generation: ${err.message || 'Unknown error'}`);
      console.error(err);
    } finally {
      setActionInProgress(false);
    }
  };

  if (!pendingId) {
    // This state should ideally be handled by the parent component (AiModerationDashboardPage)
    // by not rendering this detail page if no pendingId is selected.
    return <p>Select an item from the list to see details.</p>;
  }
  if (loading) return <p>Loading details for item ID {pendingId}...</p>;
  if (error && !item) return <p style={{ color: 'red' }}>Error: {error}</p>; // Show general error if item failed to load
  if (!item) return <p>Pending generation item ID {pendingId} not found.</p>;

  const canApprove = item.status === UIMRModerationStatus.PENDING_MODERATION ||
                     item.status === UIMRModerationStatus.EDITED_PENDING_APPROVAL ||
                     item.status === UIMRModerationStatus.VALIDATION_FAILED;

  return (
    <div style={{border: '1px solid #ccc', padding: '20px', borderRadius: '8px', backgroundColor: '#f9f9f9'}}>
      <button onClick={onBackToList} style={{ marginBottom: '20px' }}>&larr; Back to List</button>
      <h2>Details for Pending Generation ID: {item.id}</h2>
      {error && <p style={{ color: 'red' }}>Error: {error}</p>}

      <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '10px 20px'}}>
        <p><strong>Status:</strong></p><p>{item.status.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase())}</p>
        <p><strong>Requested Type:</strong></p><p>{item.trigger_context_json?.requested_entity_type || 'N/A'}</p>
        <p><strong>Created At:</strong></p><p>{new Date(item.created_at).toLocaleString()}</p>
        <p><strong>Updated At:</strong></p><p>{new Date(item.updated_at).toLocaleString()}</p>
        {item.triggered_by_user_id && (<><p><strong>Triggered By User ID:</strong></p><p>{item.triggered_by_user_id}</p></>)}
        {item.master_id && (<><p><strong>Moderated By Master ID:</strong></p><p>{item.master_id}</p></>)}
      </div>

      <CollapsibleSection title="AI Prompt:">
        <pre>{item.ai_prompt_text || 'N/A'}</pre>
      </CollapsibleSection>

      <CollapsibleSection title="Raw AI Response:">
        <pre>{item.raw_ai_response_text || 'N/A'}</pre>
      </CollapsibleSection>

      <CollapsibleSection title="Parsed/Validated Data:" initiallyOpen={true}>
        {editMode ? (
          <textarea
            value={editedData}
            onChange={(e) => setEditedData(e.target.value)}
            rows={15}
            style={{ width: '98%', fontFamily: 'monospace', border: '1px solid #ccc', padding: '5px' }}
            disabled={actionInProgress}
          />
        ) : (
          <pre>{JSON.stringify(item.parsed_validated_data_json || {}, null, 2)}</pre>
        )}
        <button onClick={() => setEditMode(!editMode)} disabled={actionInProgress} style={{ marginTop: '5px' }}>
          {editMode ? 'Cancel Edit' : 'Edit Parsed Data'}
        </button>
      </CollapsibleSection>

      <CollapsibleSection title="Validation Issues:">
        <pre>{item.validation_issues_json ? JSON.stringify(item.validation_issues_json, null, 2) : 'No issues reported.'}</pre>
      </CollapsibleSection>

      <div>
        <h3>Master Notes:</h3>
        <textarea
          value={masterNotes}
          onChange={(e) => setMasterNotes(e.target.value)}
          rows={4}
          style={{ width: '98%', border: '1px solid #ccc', padding: '5px' }}
          placeholder="Enter moderation notes here..."
          disabled={actionInProgress}
        />
      </div>

      <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: '1px solid #ddd', display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
        <button
          onClick={handleApprove}
          disabled={actionInProgress || !canApprove}
          style={{ backgroundColor: canApprove ? 'lightgreen' : '#e0e0e0', padding: '10px 15px' }}
        >
          Approve
        </button>
        <button
          onClick={() => handleUpdate(UIMRModerationStatus.REJECTED)}
          disabled={actionInProgress || item.status === UIMRModerationStatus.REJECTED}
          style={{ backgroundColor: item.status !== UIMRModerationStatus.REJECTED ? 'lightcoral' : '#e0e0e0', padding: '10px 15px' }}
        >
          Reject
        </button>
        <button
          onClick={() => handleUpdate()} // Will save notes and/or edited data
          disabled={actionInProgress}
          style={{ backgroundColor: 'lightgoldenrodyellow', padding: '10px 15px' }}
        >
          {editMode ? 'Save Edits & Notes' : 'Save Notes'}
        </button>
      </div>
    </div>
  );
};

// Simple Collapsible Section HOC or Component
const CollapsibleSection: React.FC<{ title: string, children: React.ReactNode, initiallyOpen?: boolean }> = ({ title, children, initiallyOpen = false }) => {
  const [isOpen, setIsOpen] = useState(initiallyOpen);
  return (
    <div style={{ margin: '15px 0', border: '1px solid #e0e0e0', borderRadius: '4px' }}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{ width: '100%', textAlign: 'left', padding: '10px', background: '#f7f7f7', border: 'none', borderBottom: isOpen ? '1px solid #e0e0e0' : 'none', cursor: 'pointer', fontWeight: 'bold' }}
      >
        {isOpen ? '▼' : '►'} {title}
      </button>
      {isOpen && <div style={{ padding: '10px', whiteSpace: 'pre-wrap', wordBreak: 'break-all', background: 'white', maxHeight: '300px', overflowY: 'auto' }}>{children}</div>}
    </div>
  )
}

export default PendingGenerationDetailPage;
