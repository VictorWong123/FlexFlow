import { NextResponse } from 'next/server'
import { randomUUID } from 'node:crypto'
import { createClient } from '@/utils/supabase/server'
import { createSessionToken } from '@/utils/session-token'

const NO_STORE = { 'Cache-Control': 'no-store' }

export async function POST(_request: Request) {
  const origin = _request.headers.get('origin')
  if (origin) {
    try {
      if (new URL(origin).origin !== new URL(_request.url).origin) throw new Error('cross-origin')
    } catch {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403, headers: NO_STORE })
    }
  }
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) {
    return NextResponse.json({ error: 'Authentication is not configured' }, { status: 503, headers: NO_STORE })
  }
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401, headers: NO_STORE })

  const apiKey = process.env.LIVEKIT_API_KEY
  const apiSecret = process.env.LIVEKIT_API_SECRET
  const serverUrl = process.env.LIVEKIT_URL
  if (!apiKey || !apiSecret || !serverUrl) {
    return NextResponse.json({ error: 'LiveKit is not configured' }, { status: 503, headers: NO_STORE })
  }

  const candidateId = randomUUID()
  const { data, error } = await supabase.rpc('issue_therapy_session', {
    p_session_id: candidateId,
    p_room_name: `flexflow-${candidateId}`,
    p_expires_at: new Date(Date.now() + 2 * 60 * 60 * 1_000).toISOString(),
  })
  if (error) {
    const quotaExceeded = error.message.includes('session_quota_exceeded')
    const inProgress = error.message.includes('session_in_progress')
    console.warn('[token] session_issue_failed', { code: error.code, quotaExceeded, inProgress })
    return NextResponse.json(
      { error: quotaExceeded ? 'Session limit reached. Try again later.' : inProgress ? 'Session summary is still in progress.' : 'Unable to create session' },
      { status: quotaExceeded ? 429 : inProgress ? 409 : 500, headers: NO_STORE },
    )
  }
  const issued = Array.isArray(data) ? data[0] : data
  if (!issued || typeof issued.id !== 'string' || typeof issued.room_name !== 'string') {
    return NextResponse.json({ error: 'Unable to create session' }, { status: 500, headers: NO_STORE })
  }

  return NextResponse.json(
    await createSessionToken({ apiKey, apiSecret, serverUrl }, issued.id, issued.room_name),
    { headers: NO_STORE },
  )
}
