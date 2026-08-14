import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {cleanup,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {App} from '../App';

const admin={id:1,username:'admin',role:'admin',is_active:true,passkey_registered:false,passkey_registration_required:false,passkey_authentication_required:false,created_at:'2026-01-01T00:00:00Z',last_login_at:null};
const learner={...admin,id:2,username:'learner',role:'user'};
const response=(body:unknown,ok=true,status=200)=>({ok,status,json:()=>Promise.resolve(body)});
const renderApp=(route='/')=>render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={[route]}><App/></MemoryRouter></QueryClientProvider>);

afterEach(()=>{cleanup();vi.restoreAllMocks()});

describe('App',()=>{
  it('renders navigation after authentication and keeps dashboard loading explicit',async()=>{
    vi.stubGlobal('fetch',vi.fn((input:string|URL)=>String(input).includes('/auth/me')?Promise.resolve(response(admin)):new Promise(()=>{})));
    renderApp();
    expect(await screen.findByRole('navigation',{name:'주 메뉴'})).toBeInTheDocument();
    expect(screen.getAllByText('합격비서')).toHaveLength(2);
    expect(screen.getAllByText('자격증 합격 비서')).toHaveLength(2);
    expect(screen.getAllByRole('img',{name:'합격비서 아이콘'})[0]).toHaveAttribute('src','/icons/hapgyeokbiseo-main-192.png');
    expect(screen.getAllByRole('button',{name:'다크 모드'})).toHaveLength(2);
    expect(screen.getAllByRole('button',{name:'로그아웃'})).toHaveLength(2);
    expect(screen.getByRole('heading',{name:/합격까지/})).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('불러오는 중');
    const adminContextMenu=new MouseEvent('contextmenu',{bubbles:true,cancelable:true});
    document.dispatchEvent(adminContextMenu);
    expect(adminContextMenu.defaultPrevented).toBe(false);
  });

  it('shows the API error state without fake content',async()=>{
    vi.stubGlobal('fetch',vi.fn((input:string|URL)=>String(input).includes('/auth/me')?Promise.resolve(response(learner)):Promise.resolve(response({detail:'서버 점검 중'},false,503))));
    renderApp('/certifications');
    expect(await screen.findByRole('alert')).toHaveTextContent('서버 점검 중');
  });

  it('shows login instead of the app when the session is missing',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response({detail:'로그인이 필요합니다'},false,401)));
    renderApp('/admin');
    expect(await screen.findByRole('heading',{name:'로그인'})).toBeInTheDocument();
    expect(screen.getByRole('heading',{name:'로그인'}).querySelector('svg')).not.toBeNull();
    expect(screen.queryByText('CertExam')).not.toBeInTheDocument();
    expect(screen.queryByText('시험 준비의 흐름')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('임시 비밀번호')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button',{name:'최초 기기 등록'}));
    expect(screen.getByLabelText('임시 비밀번호')).toHaveAttribute('type','password');
  });

  it('does not expose administrator navigation to learners',async()=>{
    vi.stubGlobal('fetch',vi.fn((input:string|URL)=>String(input).includes('/auth/me')?Promise.resolve(response(learner)):new Promise(()=>{})));
    renderApp('/');
    await screen.findByRole('navigation',{name:'주 메뉴'});
    expect(screen.queryByRole('link',{name:'관리'})).not.toBeInTheDocument();
  });

  it('forces a managed account into passkey registration before app routes',async()=>{
    const pending={...learner,passkey_registered:false,passkey_registration_required:true,passkey_authentication_required:false};
    vi.stubGlobal('fetch',vi.fn((input:string|URL)=>String(input).includes('/auth/me')?Promise.resolve(response(pending)):new Promise(()=>{})));
    renderApp('/certifications');
    expect(await screen.findByRole('heading',{name:'Passkey 등록'})).toBeInTheDocument();
    expect(screen.queryByRole('navigation',{name:'주 메뉴'})).not.toBeInTheDocument();
  });

  it('keeps login protected and releases browser restrictions only after admin login',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response({detail:'로그인이 필요합니다'},false,401)));
    renderApp();
    await screen.findByRole('heading',{name:'로그인'});
    const loginContextMenu=new MouseEvent('contextmenu',{bubbles:true,cancelable:true});
    document.dispatchEvent(loginContextMenu);
    expect(loginContextMenu.defaultPrevented).toBe(true);
  });
});
