import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { endpoints } from './api/queries';
import { ApiError } from './api/client';
import { Loading } from './components/common';
import { ContentProtection } from './components/ContentProtection';
import { Layout } from './components/Layout';
import { SESSION_EXPIRED_EVENT, SessionActivity } from './components/SessionActivity';
import { Admin } from './pages/Admin';
import { CertificationDetail, Certifications } from './pages/Certifications';
import { Dashboard } from './pages/Dashboard';
import { Login } from './pages/Login';
import { MockExamSession, MockExamSetup } from './pages/MockExam';
import { PasskeyGate } from './pages/PasskeyGate';
import { Results } from './pages/Results';
import { Study } from './pages/Study';
import { WrongNotes } from './pages/WrongNotes';

export function App() {
  const me = useQuery({ queryKey: ['me'], queryFn: endpoints.me, retry: false });
  const [sessionExpired, setSessionExpired] = useState(false);
  const [showExpirationNotice, setShowExpirationNotice] = useState(false);
  const unauthenticated = me.error instanceof ApiError && me.error.status === 401;
  useEffect(() => {
    const expire = () => { setSessionExpired(true); setShowExpirationNotice(true); };
    window.addEventListener(SESSION_EXPIRED_EVENT, expire);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expire);
  }, []);
  useEffect(()=>{
    if(!me.isError||unauthenticated)return;
    const timer=window.setInterval(()=>void me.refetch(),5_000);
    return()=>window.clearInterval(timer);
  },[me.isError,me.refetch,unauthenticated]);
  let content;
  if (sessionExpired) content = <Routes><Route path="*" element={<Login onAuthenticated={() => { setSessionExpired(false); setShowExpirationNotice(false); }} />} /></Routes>;
  else if (me.isLoading) content = <main className="login-page"><Loading /></main>;
  else if (unauthenticated) content = <Routes><Route path="*" element={<Login />} /></Routes>;
  else if (!me.data) content = <main className="login-page"><div className="state error" role="alert"><strong>서버 연결이 일시적으로 끊겼습니다</strong><span>현재 화면과 임시 답안을 유지한 채 자동으로 다시 연결합니다.</span><button onClick={() => void me.refetch()}>다시 연결</button></div></main>;
  else if (me.data.passkey_registration_required || me.data.passkey_authentication_required) content = <PasskeyGate user={me.data} />;
  else content = <Routes>
    <Route element={<Layout />}>
      <Route index element={<Dashboard />} />
      <Route path="certifications" element={<Certifications />} />
      <Route path="certifications/:code" element={<CertificationDetail />} />
      <Route path="study/new" element={<Study />} />
      <Route path="study/:id" element={<Study />} />
      <Route path="mock-exam" element={<MockExamSetup />} />
      <Route path="mock-exam/:id" element={<MockExamSession />} />
      <Route path="results/:id" element={<Results />} />
      <Route path="results/:id/review" element={<Results />} />
      <Route path="wrong-notes" element={<WrongNotes />} />
      <Route path="admin" element={me.data.role === 'admin' ? <Admin /> : <Navigate to="/" replace />} />
      <Route path="*" element={<div className="state"><strong>페이지를 찾을 수 없습니다.</strong><a href="/">대시보드로 이동</a></div>} />
    </Route>
  </Routes>;
  return <ContentProtection enabled={me.data?.role !== 'admin'}>
    {me.data && !sessionExpired && !me.data.passkey_registration_required && !me.data.passkey_authentication_required && <SessionActivity />}
    {me.data&&me.isError&&!unauthenticated&&<div className="connection-banner global-connection-banner" role="status">서버 연결이 끊겼습니다. 현재 답안을 이 기기에 보관하고 재연결 중입니다.</div>}
    {content}
    {showExpirationNotice && <div className="modal-backdrop"><section className="modal session-expired-modal" role="alertdialog" aria-modal="true" aria-labelledby="session-expired-title"><p className="eyebrow">로그인 안내</p><h2 id="session-expired-title">세션이 만료되었습니다</h2><p>30분 동안 활동이 없어 자동으로 로그아웃되었습니다. 다시 로그인해 주세요.</p><div className="actions"><button className="button" onClick={() => setShowExpirationNotice(false)}>확인</button></div></section></div>}
  </ContentProtection>;
}
