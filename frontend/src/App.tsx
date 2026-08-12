import { useQuery } from '@tanstack/react-query';
import { Navigate, Route, Routes } from 'react-router-dom';
import { endpoints } from './api/queries';
import { Loading } from './components/common';
import { ContentProtection } from './components/ContentProtection';
import { Layout } from './components/Layout';
import { Admin } from './pages/Admin';
import { CertificationDetail, Certifications } from './pages/Certifications';
import { Dashboard } from './pages/Dashboard';
import { Login } from './pages/Login';
import { MockExamSession, MockExamSetup } from './pages/MockExam';
import { Results } from './pages/Results';
import { Study } from './pages/Study';
import { WrongNotes } from './pages/WrongNotes';

export function App() {
  const me = useQuery({ queryKey: ['me'], queryFn: endpoints.me, retry: false });
  if (me.isLoading) return <main className="login-page"><Loading /></main>;
  if (!me.data) return <Routes><Route path="*" element={<Login />} /></Routes>;
  return <ContentProtection><Routes>
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
  </Routes></ContentProtection>;
}
