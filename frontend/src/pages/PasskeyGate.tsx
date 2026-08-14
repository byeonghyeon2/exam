import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Fingerprint, LogOut } from 'lucide-react';
import { endpoints } from '../api/queries';
import { passkeyErrorMessage, startPasskeyRegistration } from '../auth/passkeys';
import type { User } from '../types';

export function PasskeyGate({ user }: { user: User }) {
  const client = useQueryClient();
  const passkey = useMutation({
    mutationFn: async () => {
      const options = await endpoints.passkeyRegistrationOptions();
      return endpoints.verifyPasskeyRegistration(await startPasskeyRegistration(options));
    },
    onSuccess: verified => client.setQueryData(['me'], verified),
  });
  const logout = useMutation({
    mutationFn: endpoints.logout,
    onSettled: () => { client.clear(); window.location.assign('/'); },
  });
  return <main className="login-page"><section className="login-card passkey-card">
    <h1 className="auth-title"><Fingerprint />Passkey 등록</h1>
    <p className="muted">현재 기기의 지문, Face ID 또는 화면 잠금으로 최초 Passkey를 등록하세요.</p>
    <div className="passkey-notice"><b>{user.username}</b><span>등록 완료 전에는 문제 데이터에 접근할 수 없습니다.</span></div>
    {passkey.isError && <p className="form-error" role="alert">{passkeyErrorMessage(passkey.error, true)}</p>}
    <button className="button" disabled={passkey.isPending} onClick={() => passkey.mutate()}>{passkey.isPending ? '등록 확인 중…' : '이 기기에 Passkey 등록'}</button>
    <button className="passkey-logout" disabled={logout.isPending} onClick={() => logout.mutate()}><LogOut size={17} />로그아웃</button>
  </section></main>;
}
