import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Clock3, LoaderCircle } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { endpoints } from '../api/queries';
import { ErrorState, Loading, PageHeader, Progress } from '../components/common';
import { useStudyExitGuard } from '../components/StudyExitGuard';

export function MockExamSetup() {
  const navigate = useNavigate();
  const certifications = useQuery({ queryKey: ['certifications'], queryFn: endpoints.certifications });
  const [code, setCode] = useState('');
  const create = useMutation({ mutationFn: () => endpoints.createExam({ certification_code: code }), onSuccess: exam => navigate(`/mock-exam/${exam.id}`) });
  return <>
    <PageHeader eyebrow="실전 점검" title="모의고사" description="실제 시험 시간과 문항 수를 적용합니다. 제출 전에는 정답을 확인할 수 없습니다." />
    <section className="panel form mock-exam-setup"><label>응시 자격증<select value={code} onChange={event => setCode(event.target.value)}><option value="">선택해 주세요</option>{certifications.data?.map(certification => <option key={certification.code} value={certification.code}>{certification.name_ko}</option>)}</select></label><div className="notice"><Clock3 /> 시험이 시작되면 타이머가 작동하며 시간이 끝나면 자동 제출됩니다.</div><button className="button" disabled={!code || create.isPending} onClick={() => create.mutate()}>{create.isPending ? '시험 생성 중…' : '모의고사 시작'}</button>{create.isError && <ErrorState error={create.error} />}</section>
  </>;
}

