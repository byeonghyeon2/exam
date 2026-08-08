import { useMutation, useQuery } from '@tanstack/react-query';
import { AlertCircle, RotateCcw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { endpoints } from '../api/queries';
import { Empty, ErrorState, Loading, PageHeader } from '../components/common';

function formatStudyTime(value: string) {
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(normalized));
}

export function WrongNotes() {
  const navigate = useNavigate();
  const query = useQuery({ queryKey: ['study-history'], queryFn: endpoints.studyHistory });
  const retry = useMutation({
    mutationFn: endpoints.retryStudyHistory,
    onSuccess: session => navigate(`/study/${session.id}`),
  });
  const histories = query.data ?? [];

  return <>
    <PageHeader eyebrow="학습 기록" title="오답노트" description="한 번의 학습을 하나의 묶음으로 확인하고, 틀린 문제만 다시 풀어보세요." />
    {query.isLoading ? <Loading /> : query.isError ? <ErrorState error={query.error} retry={() => void query.refetch()} /> : !histories.length
      ? <Empty>완료한 학습에서 틀린 문제가 생기면 학습 묶음이 여기에 표시됩니다.</Empty>
      : <div className="wrong-session-list">{histories.map((history, index) => <section className="wrong-session-card" key={history.session_id}>
        <header>
          <div><span className="badge">{history.certification_code}</span><h2>학습 기록 #{histories.length - index}</h2><p>{history.certification_name} · {formatStudyTime(history.completed_at)}</p></div>
          <button className="button" disabled={retry.isPending} onClick={() => retry.mutate(history.session_id)}><RotateCcw size={17} />{retry.isPending && retry.variables === history.session_id ? '준비 중…' : `${history.wrong_count}문제 다시 풀기`}</button>
        </header>
        <div className="session-metrics" aria-label="학습 결과 요약">
          <div><small>총 문제</small><b>{history.total_count}</b></div><div><small>정답</small><b>{history.correct_count}</b></div><div className="wrong-count"><small>오답</small><b>{history.wrong_count}</b></div>
        </div>
        <div className="wrong-question-group"><h3><AlertCircle size={18} /> 틀린 문제</h3><ol>{history.wrong_questions.map(question => <li key={question.id}><span>{question.question_uid}</span><p>{question.question_ko}</p></li>)}</ol></div>
      </section>)}</div>}
    {retry.isError && <ErrorState error={retry.error} />}
  </>;
}
