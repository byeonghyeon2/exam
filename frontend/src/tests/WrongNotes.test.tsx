import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { endpoints } from '../api/queries';
import { WrongNotes } from '../pages/WrongNotes';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function mockConceptSummary(overrides: Partial<Awaited<ReturnType<typeof endpoints.conceptSummary>>> = {}) {
  vi.spyOn(endpoints, 'conceptSummary').mockResolvedValue({
    certification_code: 'DEA-C01', certification_name: 'AWS 데이터 엔지니어',
    answer_count: 2, minimum_answer_count: 10,
    can_generate: false, result: null, ...overrides,
  });
}

describe('WrongNotes', () => {
  it('marks a fully corrected study group complete and only offers deletion', async () => {
    mockConceptSummary();
    vi.spyOn(endpoints, 'studyHistory').mockResolvedValue([{
      session_id:'batch-done',certification_code:'DEA-C01',certification_name:'AWS 데이터 엔지니어',completed_at:'2026-08-08T10:00:00Z',
      total_count:3,wrong_count:0,correct_count:3,wrong_questions:[],
    }]);
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><WrongNotes /></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByText('모두 맞힘')).toBeInTheDocument();
    expect(screen.queryByRole('button',{name:/다시 풀기/})).not.toBeInTheDocument();
    expect(screen.getByRole('button',{name:/삭제/})).toBeInTheDocument();
  });
  it('lets the learner expand their wrong questions and retries only wrong questions', async () => {
    mockConceptSummary();
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
    const detail = screen.getByText('틀린 문제 보기 (3)').closest('details');
    expect(detail).not.toHaveAttribute('open');
    await user.click(screen.getByText('틀린 문제 보기 (3)'));
    expect(detail).toHaveAttribute('open');
    expect(screen.getByText('틀린 문제 1')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '3문제 다시 풀기' }));
    expect(retry).toHaveBeenCalledWith('batch-1', expect.anything());
    expect(await screen.findByRole('heading', { name: '재학습 화면' })).toBeInTheDocument();
  });

  it('deletes a study history card after confirmation', async () => {
    mockConceptSummary();
    vi.spyOn(endpoints, 'studyHistory').mockResolvedValueOnce([{
      session_id: 'batch-1', certification_code: 'DEA-C01', certification_name: 'AWS 데이터 엔지니어', completed_at: '2026-08-08T10:00:00Z',
      total_count: 10, correct_count: 7, wrong_count: 3, wrong_questions: [],
    }]).mockResolvedValue([]);
    const remove = vi.spyOn(endpoints, 'deleteStudyHistory').mockResolvedValue({ deleted_count: 10 });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><WrongNotes /></MemoryRouter></QueryClientProvider>);

    await user.click(await screen.findByRole('button', { name: '삭제' }));
    expect(window.confirm).toHaveBeenCalled();
    expect(remove).toHaveBeenCalledWith('batch-1', expect.anything());
    await waitFor(() => expect(screen.queryByRole('heading', { name: '학습 기록 #1' })).not.toBeInTheDocument());
  });

  it('shows the pattern-analysis activation guide with the current progress', async () => {
    mockConceptSummary();
    vi.spyOn(endpoints, 'studyHistory').mockResolvedValue([{
      session_id:'batch-1', certification_code:'DEA-C01', certification_name:'AWS 데이터 엔지니어', completed_at:'2026-08-08T10:00:00Z',
      total_count:10, wrong_count:2, correct_count:8, wrong_questions:[],
    }]);
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><WrongNotes /></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByRole('button', { name: 'AWS 데이터 엔지니어 오답 패턴 분석 안내' })).toBeInTheDocument();
    expect(screen.getByText('완료한 학습 및 오답노트 재학습 답안이 10문제 이상이면 분석할 수 있습니다.')).toBeInTheDocument();
    expect(await screen.findByText('완료 답안 2/10문제')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '오답 패턴 분석' })).toBeDisabled();
  });

  it('keeps the wrong-note screen usable when the optional AI summary status is unavailable', async () => {
    vi.spyOn(endpoints, 'conceptSummary').mockRejectedValue(new Error('unavailable'));
    vi.spyOn(endpoints, 'studyHistory').mockResolvedValue([{
      session_id:'batch-1', certification_code:'DEA-C01', certification_name:'AWS 데이터 엔지니어', completed_at:'2026-08-08T10:00:00Z',
      total_count:10, wrong_count:2, correct_count:8, wrong_questions:[],
    }]);
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><WrongNotes /></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: '학습 기록 #1' })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('오답 패턴 분석 정보를 불러오지 못했습니다.')).not.toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '오답 패턴 분석' })).not.toBeInTheDocument();
  });
});
