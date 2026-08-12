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
    setGuard({kind:'study',sessionId:'study-1',answeredCount:3,saveAndLeave,discardAndLeave});
    return ()=>setGuard(current=>current?.sessionId==='study-1'?null:current);
  },[discardAndLeave,saveAndLeave,setGuard]);
  return <h1>학습 화면</h1>;
}

function ActiveExam(){
  const {setGuard}=useStudyExitGuard();
  useEffect(()=>{
    setGuard({kind:'exam',sessionId:'exam-1',answeredCount:1,totalCount:3,unansweredNumbers:[2,3]});
    return ()=>setGuard(current=>current?.sessionId==='exam-1'?null:current);
  },[setGuard]);
  return <h1>모의고사 화면</h1>;
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

  it('keeps the study open and reports a save failure',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response(admin)));
    renderGuard(vi.fn().mockRejectedValue(new Error('저장 실패')));
    await userEvent.click(await screen.findByRole('link',{name:'대시보드'}));
    await userEvent.click(screen.getByRole('button',{name:'저장 후 나가기'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('저장 실패');
    expect(screen.getByRole('heading',{name:'학습 화면'})).toBeInTheDocument();
  });
});

describe('Mock exam exit guard',()=>{
  it('shows progress and unanswered numbers before menu navigation',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response(admin)));
    const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/mock-exam/1']}><Routes><Route element={<Layout/>}><Route path="mock-exam/:id" element={<ActiveExam/>}/><Route index element={<h1>대시보드 화면</h1>}/></Route></Routes></MemoryRouter></QueryClientProvider>);

    await userEvent.click(await screen.findByRole('link',{name:'대시보드'}));
    const dialog=screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('모의고사를 종료하시겠습니까?');
    expect(dialog).toHaveTextContent('총 3문제 중 1문제를 풀었습니다.');
    expect(dialog).toHaveTextContent('2, 3');
    await userEvent.click(screen.getByRole('button',{name:'취소'}));
    expect(screen.getByRole('heading',{name:'모의고사 화면'})).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link',{name:'대시보드'}));
    await userEvent.click(screen.getByRole('button',{name:'시험 종료'}));
    expect(await screen.findByRole('heading',{name:'대시보드 화면'})).toBeInTheDocument();
  });
});
