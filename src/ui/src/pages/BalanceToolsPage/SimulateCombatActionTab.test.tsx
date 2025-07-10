// src/ui/src/pages/BalanceToolsPage/SimulateCombatActionTab.test.tsx
import { render, screen } from '@testing-library/react';
import SimulateCombatActionTab from './SimulateCombatActionTab';
import React from 'react';

describe('SimulateCombatActionTab', () => {
  it('renders the tab heading', () => {
    render(<SimulateCombatActionTab />);
    expect(screen.getByRole('heading', { name: /Simulate Combat Action/i })).toBeInTheDocument();
  });
});
console.log("src/ui/src/pages/BalanceToolsPage/SimulateCombatActionTab.test.tsx defined");
