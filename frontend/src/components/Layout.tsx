import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, ClipboardCheck, LayoutDashboard, LogOut, Moon, NotebookTabs, Settings, Sun } from 'lucide-react';
import { type MouseEvent, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { endpoints } from '../api/queries';
import { useUI } from '../stores/ui';
import { StudyExitGuardContext, type StudyExitGuard } from './StudyExitGuard';

const nav = [['/', '대시보드', LayoutDashboard], ['/certifications', '자격증', BookOpen], ['/mock-exam', '모의고사', ClipboardCheck], ['/wrong-notes', '오답노트', NotebookTabs]] as const;

export function Layout() {
  const { dark, toggleDark } = useUI();
  const client = useQueryClient();
  const navigate = useNavigate();
  const { data: user } = useQuery({ queryKey: ['me'], queryFn: endpoints.me });
  const [guard, setGuard] = useState<StudyExitGuard | null>(null);
  const [destination, setDestination] = useState<string | null>(null);
  const [leaving, setLeaving] = useState<'save' | 'discard' | null>(null);
  const [leaveError, setLeaveError] = useState<Error | null>(null);
  const logout = useMutation({ mutationFn: endpoints.logout, onSettled: () => { client.clear(); window.location.assign('/'); } });
  const requestExit = (to: string) => {
    if (guard) { setDestination(to); setLeaveError(null); }
    else navigate(to);
  };
  const requestNavigation = (event: MouseEvent<HTMLAnchorElement>, to: string) => {
    if (!guard) return;
    event.preventDefault(); requestExit(to);
  };
  const leaveAndNavigate = async (save: boolean) => {
    if (!guard || !destination) return;
    setLeaving(save ? 'save' : 'discard'); setLeaveError(null);
    try {
      await (save ? guard.saveAndLeave() : guard.discardAndLeave());
      const target = destination; setGuard(null); setDestination(null);
      await client.invalidateQueries({ queryKey: ['study-history'] });
      navigate(target);
    } catch (error) { setLeaveError(error instanceof Error ? error : new Error('학습 종료를 처리하지 못했습니다.')); }
    finally { setLeaving(null); }
  };
  return <StudyExitGuardContext.Provider value={{ setGuard, requestExit }}><div className={dark ? 'app dark' : 'app'}>
    <a className="skip" href="#main">본문 바로가기</a>
    <aside><NavLink to="/" className="brand" onClick={event => requestNavigation(event, '/')}><span>CE</span><div><b>CertFlow</b><small>시험 준비의 흐름</small></div></NavLink>
      <nav aria-label="주 메뉴">{nav.map(([to, label, Icon]) => <NavLink key={to} to={to} end={to === '/'} onClick={event => requestNavigation(event, to)}><Icon size={19} />{label}</NavLink>)}{user?.role === 'admin' && <NavLink to="/admin" onClick={event => requestNavigation(event, '/admin')}><Settings size={19} />관리</NavLink>}</nav>
      <div className="sidebar-actions"><button className="theme" onClick={toggleDark}>{dark ? <Sun /> : <Moon />}<span>{dark ? '라이트 모드' : '다크 모드'}</span></button><button className="theme" onClick={() => logout.mutate()} disabled={logout.isPending}><LogOut /><span>로그아웃</span></button></div>
    </aside>
    <div className="shell"><header className="top"><span className="mobile-brand">CertFlow</span><span className="current-user"><b>{user?.username}</b><small>{user?.role === 'admin' ? '관리자' : '학습자'}</small></span><span className="status"><i /> API 연결 모드</span><div className="top-actions"><button className="theme" aria-label={dark ? '라이트 모드' : '다크 모드'} onClick={toggleDark}>{dark ? <Sun /> : <Moon />}</button><button className="theme" aria-label="로그아웃" onClick={() => logout.mutate()} disabled={logout.isPending}><LogOut /></button></div></header><main id="main"><Outlet /></main></div>
  </div>{destination && guard && <div className="modal-backdrop"><section className="modal study-exit-modal" role="dialog" aria-modal="true" aria-labelledby="study-exit-title"><p className="eyebrow">학습 종료</p><h2 id="study-exit-title">학습을 중단하고 이동할까요?</h2><p>메뉴로 나가면 현재까지 푼 결과는 오답노트에 자동 저장되지 않습니다. 지금까지의 결과를 저장할지 선택해 주세요.</p><p className="muted">현재까지 {guard.answeredCount}문제를 풀었습니다.</p>{leaveError && <p className="form-error" role="alert">{leaveError.message}</p>}<div className="study-exit-actions"><button className="button" disabled={guard.answeredCount === 0 || Boolean(leaving)} onClick={() => void leaveAndNavigate(true)}>{leaving === 'save' ? '저장 중…' : '저장 후 나가기'}</button><button className="button secondary danger-button" disabled={Boolean(leaving)} onClick={() => void leaveAndNavigate(false)}>{leaving === 'discard' ? '이동 중…' : '저장하지 않고 나가기'}</button><button disabled={Boolean(leaving)} onClick={() => setDestination(null)}>계속 학습</button></div></section></div>}</StudyExitGuardContext.Provider>;
}
