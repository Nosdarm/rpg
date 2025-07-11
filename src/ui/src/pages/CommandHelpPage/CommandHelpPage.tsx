// src/ui/src/pages/CommandHelpPage/CommandHelpPage.tsx
import React, { useEffect, useState } from 'react';
import { fetchCommandList } from '../../services/commandListService';
import { UICommandInfo, UICommandListResponse } from '../../types/commands';

const CommandHelpPage: React.FC = () => {
  const [commandResponse, setCommandResponse] = useState<UICommandListResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedLanguage, setSelectedLanguage] = useState<string>('en'); // Default language

  useEffect(() => {
    const loadCommands = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await fetchCommandList(selectedLanguage);
        setCommandResponse(data);
      } catch (err) {
        setError('Failed to load commands.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    loadCommands();
  }, [selectedLanguage]);

  const handleLanguageChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    setSelectedLanguage(event.target.value);
  };

  if (loading) {
    return <div>Loading commands...</div>;
  }

  if (error) {
    return <div style={{ color: 'red' }}>Error: {error}</div>;
  }

  if (!commandResponse || commandResponse.commands.length === 0) {
    return <div>No commands available. (Language: {commandResponse?.language_code || selectedLanguage})</div>;
  }

  return (
    <div style={{ padding: '20px' }}>
      <h1>Bot Command List</h1>
      <div>
        <label htmlFor="language-select">Select Language: </label>
        <select id="language-select" value={selectedLanguage} onChange={handleLanguageChange}>
          <option value="en">English (en)</option>
          <option value="ru">Русский (ru)</option>
          {/* Add other supported languages here */}
        </select>
        <p><small>Displaying commands for language: {commandResponse.language_code}</small></p>
      </div>
      <hr />
      {commandResponse.commands.map((command: UICommandInfo) => (
        <div key={command.name} style={{ marginBottom: '20px', padding: '10px', border: '1px solid #ccc' }}>
          <h2>/{command.name}</h2>
          <p>{command.description || 'No description provided.'}</p>
          {command.parameters && command.parameters.length > 0 && (
            <div>
              <strong>Parameters:</strong>
              <ul style={{ listStyleType: 'none', paddingLeft: '20px' }}>
                {command.parameters.map(param => (
                  <li key={param.name} style={{ marginTop: '5px' }}>
                    <code>{param.name}</code> ({param.type}){param.required ? <span style={{ color: 'red' }}>*</span> : ''}
                    <p style={{ margin: '2px 0 0 10px', fontSize: '0.9em' }}>
                      {param.description || 'No parameter description.'}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

export default CommandHelpPage;
