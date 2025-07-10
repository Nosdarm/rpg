import React from 'react';
import { render, screen } from '@testing-library/react';
import NpcDetailPage from './NpcDetailPage';

describe('NpcDetailPage', () => {
  it('renders page title', () => {
    render(<NpcDetailPage />);
    expect(screen.getByText(/NPC Detail Page/i)).toBeInTheDocument();
  });
});
