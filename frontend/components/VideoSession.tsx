'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Room, RoomEvent, Track } from 'livekit-client'
import { Camera, LayoutDashboard } from 'lucide-react'
import { createClient } from '@/utils/supabase/client'
import ExerciseCard, { ExerciseData } from './ExerciseCard'
import PushToTalk from './PushToTalk'
import type { TranscriptMessage } from '@/utils/types'

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

  const router = useRouter()
  const localVideoRef = useRef<HTMLVideoElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const roomRef = useRef<Room | null>(null)
  const transcriptEndRef = useRef<HTMLDivElement>(null)
  const endingRef = useRef(false)

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
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

        const tokenResponse = await fetch(`${apiUrl}/api/token`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            room_name: 'flexflow-room',
            participant_identity: `user-${Date.now()}`,
            participant_name: 'FlexFlow User',
          }),
          signal: abortController.signal,
        })

        if (cancelled) return

        if (!tokenResponse.ok) {
          const errorData = await tokenResponse.json().catch(() => ({}))
          throw new Error(errorData.detail || `Failed to get token: ${tokenResponse.statusText}`)
        }

        const { server_url, participant_token } = await tokenResponse.json()
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
        body: JSON.stringify({ transcript: finalTranscript, duration: elapsed }),
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

  const disconnect = useCallback(() => {
    if (roomRef.current) roomRef.current.disconnect()
    onDisconnect()
  }, [onDisconnect])

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
    <div className="h-screen bg-slate-950 flex flex-col" spellCheck={false} data-grammarly="false">
      <audio ref={audioRef} autoPlay />

      <header className="h-20 px-8 flex items-center justify-between shrink-0 border-b border-slate-800">
        <h1 className="text-2xl font-bold text-slate-50">
          Flex<span className="text-emerald-400">Flow</span>
        </h1>
        <span className="text-slate-500 font-mono text-sm tabular-nums">
          {formatTime(elapsed)}
        </span>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              if (roomRef.current) roomRef.current.disconnect()
              router.push('/dashboard')
            }}
            className="px-4 py-2 bg-slate-800 text-slate-400 rounded-xl border border-slate-700 hover:text-slate-50 hover:bg-slate-700 transition text-sm font-medium flex items-center gap-2"
          >
            <LayoutDashboard className="w-4 h-4" />
            Dashboard
          </button>
          <button
            onClick={endSession}
            disabled={isSaving}
            className="px-5 py-2 bg-rose-500/10 text-rose-500 rounded-xl border border-rose-500/30 hover:bg-rose-500/20 transition text-sm font-medium disabled:opacity-50"
          >
            {isSaving ? 'Generating Summary...' : 'End Session'}
          </button>
        </div>
      </header>

      <div className="grid grid-cols-12 gap-6 h-[calc(100vh-80px)] p-6 min-h-0">
        <div className="col-span-8 relative rounded-3xl overflow-hidden bg-slate-900 border border-slate-800 shadow-2xl min-h-0 shrink-0">
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

        <div className="col-span-4 flex flex-col gap-4 min-h-0 overflow-y-auto h-full">
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
