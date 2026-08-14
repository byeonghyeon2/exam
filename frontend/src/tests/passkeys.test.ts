import { afterEach, describe, expect, it, vi } from 'vitest';
import { startPasskeyAuthentication, startPasskeyRegistration } from '../auth/passkeys';

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('browser passkey ceremonies', () => {
  it('uses native JSON parsers and returns the browser credential JSON', async () => {
    class NativeCredential {
      static parseCreationOptionsFromJSON = vi.fn(() => ({ challenge: new ArrayBuffer(1) }));
      static parseRequestOptionsFromJSON = vi.fn(() => ({ challenge: new ArrayBuffer(1) }));
      toJSON = vi.fn(() => ({ id: 'native-credential' }));
    }
    const credential = new NativeCredential();
    vi.stubGlobal('PublicKeyCredential', NativeCredential);
    vi.stubGlobal('isSecureContext', true);
    Object.defineProperty(navigator, 'credentials', { configurable: true, value: {
      create: vi.fn().mockResolvedValue(credential), get: vi.fn().mockResolvedValue(credential),
    } });

    await expect(startPasskeyRegistration({ challenge: 'AA', user: { id: 'AA' } })).resolves.toEqual({ id: 'native-credential' });
    await expect(startPasskeyAuthentication({ challenge: 'AA' })).resolves.toEqual({ id: 'native-credential' });
    expect(NativeCredential.parseCreationOptionsFromJSON).toHaveBeenCalled();
    expect(NativeCredential.parseRequestOptionsFromJSON).toHaveBeenCalled();
  });

  it('converts legacy attestation and assertion responses to base64url JSON', async () => {
    class Attestation {
      clientDataJSON = Uint8Array.from([1]).buffer;
      attestationObject = Uint8Array.from([2]).buffer;
      getTransports = () => ['internal'];
    }
    class Assertion {
      clientDataJSON = Uint8Array.from([1]).buffer;
      authenticatorData = Uint8Array.from([2]).buffer;
      signature = Uint8Array.from([3]).buffer;
      userHandle = Uint8Array.from([4]).buffer;
    }
    class LegacyCredential {
      id = 'legacy'; rawId = Uint8Array.from([5]).buffer; type = 'public-key';
      authenticatorAttachment = 'platform';
      response: Attestation | Assertion;
      constructor(response: Attestation | Assertion) { this.response = response; }
      getClientExtensionResults = () => ({});
    }
    vi.stubGlobal('PublicKeyCredential', LegacyCredential);
    vi.stubGlobal('AuthenticatorAttestationResponse', Attestation);
    vi.stubGlobal('AuthenticatorAssertionResponse', Assertion);
    vi.stubGlobal('isSecureContext', true);
    const create = vi.fn().mockResolvedValue(new LegacyCredential(new Attestation()));
    const get = vi.fn().mockResolvedValue(new LegacyCredential(new Assertion()));
    Object.defineProperty(navigator, 'credentials', { configurable: true, value: { create, get } });

    const registered = await startPasskeyRegistration({
      challenge: 'AQ', user: { id: 'Ag' }, excludeCredentials: [{ id: 'Aw', type: 'public-key' }],
    });
    const authenticated = await startPasskeyAuthentication({
      challenge: 'AQ', allowCredentials: [{ id: 'Ag', type: 'public-key' }],
    });
    expect(registered).toMatchObject({ id: 'legacy', response: { transports: ['internal'] } });
    expect(authenticated).toMatchObject({ id: 'legacy', response: { userHandle: 'BA' } });
    expect(create.mock.calls[0]![0].publicKey.excludeCredentials[0].id).toBeInstanceOf(ArrayBuffer);
    expect(get.mock.calls[0]![0].publicKey.allowCredentials[0].id).toBeInstanceOf(ArrayBuffer);
  });

  it('rejects unsupported contexts and cancelled ceremonies', async () => {
    vi.stubGlobal('isSecureContext', false);
    await expect(startPasskeyRegistration({})).rejects.toThrow('HTTPS');

    class EmptyCredential {}
    vi.stubGlobal('PublicKeyCredential', EmptyCredential);
    vi.stubGlobal('isSecureContext', true);
    Object.defineProperty(navigator, 'credentials', { configurable: true, value: {
      create: vi.fn().mockResolvedValue(null), get: vi.fn().mockResolvedValue(null),
    } });
    await expect(startPasskeyRegistration({ challenge: 'AQ', user: { id: 'AQ' } })).rejects.toThrow('취소');
    await expect(startPasskeyAuthentication({ challenge: 'AQ' })).rejects.toThrow('취소');
  });
});
