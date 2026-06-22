/**
 * Auth for the public platform user pool (platform.bridging-data.com).
 * Separate from the corp user pool used in /corp.
 */

const REGION = process.env.NEXT_PUBLIC_PLATFORM_COGNITO_REGION ?? 'eu-central-1'
const CLIENT_ID = process.env.NEXT_PUBLIC_PLATFORM_COGNITO_CLIENT_ID ?? ''
const COGNITO_URL = `https://cognito-idp.${REGION}.amazonaws.com/`

const TOKEN_KEY = 'platform_id_token'
const EXPIRY_KEY = 'platform_token_expiry'
const EMAIL_KEY = 'platform_email'
const GROUPS_KEY = 'platform_groups'

export interface PlatformAuth {
  idToken: string
  email: string
  expiresAt: number
  groups: string[]
}

export function isCorpAdmin(auth: PlatformAuth): boolean {
  return auth.groups.includes('corp-admins')
}

function decodeGroups(idToken: string): string[] {
  try {
    const payload = JSON.parse(atob(idToken.split('.')[1]))
    const raw = payload['cognito:groups']
    if (!raw) return []
    if (Array.isArray(raw)) return raw
    return String(raw).replace(/^\[|\]$/g, '').split(/\s+/).filter(Boolean)
  } catch {
    return []
  }
}

async function cognitoRequest(target: string, body: Record<string, unknown>): Promise<Response> {
  return fetch(COGNITO_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': `AWSCognitoIdentityProviderService.${target}`,
    },
    body: JSON.stringify(body),
  })
}

export async function platformSignUp(email: string, password: string): Promise<void> {
  const res = await cognitoRequest('SignUp', {
    ClientId: CLIENT_ID,
    Username: email,
    Password: password,
    UserAttributes: [{ Name: 'email', Value: email }],
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message ?? `Sign up failed (${res.status})`)
  }
}

export async function platformConfirmSignUp(email: string, code: string): Promise<void> {
  const res = await cognitoRequest('ConfirmSignUp', {
    ClientId: CLIENT_ID,
    Username: email,
    ConfirmationCode: code,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message ?? `Confirmation failed (${res.status})`)
  }
}

export async function platformLogin(email: string, password: string): Promise<PlatformAuth> {
  const res = await cognitoRequest('InitiateAuth', {
    AuthFlow: 'USER_PASSWORD_AUTH',
    ClientId: CLIENT_ID,
    AuthParameters: { USERNAME: email, PASSWORD: password },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message ?? `Login failed (${res.status})`)
  }
  const data = await res.json()
  const idToken: string = data.AuthenticationResult.IdToken
  const expiresIn: number = data.AuthenticationResult.ExpiresIn ?? 3600
  const expiresAt = Date.now() + expiresIn * 1000

  const groups = decodeGroups(idToken)
  localStorage.setItem(TOKEN_KEY, idToken)
  localStorage.setItem(EXPIRY_KEY, String(expiresAt))
  localStorage.setItem(EMAIL_KEY, email)
  localStorage.setItem(GROUPS_KEY, JSON.stringify(groups))

  return { idToken, email, expiresAt, groups }
}

export function platformLogout(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(EXPIRY_KEY)
  localStorage.removeItem(EMAIL_KEY)
  localStorage.removeItem(GROUPS_KEY)
}

export function getPlatformAuth(): PlatformAuth | null {
  if (typeof window === 'undefined') return null
  const idToken = localStorage.getItem(TOKEN_KEY)
  const expiresAt = Number(localStorage.getItem(EXPIRY_KEY) ?? 0)
  const email = localStorage.getItem(EMAIL_KEY) ?? ''
  if (!idToken || Date.now() >= expiresAt) return null
  const groups: string[] = JSON.parse(localStorage.getItem(GROUPS_KEY) ?? '[]')
  return { idToken, email, expiresAt, groups }
}
