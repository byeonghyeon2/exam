import { afterEach, describe, expect, it, vi } from 'vitest';
import { passkeyErrorMessage, startPasskeyAuthentication, startPasskeyRegistration } from '../auth/passkeys';

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

    const noTransports = new LegacyCredential(new Attestation());
    (noTransports.response as Attestation).getTransports = undefined as unknown as () => string[];
    create.mockResolvedValueOnce(noTransports);
    await expect(startPasskeyRegistration({ challenge: 'AQ', user: { id: 'Ag' } }))
      .resolves.toMatchObject({ response: { transports: [] } });
    const noUserHandle = new LegacyCredential(new Assertion());
    (noUserHandle.response as Assertion).userHandle = null as unknown as ArrayBuffer;
    get.mockResolvedValueOnce(noUserHandle);
    await expect(startPasskeyAuthentication({ challenge: 'AQ' }))
      .resolves.toMatchObject({ response: { userHandle: null } });
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

    vi.stubGlobal('isSecureContext', true);
    vi.stubGlobal('PublicKeyCredential', undefined);
    await expect(startPasskeyAuthentication({ challenge: 'AQ' })).rejects.toThrow('Passkey');
    class SupportedCredential {}
    vi.stubGlobal('PublicKeyCredential', SupportedCredential);
    Object.defineProperty(navigator, 'credentials', { configurable: true, value: undefined });
    await expect(startPasskeyAuthentication({ challenge: 'AQ' })).rejects.toThrow('Passkey');
  });

  it('maps browser and server failures to stable Korean guidance', () => {
    expect(passkeyErrorMessage(new DOMException('', 'NotAllowedError'), false)).toBe(
      'Passkey 인증이 취소되었거나 시간이 초과되었습니다. 다시 시도해주세요.',
    );
    expect(passkeyErrorMessage(new DOMException('', 'SecurityError'), false)).toBe(
      '현재 접속 주소에서는 Passkey 인증을 사용할 수 없습니다. 관리자에게 문의해주세요.',
    );
    expect(passkeyErrorMessage(new DOMException('', 'SecurityError'), true)).toContain('등록');
    expect(passkeyErrorMessage(new DOMException('', 'NotSupportedError'), false)).toBe(
      '이 브라우저 또는 기기는 Passkey를 지원하지 않습니다. 관리자에게 문의해주세요.',
    );
    expect(passkeyErrorMessage(new DOMException('', 'InvalidStateError'), true)).toBe(
      '이미 등록된 인증키입니다. 관리자에게 기기 초기화를 요청해주세요.',
    );
    expect(passkeyErrorMessage(new DOMException('', 'AbortError'), true)).toBe(
      'Passkey 등록이 중단되었습니다. 다시 시도해주세요.',
    );
    expect(passkeyErrorMessage(new DOMException('', 'AbortError'), false)).toContain('인증');
    expect(passkeyErrorMessage(new Error('등록된 Passkey와 일치하지 않습니다'), false)).toBe(
      '인증키가 일치하지 않습니다. 관리자에게 문의해주세요.',
    );
    expect(passkeyErrorMessage(new Error('등록된 Passkey가 없습니다'), false)).toBe(
      '등록된 인증키를 찾을 수 없습니다. 관리자에게 기기 초기화를 요청해주세요.',
    );
    expect(passkeyErrorMessage(new Error('Passkey 요청이 만료되었습니다'), true)).toBe(
      'Passkey 등록 요청이 만료되었습니다. 다시 시도해주세요.',
    );
    expect(passkeyErrorMessage(new Error('Passkey 요청이 만료되었습니다'), false)).toContain('인증 요청');
    expect(passkeyErrorMessage(new Error('HTTPS를 지원하지 않습니다'), false)).toBe(
      '이 브라우저 또는 접속 환경에서는 Passkey를 사용할 수 없습니다. 관리자에게 문의해주세요.',
    );
    expect(passkeyErrorMessage(new Error('지원하지 않습니다'), false)).toContain('접속 환경');
    expect(passkeyErrorMessage(new Error('검증하지 못했습니다'), true)).toContain('등록에 실패');
    expect(passkeyErrorMessage(new Error('unknown'), true)).toBe(
      'Passkey 등록에 실패했습니다. 다시 시도하거나 관리자에게 문의해주세요.',
    );
    expect(passkeyErrorMessage('unknown', false)).toBe(
      'Passkey 인증에 실패했습니다. 다시 시도하거나 관리자에게 문의해주세요.',
    );
    expect(passkeyErrorMessage(new Error('Passkey 인증에 실패했습니다'), false)).toBe(
      'Passkey 인증에 실패했습니다. 다시 시도하거나 관리자에게 문의해주세요.',
    );
  });
});
