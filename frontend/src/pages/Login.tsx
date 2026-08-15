import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CircleAlert, Fingerprint, LockKeyhole } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { endpoints } from '../api/queries';
import { passkeyErrorMessage, startPasskeyAuthentication } from '../auth/passkeys';

export function Login() {
  const client = useQueryClient();
  const [showRegistration, setShowRegistration] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const passkey = useMutation({
    mutationFn: async () => {
      const options = await endpoints.passkeyAuthenticationOptions();
      const credential = await startPasskeyAuthentication(options);
      return endpoints.verifyPasskeyAuthentication(credential);
    },
    onSuccess: user => client.setQueryData(['me'], user),
  });
  const registration = useMutation({
    mutationFn: () => endpoints.login(username, password),
    onSuccess: user => client.setQueryData(['me'], user),
  });
  const submitRegistration = (event: FormEvent) => {
    event.preventDefault();
    registration.mutate();
  };

  return <main className="login-page"><section className="login-card passkey-card">
    <div className="auth-heading-row"><h1 className="auth-title"><LockKeyhole /><span>로그인</span></h1><CircleAlert className="auth-info-icon" aria-label="로그인 안내" /></div>
    <div className="auth-guidance muted">
      <p><span className="auth-guidance-line">관리자가 발급한 계정으로</span><span className="auth-guidance-line">사용 기기를 등록합니다.</span></p>
      <p><span className="auth-guidance-line">Passkey 정보는 합격비서 사용자 인증과</span><span className="auth-guidance-line">기기 등록에만 사용됩니다.</span></p>
    </div>
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
  </section></main>;
}
