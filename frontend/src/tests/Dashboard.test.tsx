import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

  it('opens the available certification list from the count', async () => {
    vi.spyOn(endpoints, 'certifications').mockResolvedValue([
      { code: 'DEA-C01', name_ko: 'AWS 데이터 엔지니어', name_en: 'AWS Data Engineer', exam_version: 'DEA-C01', default_question_count: 65, default_duration_minutes: 130, passing_score: 720 },
    ]);
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><Dashboard /></MemoryRouter>
      </QueryClientProvider>,
    );

    await user.click(await screen.findByRole('button', { name: '학습 가능 자격증 1개 보기' }));
    const dialog = screen.getByRole('dialog', { name: '학습 가능 자격증' });
    expect(within(dialog).getByRole('img', { name: 'Amazon Web Services' })).toBeInTheDocument();
    expect(within(dialog).getByText('DEA-C01')).toBeInTheDocument();
    expect(within(dialog).getByText('AWS 데이터 엔지니어')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '닫기' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows a fallback mark when a provider logo fails to load', async () => {
    vi.spyOn(endpoints, 'certifications').mockResolvedValue([
      { code: 'DEA-C01', name_ko: 'AWS 데이터 엔지니어', name_en: 'AWS Data Engineer', exam_version: 'DEA-C01', default_question_count: 65, default_duration_minutes: 130, passing_score: 720 },
    ]);
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><Dashboard /></MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.error(await screen.findByRole('img', { name: 'Amazon Web Services' }));
    expect(screen.getByRole('img', { name: 'DEA-C01 자격증' })).toBeInTheDocument();
  });
});
