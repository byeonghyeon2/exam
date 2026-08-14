import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
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

  it('requires the registered passkey after password verification', async () => {
    const authenticating = {
      ...pending, passkey_registered: true, passkey_registration_required: false,
      passkey_authentication_required: true,
    };
    vi.spyOn(endpoints, 'passkeyAuthenticationOptions').mockResolvedValue({ challenge: 'challenge' });
    vi.spyOn(passkeys, 'startPasskeyAuthentication').mockResolvedValue({ id: 'credential' });
    vi.spyOn(endpoints, 'verifyPasskeyAuthentication').mockResolvedValue({
      ...authenticating, passkey_authentication_required: false,
    });
    renderGate(authenticating);

    await userEvent.click(screen.getByRole('button', { name: 'Passkey로 인증' }));
    expect(endpoints.verifyPasskeyAuthentication).toHaveBeenCalledWith({ id: 'credential' });
  });
});
