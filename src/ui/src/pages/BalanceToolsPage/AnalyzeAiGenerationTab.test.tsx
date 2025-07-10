// src/ui/src/pages/BalanceToolsPage/AnalyzeAiGenerationTab.test.tsx
import { render, screen } from '@testing-library/react';
import AnalyzeAiGenerationTab from './AnalyzeAiGenerationTab';
import React from 'react';

describe('AnalyzeAiGenerationTab', () => {
  it('renders the tab heading', () => {
    render(<AnalyzeAiGenerationTab />);
    expect(screen.getByRole('heading', { name: /Analyze AI Generation/i })).toBeInTheDocument();
  });
});
console.log("src/ui/src/pages/BalanceToolsPage/AnalyzeAiGenerationTab.test.tsx defined");
