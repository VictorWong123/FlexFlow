import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/supabase/server', () => ({ createClient: vi.fn() }))

import { validateSessionInput, validateSummary } from '@/utils/session-validation'
import { createClient } from '@/utils/supabase/server'
import { POST } from './route'

const session_id = '123e4567-e89b-42d3-a456-426614174000'

describe('save-session validation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://example.supabase.co')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'anon')
  })

  it('rejects unauthenticated callers', async () => {
    vi.mocked(createClient).mockResolvedValueOnce({ auth: { getUser: vi.fn(async () => ({ data: { user: null } })) } } as never)
    expect((await POST(new Request('http://local', { method: 'POST', body: '{}' }))).status).toBe(401)
  })

  it('skips empty transcripts without writing', async () => {
    const rpc = vi.fn().mockResolvedValueOnce({ data: 'claimed', error: null }).mockResolvedValueOnce({ data: true, error: null })
    vi.mocked(createClient).mockResolvedValueOnce({ auth: { getUser: vi.fn(async () => ({ data: { user: { id: 'user' } } })) }, rpc } as never)
    const response = await POST(new Request('http://local', { method: 'POST', body: JSON.stringify({ session_id, duration: 0, transcript: [] }) }))
    expect(await response.json()).toEqual({ status: 'skipped' })
    expect(rpc.mock.calls.map(call => call[0])).toEqual(['claim_therapy_session', 'close_therapy_session'])
  })

  it('rejects sessions not owned by caller', async () => {
    const rpc = vi.fn().mockResolvedValueOnce({ data: 'not_found', error: null })
    vi.mocked(createClient).mockResolvedValueOnce({ auth: { getUser: vi.fn(async () => ({ data: { user: { id: 'user' } } })) }, rpc } as never)
    const response = await POST(new Request('http://local', { method: 'POST', body: JSON.stringify({ session_id, duration: 1, transcript: [] }) }))
    expect(response.status).toBe(404)
  })

  it('claims before provider work and persists bounded fallback on provider failure', async () => {
    vi.stubEnv('GOOGLE_API_KEY', '')
    const rpc = vi.fn().mockResolvedValueOnce({ data: 'claimed', error: null }).mockResolvedValueOnce({ data: true, error: null })
    vi.mocked(createClient).mockResolvedValueOnce({ auth: { getUser: vi.fn(async () => ({ data: { user: { id: 'user' } } })) }, rpc } as never)
    const response = await POST(new Request('http://local', { method: 'POST', body: JSON.stringify({ session_id, duration: 1, transcript: [{ speaker: 'user', text: 'hello' }] }) }))
    expect(await response.json()).toEqual({ status: 'ok', fallback: true })
    expect(rpc.mock.calls.map(call => call[0])).toEqual(['claim_therapy_session', 'complete_therapy_session'])
    expect(rpc.mock.calls[1][1]).toMatchObject({
      p_summary_text: 'Session completed. Automated summary was unavailable.',
      p_pain_points: [],
      p_stretches_performed: [],
      p_youtube_links: [],
    })
    expect(rpc.mock.calls[1][1]).not.toHaveProperty('transcript')
  })

  it('reuses completed sessions without provider work', async () => {
    const rpc = vi.fn().mockResolvedValueOnce({ data: 'completed', error: null })
    const maybeSingle = vi.fn(async () => ({ data: { id: 'summary-id' }, error: null }))
    const from = vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle })) })) }))
    vi.mocked(createClient).mockResolvedValueOnce({ auth: { getUser: vi.fn(async () => ({ data: { user: { id: 'user' } } })) }, rpc, from } as never)
    const response = await POST(new Request('http://local', { method: 'POST', body: JSON.stringify({ session_id, duration: 1, transcript: [{ speaker: 'user', text: 'hello' }] }) }))
    expect(await response.json()).toEqual({ status: 'ok', reused: true, summary_id: 'summary-id' })
    expect(rpc).toHaveBeenCalledTimes(1)
  })

  it('accepts bounded valid input', () => {
    expect(validateSessionInput({ session_id, duration: 30, transcript: [{ speaker: 'user', text: 'hello' }] })).not.toBeNull()
  })

  it('rejects invalid UUIDs, duration, transcript size, and message length', () => {
    expect(validateSessionInput({ session_id: 'room', duration: 30, transcript: [] })).toBeNull()
    expect(validateSessionInput({ session_id, duration: 99_999, transcript: [] })).toBeNull()
    expect(validateSessionInput({ session_id, duration: 1, transcript: Array(201).fill({ speaker: 'user', text: 'x' }) })).toBeNull()
    expect(validateSessionInput({ session_id, duration: 1, transcript: [{ speaker: 'user', text: 'x'.repeat(1_001) }] })).toBeNull()
  })

  it('rejects malformed provider output and oversized youtube arrays', () => {
    expect(validateSummary({ summary_text: 'ok', pain_points: [], stretches_performed: [], youtube_queries: ['one'] })).not.toBeNull()
    expect(validateSummary({ summary_text: 'ok', pain_points: 'none', stretches_performed: [], youtube_queries: [] })).toBeNull()
    expect(validateSummary({ summary_text: 'ok', pain_points: [], stretches_performed: [], youtube_queries: ['1', '2', '3', '4'] })).toBeNull()
  })
})
