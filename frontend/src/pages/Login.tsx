import {useMutation,useQueryClient} from '@tanstack/react-query';
import {LockKeyhole} from 'lucide-react';
import {type FormEvent,useState} from 'react';
import {endpoints} from '../api/queries';

export function Login(){
  const client=useQueryClient();
  const [username,setUsername]=useState('');
  const [password,setPassword]=useState('');
  const login=useMutation({mutationFn:()=>endpoints.login(username,password),onSuccess:user=>client.setQueryData(['me'],user)});
  const submit=(event:FormEvent)=>{event.preventDefault();login.mutate()};
  return <main className="login-page"><section className="login-card"><h1 className="auth-title"><LockKeyhole/>로그인</h1><p className="muted">관리자가 등록한 계정으로 로그인하세요.</p><form onSubmit={submit}><label>아이디<input value={username} onChange={event=>setUsername(event.target.value)} autoComplete="username" required minLength={3}/></label><label>비밀번호<input type="password" value={password} onChange={event=>setPassword(event.target.value)} autoComplete="current-password" required minLength={8}/></label>{login.isError&&<p className="form-error">{login.error.message}</p>}<button className="button" disabled={login.isPending}>{login.isPending?'로그인 중…':'로그인'}</button></form></section></main>;
}
