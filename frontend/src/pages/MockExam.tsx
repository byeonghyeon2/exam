import { useMutation, useQuery } from '@tanstack/react-query';
import { Clock3, LoaderCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { endpoints } from '../api/queries';
import { ErrorState, Loading, PageHeader, Progress } from '../components/common';

export function MockExamSetup() {
  const navigate = useNavigate();
  const certifications = useQuery({ queryKey: ['certifications'], queryFn: endpoints.certifications });
  const [code, setCode] = useState('');
  const create = useMutation({ mutationFn: () => endpoints.createExam({ certification_code: code }), onSuccess: exam => navigate(`/mock-exam/${exam.id}`) });
  return <>
    <PageHeader eyebrow="실전 점검" title="모의고사" description="실제 시험 시간과 문항 수를 적용합니다. 제출 전에는 정답을 확인할 수 없습니다." />
    <section className="panel form"><label>응시 자격증<select value={code} onChange={event => setCode(event.target.value)}><option value="">선택해 주세요</option>{certifications.data?.map(certification => <option key={certification.code} value={certification.code}>{certification.name_ko}</option>)}</select></label><div className="notice"><Clock3 /> 시험이 시작되면 타이머가 작동하며 시간이 끝나면 자동 제출됩니다.</div><button className="button" disabled={!code || create.isPending} onClick={() => create.mutate()}>{create.isPending ? '시험 생성 중…' : '모의고사 시작'}</button>{create.isError && <ErrorState error={create.error} />}</section>
  </>;
}

export function MockExamSession() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const questions = useQuery({ queryKey: ['exam-questions', id], queryFn: () => endpoints.examQuestions(id) });
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string[]>>({});
  const [seconds, setSeconds] = useState(7800);
  const submit = useMutation({
    mutationFn: async () => {
      await Promise.all(Object.entries(answers).map(([questionId, selected]) => endpoints.saveAnswer(id, Number(questionId), selected)));
      return endpoints.submitExam(id);
    },
    onSuccess: () => navigate(`/results/${id}`),
  });
  const { mutate: submitExam } = submit;

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
  const question = questions.data![index];
  if (!question) return <ErrorState error={new Error('시험 문제가 없습니다.')} />;
  const selected = answers[question.id] ?? [];
  const choose = (choiceId: string) => {
    if (submit.isPending) return;
    const multiple = question.question_type === 'multiple_response';
    const next = multiple ? (selected.includes(choiceId) ? selected.filter(item => item !== choiceId) : [...selected, choiceId]) : [choiceId];
    setAnswers(current => ({ ...current, [question.id]: next }));
    void endpoints.saveAnswer(id, question.id, next);
  };

  return <>
    <div className="exam-content" aria-busy={submit.isPending}>
      <div className="exam-bar"><b>모의고사</b><span className="timer"><Clock3 /> {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</span><button disabled={submit.isPending} onClick={() => submitExam()}>시험 제출</button></div>
      <Progress label="시험 진행" value={((index + 1) / questions.data!.length) * 100} />
      <section className="question"><span className="badge">문제 {index + 1} · {question.question_type === 'multiple_response' ? '복수 선택' : '단일 선택'}</span><p className="question-en">{question.question_en}</p><h2>{question.question_ko}</h2><fieldset disabled={submit.isPending}><legend className="sr-only">답안</legend>{question.choices.map(choice => <label key={choice.id} className={`choice ${selected.includes(choice.id) ? 'selected' : ''}`}><input type={question.question_type === 'multiple_response' ? 'checkbox' : 'radio'} checked={selected.includes(choice.id)} onChange={() => choose(choice.id)} /><b>{choice.id}</b><span>{choice.text_ko}<small>{choice.text_en}</small></span></label>)}</fieldset><div className="actions"><button disabled={submit.isPending || index === 0} onClick={() => setIndex(current => current - 1)}>이전</button><button className="button" disabled={submit.isPending || index === questions.data!.length - 1} onClick={() => setIndex(current => current + 1)}>다음 문제</button></div></section>
      <div className="palette" aria-label="문제 이동">{questions.data!.map((item, itemIndex) => <button disabled={submit.isPending} aria-label={`${itemIndex + 1}번 문제`} className={`${itemIndex === index ? 'current' : ''} ${answers[item.id]?.length ? 'answered' : ''}`} key={item.id} onClick={() => setIndex(itemIndex)}>{itemIndex + 1}</button>)}</div>
      {submit.isError && <ErrorState error={submit.error} />}
    </div>
    {submit.isPending && <div className="grading-overlay" role="alert" aria-live="assertive"><LoaderCircle className="spin" /><strong>채점중입니다.</strong><span>답안을 확인하고 결과를 계산하고 있습니다.</span></div>}
  </>;
}
