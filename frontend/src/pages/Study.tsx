import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LoaderCircle } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { endpoints } from '../api/queries';
import type { Explanation, Question, StudySession, Submission } from '../types';
import { ErrorState, InvalidAccess, isInvalidSessionError, Loading, PageHeader, Progress } from '../components/common';
import { ReportModal } from '../components/ReportModal';
import { useStudyExitGuard } from '../components/StudyExitGuard';
import { deleteQuestionDraft, deleteSessionDrafts, listSessionDrafts, saveAnswerDraft } from '../offline/answerDrafts';
import type { User } from '../types';

const DEFAULT_STUDY_QUESTION_COUNT = 10;

export function Study() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const userId=queryClient.getQueryData<User>(['me'])?.id??0;
  const { setGuard, requestExit } = useStudyExitGuard();
  const [currentAnswered, setCurrentAnswered] = useState(false);
  const certificationCode = new URLSearchParams(location.search).get('cert') ?? 'DEA-C01';
  const domainCode = new URLSearchParams(location.search).get('domain');
  const studyAll = new URLSearchParams(location.search).get('all') === 'true';
  const create = useMutation({
    mutationFn: () => endpoints.createStudy({
      certification_code: certificationCode,
      domain_code: domainCode,
      mode: 'random',
      question_count: studyAll && domainCode ? null : DEFAULT_STUDY_QUESTION_COUNT,
    }),
    onSuccess: session => navigate(`/study/${session.id}`, { replace: true }),
  });
  const { mutate: createSession, isPending, data } = create;

  useEffect(() => {
    if (!id && !isPending && !data && !create.isError) createSession();
  }, [id, isPending, data, create.isError, createSession]);

  const session = useQuery({
    queryKey: ['study', id],
    queryFn: () => endpoints.study(id!),
    enabled: Boolean(id),
  });
  const complete = useMutation({
    mutationFn: () => endpoints.completeStudy(id!),
    onSuccess: summary => {void deleteSessionDrafts(userId,'study',id!);queryClient.setQueryData<StudySession>(['study', id], current => current ? ({
      ...current,current_index: summary.answered_count,question: undefined,summary,
    }) : current)},
  });
  const sessionActive = Boolean(id && session.data && !session.data.summary?.finalized);
  const answeredCount = (session.data?.current_index ?? 0) + (currentAnswered ? 1 : 0);
  useEffect(() => {
    if (!sessionActive || !id) {
      setGuard(current => current?.sessionId === id ? null : current);
      return;
    }
    setGuard({
      kind: 'study',
      sessionId: id,
      answeredCount,
      saveAndLeave: async() => {const result=await endpoints.leaveStudy(id,true);await deleteSessionDrafts(userId,'study',id);return result},
      discardAndLeave: async() => {const result=await endpoints.leaveStudy(id,false);await deleteSessionDrafts(userId,'study',id);return result},
    });
    const warnBeforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', warnBeforeUnload);
      setGuard(current => current?.sessionId === id ? null : current);
    };
  }, [answeredCount, id, sessionActive, setGuard, userId]);
  useEffect(() => {
    if (!sessionActive || !id) return;
    const marker = { ...window.history.state, certflowGuard: `study-${id}` };
    window.history.pushState(marker, '', window.location.href);
    const warnOnBack = () => {
      window.history.pushState(marker, '', window.location.href);
      requestExit('/');
    };
    window.addEventListener('popstate', warnOnBack);
    return () => window.removeEventListener('popstate', warnOnBack);
  }, [id, requestExit, sessionActive]);

  if (!id) {
    return create.isError
      ? <ErrorState error={create.error} retry={() => createSession()} />
      : <Loading label="학습 세션을 준비하는 중" />;
  }
  if (session.isLoading) return <Loading />;
  if (session.isError) return isInvalidSessionError(session.error)
    ? <InvalidAccess onConfirm={() => navigate('/', { replace: true })} />
    : <ErrorState error={session.error} retry={() => void session.refetch()} />;

  return (
    <QuestionView
      key={session.data!.question?.id ?? 'complete'}
      question={session.data!.question}
      sessionId={id}
      session={session.data!}
      onNext={async () => { const response = await session.refetch(); setCurrentAnswered(false); return response; }}
      onComplete={() => complete.mutateAsync()}
      onAnswered={() => setCurrentAnswered(true)}
      completeError={complete.error}
      userId={userId}
      onExit={() => requestExit('/')}
      onReturnToWrongNotes={async () => {
        await queryClient.invalidateQueries({ queryKey: ['study-history'], refetchType: 'all' });
        navigate('/wrong-notes');
      }}
    />
  );
}

