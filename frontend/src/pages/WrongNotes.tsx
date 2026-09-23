import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpenCheck, ChevronLeft, ChevronRight, CircleHelp, RotateCcw, Sparkles, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { endpoints } from '../api/queries';
import type { StudyHistory } from '../types';
import { Empty, ErrorState, Loading, PageHeader } from '../components/common';

const PAGE_SIZE = 10;

function formatStudyTime(value: string) {
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(normalized));
}

function ConceptSummaryCard({ certificationCode, certificationName }: { certificationCode: string; certificationName: string }) {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ['ai-concept-summary', certificationCode], queryFn: () => endpoints.conceptSummary(certificationCode) });
  const generate = useMutation({ mutationFn: () => endpoints.generateConceptSummary(certificationCode), onSuccess: result => queryClient.setQueryData(['ai-concept-summary', certificationCode], result) });
  const data = status.data;
  const result = data?.result;
  const progress = data ? `완료 답안 ${data.answer_count}/${data.minimum_answer_count}문제` : '분석 가능 여부를 확인하는 중입니다.';

  if (status.isError || (!status.isLoading && !data)) return null;

  return <section className="concept-summary-card" aria-label={`${certificationName} 오답 패턴 분석`}>
    <header className="concept-summary-header">
      <div><span className="section-eyebrow"><Sparkles size={14} /> AI 학습 분석</span><h2>{certificationName} 오답 패턴 분석</h2><p>자주 고른 오답과 약점 개념을 자격증별로 분석합니다.</p></div>
      <div className="concept-summary-actions">
        <span className="concept-help-wrap">
          <button className="icon-button concept-help-button" type="button" aria-label={`${certificationName} 오답 패턴 분석 안내`} aria-describedby={`concept-help-${certificationCode}`}><CircleHelp size={19} /></button>
          <span className="concept-help-tooltip" id={`concept-help-${certificationCode}`} role="tooltip"><strong><BookOpenCheck size={16} /> 오답 패턴 분석 기준</strong><span>완료한 학습 및 오답노트 재학습 답안이 10문제 이상이면 분석할 수 있습니다.</span><span>정답률, 자주 틀리는 단원, 반복 선택한 오답 보기를 바탕으로 복습 우선순위를 안내합니다.</span><em>{progress}</em></span>
        </span>
        <button className="button" disabled={!data?.can_generate || generate.isPending} onClick={() => generate.mutate()}><Sparkles size={17} />{generate.isPending ? '분석 생성 중…' : result ? '분석 갱신' : '오답 패턴 분석'}</button>
      </div>
    </header>
    {status.isLoading ? <p className="muted">활성화 조건을 확인하고 있습니다.</p> : data ? <>
      <div className="concept-progress" aria-label="오답 패턴 분석 진행도"><span>완료 답안 <b>{data.answer_count}/{data.minimum_answer_count}</b>문제</span><span>{data.can_generate ? '분석 가능' : '답안이 더 필요합니다'}</span></div>
      {result && <div className="concept-result"><p className="concept-overview">{result.summary.overview}</p><div className="concept-weaknesses">{result.summary.weaknesses.map(item => <article key={item.domain}><h3>{item.domain}</h3><p>{item.diagnosis}</p><div className="concept-tags">{item.concepts.map(concept => <span key={concept}>{concept}</span>)}</div><ul>{item.actions.map(action => <li key={action}>{action}</li>)}</ul></article>)}</div><div className="concept-detail-grid"><section><h3>우선 복습 개념</h3><div className="concept-tags">{result.summary.priority_concepts.map(concept => <span key={concept}>{concept}</span>)}</div></section><section><h3>추천 학습 순서</h3><ol>{result.summary.study_plan.map(step => <li key={step}>{step}</li>)}</ol></section></div>{result.summary.related_questions.length > 0 && <details className="wrong-question-details concept-questions"><summary>분석에 반영된 오답 문제 보기 ({result.summary.related_questions.length})</summary><ol>{result.summary.related_questions.map(question => <li key={question.question_id}><b>{question.question_uid}</b> · {question.concept}<small>{question.why_review}</small></li>)}</ol></details>}<p className="concept-memory-summary"><b>기억하기</b> {result.summary.memory_summary}</p></div>}
    </> : null}
    {generate.isError && <p className="inline-error">오답 패턴 분석 생성에 실패했습니다. 잠시 후 다시 시도해주세요.</p>}
  </section>;
}

