import React, { useState, useEffect, useCallback } from 'react';
import { ruleConfigService } from 'src/services/ruleConfigService';
import type { RuleConfigEntry } from 'src/types/ruleconfig';
import type { PaginatedResponse } from 'src/types/entities';

interface RuleConfigListPageProps {
  guildId: string;
  onEditRule: (ruleKey: string) => void;
  onCreateRule: () => void;
  notify: (message: string, type?: 'success' | 'error') => void;
}

const RuleConfigListPage: React.FC<RuleConfigListPageProps> = ({ guildId, onEditRule, onCreateRule, notify }) => {
  const [rulesResponse, setRulesResponse] = useState<PaginatedResponse<RuleConfigEntry> | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [limitPerPage, setLimitPerPage] = useState(10); // Can be made configurable
  const [prefixFilter, setPrefixFilter] = useState('');
  const [appliedPrefixFilter, setAppliedPrefixFilter] = useState('');

  const fetchRules = useCallback(async (page: number, prefix: string) => {
    if (!guildId) return;
    setIsLoading(true);
    setError(null);
    try {
      // Backend doesn't support prefix filter directly on list, so we fetch all for the page
      // and then filter client-side if a prefix is applied. This is not ideal for large datasets.
      // A better approach would be API gateway or backend support for prefix filtering.
      const response = await ruleConfigService.listRuleConfigEntries(guildId, undefined, page, limitPerPage);

      if (prefix) {
        const filteredItems = response.items.filter(rule => rule.key.startsWith(prefix));
        setRulesResponse({ ...response, items: filteredItems }); // Note: pagination data might be skewed by client-side filter
      } else {
        setRulesResponse(response);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch rules';
      setError(errorMessage);
      notify(errorMessage, 'error');
    } finally {
      setIsLoading(false);
    }
  }, [guildId, limitPerPage, notify]);

  useEffect(() => {
    fetchRules(currentPage, appliedPrefixFilter);
  }, [fetchRules, currentPage, appliedPrefixFilter]);

  const handleDeleteRule = async (ruleKey: string) => {
    if (!guildId) return;
    if (window.confirm(`Are you sure you want to delete the rule "${ruleKey}"?`)) {
      try {
        await ruleConfigService.deleteRuleConfigEntry(guildId, ruleKey);
        notify(`Rule "${ruleKey}" deleted successfully.`, 'success');
        fetchRules(currentPage, appliedPrefixFilter); // Refresh list
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to delete rule';
        setError(errorMessage); // Also display error locally if needed
        notify(errorMessage, 'error');
      }
    }
  };

  const handleFilterSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1); // Reset to first page on new filter
    setAppliedPrefixFilter(prefixFilter);
  };

  const handlePageChange = (newPage: number) => {
    if (newPage > 0 && (!rulesResponse || newPage <= rulesResponse.total_pages)) {
      setCurrentPage(newPage);
    }
  };

  if (isLoading) return <p>Loading rules...</p>;
  if (error && !rulesResponse) return <p>Error fetching rules: {error}</p>; // Show general error if list fails completely

  return (
    <div>
      <h2>RuleConfig List</h2>
      <button type="button" onClick={onCreateRule} style={{ marginBottom: '10px' }}>
        Add New Rule
      </button>

      <form onSubmit={handleFilterSubmit} style={{ marginBottom: '10px' }}>
        <input
          type="text"
          placeholder="Filter by key prefix..."
          value={prefixFilter}
          onChange={(e) => setPrefixFilter(e.target.value)}
        />
        <button type="submit">Filter</button>
        <button type="button" onClick={() => { setPrefixFilter(''); setAppliedPrefixFilter(''); setCurrentPage(1);}}>Clear Filter</button>
      </form>

      {error && <p style={{color: 'red'}}>Error: {error}</p>} {/* Display error for specific actions like delete */}

      {rulesResponse && rulesResponse.items.length > 0 ? (
        <>
          <table border={1} style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th>Key</th>
                <th>Value (JSON Preview)</th>
                <th>Description</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rulesResponse.items.map((rule) => (
                <tr key={rule.key}>
                  <td>{rule.key}</td>
                  <td>
                    <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: '100px', overflowY: 'auto' }}>
                      {typeof rule.value_json === 'string' ? rule.value_json : JSON.stringify(rule.value_json, null, 2)}
                    </pre>
                  </td>
                  <td>{rule.description || 'N/A'}</td>
                  <td>
                    <button type="button" onClick={() => onEditRule(rule.key)} style={{ marginRight: '5px' }}>Edit</button>
                    <button type="button" onClick={() => handleDeleteRule(rule.key)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination Controls */}
          <div style={{ marginTop: '10px' }}>
            <span>
              Page {rulesResponse.current_page} of {rulesResponse.total_pages} (Total items: {rulesResponse.total_items})
            </span>
            <button
              onClick={() => handlePageChange(currentPage - 1)}
              disabled={currentPage === 1}
              style={{ marginLeft: '10px' }}
            >
              Previous
            </button>
            <button
              onClick={() => handlePageChange(currentPage + 1)}
              disabled={currentPage === rulesResponse.total_pages || rulesResponse.items.length < limitPerPage}
            >
              Next
            </button>
             <select value={limitPerPage} onChange={(e) => { setLimitPerPage(Number(e.target.value)); setCurrentPage(1); }}>
                <option value={5}>5 per page</option>
                <option value={10}>10 per page</option>
                <option value={20}>20 per page</option>
              </select>
          </div>
        </>
      ) : (
        <p>No rules found{appliedPrefixFilter ? ` for prefix "${appliedPrefixFilter}"` : ''}.</p>
      )}
    </div>
  );
};

export default RuleConfigListPage;