function QuestionView({ question, sessionId, session, onNext, onComplete, onAnswered, onExit, onReturnToWrongNotes, completeError, userId }: {
  question?: Question;
  sessionId: string;
  session: StudySession;
  onNext: () => Promise<unknown>;
  onComplete: () => Promise<unknown>;
  onAnswered: () => void;
  onExit: () => void;
  onReturnToWrongNotes: () => Promise<void>;
  completeError: Error | null;
  userId:number;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [result, setResult] = useState<Submission>();
  const [movingNext, setMovingNext] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const questionRef = useRef<HTMLElement>(null);
  const submit = useMutation({
    mutationFn: () => endpoints.submitStudy(question!.id, sessionId, { selected_answers: selected }),
    onSuccess: value => { setResult(value);onAnswered();if(question)void deleteQuestionDraft(userId,'study',sessionId,question.id); },
  });
  const explanation = useMutation({
    mutationFn: () => endpoints.generateExplanation(question!.id),
  });
  useEffect(() => {
    if (!explanation.isPending) return;
    const previousOverflow = document.body.style.overflow;
    const blockKeyboard = (event: KeyboardEvent) => event.preventDefault();
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', blockKeyboard, true);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', blockKeyboard, true);
    };
  }, [explanation.isPending]);
  const moveNext = async (finish = false) => {
    setMovingNext(true);
    try {
      await (finish ? onComplete() : onNext());
      if (!finish) document.querySelector('.question')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    } finally { setMovingNext(false); }
  };
  useEffect(()=>{
    if(!question)return;
    let active=true;
    void listSessionDrafts(userId,'study',sessionId).then(drafts=>{
      const draft=drafts.find(item=>item.questionId===question.id);
      if(active&&draft)setSelected(draft.selectedAnswers);
    });
    return()=>{active=false};
  },[question,sessionId,userId]);

  if (!question) {
    const summary = session.summary;
    if (!summary?.finalized) {
      return <div className="state"><strong>모든 문제를 풀었습니다</strong><span>오답 노트를 한 번에 정리해 주세요.</span><button className="button" disabled={movingNext} onClick={() => void moveNext(true)}>학습 결과 정리</button>{completeError&&<span className="form-error">{completeError.message}</span>}</div>;
    }
    const masteredRetry = Boolean(session.retry_of_session_id && summary.wrong_count === 0);
    return <div className="state study-summary"><strong>학습을 완료했습니다</strong><div className="metrics"><article><small>총 풀이</small><b>{summary.answered_count}</b></article><article><small>정답</small><b>{summary.correct_count}</b></article><article><small>오답</small><b>{summary.wrong_count}</b></article></div><span>{masteredRetry ? '모든 오답을 맞혔습니다. 완료한 오답노트를 확인해 주세요.' : `틀린 문제 ${summary.wrong_count}개가 오답 노트에 한 번에 반영되었습니다.`}</span>{masteredRetry && <button className="button" type="button" onClick={() => void onReturnToWrongNotes()}>오답노트로 돌아가기</button>}</div>;
  }

  const multiple = question.question_type === 'multiple_response';
  const choose = (choiceId: string) => setSelected(current => {
    const next=multiple
      ? (current.includes(choiceId)
        ? current.filter(item => item !== choiceId)
        : current.length < question.required_answer_count ? [...current, choiceId] : current)
      : (current.includes(choiceId) ? [] : [choiceId]);
    void saveAnswerDraft({userId,kind:'study',sessionId,questionId:question.id,selectedAnswers:next,currentIndex:session.current_index,pending:true});
    return next;
  });
  return <>
    <PageHeader
      eyebrow="집중 학습"
      title={`${session.current_index + 1} / ${session.total_questions}`}
      action={<span className="badge">{multiple ? `${question.required_answer_count}개 선택` : '1개 선택'}</span>}
    />
    <Progress label="학습 진도" value={(session.current_index / session.total_questions) * 100} />
    <section className="question" ref={questionRef}>
      <p className="question-en">{question.question_en}</p>
      <h2>{question.question_ko}</h2>
      <fieldset disabled={Boolean(result)}>
        <legend className="sr-only">답안 선택</legend>
        {question.choices.map(choice => {
          const checked = selected.includes(choice.id);
          const correct = result?.correct_answers.includes(choice.id);
          return <label key={choice.id} className={`choice ${checked ? 'selected' : ''} ${correct ? 'correct' : ''} ${result && checked && !correct ? 'incorrect' : ''}`}>
            <input type="checkbox" role={multiple ? undefined : 'radio'} name="answer" checked={checked} onChange={() => choose(choice.id)} />
            <b>{choice.id}</b>
            <span>{choice.text_ko}<small>{choice.text_en}</small></span>
            {result && correct && <em className="choice-status correct-status">정답</em>}
            {result && checked && !correct && <em className="choice-status incorrect-status">내 선택 · 오답</em>}
          </label>;
        })}
      </fieldset>
      {result && <div className={`feedback ${result.is_correct ? 'success' : 'danger'}`} role="status">
        <div><b>{result.is_correct ? '정답입니다!' : '아쉬워요. 다시 기억해 두세요.'}</b><p>{result.explanation?.core_reason ?? '정답과 선택지를 비교해 보세요.'}</p></div>
        <button className="ai-explanation-button" type="button" disabled={explanation.isPending || Boolean(explanation.data)} onClick={() => explanation.mutate()}>{explanation.isPending ? '생성 중…' : explanation.data ? '해설 생성 완료' : 'AI 해설'}</button>
      </div>}
      {explanation.data && <ExplanationCard explanation={explanation.data} question={question} selected={selected} correctAnswers={result?.correct_answers ?? []} />}
      {explanation.isError && <div className="ai-explanation-error" role="alert"><b>AI 해설을 생성하지 못했습니다.</b><span>{explanation.error.message}</span><button type="button" onClick={() => explanation.mutate()}>다시 시도</button></div>}
      <div className="actions study-question-actions">
        <button type="button" onClick={onExit}>학습 나가기</button>
        <button className="button secondary" type="button" onClick={() => setReportOpen(true)}>문제 신고</button>
        {!result
          ? <button className="button" disabled={!selected.length || submit.isPending} onClick={() => submit.mutate()}>{submit.isPending ? '채점 중…' : '정답 확인'}</button>
          : <button className="button" disabled={movingNext} onClick={() => void moveNext(session.current_index + 1 >= session.total_questions)}>{movingNext ? '정리하는 중…' : session.current_index + 1 >= session.total_questions ? '학습 결과 보기' : '다음 문제'}</button>}
      </div>
      {submit.isError && <ErrorState error={submit.error} />}
      {completeError && <ErrorState error={completeError} />}
    </section>
    {reportOpen && <ReportModal questionId={question.id} onClose={() => setReportOpen(false)} />}
    {explanation.isPending && <div className="grading-overlay ai-loading-overlay" role="alertdialog" aria-modal="true" aria-live="assertive" tabIndex={-1} autoFocus><LoaderCircle className="spin"/><strong>AI 해설 생성 중입니다.</strong><span>문제와 선택지를 분석하고 있습니다. 잠시만 기다려 주세요.</span><div className="loading-bar" aria-hidden="true"><i/></div></div>}
  </>;
}

