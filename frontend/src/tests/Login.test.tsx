import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { endpoints } from '../api/queries';
import * as passkeys from '../auth/passkeys';
import { Login } from '../pages/Login';
import type { User } from '../types';

const authenticated: User = {
  id: 2, username: 'learner', role: 'user', is_active: true,
  password_managed_by_environment: false, passkey_registered: true,
  passkey_registration_required: false, passkey_authentication_required: false,
  created_at: '2026-08-14T00:00:00Z', last_login_at: '2026-08-14T01:00:00Z',
};

function renderLogin() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><Login /></QueryClientProvider>);
  return client;
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Passkey-first login', () => {
  it('logs in directly with a discoverable Passkey without asking for a password', async () => {
    vi.spyOn(endpoints, 'passkeyAuthenticationOptions').mockResolvedValue({ challenge: 'AA' });
    vi.spyOn(passkeys, 'startPasskeyAuthentication').mockResolvedValue({ id: 'credential' });
    vi.spyOn(endpoints, 'verifyPasskeyAuthentication').mockResolvedValue(authenticated);
    const client = renderLogin();

    expect(screen.queryByLabelText('아이디')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Passkey로 로그인' }));

    expect(endpoints.passkeyAuthenticationOptions).toHaveBeenCalled();
    expect(endpoints.verifyPasskeyAuthentication).toHaveBeenCalledWith({ id: 'credential' });
    await waitFor(() => expect(client.getQueryData(['me'])).toEqual(authenticated));
  });

  it('uses the administrator-issued credentials only for initial device registration', async () => {
    const pending = {
      ...authenticated, passkey_registered: false, passkey_registration_required: true,
    };
    vi.spyOn(endpoints, 'login').mockResolvedValue(pending);
    const client = renderLogin();

    await userEvent.click(screen.getByRole('button', { name: '최초 기기 등록' }));
    await userEvent.type(screen.getByLabelText('아이디'), 'learner');
    await userEvent.type(screen.getByLabelText('임시 비밀번호'), 'temporary-password');
    await userEvent.click(screen.getByRole('button', { name: '기기 등록 계속' }));

    expect(endpoints.login).toHaveBeenCalledWith('learner', 'temporary-password');
    await waitFor(() => expect(client.getQueryData(['me'])).toEqual(pending));
  });

  it('shows stable Korean guidance when mobile Passkey authentication is cancelled', async () => {
    vi.spyOn(endpoints, 'passkeyAuthenticationOptions').mockResolvedValue({ challenge: 'AA' });
    vi.spyOn(passkeys, 'startPasskeyAuthentication').mockRejectedValue(
      new DOMException('The operation was not allowed.', 'NotAllowedError'),
    );
    renderLogin();

    await userEvent.click(screen.getByRole('button', { name: 'Passkey로 로그인' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Passkey 인증이 취소되었거나 시간이 초과되었습니다. 다시 시도해주세요.',
    );
  });

  it('shows pending states, closes registration, and renders registration API errors', async () => {
    let resolveOptions!: (value: Record<string, unknown>) => void;
    vi.spyOn(endpoints, 'passkeyAuthenticationOptions').mockImplementation(
      () => new Promise(resolve => { resolveOptions = resolve; }),
    );
    vi.spyOn(passkeys, 'startPasskeyAuthentication').mockRejectedValue(new Error('취소'));
    renderLogin();
    await userEvent.click(screen.getByRole('button', { name: 'Passkey로 로그인' }));
    expect(screen.getByRole('button', { name: '인증 확인 중…' })).toBeDisabled();
    resolveOptions({ challenge: 'AA' });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Passkey로 로그인' })).toBeEnabled());

    await userEvent.click(screen.getByRole('button', { name: '최초 기기 등록' }));
    await userEvent.click(screen.getByRole('button', { name: '등록 입력 닫기' }));
    expect(screen.queryByLabelText('아이디')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '최초 기기 등록' }));
    let rejectLogin!: (reason: Error) => void;
    vi.spyOn(endpoints, 'login').mockImplementation(
      () => new Promise((_resolve, reject) => { rejectLogin = reject; }),
    );
    await userEvent.type(screen.getByLabelText('아이디'), 'learner');
    await userEvent.type(screen.getByLabelText('임시 비밀번호'), 'temporary-password');
    await userEvent.click(screen.getByRole('button', { name: '기기 등록 계속' }));
    expect(screen.getByRole('button', { name: '확인 중…' })).toBeDisabled();
    rejectLogin(new Error('발급 계정을 확인해주세요.'));
    expect(await screen.findByText('발급 계정을 확인해주세요.')).toBeInTheDocument();
  });
});
