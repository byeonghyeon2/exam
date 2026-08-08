import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { endpoints } from '../api/queries';
import { WrongNotes } from '../pages/WrongNotes';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('WrongNotes', () => {
  it('shows one card per study session and retries only wrong questions', async () => {
    vi.spyOn(endpoints, 'studyHistory').mockResolvedValue([{
      session_id: 'batch-1', certification_code: 'DEA-C01', certification_name: 'AWS 데이터 엔지니어', completed_at: '2026-08-08T10:00:00Z',
      total_count: 10, correct_count: 7, wrong_count: 3,
      wrong_questions: [
        { id: 1, question_uid: 'DEA-1', question_ko: '틀린 문제 1' },
        { id: 2, question_uid: 'DEA-2', question_ko: '틀린 문제 2' },
        { id: 3, question_uid: 'DEA-3', question_ko: '틀린 문제 3' },
      ],
    }]);
    const retry = vi.spyOn(endpoints, 'retryStudyHistory').mockResolvedValue({ id: 'retry-1', certification_code: 'DEA-C01', mode: 'review', total_questions: 3, current_index: 0 });
    const user = userEvent.setup();
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={['/wrong-notes']}><Routes><Route path="/wrong-notes" element={<WrongNotes />} /><Route path="/study/:id" element={<h1>재학습 화면</h1>} /></Routes></MemoryRouter></QueryClientProvider>);

    expect(await screen.findByRole('heading', { name: '학습 기록 #1' })).toBeInTheDocument();
    expect(screen.getByText('총 문제').parentElement).toHaveTextContent('10');
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    await user.click(screen.getByRole('button', { name: '3문제 다시 풀기' }));
    expect(retry).toHaveBeenCalledWith('batch-1', expect.anything());
    expect(await screen.findByRole('heading', { name: '재학습 화면' })).toBeInTheDocument();
  });
});
