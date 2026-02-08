import { NextResponse } from 'next/server'
import { createClient } from '@/utils/supabase/server'
import { GoogleGenerativeAI } from '@google/generative-ai'
import type { TranscriptMessage } from '@/utils/types'

const SYSTEM_PROMPT = `You are an expert Physical Therapist. Summarize this session. Return JSON ONLY with keys: "summary_text" (3-4 sentences), "pain_points" (array of strings), "stretches_performed" (array of strings), and "youtube_queries" (3 specific search terms for their issues).`

export async function POST(request: Request) {
  const supabase = await createClient()

  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  let body: { transcript: TranscriptMessage[]; duration: number }
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 })
  }

  const { transcript, duration } = body
  if (!transcript || !Array.isArray(transcript) || typeof duration !== 'number') {
    return NextResponse.json({ error: 'Missing transcript or duration' }, { status: 400 })
  }

  const conversationText = transcript
    .map((m) => `${m.speaker === 'agent' ? 'Therapist' : 'Patient'}: ${m.text}`)
    .join('\n')

  let summaryData: {
    summary_text: string
    pain_points: string[]
    stretches_performed: string[]
    youtube_queries: string[]
  }

  try {
    const apiKey = process.env.GOOGLE_API_KEY
    if (!apiKey) throw new Error('GOOGLE_API_KEY not set')

    const genAI = new GoogleGenerativeAI(apiKey)
    const model = genAI.getGenerativeModel({
      model: 'gemini-2.0-flash',
      generationConfig: {
        responseMimeType: 'application/json',
      },
    })

    const result = await model.generateContent(
      `${SYSTEM_PROMPT}\n\n---\n\n${conversationText}`
    )

    const text = result.response.text()
    summaryData = JSON.parse(text)
  } catch (err) {
    console.error('Gemini analysis failed:', err)
    summaryData = {
      summary_text: 'Session completed. AI summary could not be generated.',
      pain_points: [],
      stretches_performed: [],
      youtube_queries: [],
    }
  }

  const youtubeLinks = (summaryData.youtube_queries || []).map((q: string) => ({
    label: q,
    url: `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}`,
  }))

  const { error: dbError } = await supabase.from('session_summaries').insert({
    user_id: user.id,
    summary_text: summaryData.summary_text,
    pain_points: summaryData.pain_points || [],
    stretches_performed: summaryData.stretches_performed || [],
    youtube_links: youtubeLinks,
    duration_seconds: Math.round(duration),
  })

  if (dbError) {
    console.error('DB insert error:', dbError)
    return NextResponse.json({ error: 'Failed to save session' }, { status: 500 })
  }

  return NextResponse.json({ status: 'ok' })
}
