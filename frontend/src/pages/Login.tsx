import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CircleAlert, Fingerprint, LockKeyhole } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { endpoints } from '../api/queries';
import { passkeyErrorMessage, startPasskeyAuthentication } from '../auth/passkeys';

export function Login({ onAuthenticated }: { onAuthenticated?: () => void }) {
  const client = useQueryClient();
  const [credentialMode,setCredentialMode]=useState<'admin'|'registration'|null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const passkey = useMutation({
    mutationFn: async () => {
      const options = await endpoints.passkeyAuthenticationOptions();
      const credential = await startPasskeyAuthentication(options);
      return endpoints.verifyPasskeyAuthentication(credential);
    },
    onSuccess: user => { client.setQueryData(['me'], user); onAuthenticated?.(); },
  });
  const registration = useMutation({
    mutationFn: () => endpoints.login(username, password),
    onSuccess: user => { client.setQueryData(['me'], user); onAuthenticated?.(); },
  });
  const submitRegistration = (event: FormEvent) => {
    event.preventDefault();
    registration.mutate();
  };

  return <main className="login-page"><section className="login-card passkey-card">
    <div className="auth-heading-row">
      <h1 className="auth-title"><LockKeyhole /><span>로그인</span></h1>
      <button type="button" className="auth-info-trigger" aria-label="로그인 안내" aria-describedby="login-guidance-tooltip">
        <CircleAlert className="auth-info-icon" />
        <span id="login-guidance-tooltip" className="auth-guidance-tooltip" role="tooltip">
          <span className="auth-guidance-line">관리자가 발급한 계정으로</span>
          <span className="auth-guidance-line">사용 기기를 등록합니다.</span>
          <span className="auth-guidance-line tooltip-section">Passkey 정보는 합격비서 사용자 인증과</span>
          <span className="auth-guidance-line">기기 등록에만 사용됩니다.</span>
        </span>
      </button>
    </div>
    <p className="muted login-intro">등록된 기기의 지문, Face ID 또는 화면 잠금으로 로그인하세요.</p>
    {passkey.isError && <p className="form-error" role="alert">{passkeyErrorMessage(passkey.error, false)}</p>}
    <button className="button" disabled={passkey.isPending || registration.isPending} onClick={() => passkey.mutate()}>
      <Fingerprint size={20} />{passkey.isPending ? '인증 확인 중…' : 'Passkey로 로그인'}
    </button>
    <button className="passkey-logout" disabled={passkey.isPending || registration.isPending} onClick={()=>setCredentialMode(current=>current==='admin'?null:'admin')}>
      {credentialMode==='admin'?'관리자 로그인 닫기':'관리자 로그인'}
    </button>
    <button className="passkey-logout" disabled={passkey.isPending || registration.isPending} onClick={()=>setCredentialMode(current=>current==='registration'?null:'registration')}>
      {credentialMode==='registration'?'등록 입력 닫기':'최초 기기 등록'}
    </button>
    {credentialMode && <form onSubmit={submitRegistration}>
      <p className="muted">{credentialMode==='admin'?'환경파일에 설정된 관리자 계정으로 로그인하세요.':'관리자가 발급한 계정으로 진행하세요.'}</p>
      <label>{credentialMode==='admin'?'관리자 아이디':'아이디'}<input value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" required minLength={3} /></label>
      <label>{credentialMode==='admin'?'관리자 비밀번호':'임시 비밀번호'}<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" required minLength={8} /></label>
      {registration.isError && <p className="form-error" role="alert">{registration.error.message}</p>}
      <button className="button" disabled={registration.isPending}>{registration.isPending?'확인 중…':credentialMode==='admin'?'로그인':'기기 등록 계속'}</button>
    </form>}
  </section></main>;
}

export function AdminReset() {
  const [username,setUsername]=useState('admin');
  const [recoveryKey,setRecoveryKey]=useState('');
  const recovery=useMutation({
    mutationFn:()=>endpoints.recoverAdminPasskey(username,recoveryKey),
    onSuccess:()=>setRecoveryKey(''),
  });
  if(recovery.isSuccess)return <main className="login-page"><section className="login-card passkey-card">
    <div className="auth-heading-row"><h1 className="auth-title"><LockKeyhole/><span>관리자 기기 복구</span></h1></div>
    <div className="state" role="status"><strong>관리자 기기 인증 정보가 초기화되었습니다</strong><span>로그인 화면에서 관리자 계정으로 다시 로그인하세요.</span><a className="button" href="/login">로그인 화면으로 이동</a></div>
  </section></main>;
  return <main className="login-page"><section className="login-card passkey-card">
    <div className="auth-heading-row"><h1 className="auth-title"><LockKeyhole/><span>관리자 기기 복구</span></h1></div>
    <p className="muted">관리자 Passkey와 활성 로그인 세션만 초기화합니다. 계정과 학습 데이터는 삭제되지 않습니다.</p>
    <form onSubmit={event=>{event.preventDefault();recovery.mutate()}}>
      <label>관리자 아이디<input value={username} onChange={event=>setUsername(event.target.value)} autoComplete="username" required minLength={3}/></label>
      <label>복구 키<input type="password" value={recoveryKey} onChange={event=>setRecoveryKey(event.target.value)} autoComplete="off" required minLength={32}/></label>
      {recovery.isError&&<p className="form-error" role="alert">관리자 기기 복구에 실패했습니다.</p>}
      <button className="button danger-button" disabled={recovery.isPending}>{recovery.isPending?'초기화 중…':'관리자 기기 초기화'}</button>
    </form>
    <a className="passkey-logout" href="/login">로그인 화면으로 돌아가기</a>
  </section></main>;
}
