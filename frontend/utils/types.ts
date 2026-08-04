export interface TranscriptMessage {
  speaker: 'user' | 'agent'
  text: string
}

export interface SessionSummaryRow {
  id: string
  user_id: string
  session_key: string
  schema_version: number
  summary_text: string
  pain_points: string[]
  stretches_performed: string[]
  youtube_links: { label: string; url: string }[]
  duration_seconds: number
  created_at: string
}
