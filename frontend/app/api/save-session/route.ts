import { NextResponse } from 'next/server'
import { GoogleGenerativeAI } from '@google/generative-ai'
import { createClient } from '@/utils/supabase/server'
import { validateSessionInput, validateSummary, type Summary } from '@/utils/session-validation'

const SYSTEM_PROMPT = `Summarize this movement-coaching session. Return JSON only with keys summary_text (3-4 sentences), pain_points (string array), stretches_performed (string array), and youtube_queries (three safe search terms). Do not diagnose.`
const FALLBACK_SUMMARY: Summary = {
  summary_text: 'Session completed. Automated summary was unavailable.',
  pain_points: [],
  stretches_performed: [],
  youtube_queries: [],
}

export async function POST(request: Request) {
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) {
    return NextResponse.json({ error: 'Authentication is not configured' }, { status: 503 })
  }
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  let parsed: unknown
  try { parsed = await request.json() } catch { return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 }) }
  const input = validateSessionInput(parsed)
  if (!input) return NextResponse.json({ error: 'Invalid session data' }, { status: 400 })
  const claim = await supabase.rpc('claim_therapy_session', { p_session_id: input.sessionId })
  if (claim.error) return NextResponse.json({ error: 'Unable to claim session' }, { status: 500 })
  if (claim.data === 'completed') {
    const { data: existing } = await supabase.from('session_summaries').select('id').eq('session_key', input.sessionId).maybeSingle()
    return NextResponse.json({ status: 'ok', reused: true, summary_id: existing?.id ?? null })
  }
  if (claim.data === 'not_found') return NextResponse.json({ error: 'Unknown session' }, { status: 404 })
  if (claim.data === 'in_progress') return NextResponse.json({ error: 'Summary already in progress' }, { status: 409 })
  if (claim.data !== 'claimed') return NextResponse.json({ error: 'Session expired' }, { status: 410 })
  if (input.transcript.length === 0) {
    const closed = await supabase.rpc('close_therapy_session', { p_session_id: input.sessionId })
    if (closed.error || !closed.data) {
      await supabase.rpc('release_therapy_session', { p_session_id: input.sessionId, p_failed: true })
      return NextResponse.json({ error: 'Failed to close session' }, { status: 500 })
    }
    return NextResponse.json({ status: 'skipped' })
  }

  const conversation = input.transcript.map(message => `${message.speaker === 'agent' ? 'Coach' : 'User'}: ${message.text}`).join('\n')
  let summary: Summary
  let fallback = false
  try {
    if (!process.env.GOOGLE_API_KEY) throw new Error('missing provider configuration')
    const model = new GoogleGenerativeAI(process.env.GOOGLE_API_KEY).getGenerativeModel({
      model: 'gemini-2.5-flash',
      generationConfig: { responseMimeType: 'application/json' },
    })
    const generated = await model.generateContent(`${SYSTEM_PROMPT}\n\n${conversation}`)
    const validated = validateSummary(JSON.parse(generated.response.text()))
    if (!validated) throw new Error('invalid provider response')
    summary = validated
  } catch {
    console.warn('[save-session] summary_provider_failed', { sessionId: input.sessionId })
    summary = FALLBACK_SUMMARY
    fallback = true
  }

  const youtubeLinks = summary.youtube_queries.map(query => ({
    label: query,
    url: `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`,
  }))
  const { error } = await supabase.rpc('complete_therapy_session', {
    p_session_id: input.sessionId,
    p_summary_text: summary.summary_text,
    p_pain_points: summary.pain_points,
    p_stretches_performed: summary.stretches_performed,
    p_youtube_links: youtubeLinks,
    p_duration_seconds: Math.round(input.duration),
  })

  if (error) {
    console.error('[save-session] database_write_failed', { sessionId: input.sessionId, code: error.code })
    await supabase.rpc('release_therapy_session', { p_session_id: input.sessionId, p_failed: true })
    return NextResponse.json({ error: 'Failed to save session' }, { status: 500 })
  }
  return NextResponse.json({ status: 'ok', ...(fallback ? { fallback: true } : {}) })
}
