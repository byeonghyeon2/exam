import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { endpoints } from '../api/queries';
import { Admin, AdminNotices, AdminQuestions, AdminUsers } from '../pages/Admin';
import styles from '../styles.css?raw';

function renderAdmin(Page=AdminUsers) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><Page /></MemoryRouter></QueryClientProvider>);
}

function mockAdminData() {
  vi.spyOn(endpoints, 'certifications').mockResolvedValue([
    {code:'DEA-C01',name_ko:'AWS 데이터 엔지니어',name_en:'AWS Data Engineer',exam_version:'DEA-C01',default_question_count:65,default_duration_minutes:130,passing_score:720},
    {code:'SNOW-CORE',name_ko:'스노우프로 코어',name_en:'SnowPro Core',exam_version:'SNOW-CORE',default_question_count:5,default_duration_minutes:115,passing_score:750},
  ]);
  vi.spyOn(endpoints, 'adminDashboard').mockResolvedValue({ questions: 295, verified: 295 });
  vi.spyOn(endpoints, 'users').mockResolvedValue([{
    id: 1, username: 'user', role: 'user', is_active: true,
    password_managed_by_environment: false, passkey_registered: true, created_at: '2026-08-09T00:00:00Z', last_login_at: null,
  }]);
  vi.spyOn(endpoints, 'resetUserPasskey').mockResolvedValue();
  vi.spyOn(endpoints, 'deleteUser').mockResolvedValue();
  vi.spyOn(endpoints, 'adminReports').mockResolvedValue([{
    id: 7, question_id: 149, question_uid: 'AWS-DEA-C01-000149',
    question_ko: '긴 문제 내용', question_en: 'Long question', report_type: 'explanation_error',
    description: '해설에 오타 존재', status: 'received', resolution_note: null,
    created_at: '2026-08-12T00:14:22Z', resolved_at: null,
  }]);
  vi.spyOn(endpoints, 'mockReadiness').mockResolvedValue({
    certification_code:'DEA-C01',certification_name:'AWS 데이터 엔지니어',ready: true, question_count: 65,
    domains: [
      { domain_code: 'DEA-D1',name_ko:'수집 및 변환',name_en:'Ingestion', required: 22, available: 106, shortage: 0 },
      { domain_code: 'DEA-D2',name_ko:'데이터 저장소',name_en:'Storage', required: 17, available: 76, shortage: 0 },
      { domain_code: 'DEA-D3',name_ko:'운영 및 지원',name_en:'Operations', required: 14, available: 64, shortage: 0 },
      { domain_code: 'DEA-D4',name_ko:'보안 및 거버넌스',name_en:'Security', required: 12, available: 49, shortage: 0 },
    ],
  });
  vi.spyOn(endpoints, 'classificationReport').mockResolvedValue({
    certification: 'DEA-C01',certification_name:'AWS 데이터 엔지니어',domain_counts: { 'DEA-D1': 106, 'DEA-D2': 76, 'DEA-D3': 64, 'DEA-D4': 49 }, status_counts: {},
    domains:[
      {domain_code:'DEA-D1',name_ko:'수집 및 변환',name_en:'Ingestion',count:106},
      {domain_code:'DEA-D2',name_ko:'데이터 저장소',name_en:'Storage',count:76},
      {domain_code:'DEA-D3',name_ko:'운영 및 지원',name_en:'Operations',count:64},
      {domain_code:'DEA-D4',name_ko:'보안 및 거버넌스',name_en:'Security',count:49},
    ],
  });
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Admin mobile layout', () => {
  it('renders account data with mobile labels and removes the unclassified area', async () => {
    mockAdminData();
    renderAdmin();

    const user = await screen.findByText('user');
    expect(user.closest('td')).toHaveAttribute('data-label', '아이디');
    expect(screen.getByText('사용 중').closest('td')).toHaveAttribute('data-label', '상태');
    expect(screen.getByText('등록됨').closest('td')).toHaveAttribute('data-label', 'Passkey');
    expect(screen.getByRole('button', { name: '기기 초기화' })).toBeInTheDocument();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => undefined);
    await userEvent.click(screen.getByRole('button', { name: '기기 초기화' }));
    expect(confirm).toHaveBeenCalledWith('기기를 초기화하시겠습니까?\n등록된 Passkey가 삭제되고 모든 로그인 세션이 종료됩니다.');
    await waitFor(() => expect(endpoints.resetUserPasskey).toHaveBeenCalledWith(1));
    await waitFor(() => expect(alert).toHaveBeenCalledWith('기기 초기화가 완료되었습니다.'));
    await userEvent.click(screen.getByRole('button', { name: '계정 삭제' }));
    expect(confirm).toHaveBeenLastCalledWith('user 계정을 삭제하시겠습니까?\n학습 기록과 인증 정보가 모두 삭제되며 복구할 수 없습니다.');
    await waitFor(() => expect(endpoints.deleteUser).toHaveBeenCalledWith(1));
    await waitFor(() => expect(alert).toHaveBeenCalledWith('계정이 삭제되었습니다.'));
    cleanup();
    renderAdmin(AdminQuestions);
    await waitFor(()=>expect(screen.getByLabelText('관리할 자격증')).toHaveValue('DEA-C01'));
    expect(screen.queryByText('DEA-UNCLASSIFIED')).not.toBeInTheDocument();
    expect(screen.queryByText(/미분류 활성 문제/)).not.toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: '상태/신뢰도' })).not.toBeInTheDocument();
    expect(await screen.findByRole('columnheader', { name: '사용 가능' })).toBeInTheDocument();
    const reports = within(screen.getByRole('heading', { name: '문제 신고' }).closest('section')!);
    expect(reports.getByRole('columnheader', { name: '접수 시각' })).toHaveClass('report-time');
    expect(reports.getByRole('columnheader', { name: '유형' })).toHaveClass('report-type');
    expect(reports.queryByRole('columnheader', { name: '상태' })).not.toBeInTheDocument();
  });

  it('loads problem counts, reports, and readiness for a newly added certification',async()=>{
    mockAdminData();
    vi.mocked(endpoints.classificationReport).mockImplementation(async code=>code==='SNOW-CORE'?{
      certification:'SNOW-CORE',certification_name:'스노우프로 코어',domain_counts:{'SNOW-STORAGE':3,'SNOW-SECURITY':2},status_counts:{},
      domains:[
        {domain_code:'SNOW-STORAGE',name_ko:'스토리지',name_en:'Storage',count:3},
        {domain_code:'SNOW-SECURITY',name_ko:'보안',name_en:'Security',count:2},
      ],
    }:{certification:'DEA-C01',certification_name:'AWS 데이터 엔지니어',domain_counts:{} as Record<string,number>,status_counts:{},domains:[]});
    vi.mocked(endpoints.mockReadiness).mockImplementation(async code=>({
      certification_code:code,certification_name:code==='SNOW-CORE'?'스노우프로 코어':'AWS 데이터 엔지니어',ready:true,question_count:code==='SNOW-CORE'?5:65,
      domains:code==='SNOW-CORE'?[{domain_code:'SNOW-STORAGE',name_ko:'스토리지',name_en:'Storage',required:3,available:3,shortage:0},{domain_code:'SNOW-SECURITY',name_ko:'보안',name_en:'Security',required:2,available:2,shortage:0}]:[],
    }));
    vi.mocked(endpoints.adminReports).mockImplementation(async code=>code==='SNOW-CORE'?[{
      id:8,question_id:200,question_uid:'SNOW-001',question_ko:'Snow 문제',question_en:'Snow question',report_type:'other',description:'Snow 신고',status:'received',resolution_note:null,created_at:'2026-08-12T00:14:22Z',resolved_at:null,
    }]:[]);
    renderAdmin(AdminQuestions);
    const selector=await screen.findByLabelText('관리할 자격증');
    await waitFor(()=>expect(within(selector).getByRole('option',{name:/스노우프로 코어/})).toBeInTheDocument());
    await userEvent.selectOptions(selector,'SNOW-CORE');
    expect((await screen.findAllByText('스토리지')).length).toBeGreaterThan(0);
    expect(screen.getByText('Snow 신고')).toBeInTheDocument();
    expect(endpoints.classificationReport).toHaveBeenLastCalledWith('SNOW-CORE');
    expect(endpoints.mockReadiness).toHaveBeenLastCalledWith('SNOW-CORE');
    expect(endpoints.adminReports).toHaveBeenLastCalledWith('SNOW-CORE');
  });

  it('keeps the admin landing page concise and links to each management area', async()=>{
    mockAdminData();
    renderAdmin(Admin);
    expect(await screen.findByRole('heading',{name:'관리자 대시보드'})).toBeInTheDocument();
    expect(await screen.findAllByText('295',{selector:'strong'})).toHaveLength(2);
    expect(screen.queryByLabelText('임시 비밀번호')).not.toBeInTheDocument();
    expect(screen.getAllByRole('link',{name:'계정 관리'}).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link',{name:'문제 관리'}).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link',{name:'공지 관리'}).length).toBeGreaterThan(0);
  });

  it('creates a popup-only maintenance notice without enabling the maintenance screen',async()=>{
    mockAdminData();
    vi.spyOn(endpoints,'notices').mockResolvedValue([]);
    const create=vi.spyOn(endpoints,'createNotice').mockImplementation(async body=>({id:1,updated_at:new Date().toISOString(),...body}));
    renderAdmin(AdminNotices);
    await screen.findByText('공지 목록이 비어 있습니다.');
    expect(screen.getByRole('heading',{name:'기본 정보'})).toBeInTheDocument();
    expect(screen.getByRole('heading',{name:'노출 일정'})).toBeInTheDocument();
    expect(screen.getByRole('heading',{name:'스타일 및 게시'})).toBeInTheDocument();
    expect(screen.queryByRole('heading',{name:'공지 미리보기'})).not.toBeInTheDocument();
    expect(screen.getByRole('button',{name:'미리보기'})).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('공지 유형'),'maintenance');
    expect(screen.getByLabelText('점검 화면 표출')).not.toBeChecked();
    expect(screen.queryByLabelText('점검 화면 시작')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('점검 화면 종료')).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('제목'),'점검 안내');
    await userEvent.type(screen.getByLabelText('내용'),'점검 예정 안내입니다.');
    await userEvent.click(screen.getByRole('button',{name:'미리보기'}));
    expect(screen.getByRole('dialog',{name:'공지 미리보기'})).toHaveTextContent('점검 안내');
    await userEvent.click(screen.getByRole('button',{name:'미리보기 닫기'}));
    await userEvent.type(screen.getByLabelText('시작 일시'),'2026-08-25T09:00');
    await userEvent.type(screen.getByLabelText('종료 일시'),'2026-08-30T02:00');
    await userEvent.click(screen.getByRole('button',{name:'공지 등록'}));
    await waitFor(()=>expect(create).toHaveBeenCalledWith(expect.objectContaining({notice_type:'maintenance',maintenance_screen_enabled:false,maintenance_start_at:null,maintenance_end_at:null,title:'점검 안내'})));
  },15_000);

  it('creates a blocking maintenance notice with explicit display and maintenance periods',async()=>{
    mockAdminData();
    vi.spyOn(endpoints,'notices').mockResolvedValue([]);
    const create=vi.spyOn(endpoints,'createNotice').mockImplementation(async body=>({id:1,updated_at:new Date().toISOString(),...body}));
    renderAdmin(AdminNotices);
    await screen.findByText('공지 목록이 비어 있습니다.');
    await userEvent.selectOptions(screen.getByLabelText('공지 유형'),'maintenance');
    await userEvent.click(screen.getByLabelText('점검 화면 표출'));
    await userEvent.type(screen.getByLabelText('제목'),'정기 점검');
    await userEvent.type(screen.getByLabelText('내용'),'서비스 점검을 진행합니다.');
    await userEvent.type(screen.getByLabelText('시작 일시'),'2026-08-25T09:00');
    await userEvent.type(screen.getByLabelText('종료 일시'),'2026-08-30T02:00');
    await userEvent.type(screen.getByLabelText('점검 화면 시작'),'2026-08-30T02:00');
    await userEvent.type(screen.getByLabelText('점검 화면 종료'),'2026-08-30T04:00');
    await userEvent.click(screen.getByLabelText('게시'));
    await userEvent.click(screen.getByRole('button',{name:'공지 등록'}));
    await waitFor(()=>expect(create).toHaveBeenCalledWith(expect.objectContaining({notice_type:'maintenance',maintenance_screen_enabled:true,is_published:true,title:'정기 점검'})));
  },15_000);

  it('visually separates active, scheduled, ended, and private notices in the notice list',async()=>{
    mockAdminData();
    const now=Date.now();
    const date=(offset:number)=>new Date(now+offset).toISOString();
    const base={notice_type:'general' as const,maintenance_start_at:null,maintenance_end_at:null,maintenance_screen_enabled:false,title_color:'default' as const,content_color:'default' as const,title_weight:'bold' as const,content_weight:'normal' as const,revision:1};
    vi.spyOn(endpoints,'notices').mockResolvedValue([
      {id:1,...base,title:'현재 공지',content:'현재 노출',is_published:true,display_start_at:date(-60_000),display_end_at:date(60_000),updated_at:date(0)},
      {id:2,...base,title:'예약 공지',content:'예약',is_published:true,display_start_at:date(60_000),display_end_at:date(120_000),updated_at:date(0)},
      {id:3,...base,title:'종료 공지',content:'종료',is_published:true,display_start_at:date(-120_000),display_end_at:date(-60_000),updated_at:date(0)},
      {id:4,...base,title:'비공개 공지',content:'비공개',is_published:false,display_start_at:date(-60_000),display_end_at:date(60_000),updated_at:date(0)},
    ]);
    renderAdmin(AdminNotices);
    expect(await screen.findByText('현재 노출 중')).toBeInTheDocument();
    expect(screen.getByText('노출 예정')).toBeInTheDocument();
    expect(screen.getByText('노출 종료')).toBeInTheDocument();
    expect(screen.getByText('비공개')).toBeInTheDocument();
    expect(screen.getByText('현재 공지').closest('article')).toHaveClass('notice-admin-active');
  });

  it('does not reset without confirmation and alerts when reset fails', async () => {
    mockAdminData();
    renderAdmin();
    await screen.findByText('user');
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    await userEvent.click(screen.getByRole('button', { name: '기기 초기화' }));
    expect(confirm).toHaveBeenCalled();
    expect(endpoints.resetUserPasskey).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    vi.mocked(endpoints.resetUserPasskey).mockRejectedValueOnce(new Error('서버 오류'));
    await userEvent.click(screen.getByRole('button', { name: '기기 초기화' }));
    await waitFor(() => expect(alert).toHaveBeenCalledWith('기기 초기화에 실패했습니다. 다시 시도해주세요.'));

    confirm.mockReturnValue(false);
    await userEvent.click(screen.getByRole('button', { name: '계정 삭제' }));
    expect(endpoints.deleteUser).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    vi.mocked(endpoints.deleteUser).mockRejectedValueOnce(new Error('서버 오류'));
    await userEvent.click(screen.getByRole('button', { name: '계정 삭제' }));
    await waitFor(() => expect(alert).toHaveBeenCalledWith('계정 삭제에 실패했습니다. 다시 시도해주세요.'));
  });

  it('keeps admin responsive rules scoped to the admin page', () => {
    const compact = styles.replace(/\s+/g, '');
    expect(compact).toContain('.admin-responsive-tablethead{display:none}');
    expect(compact).toContain('.admin-responsive-tabletd::before{content:attr(data-label)');
    expect(compact).toContain('.admin-readinesstable{table-layout:fixed;font-size:12px}');
    expect(compact).toContain('.admin-domain-counts.metrics{grid-template-columns:1fr;gap:8px}');
    expect(compact).toContain('.admin-reports-table.report-time{width:145px;min-width:145px;white-space:nowrap}');
    expect(compact).toContain('.admin-reports-table.report-type{width:92px;min-width:92px;white-space:nowrap;word-break:keep-all}');
    expect(compact).toContain('@media(max-width:380px){.admin-page.panel{padding:18px13px}');
  });
});
