'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { ExternalLink } from 'lucide-react'
import { createClient } from '@/utils/supabase/client'
import type { SessionSummaryRow } from '@/utils/types'

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

function formatDuration(seconds: number): string {
  const mins = Math.round(seconds / 60)
  if (mins < 1) return 'Under 1 min'
  if (mins === 1) return '1 minute'
  return `${mins} minutes`
}

export default function SessionDetailClient({ session }: { session: SessionSummaryRow }) {
  const router = useRouter()
  const [showConfirm, setShowConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleDelete() {
    setDeleting(true)
    try {
      const supabase = createClient()
      const { error } = await supabase
        .from('session_summaries')
        .delete()
        .eq('id', session.id)

      if (error) throw error
      router.push('/dashboard')
      router.refresh()
    } catch (err) {
      console.error('Delete failed:', err)
      setDeleting(false)
      setShowConfirm(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Header */}
      <header className="h-20 px-8 flex items-center justify-between border-b border-slate-800">
        <button
          onClick={() => router.push('/')}
          className="text-2xl font-bold text-slate-50 hover:opacity-80 transition"
        >
          Flex<span className="text-emerald-400">Flow</span>
        </button>
        <button
          onClick={() => router.push('/dashboard')}
          className="text-sm text-slate-400 hover:text-slate-50 transition"
        >
          Back to Dashboard
        </button>
      </header>

      {/* Content */}
      <main className="max-w-3xl mx-auto px-8 py-10">
        {/* Date & Duration */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-slate-50 mb-1">
            Session on {formatDate(session.created_at)}
          </h1>
          <p className="text-slate-500 text-sm">
            {formatTime(session.created_at)} &middot; {formatDuration(session.duration_seconds)}
          </p>
        </div>

        {/* AI Summary */}
        <section className="bg-slate-900 rounded-2xl border border-slate-800 p-6 mb-6">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-emerald-400 mb-3">
            AI Summary
          </h2>
          <p className="text-slate-200 leading-relaxed">
            {session.summary_text}
          </p>
        </section>

        {/* Pain Points */}
        {session.pain_points.length > 0 && (
          <section className="bg-slate-900 rounded-2xl border border-slate-800 p-6 mb-6">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-rose-400 mb-3">
              Pain Points Identified
            </h2>
            <div className="flex flex-wrap gap-2">
              {session.pain_points.map((p, i) => (
                <span
                  key={i}
                  className="text-sm px-3 py-1.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20"
                >
                  {p}
                </span>
              ))}
            </div>
          </section>
        )}

        {/* Stretches Performed */}
        {session.stretches_performed.length > 0 && (
          <section className="bg-slate-900 rounded-2xl border border-slate-800 p-6 mb-6">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-emerald-400 mb-3">
              Stretches Performed
            </h2>
            <div className="flex flex-wrap gap-2">
              {session.stretches_performed.map((s, i) => (
                <span
                  key={i}
                  className="text-sm px-3 py-1.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                >
                  {s}
                </span>
              ))}
            </div>
          </section>
        )}

        {/* YouTube Resources */}
        {session.youtube_links.length > 0 && (
          <section className="bg-slate-900 rounded-2xl border border-slate-800 p-6 mb-6">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">
              Recommended Resources
            </h2>
            <div className="flex flex-col gap-2">
              {session.youtube_links.map((link, i) => (
                <a
                  key={i}
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-emerald-400 hover:text-emerald-300 transition flex items-center gap-2"
                >
                  <ExternalLink className="w-3.5 h-3.5 shrink-0" />
                  {link.label}
                </a>
              ))}
            </div>
          </section>
        )}

        {/* Delete Section */}
        <div className="border-t border-slate-800 pt-8 mt-8">
          {!showConfirm ? (
            <button
              onClick={() => setShowConfirm(true)}
              className="text-sm text-slate-500 hover:text-rose-400 transition"
            >
              Delete this session
            </button>
          ) : (
            <div className="bg-rose-500/5 border border-rose-500/20 rounded-2xl p-5">
              <p className="text-rose-400 font-semibold text-sm mb-1">
                Are you sure?
              </p>
              <p className="text-slate-400 text-sm mb-4">
                This action is permanent and cannot be undone. The session summary, pain points, stretches, and all associated data will be permanently deleted.
              </p>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="px-4 py-2 bg-rose-500 text-white rounded-xl text-sm font-semibold hover:bg-rose-400 transition disabled:opacity-50"
                >
                  {deleting ? 'Deleting...' : 'Yes, Delete Permanently'}
                </button>
                <button
                  onClick={() => setShowConfirm(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-400 rounded-xl text-sm font-medium border border-slate-700 hover:text-slate-50 hover:bg-slate-700 transition"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
