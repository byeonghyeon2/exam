import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { endpoints } from '../api/queries';
import { Dashboard } from '../pages/Dashboard';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Dashboard', () => {
  it('shows every available certification and its count', async () => {
    vi.spyOn(endpoints, 'certifications').mockResolvedValue([
      { code: 'DEA-C01', name_ko: '데이터 엔지니어', name_en: 'Data Engineer', exam_version: 'DEA-C01', default_question_count: 65, default_duration_minutes: 130, passing_score: 720 },
      { code: 'SAA-C03', name_ko: '솔루션스 아키텍트', name_en: 'Solutions Architect', exam_version: 'SAA-C03', default_question_count: 65, default_duration_minutes: 130, passing_score: 720 },
    ]);
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><Dashboard /></MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText('학습 가능 자격증')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: '데이터 엔지니어' })).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '솔루션스 아키텍트' })).toBeInTheDocument();
    expect(screen.queryByText('학습 가능 문제')).not.toBeInTheDocument();
  });
});
