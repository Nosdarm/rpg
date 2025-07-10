// src/ui/src/pages/BalanceToolsPage/BalanceToolsPage.test.tsx
import { render, screen } from '@testing-library/react';
import BalanceToolsPage from './BalanceToolsPage';
import React from 'react';

describe('BalanceToolsPage', () => {
  it('renders the main heading', () => {
    render(<BalanceToolsPage />);
    expect(screen.getByRole('heading', { name: /Balance Tools/i })).toBeInTheDocument();
  });
});
console.log("src/ui/src/pages/BalanceToolsPage/BalanceToolsPage.test.tsx defined");
