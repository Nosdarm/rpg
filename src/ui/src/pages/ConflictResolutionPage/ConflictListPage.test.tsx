import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ConflictListPage from './ConflictListPage';

describe('ConflictListPage', () => {
  const mockOnSelectConflict = jest.fn();
  const mockGuildId = "guild123";

  beforeEach(() => {
    mockOnSelectConflict.mockClear();
  });

  it('renders the heading', () => {
    render(<ConflictListPage guildId={mockGuildId} onSelectConflict={mockOnSelectConflict} />);
    expect(screen.getByText('Pending Conflicts')).toBeInTheDocument();
  });

  it('renders placeholder text and a mock button', () => {
    render(<ConflictListPage guildId={mockGuildId} onSelectConflict={mockOnSelectConflict} />);
    expect(screen.getByText('List of conflicts will be displayed here.')).toBeInTheDocument();
    expect(screen.getByText('Select Mock Conflict 1')).toBeInTheDocument();
  });

  it('calls onSelectConflict with conflict ID when mock button is clicked', () => {
    render(<ConflictListPage guildId={mockGuildId} onSelectConflict={mockOnSelectConflict} />);
    fireEvent.click(screen.getByText('Select Mock Conflict 1'));
    expect(mockOnSelectConflict).toHaveBeenCalledWith(1);
  });

  // Add more tests here when actual data fetching and rendering is implemented
  // e.g., test for loading state, error state, rendering of list items
});