function ExplanationCard({ explanation, question, selected, correctAnswers }: {
  explanation: Explanation;
  question: Question;
  selected: string[];
  correctAnswers: string[];
}) {
  return <section className="ai-explanation" aria-labelledby="ai-explanation-title">
    <header><div><span>AI GENERATED</span><h3 id="ai-explanation-title">AI 해설</h3></div>{explanation.keywords_json.length > 0 && <div className="explanation-keywords">{explanation.keywords_json.map(keyword => <em key={keyword}>{keyword}</em>)}</div>}</header>
    <div className="explanation-summary"><strong>핵심 해설</strong><p>{explanation.core_reason}</p><small>{explanation.correct_answer_summary}</small></div>
    <div className="choice-analysis"><h4>선택지별 설명</h4>{question.choices.map(choice => <article key={choice.id} className={correctAnswers.includes(choice.id) ? 'answer-correct' : selected.includes(choice.id) ? 'answer-selected' : ''}>
      <b>{choice.id}</b><div><span>{correctAnswers.includes(choice.id) ? '정답' : selected.includes(choice.id) ? '내가 고른 오답' : '다른 선택지'}</span><p>{explanation.choice_analysis_json[choice.id] ?? '이 선택지에 대한 해설이 없습니다.'}</p></div>
    </article>)}</div>
    <div className="explanation-notes"><div><strong>시험 포인트</strong><p>{explanation.exam_traps}</p></div><div><strong>함께 기억할 개념</strong><p>{explanation.related_concepts}</p></div></div>
    <footer><strong>한 줄 암기</strong><span>{explanation.memory_summary}</span></footer>
  </section>;
}
