type WebAuthnJson = Record<string, unknown>;

export function passkeyErrorMessage(error: unknown, registration: boolean): string {
  const fallback = registration
    ? 'Passkey 등록에 실패했습니다. 다시 시도하거나 관리자에게 문의해주세요.'
    : 'Passkey 인증에 실패했습니다. 다시 시도하거나 관리자에게 문의해주세요.';
  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError') {
      return `Passkey ${registration ? '등록' : '인증'}이 취소되었거나 시간이 초과되었습니다. 다시 시도해주세요.`;
    }
    if (error.name === 'SecurityError') {
      return `현재 접속 주소에서는 Passkey ${registration ? '등록' : '인증'}을 사용할 수 없습니다. 관리자에게 문의해주세요.`;
    }
    if (error.name === 'NotSupportedError') {
      return '이 브라우저 또는 기기는 Passkey를 지원하지 않습니다. 관리자에게 문의해주세요.';
    }
    if (error.name === 'InvalidStateError') {
      return '이미 등록된 인증키입니다. 관리자에게 기기 초기화를 요청해주세요.';
    }
    if (error.name === 'AbortError') {
      return `Passkey ${registration ? '등록' : '인증'}이 중단되었습니다. 다시 시도해주세요.`;
    }
  }
  const message = error instanceof Error ? error.message : '';
  if (message.includes('일치하지 않습니다')) {
    return '인증키가 일치하지 않습니다. 관리자에게 문의해주세요.';
  }
  if (message.includes('등록된 Passkey가 없습니다')) {
    return '등록된 인증키를 찾을 수 없습니다. 관리자에게 기기 초기화를 요청해주세요.';
  }
  if (message.includes('만료')) {
    return `Passkey ${registration ? '등록' : '인증'} 요청이 만료되었습니다. 다시 시도해주세요.`;
  }
  if (message.includes('지원하지 않습니다') || message.includes('HTTPS')) {
    return '이 브라우저 또는 접속 환경에서는 Passkey를 사용할 수 없습니다. 관리자에게 문의해주세요.';
  }
  if (message.includes('인증에 실패') || message.includes('검증하지 못했습니다')) {
    return fallback;
  }
  return fallback;
}

function decodeBase64Url(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(value.length / 4) * 4, '=');
  const binary = window.atob(padded);
  return Uint8Array.from(binary, character => character.charCodeAt(0)).buffer;
}

function encodeBase64Url(value: ArrayBuffer): string {
  const bytes = new Uint8Array(value);
  let binary = '';
  bytes.forEach(byte => { binary += String.fromCharCode(byte); });
  return window.btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function parseCreationOptions(options: WebAuthnJson): PublicKeyCredentialCreationOptions {
  const parser = PublicKeyCredential as typeof PublicKeyCredential & {
    parseCreationOptionsFromJSON?: (value: WebAuthnJson) => PublicKeyCredentialCreationOptions;
  };
  if (parser.parseCreationOptionsFromJSON) return parser.parseCreationOptionsFromJSON(options);
  const user = options.user as WebAuthnJson;
  const excluded = (options.excludeCredentials as WebAuthnJson[] | undefined) ?? [];
  return {
    ...options,
    challenge: decodeBase64Url(String(options.challenge)),
    user: { ...user, id: decodeBase64Url(String(user.id)) },
    excludeCredentials: excluded.map(item => ({ ...item, id: decodeBase64Url(String(item.id)) })),
  } as PublicKeyCredentialCreationOptions;
}

function parseRequestOptions(options: WebAuthnJson): PublicKeyCredentialRequestOptions {
  const parser = PublicKeyCredential as typeof PublicKeyCredential & {
    parseRequestOptionsFromJSON?: (value: WebAuthnJson) => PublicKeyCredentialRequestOptions;
  };
  if (parser.parseRequestOptionsFromJSON) return parser.parseRequestOptionsFromJSON(options);
  const allowed = (options.allowCredentials as WebAuthnJson[] | undefined) ?? [];
  return {
    ...options,
    challenge: decodeBase64Url(String(options.challenge)),
    allowCredentials: allowed.map(item => ({ ...item, id: decodeBase64Url(String(item.id)) })),
  } as PublicKeyCredentialRequestOptions;
}

function credentialToJson(credential: PublicKeyCredential): WebAuthnJson {
  const modern = credential as PublicKeyCredential & { toJSON?: () => WebAuthnJson };
  if (modern.toJSON) return modern.toJSON();
  const response = credential.response;
  const jsonResponse: WebAuthnJson = { clientDataJSON: encodeBase64Url(response.clientDataJSON) };
  if (response instanceof AuthenticatorAttestationResponse) {
    jsonResponse.attestationObject = encodeBase64Url(response.attestationObject);
    jsonResponse.transports = response.getTransports?.() ?? [];
  } else if (response instanceof AuthenticatorAssertionResponse) {
    jsonResponse.authenticatorData = encodeBase64Url(response.authenticatorData);
    jsonResponse.signature = encodeBase64Url(response.signature);
    jsonResponse.userHandle = response.userHandle ? encodeBase64Url(response.userHandle) : null;
  }
  return {
    id: credential.id,
    rawId: encodeBase64Url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
    response: jsonResponse,
  };
}

function ensureWebAuthn(): void {
  if (!window.isSecureContext || !window.PublicKeyCredential || !navigator.credentials) {
    throw new Error('이 기기 또는 브라우저에서는 Passkey를 사용할 수 없습니다. HTTPS와 최신 브라우저를 확인하세요.');
  }
}

export async function startPasskeyRegistration(options: WebAuthnJson): Promise<WebAuthnJson> {
  ensureWebAuthn();
  const credential = await navigator.credentials.create({ publicKey: parseCreationOptions(options) });
  if (!(credential instanceof PublicKeyCredential)) throw new Error('Passkey 등록이 취소되었습니다.');
  return credentialToJson(credential);
}

export async function startPasskeyAuthentication(options: WebAuthnJson): Promise<WebAuthnJson> {
  ensureWebAuthn();
  const credential = await navigator.credentials.get({ publicKey: parseRequestOptions(options) });
  if (!(credential instanceof PublicKeyCredential)) throw new Error('Passkey 인증이 취소되었습니다.');
  return credentialToJson(credential);
}
