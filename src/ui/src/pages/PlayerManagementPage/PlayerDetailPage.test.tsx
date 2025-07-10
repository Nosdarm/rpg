import React from 'react';
import { render, screen } from '@testing-library/react';
import PlayerDetailPage from './PlayerDetailPage';

describe('PlayerDetailPage', () => {
  it('renders page title', () => {
    render(<PlayerDetailPage />);
    expect(screen.getByText(/Player Detail Page/i)).toBeInTheDocument();
  });
});
