import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Fingerprint, LockKeyhole } from 'lucide-react';
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
    <h1 className="auth-title"><LockKeyhole />로그인</h1>
    <p className="muted">등록된 기기의 지문, Face ID 또는 화면 잠금으로 로그인하세요.</p>
    {passkey.isError && <p className="form-error" role="alert">{passkeyErrorMessage(passkey.error, false)}</p>}
    <button className="button" disabled={passkey.isPending || registration.isPending} onClick={() => passkey.mutate()}>
      <Fingerprint size={20} />{passkey.isPending ? '인증 확인 중…' : 'Passkey로 로그인'}
    </button>
    <button className="passkey-logout" disabled={passkey.isPending || registration.isPending} onClick={() => setShowRegistration(value => !value)}>
      {showRegistration ? '등록 입력 닫기' : '최초 기기 등록'}
    </button>
    {showRegistration && <form onSubmit={submitRegistration}>
      <p className="muted">관리자가 발급한 계정 또는 admin 계정으로 진행하세요.</p>
      <label>아이디<input value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" required minLength={3} /></label>
      <label>임시 비밀번호<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" required minLength={8} /></label>
      {registration.isError && <p className="form-error" role="alert">{registration.error.message}</p>}
      <button className="button" disabled={registration.isPending}>{registration.isPending ? '확인 중…' : '기기 등록 계속'}</button>
    </form>}
  </section></main>;
}
