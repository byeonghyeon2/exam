import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {type FormEvent,useEffect,useState} from 'react';
import {NavLink} from 'react-router-dom';
import {endpoints} from '../api/queries';
import {ErrorState,Loading,PageHeader} from '../components/common';
import {REPORT_TYPE_LABELS,type ReportType} from '../reporting';
import type {Notice,NoticeColor,NoticeWeight,NoticeWrite} from '../types';

const dashboardLabels:Record<string,string>={questions:'전체 문제',verified:'검증 완료',needs_review:'검토 필요',reports:'미처리 신고'};

export function Admin(){
  return <AdminContent section="dashboard"/>;
}
export function AdminUsers(){return <AdminContent section="users"/>}
export function AdminQuestions(){return <AdminContent section="questions"/>}
export function AdminNotices(){return <AdminContent section="notices"/>}

function AdminNav(){return <nav className="admin-subnav" aria-label="관리 하위 메뉴"><NavLink to="/admin" end>대시보드</NavLink><NavLink to="/admin/users">계정 관리</NavLink><NavLink to="/admin/questions">문제 관리</NavLink><NavLink to="/admin/notices">공지 관리</NavLink></nav>}

function AdminContent({section}:{section:'dashboard'|'users'|'questions'|'notices'}){
  const client=useQueryClient();
  const [username,setUsername]=useState('');const [password,setPassword]=useState('');
  const [certificationCode,setCertificationCode]=useState('');
  const dash=useQuery({queryKey:['admin-dashboard'],queryFn:endpoints.adminDashboard,enabled:section==='dashboard'});
  const certifications=useQuery({queryKey:['certifications'],queryFn:endpoints.certifications,enabled:section==='questions'});
  useEffect(()=>{const first=certifications.data?.[0];if(section==='questions'&&!certificationCode&&first)setCertificationCode(first.code)},[certificationCode,certifications.data,section]);
  const report=useQuery({queryKey:['classification-report',certificationCode],queryFn:()=>endpoints.classificationReport(certificationCode),enabled:section==='questions'&&Boolean(certificationCode)});
  const readiness=useQuery({queryKey:['mock-readiness',certificationCode],queryFn:()=>endpoints.mockReadiness(certificationCode),enabled:section==='questions'&&Boolean(certificationCode)});
  const reports=useQuery({queryKey:['admin-reports',certificationCode],queryFn:()=>endpoints.adminReports(certificationCode),enabled:section==='questions'&&Boolean(certificationCode)});
  const users=useQuery({queryKey:['admin-users'],queryFn:endpoints.users,enabled:section==='users'});
  const createUser=useMutation({mutationFn:()=>endpoints.createUser({username,password,role:'user'}),onSuccess:()=>{setUsername('');setPassword('');return client.invalidateQueries({queryKey:['admin-users']})}});
  const toggleUser=useMutation({mutationFn:({id,is_active}:{id:number;is_active:boolean})=>endpoints.updateUser(id,{is_active}),onSuccess:()=>client.invalidateQueries({queryKey:['admin-users']})});
  const resetPasskey=useMutation({
    mutationFn:(id:number)=>endpoints.resetUserPasskey(id),
    onSuccess:()=>client.invalidateQueries({queryKey:['admin-users']}).then(()=>window.alert('기기 초기화가 완료되었습니다.')),
    onError:()=>window.alert('기기 초기화에 실패했습니다. 다시 시도해주세요.'),
  });
  const deleteUser=useMutation({
    mutationFn:(id:number)=>endpoints.deleteUser(id),
    onSuccess:()=>client.invalidateQueries({queryKey:['admin-users']}).then(()=>window.alert('계정이 삭제되었습니다.')),
    onError:()=>window.alert('계정 삭제에 실패했습니다. 다시 시도해주세요.'),
  });
  const submitUser=(event:FormEvent)=>{event.preventDefault();createUser.mutate()};
  const titles={dashboard:['관리자 대시보드','운영 상태를 간략하게 확인합니다.'],users:['계정 관리','학습자 계정과 등록 기기를 관리합니다.'],questions:['문제 관리','자격증별 문제 신고와 모의고사 준비도를 관리합니다.'],notices:['공지 관리','일반 공지와 점검 일정을 예약합니다.']} as const;
  return <div className="admin-page"><PageHeader eyebrow="운영 센터" title={titles[section][0]} description={titles[section][1]}/><AdminNav/>
    {section==='dashboard'&&(dash.isLoading?<Loading/>:dash.isError?<ErrorState error={dash.error}/>:<><div className="metrics admin-overview">{Object.entries(dash.data!).map(([key,value])=><article key={key}><small>{dashboardLabels[key]??key}</small><strong>{value.toLocaleString()}</strong></article>)}</div><div className="admin-shortcuts"><NavLink to="/admin/users">계정 관리</NavLink><NavLink to="/admin/questions">문제 관리</NavLink><NavLink to="/admin/notices">공지 관리</NavLink></div></>)}
    {section==='users'&&<section className="panel user-management"><div className="section-title"><h2>계정 관리</h2><span>{users.data?.length??0}명</span></div><form className="inline-user-form" onSubmit={submitUser}><label>아이디<input value={username} onChange={event=>setUsername(event.target.value)} minLength={3} maxLength={64} pattern="[A-Za-z0-9._-]+" autoComplete="off" required/></label><label>임시 비밀번호<input type="password" value={password} onChange={event=>setPassword(event.target.value)} minLength={8} maxLength={128} autoComplete="new-password" required/></label><button className="button" disabled={createUser.isPending}>{createUser.isPending?'등록 중…':'계정 등록'}</button></form>{createUser.isError&&<p className="form-error">{createUser.error.message}</p>}{users.isLoading?<Loading/>:users.isError?<ErrorState error={users.error}/>:<div className="table-wrap admin-responsive-table"><table><thead><tr><th>아이디</th><th>등록일</th><th>최근 로그인</th><th>상태</th><th>Passkey</th><th>작업</th></tr></thead><tbody>{users.data!.map(user=><tr key={user.id}><td data-label="아이디"><b>{user.username}</b></td><td data-label="등록일">{new Date(user.created_at).toLocaleDateString('ko-KR')}</td><td data-label="최근 로그인">{user.last_login_at?new Date(user.last_login_at).toLocaleString('ko-KR'):'—'}</td><td data-label="상태"><span className={`badge ${user.is_active?'success':'danger'}`}>{user.is_active?'사용 중':'비활성'}</span></td><td data-label="Passkey"><span className={`badge ${user.passkey_registered?'success':'danger'}`}>{user.passkey_registered?'등록됨':'등록 대기'}</span></td><td data-label="작업"><div className="actions"><button disabled={toggleUser.isPending||resetPasskey.isPending||deleteUser.isPending} onClick={()=>toggleUser.mutate({id:user.id,is_active:!user.is_active})}>{user.is_active?'비활성화':'활성화'}</button>{user.passkey_registered&&<button className="danger-button" disabled={toggleUser.isPending||resetPasskey.isPending||deleteUser.isPending} onClick={()=>window.confirm('기기를 초기화하시겠습니까?\n등록된 Passkey가 삭제되고 모든 로그인 세션이 종료됩니다.')&&resetPasskey.mutate(user.id)}>기기 초기화</button>}<button className="danger-button" disabled={toggleUser.isPending||resetPasskey.isPending||deleteUser.isPending} onClick={()=>window.confirm(`${user.username} 계정을 삭제하시겠습니까?\n학습 기록과 인증 정보가 모두 삭제되며 복구할 수 없습니다.`)&&deleteUser.mutate(user.id)}>계정 삭제</button></div></td></tr>)}</tbody></table></div>}</section>}
    {section==='questions'&&<>
    <section className="panel admin-certification-filter"><label>관리할 자격증<select value={certificationCode} onChange={event=>setCertificationCode(event.target.value)} disabled={certifications.isLoading||!certifications.data?.length}><option value="">{certifications.isLoading?'자격증 불러오는 중…':'자격증을 선택하세요'}</option>{certifications.data?.map(certification=><option key={certification.code} value={certification.code}>{certification.name_ko||certification.name_en} · {certification.code}</option>)}</select></label>{certifications.isError&&<ErrorState error={certifications.error}/>}</section>
    {!certificationCode?<section className="panel"><p className="muted">관리할 자격증을 선택해주세요.</p></section>:<>
    <section className="panel"><div className="section-title"><h2>문제 신고</h2><span>{reports.data?.length??0}건</span></div>{reports.isLoading?<Loading/>:reports.isError?<ErrorState error={reports.error}/>:reports.data!.length===0?<p className="muted">접수된 문제 신고가 없습니다.</p>:<div className="table-wrap admin-responsive-table"><table className="admin-reports-table"><thead><tr><th className="report-time">접수 시각</th><th className="report-type">유형</th><th>문제</th><th>신고 내용</th></tr></thead><tbody>{reports.data!.map(item=><tr key={item.id}><td data-label="접수 시각" className="report-time">{new Date(item.created_at).toLocaleString('ko-KR')}</td><td data-label="유형" className="report-type">{REPORT_TYPE_LABELS[item.report_type as ReportType]??item.report_type}</td><td data-label="문제"><b>{item.question_uid}</b><br/><span>{item.question_ko||item.question_en}</span></td><td data-label="신고 내용" className="report-description">{item.description}</td></tr>)}</tbody></table></div>}</section>
    <section className="panel admin-readiness"><div className="section-title"><h2>모의고사 준비도</h2>{readiness.data&&<span className={`badge ${readiness.data.ready?'success':'danger'}`}>{readiness.data.ready?'구성 가능':'문제 부족'}</span>}</div>{readiness.isLoading?<Loading/>:readiness.isError?<ErrorState error={readiness.error}/>:readiness.data&&<><p className="muted">{readiness.data.certification_name} · 총 {readiness.data.question_count}문항 기준</p><div className="table-wrap"><table><thead><tr><th>단원</th><th>필요</th><th>사용 가능</th><th>부족</th></tr></thead><tbody>{readiness.data.domains.map(item=><tr key={item.domain_code}><td>{item.name_ko||item.name_en}</td><td>{item.required}</td><td>{item.available}</td><td>{item.shortage}</td></tr>)}</tbody></table></div></>}</section>
    <section className="panel admin-domain-counts"><div className="section-title"><h2>단원별 문제 수</h2><span>{report.data?.certification}</span></div>{report.isLoading?<Loading/>:report.isError?<ErrorState error={report.error}/>:report.data&&<div className="metrics">{report.data.domains.map(domain=><article key={domain.domain_code}><small>{domain.name_ko||domain.name_en}</small><strong>{domain.count}</strong></article>)}</div>}</section></>}</>}
    {section==='notices'&&<NoticeManagement/>}
  </div>;
}

