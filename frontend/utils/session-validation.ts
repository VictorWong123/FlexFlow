import type { TranscriptMessage } from '@/utils/types'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export type Summary = { summary_text: string; pain_points: string[]; stretches_performed: string[]; youtube_queries: string[] }

export function validateSessionInput(value: unknown): { sessionId: string; transcript: TranscriptMessage[]; duration: number } | null {
  if (!value || typeof value !== 'object') return null
  const body = value as Record<string, unknown>
  if (typeof body.session_id !== 'string' || !UUID.test(body.session_id)) return null
  if (typeof body.duration !== 'number' || !Number.isFinite(body.duration) || body.duration < 0 || body.duration > 28_800) return null
  if (!Array.isArray(body.transcript) || body.transcript.length > 200) return null
  const transcript: TranscriptMessage[] = []
  let length = 0
  for (const item of body.transcript) {
    if (!item || typeof item !== 'object') return null
    const message = item as Record<string, unknown>
    if ((message.speaker !== 'user' && message.speaker !== 'agent') || typeof message.text !== 'string') return null
    const text = message.text.trim()
    if (text.length > 1_000) return null
    if (!text) continue
    length += text.length
    if (length > 50_000) return null
    transcript.push({ speaker: message.speaker, text })
  }
  return { sessionId: body.session_id, transcript, duration: body.duration }
}

function stringList(value: unknown, limit: number): string[] | null {
  if (!Array.isArray(value) || value.length > limit) return null
  const result = value.filter((item): item is string => typeof item === 'string').map(item => item.trim()).filter(Boolean)
  return result.length === value.length && result.every(item => item.length <= 200) ? result : null
}

export function validateSummary(value: unknown): Summary | null {
  if (!value || typeof value !== 'object') return null
  const data = value as Record<string, unknown>
  const painPoints = stringList(data.pain_points, 10)
  const stretches = stringList(data.stretches_performed, 20)
  const queries = stringList(data.youtube_queries, 3)
  if (typeof data.summary_text !== 'string' || !data.summary_text.trim() || data.summary_text.length > 2_000 || !painPoints || !stretches || !queries) return null
  return { summary_text: data.summary_text.trim(), pain_points: painPoints, stretches_performed: stretches, youtube_queries: queries }
}
