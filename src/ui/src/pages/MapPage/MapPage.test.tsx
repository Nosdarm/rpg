import React from 'react';
import { render, screen } from '@testing-library/react';
import MapPage from './MapPage';

describe('MapPage', () => {
  it('renders map page placeholder', () => {
    render(<MapPage />);
    expect(screen.getByText('Game Map')).toBeInTheDocument();
    expect(screen.getByText(/This page will visualize the game world map/)).toBeInTheDocument();
  });
});
