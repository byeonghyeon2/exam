import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {cleanup,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {endpoints} from '../api/queries';
import {MaintenanceScreen,NoticeCenter} from '../components/NoticeCenter';
import type {Notice} from '../types';

const base:Notice={id:1,notice_type:'general',title:'서비스 안내',content:'새로운 기능이 추가되었습니다.',display_start_at:'2026-08-24T00:00:00Z',display_end_at:'2026-08-31T00:00:00Z',maintenance_start_at:null,maintenance_end_at:null,maintenance_screen_enabled:false,title_color:'red',content_color:'blue',title_weight:'bold',content_weight:'normal',is_published:true,updated_at:'2026-08-24T00:00:00Z',revision:1};
const renderCenter=(route='/')=>render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={[route]}><NoticeCenter/></MemoryRouter></QueryClientProvider>);

afterEach(()=>{cleanup();vi.restoreAllMocks();localStorage.clear();sessionStorage.clear()});

describe('scheduled notices',()=>{
  it('shows a general notice and hides the same revision for today',async()=>{
    vi.spyOn(endpoints,'activeNotices').mockResolvedValue({notices:[base],maintenance:null,server_time:new Date().toISOString()});
    renderCenter();
    expect(await screen.findByRole('heading',{name:'서비스 안내'})).toHaveClass('notice-color-red','notice-weight-bold');
    await userEvent.click(screen.getByRole('button',{name:'오늘 하루 보지 않기'}));
    expect(screen.queryByRole('heading',{name:'서비스 안내'})).not.toBeInTheDocument();
  });

  it('warns an active learner five minutes before maintenance and keeps maintenance notices free of today-hide',async()=>{
    const now=Date.now();
    const maintenance={...base,id:2,notice_type:'maintenance' as const,title:'정기 점검',maintenance_screen_enabled:true,maintenance_start_at:new Date(now+4*60_000).toISOString(),maintenance_end_at:new Date(now+64*60_000).toISOString()};
    vi.spyOn(endpoints,'activeNotices').mockResolvedValue({notices:[maintenance],maintenance:null,server_time:new Date(now).toISOString()});
    renderCenter('/study/session-1');
    expect(await screen.findByRole('alertdialog')).toHaveTextContent('5분 후 점검이 시작됩니다');
    await userEvent.click(screen.getByRole('button',{name:'확인'}));
    expect(screen.getByRole('dialog')).toHaveTextContent('점검 일시');
    expect(screen.queryByRole('button',{name:'오늘 하루 보지 않기'})).not.toBeInTheDocument();
  });

  it('does not show an empty maintenance period for a popup-only maintenance notice',async()=>{
    const popupOnly={...base,id:3,notice_type:'maintenance' as const,title:'점검 사전 안내'};
    vi.spyOn(endpoints,'activeNotices').mockResolvedValue({notices:[popupOnly],maintenance:null,server_time:new Date().toISOString()});
    renderCenter();
    expect(await screen.findByRole('heading',{name:'점검 사전 안내'})).toBeInTheDocument();
    expect(screen.queryByText('점검 일시')).not.toBeInTheDocument();
  });

  it('renders a non-dismissible maintenance screen with a separate admin login entry',()=>{
    const maintenance={...base,notice_type:'maintenance' as const,title:'점검 중',maintenance_screen_enabled:true,maintenance_start_at:'2026-08-30T02:00:00Z',maintenance_end_at:'2026-08-30T04:00:00Z'};
    const login=vi.fn();render(<MaintenanceScreen notice={maintenance} onAdminLogin={login}/>);
    expect(screen.getByRole('heading',{name:'점검 중'})).toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'닫기'})).not.toBeInTheDocument();
  });
});
