// src/ui/src/pages/BalanceToolsPage/SimulateConflictTab.test.tsx
import { render, screen } from '@testing-library/react';
import SimulateConflictTab from './SimulateConflictTab';
import React from 'react';

describe('SimulateConflictTab', () => {
  it('renders the tab heading', () => {
    render(<SimulateConflictTab />);
    expect(screen.getByRole('heading', { name: /Simulate Conflict/i })).toBeInTheDocument();
  });
});
console.log("src/ui/src/pages/BalanceToolsPage/SimulateConflictTab.test.tsx defined");
