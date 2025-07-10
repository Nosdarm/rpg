import React from 'react';
import { render, screen } from '@testing-library/react';
import NpcListPage from './NpcListPage';

describe('NpcListPage', () => {
  it('renders page title', () => {
    render(<NpcListPage />);
    expect(screen.getByText(/NPC List Page/i)).toBeInTheDocument();
  });
});
