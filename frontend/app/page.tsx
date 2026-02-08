'use client'

import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { motion, useInView } from 'framer-motion'
import { createClient } from '@/utils/supabase/client'
import VideoSession from '@/components/VideoSession'

/* ── Fade-in wrapper ─────────────────────────────────────────── */
function FadeIn({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-60px' })
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 24 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.55, ease: 'easeOut' }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/* ── Page (wrapped in Suspense for useSearchParams) ──────────── */
export default function Home() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-950" />}>
      <HomeInner />
    </Suspense>
  )
}

function HomeInner() {
  const [sessionActive, setSessionActive] = useState(false)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const router = useRouter()
  const searchParams = useSearchParams()
  const autoStartHandled = useRef(false)

  const handleDisconnect = useCallback(() => {
    setSessionActive(false)
    // Clear the ?start param so refreshing doesn't auto-start again
    router.replace('/', { scroll: false })
  }, [router])

  /* Auth check — unchanged logic */
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

  /* Auto-start session if ?start=true and authenticated */
  useEffect(() => {
    if (authChecked && isAuthenticated && searchParams.get('start') === 'true' && !autoStartHandled.current) {
      autoStartHandled.current = true
      setSessionActive(true)
    }
  }, [authChecked, isAuthenticated, searchParams])

  /* Scroll listener for nav background */
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 32)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  /* ── Active session → full-screen VideoSession ─────────────── */
  if (sessionActive) {
    return <VideoSession onDisconnect={handleDisconnect} />
  }

  /* ── Landing page ──────────────────────────────────────────── */
  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 font-sans">

      {/* ── Top Navigation ──────────────────────────────────── */}
      <nav
        className={`fixed top-0 inset-x-0 z-50 h-20 px-8 flex items-center justify-between transition-colors duration-300 ${
          scrolled ? 'bg-slate-950/90 backdrop-blur-md' : 'bg-transparent'
        }`}
      >
        <span className="text-xl font-bold">
          Flex<span className="text-emerald-400">Flow</span>
        </span>

        <div className="flex items-center gap-5">
          {authChecked && isAuthenticated ? (
            <>
              <button
                onClick={() => router.push('/dashboard')}
                className="text-sm text-slate-400 hover:text-slate-50 transition"
              >
                Dashboard
              </button>
              <button
                onClick={() => setSessionActive(true)}
                className="text-sm font-semibold bg-emerald-500 text-white px-6 py-2.5 rounded-full hover:bg-emerald-400 transition"
              >
                Start Session
              </button>
            </>
          ) : authChecked ? (
            <>
              <button
                onClick={() => router.push('/login')}
                className="text-sm text-slate-400 hover:text-slate-50 transition"
              >
                Sign In
              </button>
              <button
                onClick={() => router.push('/login')}
                className="text-sm font-semibold bg-emerald-500 text-white px-6 py-2.5 rounded-full hover:bg-emerald-400 transition"
              >
                Get Started
              </button>
            </>
          ) : null}
        </div>
      </nav>

      {/* ── Hero Section ────────────────────────────────────── */}
      <section className="pt-44 pb-32 px-8 flex flex-col items-center text-center">
        <FadeIn>
          <h1 className="text-6xl font-bold tracking-tight leading-[1.08] max-w-4xl mx-auto">
            Professional Physical Therapy.{' '}
            <span className="text-emerald-400">Right in Your Browser.</span>
          </h1>
        </FadeIn>

        <FadeIn className="mt-7">
          <p className="text-lg text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Experience real-time form correction and expert guidance.
            No appointments. No waiting rooms. Just recovery.
          </p>
        </FadeIn>

        <FadeIn className="mt-10">
          {!authChecked ? (
            <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto" />
          ) : isAuthenticated ? (
            <button
              onClick={() => setSessionActive(true)}
              className="text-base font-semibold bg-emerald-500 text-white px-10 py-4 rounded-full hover:bg-emerald-400 transition"
            >
              Start Your Session
            </button>
          ) : (
            <button
              onClick={() => router.push('/login')}
              className="text-base font-semibold bg-emerald-500 text-white px-10 py-4 rounded-full hover:bg-emerald-400 transition"
            >
              Start Your First Session Free
            </button>
          )}
        </FadeIn>
      </section>

      {/* ── Feature Grid ────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-8 pb-32">
        <div className="grid md:grid-cols-3 gap-16">
          {[
            {
              label: 'It Sees',
              text: 'Analyzes joint angles and posture in real-time using your webcam. Every rep, every stretch — tracked with clinical precision.',
            },
            {
              label: 'It Thinks',
              text: 'Identifies form errors and provides personalized correction cues instantly. Adaptive feedback that evolves with your movement.',
            },
            {
              label: 'It Guides',
              text: 'Delivers professional coaching and demonstrations curated for your recovery. A therapist that\u2019s always one step ahead.',
            },
          ].map((col, i) => (
            <FadeIn key={i}>
              <h3 className="text-emerald-400 text-sm font-semibold uppercase tracking-widest mb-4">
                {col.label}
              </h3>
              <p className="text-slate-200 leading-relaxed">
                {col.text}
              </p>
            </FadeIn>
          ))}
        </div>
      </section>

      {/* ── Privacy Commitment ──────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-8 pb-32 text-center">
        <FadeIn>
          <h2 className="text-3xl font-bold tracking-tight mb-5">
            Your Recovery is Private.
          </h2>
        </FadeIn>
        <FadeIn>
          <p className="text-slate-300 text-lg leading-relaxed">
            We analyze movement in real-time memory. We never record video,
            save audio, or store raw transcripts. Your health data is yours alone.
          </p>
        </FadeIn>
      </section>

      {/* ── Footer ──────────────────────────────────────────── */}
      <footer className="border-t border-slate-800 px-8 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-slate-500">
        <span>&copy; {new Date().getFullYear()} FlexFlow. All rights reserved.</span>
        <div className="flex gap-6">
          <span className="hover:text-slate-300 transition cursor-pointer">Terms of Service</span>
          <span className="hover:text-slate-300 transition cursor-pointer">Privacy Policy</span>
        </div>
      </footer>
    </div>
  )
}
