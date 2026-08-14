import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { endpoints } from '../api/queries';
import * as passkeys from '../auth/passkeys';
import { PasskeyGate } from '../pages/PasskeyGate';
import type { User } from '../types';

const pending: User = {
  id: 2, username: 'learner', role: 'user', is_active: true,
  password_managed_by_environment: false, passkey_registered: false,
  passkey_registration_required: true, passkey_authentication_required: false,
  created_at: '2026-08-14T00:00:00Z', last_login_at: null,
};

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function renderGate(user: User) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><PasskeyGate user={user} /></QueryClientProvider>);
  return client;
}

describe('PasskeyGate', () => {
  it('registers a platform passkey before activating a new managed account', async () => {
    const options = { challenge: 'challenge' };
    const credential = { id: 'credential' };
    vi.spyOn(endpoints, 'passkeyRegistrationOptions').mockResolvedValue(options);
    vi.spyOn(passkeys, 'startPasskeyRegistration').mockResolvedValue(credential);
    const verified = { ...pending, passkey_registered: true, passkey_registration_required: false };
    vi.spyOn(endpoints, 'verifyPasskeyRegistration').mockResolvedValue(verified);
    const client = renderGate(pending);

    await userEvent.click(screen.getByRole('button', { name: '이 기기에 Passkey 등록' }));
    expect(passkeys.startPasskeyRegistration).toHaveBeenCalledWith(options);
    expect(endpoints.verifyPasskeyRegistration).toHaveBeenCalledWith(credential);
    expect(client.getQueryData(['me'])).toEqual(verified);
  });

  it('shows browser registration failures as an actionable Korean message', async () => {
    vi.spyOn(endpoints, 'passkeyRegistrationOptions').mockResolvedValue({ challenge: 'challenge' });
    vi.spyOn(passkeys, 'startPasskeyRegistration').mockRejectedValue(
      new DOMException('The operation either timed out or was not allowed.', 'NotAllowedError'),
    );
    renderGate(pending);

    await userEvent.click(screen.getByRole('button', { name: '이 기기에 Passkey 등록' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Passkey 등록이 취소되었거나 시간이 초과되었습니다. 다시 시도해주세요.',
    );
    expect(screen.queryByText(/The operation either timed out/)).not.toBeInTheDocument();
  });

  it('shows pending controls and clears local state when logging out', async () => {
    let resolveOptions!: (value: Record<string, unknown>) => void;
    vi.spyOn(endpoints, 'passkeyRegistrationOptions').mockImplementation(
      () => new Promise(resolve => { resolveOptions = resolve; }),
    );
    vi.spyOn(endpoints, 'logout').mockResolvedValue();
    const client = renderGate(pending);
    client.setQueryData(['me'], pending);

    await userEvent.click(screen.getByRole('button', { name: '이 기기에 Passkey 등록' }));
    expect(screen.getByRole('button', { name: '등록 확인 중…' })).toBeDisabled();
    resolveOptions({ challenge: 'AA' });

    await userEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(endpoints.logout).toHaveBeenCalled());
    await waitFor(() => expect(client.getQueryData(['me'])).toBeUndefined());
  });
});
