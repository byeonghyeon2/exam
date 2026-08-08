import { useQuery } from '@tanstack/react-query';
import { ArrowRight, BookOpen, ClipboardCheck, NotebookTabs, Sparkles, X } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { siSnowflake } from 'simple-icons';
import { endpoints } from '../api/queries';
import { ErrorState, Loading, PageHeader } from '../components/common';
import type { Certification } from '../types';

function providerName(certification: Certification) {
  const name = `${certification.name_en} ${certification.name_ko}`.toLowerCase();
  if (name.includes('snowflake')) return 'snowflake';
  if (name.includes('aws') || name.includes('amazon web services')) return 'aws';
  return null;
}

function CertificationMark({ certification }: { certification: Certification }) {
  const [imageFailed, setImageFailed] = useState(false);
  const provider = providerName(certification);
  if (provider === 'aws' && !imageFailed) return <img className="aws-logo" src="/brands/aws-logo.png" alt="Amazon Web Services" onError={() => setImageFailed(true)} />;
  if (provider === 'snowflake') return <svg aria-label={siSnowflake.title} role="img" viewBox="0 0 24 24" style={{ color: `#${siSnowflake.hex}` }}><path d={siSnowflake.path} fill="currentColor" /></svg>;
  return <BookOpen aria-label={`${certification.code} 자격증`} role="img" />;
}

function CertificationModal({ certifications, onClose }: { certifications: Certification[]; onClose: () => void }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={event => event.target === event.currentTarget && onClose()}>
    <section className="modal certification-modal" role="dialog" aria-modal="true" aria-labelledby="certification-modal-title">
      <div className="modal-heading">
        <div><p className="eyebrow">Available certifications</p><h2 id="certification-modal-title">학습 가능 자격증</h2></div>
        <button className="icon-button" type="button" aria-label="닫기" onClick={onClose}><X /></button>
      </div>
      <div className="certification-list">
        {certifications.map(certification => <Link key={certification.code} to={`/certifications/${certification.code}`} onClick={onClose}>
          <span className="provider-mark"><CertificationMark certification={certification} /></span>
          <span><small>{certification.code}</small><b>{certification.name_ko || certification.name_en}</b><em>{certification.name_en}</em></span>
          <ArrowRight aria-hidden="true" />
        </Link>)}
      </div>
    </section>
  </div>;
}

export function Dashboard() {
  const [certificationsOpen, setCertificationsOpen] = useState(false);
  const query = useQuery({ queryKey: ['certifications'], queryFn: endpoints.certifications });
  const certifications = query.data ?? [];
  return <>
    <PageHeader eyebrow="오늘의 학습" title="합격까지, 한 문제씩 선명하게." description="학습할 자격증을 고르고 현재 이해도를 점검해 보세요." />
    <section className="hero">
      <div><Sparkles /><p>집중 학습</p><h2>짧게 반복하고,<br />확실하게 기억하세요.</h2><Link className="button light" to="/certifications">학습 시작 <ArrowRight size={18} /></Link></div>
      <button className="hero-ring certification-trigger" type="button" disabled={!query.data} aria-haspopup="dialog" aria-expanded={certificationsOpen} aria-label={`학습 가능 자격증 ${certifications.length}개 보기`} onClick={() => setCertificationsOpen(true)}>
        <b>{query.data ? certifications.length : '—'}</b><span>학습 가능 자격증</span>
      </button>
    </section>
    <div className="section-title"><h2>자격증 현황</h2><Link to="/certifications">전체 보기 →</Link></div>
    {query.isLoading ? <Loading /> : query.isError ? <ErrorState error={query.error} retry={() => void query.refetch()} /> : <div className="cards">{certifications.map((certification, index) => <article className="cert-card" key={certification.code}>
      <div className={`cert-icon color-${index % 2}`}><CertificationMark certification={certification} /></div><span className="badge">{certification.exam_version}</span><h3>{certification.name_ko}</h3><p>{certification.name_en}</p>
      <dl><div><dt>문제 수</dt><dd>{certification.question_count ?? certification.default_question_count}문제</dd></div><div><dt>시험 시간</dt><dd>{certification.default_duration_minutes}분</dd></div></dl>
      <Link to={`/certifications/${certification.code}`}>자세히 보기 <ArrowRight size={16} /></Link>
    </article>)}</div>}
    <div className="quick"><Link to="/mock-exam"><ClipboardCheck /><span><b>실전 모의고사</b><small>실제 시험 조건으로 점검하기</small></span><ArrowRight /></Link><Link to="/wrong-notes"><NotebookTabs /><span><b>오답 다시 보기</b><small>틀린 문제를 내 것으로 만들기</small></span><ArrowRight /></Link></div>
    {certificationsOpen && <CertificationModal certifications={certifications} onClose={() => setCertificationsOpen(false)} />}
  </>;
}