export function MockExamSession() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { setGuard, requestExit } = useStudyExitGuard();
  const questions = useQuery({ queryKey: ['exam-questions', id], queryFn: () => endpoints.examQuestions(id) });
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string[]>>({});
  const [seconds, setSeconds] = useState(7800);
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const questionRef = useRef<HTMLElement>(null);
  const currentQuestionId = questions.data?.question_ids[index];
  const currentQuestion = useQuery({
    queryKey: ['exam-question', id, currentQuestionId],
    queryFn: () => endpoints.examQuestion(id, currentQuestionId!),
    enabled: currentQuestionId !== undefined,
  });
  const submit = useMutation({
    mutationFn: async () => {
      await Promise.all(Object.entries(answers).map(([questionId, selected]) => endpoints.saveAnswer(id, Number(questionId), selected)));
      return endpoints.submitExam(id);
    },
    onSuccess: () => navigate(`/results/${id}`),
  });
  const { mutate: submitExam } = submit;
  const questionIds = useMemo(() => questions.data?.question_ids ?? [], [questions.data]);
  const unansweredNumbers = useMemo(
    () => questionIds.flatMap((questionId, itemIndex) => answers[questionId]?.length ? [] : [itemIndex + 1]),
    [answers, questionIds],
  );
  const answeredCount = questionIds.length - unansweredNumbers.length;

  useEffect(() => {
    if (!questions.data || submit.isSuccess) {
      setGuard(current => current?.sessionId === id ? null : current);
      return;
    }
    setGuard({kind:'exam',sessionId:id,answeredCount,totalCount:questions.data.total,unansweredNumbers});
    const warnBeforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', warnBeforeUnload);
      setGuard(current => current?.sessionId === id ? null : current);
    };
  }, [answeredCount, id, questions.data, setGuard, submit.isSuccess, unansweredNumbers]);
  useEffect(() => {
    if (!questions.data || submit.isSuccess) return;
    const marker = { ...window.history.state, certflowGuard: `exam-${id}` };
    window.history.pushState(marker, '', window.location.href);
    const warnOnBack = () => {
      window.history.pushState(marker, '', window.location.href);
      requestExit('/');
    };
    window.addEventListener('popstate', warnOnBack);
    return () => window.removeEventListener('popstate', warnOnBack);
  }, [id, questions.data, requestExit, submit.isSuccess]);

  useEffect(() => {
    if (submit.isPending) return;
    const timer = setInterval(() => setSeconds(current => {
      if (current <= 1) { submitExam(); return 0; }
      return current - 1;
    }), 1000);
    return () => clearInterval(timer);
  }, [submitExam, submit.isPending]);

  if (questions.isLoading) return <Loading label="시험 문제를 배정하는 중" />;
  if (questions.isError) return <ErrorState error={questions.error} />;
  if (currentQuestion.isLoading) return <Loading label="시험 문제를 불러오는 중" />;
  if (currentQuestion.isError) return <ErrorState error={currentQuestion.error} />;
  const question = currentQuestion.data;
  if (!question) return <ErrorState error={new Error('시험 문제가 없습니다.')} />;
  const selected = answers[question.id] ?? [];
  const choose = (choiceId: string) => {
    if (submit.isPending) return;
    const multiple = question.question_type === 'multiple_response';
    const next = multiple ? (selected.includes(choiceId) ? selected.filter(item => item !== choiceId) : [...selected, choiceId]) : (selected.includes(choiceId) ? [] : [choiceId]);
    setAnswers(current => ({ ...current, [question.id]: next }));
    void endpoints.saveAnswer(id, question.id, next);
  };
  const moveTo = async (nextIndex: number) => {
    const nextQuestionId = questions.data!.question_ids[nextIndex];
    if (nextQuestionId === undefined) return;
    await queryClient.fetchQuery({
      queryKey: ['exam-question', id, nextQuestionId],
      queryFn: () => endpoints.examQuestion(id, nextQuestionId),
    });
    setIndex(nextIndex);
    questionRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  };

  return <>
    <div className="exam-content" aria-busy={submit.isPending}>
      <div className="exam-bar"><b>모의고사</b><span className="timer"><Clock3 /> {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</span><button disabled={submit.isPending} onClick={() => setConfirmSubmit(true)}>시험 제출</button></div>
      <Progress label="시험 진행" value={((index + 1) / questions.data!.total) * 100} />
      <section className="question" ref={questionRef}><span className="badge">문제 {index + 1} · {question.question_type === 'multiple_response' ? '복수 선택' : '단일 선택'}</span><p className="question-en">{question.question_en}</p><h2>{question.question_ko}</h2><fieldset disabled={submit.isPending}><legend className="sr-only">답안</legend>{question.choices.map(choice => {const multiple=question.question_type==='multiple_response';return <label key={choice.id} className={`choice ${selected.includes(choice.id) ? 'selected' : ''}`}><input type="checkbox" role={multiple?undefined:'radio'} checked={selected.includes(choice.id)} onChange={() => choose(choice.id)} /><b>{choice.id}</b><span>{choice.text_ko}<small>{choice.text_en}</small></span></label>})}</fieldset><div className="actions"><button disabled={submit.isPending || index === 0} onClick={() => moveTo(index - 1)}>이전</button><button className="button" disabled={submit.isPending || index === questions.data!.total - 1} onClick={() => moveTo(index + 1)}>다음 문제</button></div></section>
      <div className="palette" aria-label="문제 이동">{questions.data!.question_ids.map((questionId, itemIndex) => <button disabled={submit.isPending} aria-label={`${itemIndex + 1}번 문제`} className={`${itemIndex === index ? 'current' : ''} ${answers[questionId]?.length ? 'answered' : ''}`} key={questionId} onClick={() => moveTo(itemIndex)}>{itemIndex + 1}</button>)}</div>
      {submit.isError && <ErrorState error={submit.error} />}
    </div>
    {confirmSubmit && <div className="modal-backdrop"><section className="modal exam-exit-modal" role="dialog" aria-modal="true" aria-labelledby="exam-submit-title"><p className="eyebrow">답안 제출</p><h2 id="exam-submit-title">모의고사를 종료하시겠습니까?</h2><p>총 {questions.data!.total}문제 중 {answeredCount}문제를 풀었습니다. <b>{answeredCount} / {questions.data!.total}</b></p><p className="unanswered-list"><b>미응답 문제</b><span>{unansweredNumbers.length ? unansweredNumbers.join(', ') : '없음'}</span></p><div className="exam-confirm-actions"><button className="button" onClick={() => {setConfirmSubmit(false);submitExam();}}>시험 종료 및 채점</button><button onClick={() => setConfirmSubmit(false)}>계속 풀기</button></div></section></div>}
    {submit.isPending && <div className="grading-overlay" role="alert" aria-live="assertive"><LoaderCircle className="spin" /><strong>채점중입니다.</strong><span>답안을 확인하고 결과를 계산하고 있습니다.</span></div>}
  </>;
}
