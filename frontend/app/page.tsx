'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { LayoutDashboard } from 'lucide-react'
import { createClient } from '@/utils/supabase/client'
import VideoSession from '@/components/VideoSession'

export default function Home() {
  const [sessionActive, setSessionActive] = useState(false)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const router = useRouter()

  const handleDisconnect = useCallback(() => setSessionActive(false), [])

  useEffect(() => {
    let cancelled = false
    async function checkAuth() {
      try {
        const supabase = createClient()
        const { data: { user } } = await supabase.auth.getUser()
        if (!cancelled) setIsAuthenticated(!!user)
      } catch {
        // not signed in
      } finally {
        if (!cancelled) setAuthChecked(true)
      }
    }
    checkAuth()
    return () => { cancelled = true }
  }, [])

  if (sessionActive) {
    return <VideoSession onDisconnect={handleDisconnect} />
  }

  return (
    <main className="flex items-center justify-center h-screen bg-slate-950">
      <div className="text-center">
        <h1 className="text-5xl font-bold text-slate-50 mb-3">
          Flex<span className="text-emerald-400">Flow</span>
        </h1>
        <p className="text-slate-400 mb-10 text-lg">
          AI-Powered Physical Therapy
        </p>

        {!authChecked ? (
          <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto" />
        ) : isAuthenticated ? (
          <div className="flex flex-col items-center gap-4">
            <button
              onClick={() => setSessionActive(true)}
              className="px-8 py-4 bg-emerald-500 text-slate-950 rounded-2xl font-semibold text-lg hover:bg-emerald-400 transition"
            >
              Start Session
            </button>
            <button
              onClick={() => router.push('/dashboard')}
              className="px-6 py-3 bg-slate-800 text-slate-400 rounded-xl border border-slate-700 hover:text-slate-50 hover:bg-slate-700 transition text-sm font-medium flex items-center gap-2"
            >
              <LayoutDashboard className="w-4 h-4" />
              View Dashboard
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4">
            <button
              onClick={() => router.push('/login')}
              className="px-8 py-4 bg-emerald-500 text-slate-950 rounded-2xl font-semibold text-lg hover:bg-emerald-400 transition"
            >
              Sign In to Get Started
            </button>
            <p className="text-slate-500 text-sm">
              Create a free account to begin your session
            </p>
          </div>
        )}
      </div>
    </main>
  )
}
