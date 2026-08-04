import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TokenVerifier } from 'livekit-server-sdk'

const getUser = vi.fn()
const rpc = vi.fn()
vi.mock('@/utils/supabase/server', () => ({
  createClient: vi.fn(async () => ({ auth: { getUser }, rpc })),
}))

import { POST } from './route'
import { createSessionToken } from '@/utils/session-token'

const env = { apiKey: 'key', apiSecret: '01234567890123456789012345678901', serverUrl: 'wss://live.example' }
const request = () => new Request('http://local/api/token', { method: 'POST' })

describe('token route', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://example.supabase.co')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'anon')
  })

  it('rejects cross-origin POST requests before authentication', async () => {
    const response = await POST(new Request('https://flexflow.example/api/token', {
      method: 'POST', headers: { Origin: 'https://evil.example' },
    }))
    expect(response.status).toBe(403)
    expect(getUser).not.toHaveBeenCalled()
  })

  it('rejects unauthenticated callers', async () => {
    getUser.mockResolvedValueOnce({ data: { user: null } })
    expect((await POST(request())).status).toBe(401)
  })

  it('fails closed when authentication configuration is missing', async () => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', '')
    expect((await POST(request())).status).toBe(503)
  })

  it('ignores client-controlled room and identity fields', async () => {
    vi.stubEnv('LIVEKIT_API_KEY', env.apiKey)
    vi.stubEnv('LIVEKIT_API_SECRET', env.apiSecret)
    vi.stubEnv('LIVEKIT_URL', env.serverUrl)
    getUser.mockResolvedValueOnce({ data: { user: { id: 'server-user' } } })
    rpc.mockResolvedValueOnce({ data: [{ id: '123e4567-e89b-42d3-a456-426614174000', room_name: 'flexflow-123e4567-e89b-42d3-a456-426614174000' }], error: null })
    const response = await POST(new Request('http://local/api/token', {
      method: 'POST',
      body: JSON.stringify({ room_name: 'evil-room', participant_identity: 'evil-user' }),
    }))
    const body = await response.json()
    const grant = await new TokenVerifier(env.apiKey, env.apiSecret).verify(body.participant_token)
    expect(grant.video?.room).not.toBe('evil-room')
    expect(grant.video?.room).toBe('flexflow-123e4567-e89b-42d3-a456-426614174000')
    expect(grant.identity).not.toBe('evil-user')
    expect(rpc).toHaveBeenCalledWith('issue_therapy_session', expect.objectContaining({ p_room_name: expect.stringMatching(/^flexflow-/) }))
  })

  it('returns 429 when server-side hourly quota is exhausted', async () => {
    vi.stubEnv('LIVEKIT_API_KEY', env.apiKey)
    vi.stubEnv('LIVEKIT_API_SECRET', env.apiSecret)
    vi.stubEnv('LIVEKIT_URL', env.serverUrl)
    getUser.mockResolvedValueOnce({ data: { user: { id: 'server-user' } } })
    rpc.mockResolvedValueOnce({ data: null, error: { message: 'session_quota_exceeded', code: 'P0001' } })
    expect((await POST(request())).status).toBe(429)
  })

  it('creates unique server-owned rooms with named dispatch and unchanged URL', async () => {
    const first = await createSessionToken(env)
    const second = await createSessionToken(env)
    const verifier = new TokenVerifier(env.apiKey, env.apiSecret)
    const grant = await verifier.verify(first.participant_token)

    expect(first.session_id).not.toBe(second.session_id)
    expect(first.server_url).toBe('wss://live.example')
    expect(grant.video?.room).toBe(`flexflow-${first.session_id}`)
    expect(grant.roomConfig?.agents[0]?.agentName).toBe('flexflow-coach')
  })
})
