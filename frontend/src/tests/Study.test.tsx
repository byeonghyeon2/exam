import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { endpoints } from '../api/queries';
import { StudyExitGuardContext } from '../components/StudyExitGuard';
import { Study } from '../pages/Study';

const session = {
  id: 'session-1',
  certification_code: 'DEA-C01',
  mode: 'random',
  total_questions: 1,
  current_index: 0,
  question: {
    id: 10,
    question_uid: 'DEA-10',
    question_type: 'multiple_choice' as const,
    question_en: 'Question',
    question_ko: '문제입니다',
    required_answer_count: 1,
    choices: [
      { id: 'A', text_ko: '사용자 선택', text_en: 'Selected answer' },
      { id: 'B', text_ko: '다른 선택', text_en: 'Other answer' },
      { id: 'C', text_ko: '실제 정답', text_en: 'Correct answer' },
      { id: 'D', text_ko: '마지막 선택', text_en: 'Last answer' },
    ],
  },
};

function renderStudy(requestExit = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <StudyExitGuardContext.Provider value={{setGuard:vi.fn(),requestExit}}><MemoryRouter initialEntries={['/study/session-1']}>
        <Routes>
          <Route path="/study/:id" element={<Study />} />
          <Route path="/wrong-notes" element={<h1>오답노트 화면</h1>} />
        </Routes>
      </MemoryRouter></StudyExitGuardContext.Provider>
    </QueryClientProvider>,
  );
  return { ...view, client };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Study', () => {
  it('allows a single answer to be deselected before grading', async () => {
    vi.spyOn(endpoints, 'study').mockResolvedValue(session);
    const user = userEvent.setup();
    renderStudy();

    const answer = await screen.findByRole('radio', { name: /사용자 선택/ });
    await user.click(answer);
    expect(answer).toBeChecked();
    await user.click(answer);
    expect(answer).not.toBeChecked();
    expect(screen.getByRole('button', { name: '정답 확인' })).toBeDisabled();
  });

  it('opens the shared three-choice exit flow from the study exit button', async () => {
    vi.spyOn(endpoints, 'study').mockResolvedValue(session);
    const requestExit = vi.fn();
    const user = userEvent.setup();
    renderStudy(requestExit);

    await user.click(await screen.findByRole('button', { name: '학습 나가기' }));
    expect(requestExit).toHaveBeenCalledWith('/');
  });

  it('warns before refresh or closing an active study page', async () => {
    vi.spyOn(endpoints, 'study').mockResolvedValue(session);
    renderStudy();
    await screen.findByRole('button', { name: '학습 나가기' });
    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it('scrolls the next study and retry question to the top', async () => {
    const nextSession = { ...session, total_questions: 2, current_index: 1, question: { ...session.question, id: 11, question_uid: 'DEA-11' } };
    vi.spyOn(endpoints, 'study').mockResolvedValueOnce({ ...session, total_questions: 2 }).mockResolvedValueOnce(nextSession);
    vi.spyOn(endpoints, 'submitStudy').mockResolvedValue({ is_correct: true, correct_answers: ['A'] });
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    const user = userEvent.setup();
    renderStudy();

    await screen.findByText('문제입니다');
    scrollIntoView.mockClear();
    await user.click(screen.getByRole('radio', { name: /사용자 선택/ }));
    await user.click(screen.getByRole('button', { name: '정답 확인' }));
    await user.click(await screen.findByRole('button', { name: '다음 문제' }));
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });
  });
  it('keeps the wrong selection and visually reveals the correct answer', async () => {
    vi.spyOn(endpoints, 'study').mockResolvedValue(session);
    vi.spyOn(endpoints, 'submitStudy').mockResolvedValue({
      is_correct: false,
      correct_answers: ['C'],
    });
    const user = userEvent.setup();
    renderStudy();

    const selectedAnswer = await screen.findByRole('radio', { name: /사용자 선택/ });
    const correctAnswer = screen.getByRole('radio', { name: /실제 정답/ });
    await user.click(selectedAnswer);
    await user.click(screen.getByRole('button', { name: '정답 확인' }));

    expect(await screen.findByText('내 선택 · 오답')).toBeInTheDocument();
    expect(screen.getByText('정답')).toBeInTheDocument();
    expect(selectedAnswer).toBeChecked();
    expect(correctAnswer).not.toBeChecked();
    expect(selectedAnswer.closest('label')).toHaveClass('incorrect');
    expect(correctAnswer.closest('label')).toHaveClass('correct');
  });

  it('generates and displays an AI explanation after grading', async () => {
    vi.spyOn(endpoints, 'study').mockResolvedValue(session);
    vi.spyOn(endpoints, 'submitStudy').mockResolvedValue({ is_correct: false, correct_answers: ['C'] });
    const generatedExplanation = {
      correct_answer_summary: 'C가 검증된 정답입니다.',
      core_reason: 'C만 요구사항을 충족합니다.',
      keywords_json: ['AWS', '데이터'],
      choice_analysis_json: { A: 'A는 다른 기능을 설명합니다.', B: 'B는 조건이 부족합니다.', C: 'C가 요구사항에 맞습니다.', D: 'D는 반대 기능입니다.' },
      related_concepts: '관련 개념', exam_traps: '서비스 이름을 구분합니다.', memory_summary: '요구사항과 기능을 연결합니다.',
    };
    let finishGeneration!: (value: typeof generatedExplanation) => void;
    const generation = new Promise<typeof generatedExplanation>(resolve => { finishGeneration = resolve; });
    const generate = vi.spyOn(endpoints, 'generateExplanation').mockReturnValue(generation);
    const user = userEvent.setup();
    renderStudy();

    await user.click(await screen.findByRole('radio', { name: /사용자 선택/ }));
    await user.click(screen.getByRole('button', { name: '정답 확인' }));
    await user.click(await screen.findByRole('button', { name: 'AI 해설' }));

    expect(generate).toHaveBeenCalledWith(10);
    expect(screen.getByRole('alertdialog')).toHaveTextContent('AI 해설 생성 중입니다.');
    expect(document.body).toHaveStyle({ overflow: 'hidden' });
    finishGeneration(generatedExplanation);
    expect(await screen.findByRole('heading', { name: 'AI 해설' })).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(document.body).not.toHaveStyle({ overflow: 'hidden' });
    expect(screen.getByText('C만 요구사항을 충족합니다.')).toBeInTheDocument();
    expect(screen.getByText('A는 다른 기능을 설명합니다.')).toBeInTheDocument();
    expect(screen.getByText('내가 고른 오답')).toBeInTheDocument();
  });

  it('submits a typed problem report from the modal', async () => {
    vi.spyOn(endpoints, 'study').mockResolvedValue(session);
    const report = vi.spyOn(endpoints, 'reportQuestion').mockResolvedValue({ id: 7 });
    const user = userEvent.setup();
    renderStudy();

    await user.click(await screen.findByRole('button', { name: '문제 신고' }));
    expect(screen.getByRole('dialog', { name: '문제 신고' })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('신고 유형'), 'wrong_answer');
    await user.type(screen.getByLabelText('신고 내용'), '정답이 이상한 것 같음');
    await user.click(screen.getByRole('button', { name: '신고 등록' }));

    expect(report).toHaveBeenCalledWith(10, {
      report_type: 'wrong_answer',
      description: '정답이 이상한 것 같음',
    });
    expect(await screen.findByRole('heading', { name: '신고가 접수되었습니다' })).toBeInTheDocument();
  });

  it('finalizes wrong notes in a batch and shows the study summary', async () => {
    vi.spyOn(endpoints, 'study')
      .mockResolvedValueOnce(session)
      .mockResolvedValueOnce({
        ...session,
        current_index: 1,
        question: undefined,
        summary: {
          total_questions: 1,
          answered_count: 1,
          correct_count: 0,
          wrong_count: 1,
          finalized: true,
        },
      });
    vi.spyOn(endpoints, 'submitStudy').mockResolvedValue({
      is_correct: false,
      correct_answers: ['C'],
    });
    const complete = vi.spyOn(endpoints, 'completeStudy').mockResolvedValue({
      total_questions: 1,
      answered_count: 1,
      correct_count: 0,
      wrong_count: 1,
      finalized: true,
    });
    const user = userEvent.setup();
    renderStudy();

    await user.click(await screen.findByRole('radio', { name: /사용자 선택/ }));
    await user.click(screen.getByRole('button', { name: '정답 확인' }));
    await user.click(await screen.findByRole('button', { name: '학습 결과 보기' }));

    expect(complete).toHaveBeenCalledWith('session-1');
    expect(await screen.findByText('학습을 완료했습니다')).toBeInTheDocument();
    expect(screen.getByText('총 풀이')).toBeInTheDocument();
    expect(screen.getByText('오답')).toBeInTheDocument();
    expect(screen.getByText(/틀린 문제 1개가 오답 노트에 한 번에 반영/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '오답노트로 돌아가기' })).not.toBeInTheDocument();
  });

  it('returns to a refreshed wrong-note list after mastering every retry question', async () => {
    vi.spyOn(endpoints, 'study').mockResolvedValue({
      ...session,
      retry_of_session_id: 'wrong-note-session',
      current_index: 1,
      question: undefined,
      summary: {
        total_questions: 1,
        answered_count: 1,
        correct_count: 1,
        wrong_count: 0,
        finalized: true,
      },
    });
    const user = userEvent.setup();
    const { client } = renderStudy();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    await user.click(await screen.findByRole('button', { name: '오답노트로 돌아가기' }));

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['study-history'], refetchType: 'all' });
    expect(await screen.findByRole('heading', { name: '오답노트 화면' })).toBeInTheDocument();
  });
});
