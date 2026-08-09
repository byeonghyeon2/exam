import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { endpoints } from '../api/queries';
import { MockExamSession, MockExamSetup } from '../pages/MockExam';
import type { Question } from '../types';
import styles from '../styles.css?raw';

const questions: Question[] = [
  {
    id: 1, question_uid: 'DEA-1', question_type: 'multiple_choice', question_en: 'Long English question', question_ko: '긴 한국어 문제', required_answer_count: 1,
    choices: [{ id: 'A', text_en: 'First answer', text_ko: '첫 답안' }, { id: 'B', text_en: 'Second answer', text_ko: '둘째 답안' }],
  },
  {
    id: 2, question_uid: 'DEA-2', question_type: 'multiple_response', question_en: 'Select two', question_ko: '복수 선택 문제', required_answer_count: 2,
    choices: [{ id: 'A', text_en: 'Answer A', text_ko: '답안 A' }, { id: 'B', text_en: 'Answer B', text_ko: '답안 B' }],
  },
];

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

function renderSetup() {
  return render(
    <QueryClientProvider client={client()}><MemoryRouter initialEntries={['/mock-exam']}><Routes>
      <Route path="/mock-exam" element={<MockExamSetup />} />
      <Route path="/mock-exam/:id" element={<h1>시험 화면</h1>} />
    </Routes></MemoryRouter></QueryClientProvider>,
  );
}

