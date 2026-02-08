'use client'

import { useRouter } from 'next/navigation'
import { LogOut, Play } from 'lucide-react'
import { createClient } from '@/utils/supabase/client'
import type { SessionSummaryRow } from '@/utils/types'

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatDuration(seconds: number): string {
  const mins = Math.round(seconds / 60)
  return mins <= 1 ? '1 min' : `${mins} mins`
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return text.slice(0, max).trimEnd() + '...'
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
        <button onClick={() => router.push('/')} className="text-2xl font-bold text-slate-50 hover:opacity-80 transition">
          Flex<span className="text-emerald-400">Flow</span>
        </button>
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.push('/?start=true')}
            className="px-4 py-2 bg-emerald-500 text-white rounded-xl text-sm font-semibold hover:bg-emerald-400 transition flex items-center gap-2"
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
              onClick={() => router.push('/?start=true')}
              className="px-6 py-3 bg-emerald-500 text-white rounded-2xl font-semibold hover:bg-emerald-400 transition"
            >
              Start Your First Session
            </button>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => router.push(`/dashboard/${session.id}`)}
                className="bg-slate-900 rounded-2xl border border-slate-800 p-5 flex flex-col gap-3 text-left hover:border-slate-700 hover:bg-slate-900/80 transition group"
              >
                <div className="flex items-center justify-between w-full">
                  <span className="text-slate-400 text-xs">
                    {formatDate(session.created_at)}
                  </span>
                  <span className="text-slate-500 text-xs">
                    {formatDuration(session.duration_seconds)}
                  </span>
                </div>

                <p className="text-slate-200 text-sm leading-relaxed">
                  {truncate(session.summary_text, 100)}
                </p>

                <div className="flex flex-wrap gap-1.5">
                  {session.pain_points.slice(0, 2).map((p, i) => (
                    <span
                      key={`pain-${i}`}
                      className="text-[10px] px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/20"
                    >
                      {p}
                    </span>
                  ))}
                  {session.stretches_performed.slice(0, 2).map((s, i) => (
                    <span
                      key={`stretch-${i}`}
                      className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    >
                      {s}
                    </span>
                  ))}
                  {(session.pain_points.length + session.stretches_performed.length) > 4 && (
                    <span className="text-[10px] px-2 py-0.5 text-slate-500">
                      +{session.pain_points.length + session.stretches_performed.length - 4} more
                    </span>
                  )}
                </div>

                <span className="text-xs text-emerald-400 group-hover:text-emerald-300 transition mt-auto">
                  View details
                </span>
              </button>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
