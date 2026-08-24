import {useQuery} from '@tanstack/react-query';
import {useEffect,useState} from 'react';
import {useLocation} from 'react-router-dom';
import {endpoints} from '../api/queries';
import type {Notice} from '../types';

const koreanDay=(date=new Date())=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
const hiddenKey=(notice:Notice)=>`notice:hidden:${notice.id}:${notice.revision??notice.updated_at}`;
const dismissedKey=(notice:Notice)=>`notice:dismissed:${notice.id}:${notice.revision??notice.updated_at}`;
const formatDate=(value:string|null)=>value?new Date(value).toLocaleString('ko-KR',{dateStyle:'long',timeStyle:'short'}):'—';

export function NoticeCenter(){
  const location=useLocation();
  const query=useQuery({queryKey:['active-notices'],queryFn:endpoints.activeNotices,refetchInterval:30_000});
  const [,render]=useState(0);
  const now=query.data?Date.now()+(new Date(query.data.server_time).getTime()-Date.now()):Date.now();
  const visible=query.data?.notices.filter(notice=>{
    if(notice.notice_type==='general')return localStorage.getItem(hiddenKey(notice))!==koreanDay();
    return sessionStorage.getItem(dismissedKey(notice))!=='yes';
  })??[];
  const notice=visible[0];
  const upcoming=query.data?.upcoming_maintenance??query.data?.notices.find(item=>item.notice_type==='maintenance'&&item.maintenance_start_at&&new Date(item.maintenance_start_at).getTime()>now);
  const remaining=upcoming?.maintenance_start_at?new Date(upcoming.maintenance_start_at).getTime()-now:Number.POSITIVE_INFINITY;
  const studying=/^\/(study|mock-exam)\//.test(location.pathname);
  const [warningDismissed,setWarningDismissed]=useState(false);
  useEffect(()=>setWarningDismissed(false),[upcoming?.id]);
  const close=()=>{if(!notice)return;sessionStorage.setItem(dismissedKey(notice),'yes');render(value=>value+1)};
  const hideToday=()=>{if(!notice)return;localStorage.setItem(hiddenKey(notice),koreanDay());render(value=>value+1)};
  return <>
    {studying&&upcoming&&remaining>0&&remaining<=300_000&&<div className="maintenance-warning-banner" role="alert"><b>곧 점검이 시작됩니다.</b><span>{formatDate(upcoming.maintenance_start_at)}부터 점검이 진행됩니다. 학습은 저장되고 모의고사는 취소됩니다.</span></div>}
    {studying&&upcoming&&remaining>0&&remaining<=300_000&&!warningDismissed&&<div className="modal-backdrop"><section className="modal maintenance-warning-modal" role="alertdialog" aria-modal="true" aria-labelledby="maintenance-warning-title"><p className="eyebrow">점검 사전 안내</p><h2 id="maintenance-warning-title">5분 후 점검이 시작됩니다</h2><p className="maintenance-datetime"><b>점검 시작</b><span>{formatDate(upcoming.maintenance_start_at)}</span></p><p>진행 중인 학습은 현재 선택 답안까지 저장되고, 모의고사는 결과 없이 취소됩니다.</p><button className="button" onClick={()=>setWarningDismissed(true)}>확인</button></section></div>}
    {notice&&<div className="modal-backdrop notice-backdrop"><section className={`modal notice-popup notice-${notice.notice_type}`} role="dialog" aria-modal="true" aria-labelledby={`notice-${notice.id}-title`}><span className="badge">{notice.notice_type==='maintenance'?'점검 공지':'일반 공지'}</span><h2 id={`notice-${notice.id}-title`} className={`notice-color-${notice.title_color} notice-weight-${notice.title_weight}`}>{notice.title}</h2><p className={`notice-content notice-color-${notice.content_color} notice-weight-${notice.content_weight}`}>{notice.content}</p>{notice.maintenance_screen_enabled&&notice.maintenance_start_at&&notice.maintenance_end_at&&<div className="maintenance-datetime"><b>점검 일시</b><span>{formatDate(notice.maintenance_start_at)} ~ {formatDate(notice.maintenance_end_at)}</span></div>}<div className="notice-actions">{notice.notice_type==='general'&&<button onClick={hideToday}>오늘 하루 보지 않기</button>}<button className="button" onClick={close}>닫기</button></div></section></div>}
  </>;
}

export function MaintenanceScreen({notice,onAdminLogin}:{notice:Notice;onAdminLogin:()=>void}){
  return <main className="maintenance-page"><section className="maintenance-card"><p className="eyebrow">서비스 점검</p><h1>{notice.title}</h1><p className="maintenance-message">{notice.content}</p><div className="maintenance-datetime"><b>점검 일시</b><span>{formatDate(notice.maintenance_start_at)} ~ {formatDate(notice.maintenance_end_at)}</span></div><p className="muted">점검이 종료되면 로그인 화면으로 이동합니다.</p><button className="maintenance-admin-login" onClick={onAdminLogin}>관리자 로그인</button></section></main>;
}