function HistoryCard({ history, index, total, isPending, retryingId, deletingId, onRetry, onDelete }: { history: StudyHistory; index: number; total: number; isPending: boolean; retryingId?: string; deletingId?: string; onRetry: (sessionId: string) => void; onDelete: (sessionId: string) => void }) {
  return <section className="wrong-session-card"><header><div><span className={`badge ${history.wrong_count === 0 ? 'success' : ''}`}>{history.wrong_count === 0 ? '모두 맞힘' : history.certification_code}</span><h2>학습 기록 #{total - index}</h2><p>{history.certification_name} · {formatStudyTime(history.completed_at)}</p></div><div className="wrong-session-actions"><button className="button secondary delete-button" disabled={isPending} onClick={() => window.confirm('이 오답노트를 삭제할까요? 삭제한 기록은 복구할 수 없습니다.') && onDelete(history.session_id)}><Trash2 size={17} />{deletingId === history.session_id ? '삭제 중…' : '삭제'}</button>{history.wrong_count > 0 && <button className="button" disabled={isPending} onClick={() => onRetry(history.session_id)}><RotateCcw size={17} />{retryingId === history.session_id ? '준비 중…' : `${history.wrong_count}문제 다시 풀기`}</button>}</div></header><div className="session-metrics" aria-label="학습 결과 요약"><div><small>총 문제</small><b>{history.total_count}</b></div><div><small>정답</small><b>{history.correct_count}</b></div><div className="wrong-count"><small>오답</small><b>{history.wrong_count}</b></div></div>{history.wrong_questions.length > 0 && <details className="wrong-question-details"><summary>틀린 문제 보기 ({history.wrong_questions.length})</summary><ol>{history.wrong_questions.map(question => <li key={question.id}><b>{question.question_uid}</b><span>{question.question_ko}</span></li>)}</ol></details>}</section>;
}

export function WrongNotes() {
  const navigate = useNavigate(); const queryClient = useQueryClient(); const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ['study-history'], queryFn: endpoints.studyHistory });
  const retry = useMutation({ mutationFn: endpoints.retryStudyHistory, onSuccess: session => navigate(`/study/${session.id}`) });
  const remove = useMutation({ mutationFn: endpoints.deleteStudyHistory, onSuccess: (_result, sessionId) => { queryClient.setQueryData(['study-history'], (current: typeof query.data) => current?.filter(history => history.session_id !== sessionId)); void queryClient.invalidateQueries({ queryKey: ['study-history'] }); } });
  const histories = query.data ?? [];
  const certifications = useMemo(() => Array.from(new Map(histories.map(history => [history.certification_code, history])).values()), [histories]);
  const pageCount = Math.max(1, Math.ceil(histories.length / PAGE_SIZE));
  const visibleHistories = histories.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  useEffect(() => setPage(current => Math.min(current, pageCount)), [pageCount]);

  return <><PageHeader eyebrow="학습 기록" title="오답노트" description="한 번의 학습을 하나의 묶음으로 확인하고, 틀린 문제만 다시 풀어보세요." />{query.isLoading ? <Loading /> : query.isError ? <ErrorState error={query.error} retry={() => void query.refetch()} /> : !histories.length ? <Empty>완료한 학습에서 틀린 문제가 생기면 학습 묶음이 여기에 표시됩니다.</Empty> : <><div className="concept-summary-list">{certifications.map(history => <ConceptSummaryCard key={history.certification_code} certificationCode={history.certification_code} certificationName={history.certification_name} />)}</div><div className="wrong-session-list">{visibleHistories.map((history, index) => <HistoryCard key={history.session_id} history={history} index={(page - 1) * PAGE_SIZE + index} total={histories.length} isPending={retry.isPending || remove.isPending} retryingId={retry.variables} deletingId={remove.variables} onRetry={retry.mutate} onDelete={remove.mutate} />)}</div>{pageCount > 1 && <nav className="wrong-notes-pagination" aria-label="오답노트 페이지"><button className="button secondary" disabled={page === 1} onClick={() => setPage(value => value - 1)}><ChevronLeft size={17} />이전</button><span>{page} / {pageCount}</span><button className="button secondary" disabled={page === pageCount} onClick={() => setPage(value => value + 1)}>다음<ChevronRight size={17} /></button></nav>}</>}{(retry.isError || remove.isError) && <ErrorState error={retry.error ?? remove.error} />}</>;
}
