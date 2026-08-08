import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { endpoints } from '../api/queries';
import { MockExamSession } from '../pages/MockExam';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('MockExamSession', () => {
  it('blocks exam controls while grading', async () => {
    vi.spyOn(endpoints, 'examQuestions').mockResolvedValue([{
      id: 1, question_uid: 'DEA-1', question_type: 'multiple_choice', question_en: 'Question', question_ko: '문제', required_answer_count: 1,
      choices: [{ id: 'A', text_en: 'Answer', text_ko: '답안' }],
    }]);
    vi.spyOn(endpoints, 'submitExam').mockImplementation(() => new Promise(() => {}));
    const user = userEvent.setup();
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={['/mock-exam/exam-1']}><Routes><Route path="/mock-exam/:id" element={<MockExamSession />} /></Routes></MemoryRouter></QueryClientProvider>);

    const submit = await screen.findByRole('button', { name: '시험 제출' });
    await user.click(submit);
    expect(await screen.findByRole('alert')).toHaveTextContent('채점중입니다.');
    expect(submit).toBeDisabled();
    expect(screen.getByRole('radio', { name: /답안/ })).toBeDisabled();
  });
});
