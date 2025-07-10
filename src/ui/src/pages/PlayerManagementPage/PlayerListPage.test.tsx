import React from 'react';
import { render, screen } from '@testing-library/react';
import PlayerListPage from './PlayerListPage';

describe('PlayerListPage', () => {
  it('renders page title', () => {
    render(<PlayerListPage />);
    expect(screen.getByText(/Player List Page/i)).toBeInTheDocument();
  });
});
