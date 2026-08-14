type WebAuthnJson = Record<string, unknown>;

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
