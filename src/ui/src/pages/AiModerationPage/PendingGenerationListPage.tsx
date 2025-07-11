// src/ui/src/pages/AiModerationPage/PendingGenerationListPage.tsx
import React, { useEffect, useState } from 'react';
import { PaginatedResponse } from '../../types/entities';
import { pendingGenerationService } from '../../services/pendingGenerationService';
import { UIPendingGeneration, UIMRModerationStatus } from '../../types/pending_generation';

interface PendingGenerationListPageProps {
  guildId: number; // Assuming guildId is passed from a parent (e.g., dashboard)
  onSelectPendingItem: (id: number) => void; // Callback to parent when an item is selected
}

const ITEMS_PER_PAGE = 10;

const PendingGenerationListPage: React.FC<PendingGenerationListPageProps> = ({ guildId, onSelectPendingItem }) => {
  const [response, setResponse] = useState<PaginatedResponse<UIPendingGeneration> | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [statusFilter, setStatusFilter] = useState<UIMRModerationStatus | ''>('');

  useEffect(() => {
    const loadPendingGenerations = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await pendingGenerationService.listPendingGenerations(
          guildId,
          statusFilter || undefined,
          currentPage,
          ITEMS_PER_PAGE
        );
        setResponse(data);
      } catch (err: any) {
        setError(`Failed to load pending generations: ${err.message || 'Unknown error'}`);
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    if (guildId) {
      loadPendingGenerations();
    }
  }, [currentPage, statusFilter, guildId]);

  const handleStatusFilterChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    setStatusFilter(event.target.value as UIMRModerationStatus | '');
    setCurrentPage(1);
  };

  const handlePreviousPage = () => {
    if (response && response.current_page > 1) {
      setCurrentPage(response.current_page - 1);
    }
  };

  const handleNextPage = () => {
    if (response && response.current_page < response.total_pages) {
      setCurrentPage(response.current_page + 1);
    }
  };

  const renderPagination = () => {
    if (!response || response.total_pages <= 1) return null;
    return (
      <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        <button onClick={handlePreviousPage} disabled={currentPage === 1 || loading} style={{marginRight: '10px'}}>
          Previous
        </button>
        <span>
          Page {response.current_page} of {response.total_pages} (Total: {response.total_items})
        </span>
        <button onClick={handleNextPage} disabled={currentPage === response.total_pages || loading} style={{marginLeft: '10px'}}>
          Next
        </button>
      </div>
    );
  };

  return (
    <div style={{padding: '10px'}}>
      <div style={{ marginBottom: '15px', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <label htmlFor="status-filter" style={{fontWeight: 'bold'}}>Filter by Status: </label>
        <select
          id="status-filter"
          value={statusFilter}
          onChange={handleStatusFilterChange}
          disabled={loading}
          style={{padding: '8px', borderRadius: '4px', border: '1px solid #ccc'}}
        >
          <option value="">All Statuses</option>
          {Object.values(UIMRModerationStatus).map(status => (
            <option key={status} value={status}>{status.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase())}</option>
          ))}
        </select>
      </div>

      {loading && <p>Loading pending generations...</p>}
      {error && <p style={{ color: 'red' }}>Error: {error}</p>}

      {!loading && !error && (!response || response.items.length === 0) && (
        <p>No pending generations found for the current filter.</p>
      )}

      {!loading && !error && response && response.items.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {response.items.map(item => (
            <li
              key={item.id}
              style={{
                border: '1px solid #eee',
                padding: '15px',
                marginBottom: '10px',
                borderRadius: '5px',
                boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                cursor: 'pointer'
              }}
              onClick={() => onSelectPendingItem(item.id)}
              role="button"
              tabIndex={0}
              onKeyPress={(e) => { if (e.key === 'Enter') onSelectPendingItem(item.id);}}
            >
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                <strong style={{fontSize: '1.1em'}}>ID: {item.id}</strong>
                <span style={{
                  padding: '4px 8px',
                  borderRadius: '12px',
                  fontSize: '0.8em',
                  backgroundColor: item.status === UIMRModerationStatus.PENDING_MODERATION ? '#ffc107' :
                                   item.status === UIMRModerationStatus.APPROVED ? '#28a745' :
                                   item.status === UIMRModerationStatus.SAVED ? '#17a2b8' :
                                   item.status === UIMRModerationStatus.REJECTED ? '#dc3545' :
                                   item.status === UIMRModerationStatus.VALIDATION_FAILED ? '#fd7e14' :
                                   item.status === UIMRModerationStatus.EDITED_PENDING_APPROVAL ? '#6f42c1' : // purple for edited
                                   '#6c757d', // default grey
                  color: 'white'
                }}>
                  {item.status.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase())}
                </span>
              </div>
              <div style={{marginTop: '8px'}}>
                <strong>Type:</strong> {item.trigger_context_json?.requested_entity_type || 'N/A'}
              </div>
              <div style={{fontSize: '0.9em', color: '#555'}}>
                <strong>Created:</strong> {new Date(item.created_at).toLocaleString()}
              </div>
               <div style={{fontSize: '0.9em', color: '#555'}}>
                <strong>Updated:</strong> {new Date(item.updated_at).toLocaleString()}
              </div>
              {item.master_notes && (
                <div style={{fontSize: '0.85em', color: '#333', marginTop: '5px', borderLeft: '3px solid #007bff', paddingLeft: '8px'}}>
                  <strong>Notes:</strong> <em>{item.master_notes}</em>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {renderPagination()}
    </div>
  );
};

export default PendingGenerationListPage;
