import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
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
        { id: 1, question_uid: 'DEA-1', question_ko: '틀린 문제 1', related_concepts: 'Amazon S3' },
        { id: 2, question_uid: 'DEA-2', question_ko: '틀린 문제 2', related_concepts: 'AWS Glue' },
        { id: 3, question_uid: 'DEA-3', question_ko: '틀린 문제 3', related_concepts: 'Amazon Redshift' },
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

  it('shows the wrong answer in a read-only question detail with an existing AI explanation', async () => {
    mockConceptSummary();
    vi.spyOn(endpoints, 'studyHistory').mockResolvedValue([{
      session_id: 'batch-1', certification_code: 'DEA-C01', certification_name: 'AWS 데이터 엔지니어', completed_at: '2026-08-08T10:00:00Z',
      total_count: 1, correct_count: 0, wrong_count: 1,
      wrong_questions: [{ id: 1, question_uid: 'DEA-1', question_ko: '틀린 문제 1', related_concepts: 'Amazon S3 lifecycle' }],
    }]);
    vi.spyOn(endpoints, 'studyHistoryQuestion').mockResolvedValue({
      question: { id: 1, question_uid: 'DEA-1', question_type: 'multiple_choice', question_ko: '저장 비용을 줄이는 방법은?', question_en: 'How can storage cost be reduced?', required_answer_count: 1, choices: [{ id: 'A', text_ko: 'Lifecycle', text_en: 'Lifecycle' }, { id: 'B', text_ko: 'DAX', text_en: 'DAX' }] },
      selected_answers: ['B'], correct_answers: ['A'], related_concepts: 'Amazon S3 lifecycle',
      explanation: { correct_answer_summary: 'A가 정답입니다.', core_reason: 'Lifecycle이 요구사항에 맞습니다.', keywords_json: ['Lifecycle'], choice_analysis_json: { A: '정답', B: '캐시 기능입니다.' }, related_concepts: 'Amazon S3 lifecycle', exam_traps: '보관 계층과 캐시를 구분하세요.', memory_summary: '수명주기는 Lifecycle' },
    });
    const user = userEvent.setup();
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><WrongNotes /></MemoryRouter></QueryClientProvider>);

    expect(await screen.findByText('핵심 개념 · Amazon S3 lifecycle')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '상세 보기' }));
    const dialog = await screen.findByRole('dialog', { name: '오답 문제 상세' });
    expect(within(dialog).getByText('내 선택 · 오답')).toBeInTheDocument();
    expect(dialog.querySelector('.correct-status')).toHaveTextContent('정답');
    expect(within(dialog).getAllByText('Lifecycle이 요구사항에 맞습니다.')).toHaveLength(2);
    expect(within(dialog).getByText('핵심 해설')).toBeInTheDocument();
    expect(within(dialog).getByText('선택지별 설명')).toBeInTheDocument();
    expect(within(dialog).getByText('한 줄 암기')).toBeInTheDocument();
    expect(within(dialog).getByRole('checkbox', { name: 'B' })).toBeDisabled();
    expect(within(dialog).queryByRole('button', { name: /정답 확인|다음 문제|AI 해설|문제 신고/ })).not.toBeInTheDocument();
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
    expect(window.confirm).toHaveBeenCalledWith('이 오답노트를 목록에서 삭제할까요? 학습 이력은 오답 패턴 분석에 계속 반영됩니다.');
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
