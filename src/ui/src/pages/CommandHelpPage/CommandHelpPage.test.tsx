// src/ui/src/pages/CommandHelpPage/CommandHelpPage.test.tsx
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import CommandHelpPage from './CommandHelpPage';
import * as commandListService from '../../services/commandListService'; // Import all as module
import { UICommandListResponse } from '../../types/commands';

// Mock the service
jest.mock('../../services/commandListService');
const mockFetchCommandList = commandListService.fetchCommandList as jest.MockedFunction<typeof commandListService.fetchCommandList>;

describe('CommandHelpPage', () => {
  beforeEach(() => {
    mockFetchCommandList.mockReset();
  });

  test('renders loading state initially', () => {
    mockFetchCommandList.mockReturnValue(new Promise(() => {})); // unresolved promise
    render(<CommandHelpPage />);
    expect(screen.getByText('Loading commands...')).toBeInTheDocument();
  });

  test('renders error state if fetching commands fails', async () => {
    mockFetchCommandList.mockRejectedValue(new Error('Failed to fetch'));
    render(<CommandHelpPage />);
    await waitFor(() => {
      expect(screen.getByText('Error: Failed to load commands.')).toBeInTheDocument();
    });
  });

  test('renders "No commands available" if command list is empty', async () => {
    const mockEmptyResponse: UICommandListResponse = { commands: [], language_code: 'en' };
    mockFetchCommandList.mockResolvedValue(mockEmptyResponse);
    render(<CommandHelpPage />);
    await waitFor(() => {
      expect(screen.getByText('No commands available. (Language: en)')).toBeInTheDocument();
    });
  });

  test('renders command list successfully', async () => {
    const mockResponse: UICommandListResponse = {
      commands: [
        { name: 'ping', description: 'Ping pong!', parameters: [] },
        {
          name: 'greet',
          description: 'Greets a user.',
          parameters: [{ name: 'user', type: 'User', required: true, description: 'User to greet' }]
        },
      ],
      language_code: 'en',
    };
    mockFetchCommandList.mockResolvedValue(mockResponse);
    render(<CommandHelpPage />);

    await waitFor(() => {
      expect(screen.getByText('/ping')).toBeInTheDocument();
      expect(screen.getByText('Ping pong!')).toBeInTheDocument();
      expect(screen.getByText('/greet')).toBeInTheDocument();
      expect(screen.getByText('Greets a user.')).toBeInTheDocument();
      expect(screen.getByText('user')).toBeInTheDocument(); // Parameter name
      // expect(screen.getByText('(User)')).toBeInTheDocument(); // Parameter type, might need more specific query
      // To find '(User)' specifically associated with the parameter:
      const userParamDisplay = screen.getByText((content, element) => {
        return element?.tagName.toLowerCase() === 'code' && content === 'user';
      });
      // Assuming type is displayed next to or near it. This is a bit fragile.
      // A better way would be to have more specific data-testid attributes in the component.
      expect(userParamDisplay.nextSibling?.textContent?.includes('(User)')).toBeTruthy();
    });
  });

  test('refetches commands when language changes', async () => {
    const mockEnResponse: UICommandListResponse = {
      commands: [{ name: 'help_en', description: 'English help', parameters: [] }],
      language_code: 'en',
    };
    const mockRuResponse: UICommandListResponse = {
      commands: [{ name: 'help_ru', description: 'Russian help', parameters: [] }],
      language_code: 'ru',
    };

    mockFetchCommandList.mockResolvedValueOnce(mockEnResponse); // First call
    render(<CommandHelpPage />);

    await waitFor(() => {
      expect(screen.getByText('/help_en')).toBeInTheDocument();
    });

    mockFetchCommandList.mockResolvedValueOnce(mockRuResponse); // Second call for 'ru'
    const selectElement = screen.getByLabelText('Select Language:');
    fireEvent.change(selectElement, { target: { value: 'ru' } });

    await waitFor(() => {
      // Check if the old command is gone and new one is present
      expect(screen.queryByText('/help_en')).not.toBeInTheDocument();
      expect(screen.getByText('/help_ru')).toBeInTheDocument();
      expect(screen.getByText('Displaying commands for language: ru')).toBeInTheDocument();
    });
    expect(mockFetchCommandList).toHaveBeenCalledTimes(2); // Initial + change
    expect(mockFetchCommandList).toHaveBeenNthCalledWith(1, 'en');
    expect(mockFetchCommandList).toHaveBeenNthCalledWith(2, 'ru');
  });
});
