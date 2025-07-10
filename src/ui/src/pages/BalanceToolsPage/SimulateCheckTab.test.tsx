// src/ui/src/pages/BalanceToolsPage/SimulateCheckTab.test.tsx
import { render, screen } from '@testing-library/react';
import SimulateCheckTab from './SimulateCheckTab';
import React from 'react';

describe('SimulateCheckTab', () => {
  it('renders the tab heading', () => {
    render(<SimulateCheckTab />);
    expect(screen.getByRole('heading', { name: /Simulate Check/i })).toBeInTheDocument();
  });
});
console.log("src/ui/src/pages/BalanceToolsPage/SimulateCheckTab.test.tsx defined");
