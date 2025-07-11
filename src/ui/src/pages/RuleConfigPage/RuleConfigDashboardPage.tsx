import React, { useState, useCallback } from 'react';
import RuleConfigListPage from './RuleConfigListPage';
import RuleConfigForm from './RuleConfigForm';

// A simple notification component (could be replaced by a more robust library like react-toastify)
const Notification: React.FC<{ message: string; type: 'success' | 'error'; onClose: () => void }> = ({ message, type, onClose }) => {
  if (!message) return null;
  return (
    <div
      style={{
        padding: '10px',
        margin: '10px 0',
        backgroundColor: type === 'success' ? 'lightgreen' : 'lightcoral',
        border: `1px solid ${type === 'success' ? 'green' : 'red'}`,
        borderRadius: '4px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}
    >
      <span>{message}</span>
      <button onClick={onClose} style={{ marginLeft: '10px', background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}>
        &times;
      </button>
    </div>
  );
};


const RuleConfigDashboardPage: React.FC = () => {
  const [view, setView] = useState<'list' | 'form'>('list');
  const [editingRuleKey, setEditingRuleKey] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  // TODO: Replace with actual guildId from context or props
  const guildId = "123456789"; // Placeholder

  const showNotification = useCallback((message: string, type: 'success' | 'error' = 'success') => {
    setNotification({ message, type });
    setTimeout(() => {
      setNotification(null);
    }, 5000); // Auto-dismiss after 5 seconds
  }, []);

  const handleCreateRule = () => {
    setEditingRuleKey(null);
    setView('form');
  };

  const handleEditRule = (ruleKey: string) => {
    setEditingRuleKey(ruleKey);
    setView('form');
  };

  const handleFormSubmitSuccess = () => {
    setView('list');
    // Notification is handled by the form itself using the notify prop
  };

  const handleCancelForm = () => {
    setView('list');
    setEditingRuleKey(null);
  };

  const closeNotification = () => {
    setNotification(null);
  };

  return (
    <div style={{ padding: '20px' }}>
      <h1>RuleConfig Management</h1>
      {notification && (
        <Notification message={notification.message} type={notification.type} onClose={closeNotification} />
      )}

      {view === 'list' && (
        <RuleConfigListPage
          guildId={guildId}
          onCreateRule={handleCreateRule}
          onEditRule={handleEditRule}
          notify={showNotification}
        />
      )}

      {view === 'form' && (
        <RuleConfigForm
          guildId={guildId}
          ruleKeyToEdit={editingRuleKey}
          onFormSubmitSuccess={handleFormSubmitSuccess}
          onCancel={handleCancelForm}
          notify={showNotification}
        />
      )}
    </div>
  );
};

export default RuleConfigDashboardPage;
