import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CircleAlert, Fingerprint, LockKeyhole } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { endpoints } from '../api/queries';
import { passkeyErrorMessage, startPasskeyAuthentication } from '../auth/passkeys';

export function Login({ onAuthenticated }: { onAuthenticated?: () => void }) {
  const client = useQueryClient();
  const [showRegistration, setShowRegistration] = useState(false);
  const [showRecovery, setShowRecovery] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [recoveryUsername, setRecoveryUsername] = useState('admin');
  const [recoveryKey, setRecoveryKey] = useState('');
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
  const recovery = useMutation({
    mutationFn: () => endpoints.recoverAdminPasskey(recoveryUsername, recoveryKey),
    onSuccess: () => { setRecoveryKey(''); setShowRecovery(false); setShowRegistration(true); },
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
    <button className="passkey-logout" disabled={passkey.isPending || registration.isPending} onClick={() => setShowRegistration(value => !value)}>
      {showRegistration ? '등록 입력 닫기' : '최초 기기 등록'}
    </button>
    {showRegistration && <form onSubmit={submitRegistration}>
      <p className="muted">관리자가 발급한 계정으로 진행하세요.</p>
      <label>아이디<input value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" required minLength={3} /></label>
      <label>임시 비밀번호<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" required minLength={8} /></label>
      {registration.isError && <p className="form-error" role="alert">{registration.error.message}</p>}
      <button className="button" disabled={registration.isPending}>{registration.isPending ? '확인 중…' : '기기 등록 계속'}</button>
    </form>}
    <button className="passkey-logout admin-recovery-toggle" disabled={passkey.isPending || registration.isPending || recovery.isPending} onClick={() => setShowRecovery(value => !value)}>관리자 기기 복구</button>
    {showRecovery && <form onSubmit={event => { event.preventDefault(); recovery.mutate(); }}>
      <p className="muted">복구는 관리자 Passkey와 로그인 세션만 초기화합니다. 완료 후 관리자 비밀번호로 기기를 다시 등록하세요.</p>
      <label>관리자 아이디<input value={recoveryUsername} onChange={event => setRecoveryUsername(event.target.value)} autoComplete="username" required minLength={3}/></label>
      <label>복구 키<input type="password" value={recoveryKey} onChange={event => setRecoveryKey(event.target.value)} autoComplete="off" required minLength={32}/></label>
      {recovery.isError && <p className="form-error" role="alert">관리자 기기 복구에 실패했습니다.</p>}
      <button className="button danger-button" disabled={recovery.isPending}>{recovery.isPending?'초기화 중…':'관리자 기기 초기화'}</button>
    </form>}
  </section></main>;
}
