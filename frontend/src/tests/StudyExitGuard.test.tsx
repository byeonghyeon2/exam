import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {cleanup,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {useEffect} from 'react';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {Layout} from '../components/Layout';
import {useStudyExitGuard} from '../components/StudyExitGuard';

const admin={id:1,username:'admin',role:'admin',is_active:true,created_at:'2026-01-01T00:00:00Z',last_login_at:null};
const response=(body:unknown)=>({ok:true,status:200,json:()=>Promise.resolve(body)});

function ActiveStudy({saveAndLeave,discardAndLeave}:{saveAndLeave:()=>Promise<unknown>;discardAndLeave:()=>Promise<unknown>}){
  const {setGuard}=useStudyExitGuard();
  useEffect(()=>{
    setGuard({sessionId:'study-1',answeredCount:3,saveAndLeave,discardAndLeave});
    return ()=>setGuard(current=>current?.sessionId==='study-1'?null:current);
  },[discardAndLeave,saveAndLeave,setGuard]);
  return <h1>학습 화면</h1>;
}

function renderGuard(saveAndLeave=vi.fn().mockResolvedValue({}),discardAndLeave=vi.fn().mockResolvedValue({})){
  const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/study/test']}><Routes><Route element={<Layout/>}><Route path="study/:id" element={<ActiveStudy saveAndLeave={saveAndLeave} discardAndLeave={discardAndLeave}/>}/><Route index element={<h1>대시보드 화면</h1>}/></Route></Routes></MemoryRouter></QueryClientProvider>);
  return {saveAndLeave,discardAndLeave};
}

afterEach(()=>{cleanup();vi.restoreAllMocks()});

describe('Study exit guard',()=>{
  it('keeps studying when the user cancels navigation',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response(admin)));
    renderGuard();
    await userEvent.click(await screen.findByRole('link',{name:'대시보드'}));
    expect(screen.getByRole('dialog')).toHaveTextContent('현재까지 3문제를 풀었습니다.');
    expect(screen.getByRole('button',{name:'저장 후 나가기'})).toBeInTheDocument();
    expect(screen.getByRole('button',{name:'저장하지 않고 나가기'})).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button',{name:'계속 학습'}));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('heading',{name:'학습 화면'})).toBeInTheDocument();
  });

  it('saves the partial session before navigating',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response(admin)));
    const {saveAndLeave,discardAndLeave}=renderGuard();
    await userEvent.click(await screen.findByRole('link',{name:'대시보드'}));
    await userEvent.click(screen.getByRole('button',{name:'저장 후 나가기'}));
    expect(saveAndLeave).toHaveBeenCalledOnce();
    expect(discardAndLeave).not.toHaveBeenCalled();
    expect(await screen.findByRole('heading',{name:'대시보드 화면'})).toBeInTheDocument();
  });

  it('discards the partial session before navigating',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response(admin)));
    const {saveAndLeave,discardAndLeave}=renderGuard();
    await userEvent.click(await screen.findByRole('link',{name:'대시보드'}));
    await userEvent.click(screen.getByRole('button',{name:'저장하지 않고 나가기'}));
    expect(discardAndLeave).toHaveBeenCalledOnce();
    expect(saveAndLeave).not.toHaveBeenCalled();
    expect(await screen.findByRole('heading',{name:'대시보드 화면'})).toBeInTheDocument();
  });
});
