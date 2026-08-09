import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {BookOpen,ClipboardCheck,LayoutDashboard,LogOut,Moon,NotebookTabs,Settings,Sun} from 'lucide-react';
import {NavLink,Outlet} from 'react-router-dom';
import {endpoints} from '../api/queries';
import {useUI} from '../stores/ui';

const nav=[['/','대시보드',LayoutDashboard],['/certifications','자격증',BookOpen],['/mock-exam','모의고사',ClipboardCheck],['/wrong-notes','오답노트',NotebookTabs]] as const;

export function Layout(){
  const {dark,toggleDark}=useUI();
  const client=useQueryClient();
  const {data:user}=useQuery({queryKey:['me'],queryFn:endpoints.me});
  const logout=useMutation({mutationFn:endpoints.logout,onSettled:()=>{client.clear();window.location.assign('/')}});
  return <div className={dark?'app dark':'app'}><a className="skip" href="#main">본문 바로가기</a><aside><NavLink to="/" className="brand"><span>CE</span><div><b>CertFlow</b><small>시험 준비의 흐름</small></div></NavLink><nav aria-label="주 메뉴">{nav.map(([to,label,Icon])=><NavLink key={to} to={to} end={to==='/' }><Icon size={19}/>{label}</NavLink>)}{user?.role==='admin'&&<NavLink to="/admin"><Settings size={19}/>관리</NavLink>}</nav><div className="sidebar-actions"><button className="theme" onClick={toggleDark}>{dark?<Sun/>:<Moon/>}<span>{dark?'라이트 모드':'다크 모드'}</span></button><button className="theme" onClick={()=>logout.mutate()} disabled={logout.isPending}><LogOut/><span>로그아웃</span></button></div></aside><div className="shell"><header className="top"><span className="mobile-brand">CertFlow</span><span className="current-user"><b>{user?.username}</b><small>{user?.role==='admin'?'관리자':'학습자'}</small></span><span className="status"><i/> API 연결 모드</span></header><main id="main"><Outlet/></main></div></div>;
}
