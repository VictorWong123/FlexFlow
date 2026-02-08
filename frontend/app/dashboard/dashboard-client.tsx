'use client'

import { useRouter } from 'next/navigation'
import { ExternalLink, LogOut, Play } from 'lucide-react'
import { createClient } from '@/utils/supabase/client'
import type { SessionSummaryRow } from '@/utils/types'

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatDuration(seconds: number): string {
  const mins = Math.round(seconds / 60)
  return mins <= 1 ? '1 min' : `${mins} mins`
}

interface DashboardClientProps {
  sessions: SessionSummaryRow[]
  userEmail: string
}

export default function DashboardClient({ sessions, userEmail }: DashboardClientProps) {
  const router = useRouter()

  async function handleSignOut() {
    const supabase = createClient()
    await supabase.auth.signOut()
    router.push('/login')
  }

  return (
    <div className="min-h-screen bg-slate-950">
      <header className="h-20 px-8 flex items-center justify-between border-b border-slate-800">
        <h1 className="text-2xl font-bold text-slate-50">
          Flex<span className="text-emerald-400">Flow</span>
        </h1>
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.push('/')}
            className="px-4 py-2 bg-emerald-500 text-slate-950 rounded-xl text-sm font-semibold hover:bg-emerald-400 transition flex items-center gap-2"
          >
            <Play className="w-4 h-4" />
            New Session
          </button>
          <span className="text-slate-500 text-sm">{userEmail}</span>
          <button
            onClick={handleSignOut}
            className="px-4 py-2 bg-slate-800 text-slate-400 rounded-xl text-sm font-medium border border-slate-700 hover:text-slate-50 hover:bg-slate-700 transition flex items-center gap-2"
          >
            <LogOut className="w-4 h-4" />
            Sign Out
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-8 py-10">
        <h2 className="text-3xl font-bold text-slate-50 mb-8">Your Recovery Journey</h2>

        {sessions.length === 0 ? (
          <div className="text-center py-20">
            <p className="text-slate-500 text-lg mb-4">No sessions yet.</p>
            <button
              onClick={() => router.push('/')}
              className="px-6 py-3 bg-emerald-500 text-slate-950 rounded-2xl font-semibold hover:bg-emerald-400 transition"
            >
              Start Your First Session
            </button>
          </div>
        ) : (
          <div className="grid gap-6 sm:grid-cols-1 md:grid-cols-2">
            {sessions.map((session) => (
              <div
                key={session.id}
                className="bg-slate-900 rounded-2xl border border-slate-800 p-6 flex flex-col gap-4"
              >
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 text-sm">
                    {formatDate(session.created_at)}
                  </span>
                  <span className="text-slate-400 text-sm">
                    {formatDuration(session.duration_seconds)}
                  </span>
                </div>

                <p className="text-slate-50 text-sm leading-relaxed">
                  {session.summary_text}
                </p>

                <div className="flex flex-wrap gap-2">
                  {session.pain_points.map((p, i) => (
                    <span
                      key={`pain-${i}`}
                      className="text-[11px] px-2.5 py-1 rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/20"
                    >
                      {p}
                    </span>
                  ))}
                  {session.stretches_performed.map((s, i) => (
                    <span
                      key={`stretch-${i}`}
                      className="text-[11px] px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    >
                      {s}
                    </span>
                  ))}
                </div>

                {session.youtube_links.length > 0 && (
                  <div className="border-t border-slate-800 pt-3 mt-1">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                      Recommended Resources
                    </p>
                    <div className="flex flex-col gap-1.5">
                      {session.youtube_links.map((link, i) => (
                        <a
                          key={i}
                          href={link.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-emerald-400 hover:text-emerald-300 transition flex items-center gap-1.5"
                        >
                          <ExternalLink className="w-3 h-3 shrink-0" />
                          {link.label}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
