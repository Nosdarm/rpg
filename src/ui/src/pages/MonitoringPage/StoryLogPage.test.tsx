import React from 'react';
import { render, screen } from '@testing-library/react';
import StoryLogPage from './StoryLogPage';

describe('StoryLogPage', () => {
  it('renders story log page placeholder', () => {
    render(<StoryLogPage />);
    expect(screen.getByText('Story Log')).toBeInTheDocument();
    expect(screen.getByText(/This page will display filterable and paginated game event logs/)).toBeInTheDocument();
  });
});
