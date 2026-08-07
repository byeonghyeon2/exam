import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { endpoints } from '../api/queries';
import { Empty, ErrorState, Loading, PageHeader, Progress } from '../components/common';

export function Certifications() {
  const query = useQuery({ queryKey: ['certifications'], queryFn: endpoints.certifications });
  return <>
    <PageHeader eyebrow="시험 선택" title="어떤 자격증을 준비하나요?" description="공식 시험 설정에 맞춘 학습 과정입니다." />
    {query.isLoading ? <Loading /> : query.isError ? <ErrorState error={query.error} /> : !query.data?.length
      ? <Empty>관리자에서 자격증을 활성화해 주세요.</Empty>
      : <div className="cards">{query.data.map(certification => <article className="cert-card" key={certification.code}>
        <span className="badge">{certification.code}</span>
        <h2>{certification.name_ko}</h2><p>{certification.name_en}</p>
        <dl><div><dt>문항</dt><dd>{certification.default_question_count}</dd></div><div><dt>시간</dt><dd>{certification.default_duration_minutes}분</dd></div><div><dt>합격 기준</dt><dd>{certification.passing_score}</dd></div></dl>
        <Link className="button" to={`/certifications/${certification.code}`}>학습 과정 보기</Link>
      </article>)}</div>}
  </>;
}

export function CertificationDetail() {
  const { code = '' } = useParams();
  const certification = useQuery({ queryKey: ['certification', code], queryFn: () => endpoints.certification(code) });
  const domains = useQuery({ queryKey: ['domains', code], queryFn: () => endpoints.domains(code) });
  if (certification.isLoading) return <Loading />;
  if (certification.isError) return <ErrorState error={certification.error} />;
  const cert = certification.data!;
  return <>
    <PageHeader eyebrow={cert.code} title={cert.name_ko} description={`${cert.default_duration_minutes}분 · ${cert.default_question_count}문항 · 합격 기준 ${cert.passing_score}`} action={<Link className="button" to={`/study/new?cert=${code}`}>랜덤 10문제</Link>} />
    <section className="panel"><h2>시험 영역</h2>
      {domains.isLoading ? <Loading /> : domains.isError ? <ErrorState error={domains.error} /> : domains.data!.map(domain => <div className="domain" key={domain.id}>
        <div><b>{domain.name_ko}</b><small>{domain.name_en}</small></div>
        <Progress label={`${domain.name_ko} 출제 비중`} value={domain.exam_weight} />
        <Link className="button domain-study" to={`/study/new?cert=${code}&domain=${domain.domain_code}&all=true`}>학습하기</Link>
      </div>)}
    </section>
  </>;
}
