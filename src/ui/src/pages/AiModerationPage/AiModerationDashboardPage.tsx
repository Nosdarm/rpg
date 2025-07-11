// src/ui/src/pages/AiModerationPage/AiModerationDashboardPage.tsx
import React, { useState, useCallback } from 'react';
import TriggerAiGenerationForm from './TriggerAiGenerationForm';
import PendingGenerationListPage from './PendingGenerationListPage';
import PendingGenerationDetailPage from './PendingGenerationDetailPage';
import { UIPendingGeneration } from '../../types/pending_generation';

type ActiveView = 'list' | 'detail' | 'trigger';

const AiModerationDashboardPage: React.FC = () => {
  const [activeView, setActiveView] = useState<ActiveView>('list');
  const [selectedPendingId, setSelectedPendingId] = useState<number | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);

  // Предполагаем, что guildId будет получен из контекста или глобального состояния UI
  // Для примера используем моковое значение
  const guildId = 1;

  const handleSelectPendingItem = useCallback((id: number) => {
    setSelectedPendingId(id);
    setActiveView('detail');
    setFeedbackMessage(null); // Clear previous messages
  }, []);

  const handleBackToList = useCallback(() => {
    setSelectedPendingId(null);
    setActiveView('list');
    // Feedback message might be set by child components upon successful action
  }, []);

  const handleActionSuccess = useCallback((message: string) => {
    setFeedbackMessage(message);
    // Optionally, could also refresh the list or specific item here
    // For now, just show message and user will go back to list to see changes
  }, []);

  const handleGenerationTriggered = (response: UIPendingGeneration) => {
    setFeedbackMessage(`Successfully triggered generation ID: ${response.id}. It's now ${response.status}.`);
    // Optionally switch to list view or clear form etc.
    // For now, just show message.
  };


  const renderActiveView = () => {
    switch (activeView) {
      case 'trigger':
        return <TriggerAiGenerationForm guildId={guildId} onGenerationTriggered={handleGenerationTriggered} />;
      case 'detail':
        return (
          <PendingGenerationDetailPage
            pendingId={selectedPendingId}
            guildId={guildId}
            onBackToList={handleBackToList}
            onActionSuccess={handleActionSuccess}
          />
        );
      case 'list':
      default:
        return (
          <PendingGenerationListPage
            guildId={guildId}
            onSelectPendingItem={handleSelectPendingItem}
          />
        );
    }
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      <header style={{ marginBottom: '20px', borderBottom: '1px solid #eee', paddingBottom: '10px' }}>
        <h1 style={{ margin: 0 }}>AI Generation & Moderation Dashboard</h1>
      </header>

      <nav style={{ marginBottom: '20px', display: 'flex', gap: '10px' }}>
        <button
          onClick={() => { setActiveView('list'); setSelectedPendingId(null); setFeedbackMessage(null); }}
          style={{ padding: '10px 15px', cursor: 'pointer', border: '1px solid #ccc', borderRadius: '4px', background: activeView === 'list' ? '#e0e0e0' : 'white' }}
        >
          Moderation List
        </button>
        <button
          onClick={() => { setActiveView('trigger'); setSelectedPendingId(null); setFeedbackMessage(null); }}
          style={{ padding: '10px 15px', cursor: 'pointer', border: '1px solid #ccc', borderRadius: '4px', background: activeView === 'trigger' ? '#e0e0e0' : 'white' }}
        >
          Trigger New Generation
        </button>
      </nav>

      {feedbackMessage && (
        <div style={{ padding: '10px', marginBottom: '15px', backgroundColor: 'lightgreen', border: '1px solid green', borderRadius: '4px' }}>
          {feedbackMessage}
        </div>
      )}

      <div style={{ marginTop: '20px', border: '1px solid #ddd', borderRadius: '8px', padding: '20px', background: '#fff' }}>
        {renderActiveView()}
      </div>
    </div>
  );
};

export default AiModerationDashboardPage;
