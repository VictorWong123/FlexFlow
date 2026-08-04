'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Room, RoomEvent, Track } from 'livekit-client'
import { Camera, LayoutDashboard } from 'lucide-react'
import ExerciseCard, { ExerciseData } from './ExerciseCard'
import PushToTalk from './PushToTalk'
import type { TranscriptMessage } from '@/utils/types'
import { isSafetyHaltTransition, parseTrackingState, shouldAcceptTrackingUpdate, type TrackingState } from '@/utils/tracking'

interface VideoSessionProps {
  onDisconnect: () => void
}

interface Landmark {
  x: number
  y: number
  z: number
  v: number
}

interface TranscriptLine {
  id: string
  text: string
  speaker: 'user' | 'agent'
  isFinal: boolean
}

function isUpperBody(landmarks: Landmark[]): boolean {
  return landmarks.slice(25, 33).every(lm => lm.v < 0.5)
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0')
  const s = (seconds % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

export default function VideoSession({ onDisconnect }: VideoSessionProps) {
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isMuted, setIsMuted] = useState(false)
  const [isVideoEnabled, setIsVideoEnabled] = useState(true)
  const [exerciseData, setExerciseData] = useState<ExerciseData | null>(null)
  const [bodyMode, setBodyMode] = useState<'upper' | 'full'>('upper')
  const [transcript, setTranscript] = useState<TranscriptLine[]>([])
  const [elapsed, setElapsed] = useState(0)
  const [isSaving, setIsSaving] = useState(false)
  const [tracking, setTracking] = useState<TrackingState | null>(null)
  const [safetyAlert, setSafetyAlert] = useState(false)
  const [resumeError, setResumeError] = useState<string | null>(null)

  const router = useRouter()
  const localVideoRef = useRef<HTMLVideoElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const roomRef = useRef<Room | null>(null)
  const transcriptEndRef = useRef<HTMLDivElement>(null)
  const endingRef = useRef(false)
  const sessionIdRef = useRef<string | null>(null)
  const trackingRef = useRef<TrackingState | null>(null)
  const resumeRequestedRef = useRef(false)

  useEffect(() => {
    if (!isConnected) return
    const interval = setInterval(() => setElapsed(prev => prev + 1), 1000)
    return () => clearInterval(interval)
  }, [isConnected])

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcript])

  useEffect(() => {
    const abortController = new AbortController()
    let cancelled = false

    const connect = async () => {
      try {
        const tokenResponse = await fetch('/api/token', {
          method: 'POST',
          signal: abortController.signal,
        })

        if (cancelled) return

        if (!tokenResponse.ok) {
          const errorData = await tokenResponse.json().catch(() => ({}))
          throw new Error(errorData.detail || `Failed to get token: ${tokenResponse.statusText}`)
        }

        const { server_url, participant_token, session_id } = await tokenResponse.json()
        sessionIdRef.current = session_id
        if (cancelled) return

        const room = new Room()
        roomRef.current = room

        room.on(RoomEvent.Connected, () => {
          if (!cancelled) setIsConnected(true)
        })

        room.on(RoomEvent.Disconnected, () => {
          if (!cancelled && !endingRef.current) {
            setIsConnected(false)
            onDisconnect()
          }
        })

        room.on(RoomEvent.TrackSubscribed, (track) => {
          if (cancelled) return
          if (track.kind === Track.Kind.Audio && audioRef.current) {
            track.attach(audioRef.current)
          }
        })

        room.on(RoomEvent.TrackUnsubscribed, (track) => {
          track.detach()
        })

        room.on(RoomEvent.LocalTrackPublished, (publication) => {
          if (cancelled) return
          if (publication.track?.kind === Track.Kind.Video && localVideoRef.current) {
            publication.track.attach(localVideoRef.current)
          }
        })

        room.on(RoomEvent.DataReceived, (
          payload: Uint8Array,
          _participant: unknown,
          _kind: unknown,
          topic?: string
        ) => {
          try {
            const data = JSON.parse(new TextDecoder().decode(payload))
            if (topic === 'landmarks' && data.l) {
              const landmarks = data.l as Landmark[]
              setBodyMode(isUpperBody(landmarks) ? 'upper' : 'full')
            }
            if (topic === 'exercise' && data.title) {
              setExerciseData(data as ExerciseData)
            }
            if (topic === 'tracking') {
              const parsed = parseTrackingState(data)
              if (parsed) {
                const previous = trackingRef.current
                if (!shouldAcceptTrackingUpdate(previous, parsed, resumeRequestedRef.current)) return
                if (isSafetyHaltTransition(previous, parsed)) {
                  setSafetyAlert(true)
                  setResumeError(null)
                }
                if (previous?.halted && !parsed.halted) {
                  resumeRequestedRef.current = false
                  setSafetyAlert(false)
                  setResumeError(null)
                }
                trackingRef.current = parsed
                setTracking(parsed)
              }
            }
          } catch {
          }
        })

        room.on(RoomEvent.TranscriptionReceived, (
          segments: Array<{ id?: string; text?: string; final?: boolean }>,
          participant?: { identity?: string }
        ) => {
          if (cancelled) return
          const isAgent = participant && participant.identity !== room.localParticipant?.identity
          for (const seg of segments) {
            setTranscript(prev => {
              const segId = seg.id || `${Date.now()}-${Math.random()}`
              const idx = prev.findIndex(t => t.id === segId)
              const line: TranscriptLine = {
                id: segId,
                text: seg.text || '',
                speaker: isAgent ? 'agent' : 'user',
                isFinal: !!seg.final,
              }
              if (idx >= 0) {
                const updated = [...prev]
                updated[idx] = line
                return updated
              }
              return [...prev, line]
            })
          }
        })

        await room.connect(server_url, participant_token)
        if (cancelled) {
          room.disconnect()
          return
        }

        await Promise.all([
          room.localParticipant.setMicrophoneEnabled(true),
          room.localParticipant.setCameraEnabled(true),
        ])
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        if (cancelled) return
        console.error('Connection error:', err)
        setError(err instanceof Error ? err.message : 'Failed to connect')
      }
    }

    connect()

    return () => {
      cancelled = true
      abortController.abort()
      if (roomRef.current) {
        roomRef.current.disconnect()
        roomRef.current = null
      }
    }
  }, [onDisconnect])

  const toggleMute = useCallback(async () => {
    if (roomRef.current) {
      await roomRef.current.localParticipant.setMicrophoneEnabled(isMuted)
      setIsMuted(!isMuted)
    }
  }, [isMuted])

  const toggleVideo = useCallback(async () => {
    if (roomRef.current) {
      await roomRef.current.localParticipant.setCameraEnabled(!isVideoEnabled)
      setIsVideoEnabled(!isVideoEnabled)
    }
  }, [isVideoEnabled])

  const endSession = useCallback(async () => {
    endingRef.current = true
    setIsSaving(true)

    // Capture transcript before disconnecting
    const finalTranscript: TranscriptMessage[] = transcript
      .filter((t) => t.isFinal && t.text.trim())
      .map((t) => ({ speaker: t.speaker, text: t.text }))

    // Disconnect the room (endingRef prevents unmount)
    if (roomRef.current) {
      roomRef.current.disconnect()
      roomRef.current = null
    }

    try {
      const res = await fetch('/api/save-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionIdRef.current, transcript: finalTranscript, duration: elapsed }),
      })

      if (res.ok) {
        router.push('/dashboard')
        return
      }

      const errData = await res.json().catch(() => ({}))
      console.error('Save session failed:', res.status, errData)
    } catch (err) {
      console.error('Failed to save session:', err)
    }

    endingRef.current = false
    setIsSaving(false)
    onDisconnect()
  }, [transcript, elapsed, onDisconnect, router])

  const resumeAfterSafety = useCallback(async () => {
    if (!roomRef.current || !window.confirm('Resume only if symptoms have stopped and you feel safe to continue.')) return
    resumeRequestedRef.current = true
    setResumeError(null)
    try {
      await roomRef.current.localParticipant.publishData(
        new TextEncoder().encode(JSON.stringify({ type: 'RESUME_AFTER_SAFETY' })),
        { reliable: true, topic: 'control' },
      )
    } catch {
      resumeRequestedRef.current = false
      setResumeError('Could not send the resume request. Please try again.')
    }
  }, [])

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen bg-slate-950">
        <div className="text-center">
          <p className="text-rose-500 mb-4 text-lg">{error}</p>
          <button
            onClick={onDisconnect}
            className="px-6 py-3 bg-slate-800 text-slate-50 rounded-xl border border-slate-700 hover:bg-slate-700 transition"
          >
            Go Back
          </button>
        </div>
      </div>
    )
  }

  if (!isConnected) {
    return (
      <div className="flex items-center justify-center h-screen bg-slate-950">
        <div className="text-center">
          <div className="w-12 h-12 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-slate-400 text-lg">Connecting to session...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen lg:h-screen bg-slate-950 flex flex-col" spellCheck={false} data-grammarly="false">
      <audio ref={audioRef} autoPlay />

      <header className="min-h-20 px-4 sm:px-8 py-3 flex flex-wrap items-center justify-between gap-3 shrink-0 border-b border-slate-800">
        <h1 className="text-2xl font-bold text-slate-50">
          Flex<span className="text-emerald-400">Flow</span>
        </h1>
        <span className="text-slate-500 font-mono text-sm tabular-nums">
          {formatTime(elapsed)}
        </span>
        <div className="flex items-center gap-3">
          <button
            aria-label="Open dashboard"
            onClick={() => {
              if (roomRef.current) roomRef.current.disconnect()
              router.push('/dashboard')
            }}
            className="px-3 sm:px-4 py-2 bg-slate-800 text-slate-400 rounded-xl border border-slate-700 hover:text-slate-50 hover:bg-slate-700 transition text-sm font-medium flex items-center gap-2"
          >
            <LayoutDashboard className="w-4 h-4" />
            <span className="hidden sm:inline">Dashboard</span>
          </button>
          <button
            onClick={endSession}
            disabled={isSaving}
            className="px-3 sm:px-5 py-2 bg-rose-500/10 text-rose-500 rounded-xl border border-rose-500/30 hover:bg-rose-500/20 transition text-xs sm:text-sm font-medium disabled:opacity-50"
          >
            {isSaving ? 'Saving...' : 'End Session'}
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 sm:gap-6 lg:h-[calc(100vh-80px)] p-4 sm:p-6 min-h-0">
        <div className="lg:col-span-8 relative h-[45vh] lg:h-auto rounded-3xl overflow-hidden bg-slate-900 border border-slate-800 shadow-2xl min-h-0 shrink-0">
          <video
            ref={localVideoRef}
            autoPlay
            playsInline
            muted
            className="absolute inset-0 w-full h-full object-cover -scale-x-100"
          />

          <div className="absolute top-6 left-6 px-4 py-2 bg-slate-950/50 backdrop-blur-md rounded-full border border-slate-800 text-sm font-medium text-slate-50 flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${bodyMode === 'upper' ? 'bg-sky-500' : 'bg-emerald-500'}`} />
            {bodyMode === 'upper' ? 'Upper Body Mode' : 'Full Body Mode'}
          </div>

          <button
            onClick={toggleVideo}
            aria-label={isVideoEnabled ? 'Turn camera off' : 'Turn camera on'}
            aria-pressed={isVideoEnabled}
            className="absolute bottom-6 right-6 p-3 bg-slate-950/50 backdrop-blur-md rounded-full border border-slate-800 text-slate-400 hover:text-slate-50 transition"
          >
            <Camera className="w-5 h-5" />
          </button>

          {!isVideoEnabled && (
            <div className="absolute inset-0 flex items-center justify-center bg-slate-900">
              <p className="text-slate-500">Camera off</p>
            </div>
          )}
        </div>

        <div className="lg:col-span-4 flex flex-col gap-4 min-h-0 lg:overflow-y-auto lg:h-full">
          {safetyAlert && (
            <div role="alert" aria-live="assertive" className="sr-only">
              Safety stop activated. Stop exercising and review the warning before resuming.
            </div>
          )}
          {tracking && (
            <div className={`rounded-2xl border p-4 shrink-0 ${tracking.halted ? 'bg-rose-950/40 border-rose-500/40' : 'bg-slate-900 border-slate-800'}`}>
              <div className="flex items-center justify-between gap-3">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Form tracking</h4>
                <span className="text-xs text-emerald-400">{tracking.status.replace('_', ' ')}</span>
              </div>
              {tracking.tracking_supported ? (
                <div className="mt-3 flex gap-5 text-sm text-slate-300">
                  <span>Reps <strong className="text-slate-50">{tracking.reps}</strong></span>
                  <span>Hold <strong className="text-slate-50">{tracking.hold_seconds}s</strong></span>
                  {tracking.required_view && <span>View <strong className="text-slate-50">{tracking.required_view}</strong></span>}
                </div>
              ) : <p className="mt-2 text-xs text-slate-500">Visual guidance only for this exercise.</p>}
              {tracking.calibration_required && !tracking.calibrated && !tracking.halted && (
                <p className="mt-2 text-xs text-sky-300">Hold the start position steady to calibrate.</p>
              )}
              {tracking.issues.length > 0 && <p className="mt-2 text-sm text-amber-300">{tracking.issues[0]}</p>}
              {tracking.cue && !tracking.halted && <p className="mt-2 text-sm text-sky-300">{tracking.cue}</p>}
              {tracking.halted && (
                <>
                  <button onClick={resumeAfterSafety} className="mt-3 w-full rounded-xl bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-400">
                    Confirm symptoms stopped and resume
                  </button>
                  {resumeError && <p role="status" className="mt-2 text-xs text-rose-300">{resumeError}</p>}
                </>
              )}
            </div>
          )}
          <div className="bg-slate-900 rounded-2xl border border-slate-800 p-4 shrink-0">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-3">
              Live Transcript
            </h4>
            <div className="space-y-2 pr-1">
              {transcript.length === 0 && (
                <p className="text-slate-600 text-sm italic">
                  Waiting for conversation...
                </p>
              )}
              {transcript.map((line) => (
                <div key={line.id} className="text-sm leading-relaxed">
                  <span
                    className={`text-xs font-medium mr-1.5 ${
                      line.speaker === 'agent' ? 'text-emerald-400' : 'text-sky-400'
                    }`}
                  >
                    {line.speaker === 'agent' ? 'Sewina' : 'You'}:
                  </span>
                  <span className={line.isFinal ? 'text-slate-400' : 'text-slate-50'}>
                    {line.text}
                  </span>
                </div>
              ))}
              <div ref={transcriptEndRef} />
            </div>
          </div>

          <ExerciseCard
            data={exerciseData}
            onClose={() => setExerciseData(null)}
          />

          <PushToTalk isMuted={isMuted} onToggle={toggleMute} />
        </div>
      </div>
    </div>
  )
}