const initialNotice:NoticeWrite={notice_type:'general',title:'',content:'',display_start_at:'',display_end_at:'',maintenance_start_at:null,maintenance_end_at:null,maintenance_screen_enabled:false,title_color:'default',content_color:'default',title_weight:'bold',content_weight:'normal',is_published:false};
const noticeColorLabels:Record<NoticeColor,string>={default:'기본',green:'초록',blue:'파랑',orange:'주황',red:'빨강',gray:'회색',purple:'보라'};
function NoticeManagement(){
  const client=useQueryClient();
  const [form,setForm]=useState<NoticeWrite>(initialNotice);
  const [editingId,setEditingId]=useState<number|null>(null);
  const notices=useQuery({queryKey:['admin-notices'],queryFn:endpoints.notices});
  const resetForm=()=>{setForm(initialNotice);setEditingId(null)};
  const save=useMutation({mutationFn:(payload:NoticeWrite)=>editingId===null?endpoints.createNotice(payload):endpoints.updateNotice(editingId,payload),onSuccess:()=>{resetForm();return client.invalidateQueries({queryKey:['admin-notices']})}});
  const remove=useMutation({mutationFn:(id:number)=>endpoints.deleteNotice(id),onSuccess:()=>client.invalidateQueries({queryKey:['admin-notices']})});
  const update=<K extends keyof NoticeWrite>(key:K,value:NoticeWrite[K])=>setForm(current=>({...current,[key]:value}));
  const localIso=(value:string)=>value?new Date(value).toISOString():'';
  const toInput=(value:string|null)=>{if(!value)return null;const date=new Date(value);return new Date(date.getTime()-date.getTimezoneOffset()*60_000).toISOString().slice(0,16)};
  const edit=(notice:Notice)=>{setEditingId(notice.id);setForm({...notice,display_start_at:toInput(notice.display_start_at)!,display_end_at:toInput(notice.display_end_at)!,maintenance_start_at:toInput(notice.maintenance_start_at),maintenance_end_at:toInput(notice.maintenance_end_at)});window.scrollTo({top:0,behavior:'smooth'})};
  const submit=(event:FormEvent)=>{event.preventDefault();save.mutate({...form,display_start_at:localIso(form.display_start_at),display_end_at:localIso(form.display_end_at),maintenance_start_at:form.maintenance_start_at?localIso(form.maintenance_start_at):null,maintenance_end_at:form.maintenance_end_at?localIso(form.maintenance_end_at):null})};
  const changeNoticeType=(value:string)=>{const maintenance=value==='maintenance';setForm(current=>({...current,notice_type:maintenance?'maintenance':'general',maintenance_screen_enabled:maintenance?current.maintenance_screen_enabled:false,maintenance_start_at:maintenance?current.maintenance_start_at:null,maintenance_end_at:maintenance?current.maintenance_end_at:null}))};
  return <>
    <section className="panel notice-editor">
      <div className="section-title"><div><h2>{editingId===null?'공지 등록':'공지 수정'}</h2><p className="muted">노출 일정과 사용자에게 보일 모습을 한 화면에서 확인합니다.</p></div>{editingId!==null&&<button onClick={resetForm}>수정 취소</button>}</div>
      <div className="notice-editor-layout">
        <form className="notice-form" onSubmit={submit}>
          <section className="notice-form-section"><h3>기본 정보</h3><div className="notice-form-grid">
            <label>공지 유형<select value={form.notice_type} onChange={event=>changeNoticeType(event.target.value)}><option value="general">일반 공지</option><option value="maintenance">점검 공지</option></select></label>
            <label>제목<input value={form.title} onChange={event=>update('title',event.target.value)} required maxLength={255} placeholder="공지 제목을 입력하세요"/></label>
            <label className="notice-content-field">내용<textarea value={form.content} onChange={event=>update('content',event.target.value)} required rows={6} placeholder="사용자에게 전달할 내용을 입력하세요"/></label>
          </div></section>
          <section className="notice-form-section"><h3>노출 일정</h3><div className="notice-form-grid">
            <label>팝업 시작<input type="datetime-local" value={form.display_start_at} onChange={event=>update('display_start_at',event.target.value)} required/></label>
            <label>팝업 종료<input type="datetime-local" value={form.display_end_at} onChange={event=>update('display_end_at',event.target.value)} required/></label>
            {form.notice_type==='maintenance'&&<><label className="notice-publish"><input aria-label="점검 화면 표출" type="checkbox" checked={form.maintenance_screen_enabled} onChange={event=>update('maintenance_screen_enabled',event.target.checked)}/>점검 화면 표출 · 일반 사용자 접근 차단</label>{form.maintenance_screen_enabled&&<><label>점검 화면 시작<input type="datetime-local" value={form.maintenance_start_at??''} onChange={event=>update('maintenance_start_at',event.target.value)} required/></label><label>점검 화면 종료<input type="datetime-local" value={form.maintenance_end_at??''} onChange={event=>update('maintenance_end_at',event.target.value)} required/></label></>}</>}
          </div></section>
          <section className="notice-form-section"><h3>스타일 및 게시</h3><div className="notice-form-grid notice-style-grid">
            <label>제목 색상<select value={form.title_color} onChange={event=>update('title_color',event.target.value as NoticeColor)}>{Object.entries(noticeColorLabels).map(([color,label])=><option key={color} value={color}>{label}</option>)}</select></label>
            <label>제목 굵기<select value={form.title_weight} onChange={event=>update('title_weight',event.target.value as NoticeWeight)}><option value="bold">굵게</option><option value="normal">보통</option></select></label>
            <label>본문 색상<select value={form.content_color} onChange={event=>update('content_color',event.target.value as NoticeColor)}>{Object.entries(noticeColorLabels).map(([color,label])=><option key={color} value={color}>{label}</option>)}</select></label>
            <label>본문 굵기<select value={form.content_weight} onChange={event=>update('content_weight',event.target.value as NoticeWeight)}><option value="normal">보통</option><option value="bold">굵게</option></select></label>
            <label className="notice-publish"><input aria-label="게시" type="checkbox" checked={form.is_published} onChange={event=>update('is_published',event.target.checked)}/>저장 후 게시 상태로 전환</label>
          </div></section>
          {save.isError&&<p className="form-error" role="alert">{save.error.message}</p>}
          <button className="button notice-save" disabled={save.isPending}>{save.isPending?'저장 중…':editingId===null?'공지 등록':'공지 수정'}</button>
        </form>
        <aside className="notice-preview-pane"><h3>공지 미리보기</h3><article className="notice-preview" aria-label="공지 미리보기"><span className={`badge ${form.notice_type==='maintenance'?'danger':'success'}`}>{form.notice_type==='maintenance'?'점검 공지':'일반 공지'}</span><h2 className={`notice-color-${form.title_color} notice-weight-${form.title_weight}`}>{form.title||'공지 제목이 표시됩니다'}</h2><p className={`notice-color-${form.content_color} notice-weight-${form.content_weight}`}>{form.content||'공지 내용을 입력하면 이곳에서 미리 확인할 수 있습니다.'}</p>{form.display_start_at&&form.display_end_at&&<small>{form.display_start_at.replace('T',' ')} ~ {form.display_end_at.replace('T',' ')}</small>}</article></aside>
      </div>
    </section>
    <section className="panel"><div className="section-title"><div><h2>등록된 공지</h2><p className="muted">예약된 공지와 게시 상태를 관리합니다.</p></div><span>{notices.data?.length??0}건</span></div>{notices.isLoading?<Loading/>:notices.isError?<ErrorState error={notices.error}/>:notices.data!.length===0?<p className="muted">등록된 공지가 없습니다.</p>:<div className="notice-admin-list">{notices.data!.map(notice=><article key={notice.id}><div className="notice-admin-summary"><div className="notice-badges"><span className={`badge ${notice.notice_type==='maintenance'?'danger':'success'}`}>{notice.notice_type==='maintenance'?'점검':'일반'}</span><span className={`badge ${notice.is_published?'success':''}`}>{notice.is_published?'게시 중':'비공개'}</span></div><h3>{notice.title}</h3><p><b>노출</b> {new Date(notice.display_start_at).toLocaleString('ko-KR')} ~ {new Date(notice.display_end_at).toLocaleString('ko-KR')}</p>{notice.maintenance_screen_enabled&&notice.maintenance_start_at&&notice.maintenance_end_at&&<p><b>점검</b> {new Date(notice.maintenance_start_at).toLocaleString('ko-KR')} ~ {new Date(notice.maintenance_end_at).toLocaleString('ko-KR')}</p>}</div><div className="actions"><button disabled={save.isPending} onClick={()=>edit(notice)}>수정</button><button className="danger-button" disabled={remove.isPending} onClick={()=>window.confirm('공지를 삭제하시겠습니까?')&&remove.mutate(notice.id)}>삭제</button></div></article>)}</div>}</section>
  </>;
}