function renderSession() {
  return render(
    <QueryClientProvider client={client()}><MemoryRouter initialEntries={['/mock-exam/exam-1']}><Routes>
      <Route path="/mock-exam/:id" element={<MockExamSession />} />
      <Route path="/results/:id" element={<h1>결과 화면</h1>} />
    </Routes></MemoryRouter></QueryClientProvider>,
  );
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

describe('MockExamSetup', () => {
  it('keeps the full-width start action disabled until a certification is selected', async () => {
    vi.spyOn(endpoints, 'certifications').mockResolvedValue([{
      code: 'DEA-C01', name_ko: 'AWS 데이터 엔지니어', name_en: 'AWS Data Engineer', exam_version: 'DEA-C01', default_question_count: 65, default_duration_minutes: 130, passing_score: 720,
    }]);
    vi.spyOn(endpoints, 'createExam').mockResolvedValue({ id: 'created-1' });
    const user = userEvent.setup();
    renderSetup();

    const select = await screen.findByRole('combobox');
    await screen.findByRole('option', { name: 'AWS 데이터 엔지니어' });
    const start = screen.getByRole('button');
    expect(select.closest('section')).toHaveClass('mock-exam-setup');
    expect(start).toBeDisabled();
    await user.selectOptions(select, 'DEA-C01');
    expect(start).toBeEnabled();
    await user.click(start);

    expect(endpoints.createExam).toHaveBeenCalledWith({ certification_code: 'DEA-C01' });
    expect(await screen.findByRole('heading', { name: '시험 화면' })).toBeInTheDocument();
  });

  it('renders creation errors without leaving the setup screen', async () => {
    vi.spyOn(endpoints, 'certifications').mockResolvedValue([{
      code: 'DEA-C01', name_ko: 'AWS 데이터 엔지니어', name_en: 'AWS Data Engineer', exam_version: 'DEA-C01', default_question_count: 65, default_duration_minutes: 130, passing_score: 720,
    }]);
    vi.spyOn(endpoints, 'createExam').mockRejectedValue(new Error('시험 생성 실패'));
    const user = userEvent.setup();
    renderSetup();

    await screen.findByRole('option', { name: 'AWS 데이터 엔지니어' });
    await user.selectOptions(screen.getByRole('combobox'), 'DEA-C01');
    await user.click(screen.getByRole('button'));
    expect(await screen.findByRole('alert')).toHaveTextContent('시험 생성 실패');
  });
});

describe('mobile exam regression styles', () => {
  const compact = styles.replace(/\s+/g, '');

  it('constrains every setup control to the mobile card width', () => {
    expect(compact).toContain('.mock-exam-setup{width:100%;min-width:0}');
    expect(compact).toContain('.mock-exam-setuplabel,.mock-exam-setupselect,.mock-exam-setup.button{width:100%;min-width:0;max-width:100%}');
    expect(compact).toContain('.panel.mock-exam-setup{padding:20px16px;gap:18px}');
  });

  it('uses compact readable question typography and bottom safe areas on mobile', () => {
    expect(compact).toContain('.questionh2{font-size:clamp(17px,4.5vw,19px);line-height:1.65');
    expect(compact).toContain('.question-en{font-size:13px;line-height:1.55}');
    expect(compact).toContain('.choice{padding:14px13px;gap:11px;font-size:15px;line-height:1.55}');
    expect(compact).toContain('padding-bottom:calc(80px+env(safe-area-inset-bottom))');
    expect(compact).toContain('height:calc(67px+env(safe-area-inset-bottom))');
  });
});

describe('MockExamSession', () => {
  it('shows loading, request errors, and an empty-exam error explicitly', async () => {
    let resolveQuestions!: (value: Question[]) => void;
    vi.spyOn(endpoints, 'examQuestions').mockReturnValue(new Promise(resolve => { resolveQuestions = resolve; }));
    const view = renderSession();
    expect(screen.getByRole('status')).toBeInTheDocument();
    resolveQuestions([]);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    view.unmount();

    vi.spyOn(endpoints, 'examQuestions').mockRejectedValue(new Error('문제 요청 실패'));
    renderSession();
    expect(await screen.findByRole('alert')).toHaveTextContent('문제 요청 실패');
  });

  it('supports single and multiple answers, paging, and direct palette navigation', async () => {
    const save = vi.spyOn(endpoints, 'saveAnswer').mockResolvedValue(undefined);
    vi.spyOn(endpoints, 'examQuestions').mockResolvedValue(questions);
    const user = userEvent.setup();
    renderSession();

    const first = await screen.findByRole('radio', { name: /첫 답안/ });
    const second = screen.getByRole('radio', { name: /둘째 답안/ });
    await user.click(first);
    await user.click(second);
    expect(first).not.toBeChecked();
    expect(second).toBeChecked();

    const palette = document.querySelector('.palette')!;
    await user.click(screen.getByRole('button', { name: '다음 문제' }));
    await user.click(screen.getByRole('button', { name: '이전' }));
    await user.click(screen.getByRole('button', { name: /2번 문제/ }));
    const answerA = await screen.findByRole('checkbox', { name: /답안 A/ });
    const answerB = screen.getByRole('checkbox', { name: /답안 B/ });
    await user.click(answerA);
    await user.click(answerB);
    await user.click(answerA);
    expect(answerA).not.toBeChecked();
    expect(answerB).toBeChecked();
    expect(palette.querySelectorAll('.answered')).toHaveLength(2);
    expect(save).toHaveBeenLastCalledWith('exam-1', 2, ['B']);
  });

  it('saves the accumulated answers, submits, and navigates to results', async () => {
    vi.spyOn(endpoints, 'examQuestions').mockResolvedValue(questions);
    const save = vi.spyOn(endpoints, 'saveAnswer').mockResolvedValue(undefined);
    const submit = vi.spyOn(endpoints, 'submitExam').mockResolvedValue({} as never);
    const user = userEvent.setup();
    renderSession();

    await user.click(await screen.findByRole('radio', { name: /첫 답안/ }));
    await user.click(screen.getByRole('button', { name: /시험 제출/ }));
    expect(await screen.findByRole('heading', { name: '결과 화면' })).toBeInTheDocument();
    expect(save).toHaveBeenCalledWith('exam-1', 1, ['A']);
    expect(submit).toHaveBeenCalledWith('exam-1');
  });

  it('blocks controls while grading and exposes submission failures', async () => {
    vi.spyOn(endpoints, 'examQuestions').mockResolvedValue([questions[0]!]);
    let rejectSubmit!: (error: Error) => void;
    vi.spyOn(endpoints, 'submitExam').mockReturnValue(new Promise((_resolve, reject) => { rejectSubmit = reject; }));
    const user = userEvent.setup();
    renderSession();

    const submit = await screen.findByRole('button', { name: /시험 제출/ });
    await user.click(submit);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(submit).toBeDisabled();
    expect(screen.getByRole('radio', { name: /첫 답안/ })).toBeDisabled();
    rejectSubmit(new Error('채점 실패'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('채점 실패'));
    expect(submit).toBeEnabled();
  });
});
