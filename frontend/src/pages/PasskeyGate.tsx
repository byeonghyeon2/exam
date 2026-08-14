import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Fingerprint, LogOut } from 'lucide-react';
import { endpoints } from '../api/queries';
import { passkeyErrorMessage, startPasskeyAuthentication, startPasskeyRegistration } from '../auth/passkeys';
import type { User } from '../types';

export function PasskeyGate({ user }: { user: User }) {
  const client = useQueryClient();
  const registration = Boolean(user.passkey_registration_required);
  const passkey = useMutation({
    mutationFn: async () => {
      if (registration) {
        const options = await endpoints.passkeyRegistrationOptions();
        return endpoints.verifyPasskeyRegistration(await startPasskeyRegistration(options));
      }
      const options = await endpoints.passkeyAuthenticationOptions();
      return endpoints.verifyPasskeyAuthentication(await startPasskeyAuthentication(options));
    },
    onSuccess: verified => client.setQueryData(['me'], verified),
  });
  const logout = useMutation({
    mutationFn: endpoints.logout,
    onSettled: () => { client.clear(); window.location.assign('/'); },
  });
  return <main className="login-page"><section className="login-card passkey-card">
    <h1 className="auth-title"><Fingerprint />{registration ? 'Passkey 등록' : 'Passkey 인증'}</h1>
    <p className="muted">{registration
      ? '이 계정은 최초 사용 전 현재 기기의 지문, Face ID 또는 화면 잠금을 등록해야 합니다.'
      : '등록된 기기의 지문, Face ID 또는 화면 잠금으로 인증해 주세요.'}</p>
    <div className="passkey-notice"><b>{user.username}</b><span>{registration ? '등록 완료 전에는 문제 데이터에 접근할 수 없습니다.' : '인증이 완료되면 기존 로그인 기기는 자동 로그아웃됩니다.'}</span></div>
    {passkey.isError && <p className="form-error" role="alert">{passkeyErrorMessage(passkey.error, registration)}</p>}
    <button className="button" disabled={passkey.isPending} onClick={() => passkey.mutate()}>{passkey.isPending
      ? registration ? '등록 확인 중…' : '인증 확인 중…'
      : registration ? '이 기기에 Passkey 등록' : 'Passkey로 인증'}</button>
    <button className="passkey-logout" disabled={logout.isPending} onClick={() => logout.mutate()}><LogOut size={17} />로그아웃</button>
  </section></main>;
}
