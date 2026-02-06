'use client'

import { useEffect, useRef, useState } from 'react'
import { Room, RoomEvent, Track } from 'livekit-client'

interface VideoSessionProps {
  onDisconnect: () => void
}

export default function VideoSession({ onDisconnect }: VideoSessionProps) {
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isMuted, setIsMuted] = useState(false)
  const [isVideoEnabled, setIsVideoEnabled] = useState(false)

  const videoRef = useRef<HTMLVideoElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const roomRef = useRef<Room | null>(null)

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
          if (!cancelled) {
            setIsConnected(false)
            onDisconnect()
          }
        })

        room.on(RoomEvent.TrackSubscribed, (track) => {
          if (cancelled) return
          if (track.kind === Track.Kind.Video && videoRef.current) {
            track.attach(videoRef.current)
          }
          if (track.kind === Track.Kind.Audio && audioRef.current) {
            track.attach(audioRef.current)
          }
        })

        room.on(RoomEvent.TrackUnsubscribed, (track) => {
          track.detach()
        })

        await room.connect(server_url, participant_token)
        if (cancelled) {
          room.disconnect()
          return
        }

        await room.localParticipant.setMicrophoneEnabled(true)
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

  const toggleMute = async () => {
    if (roomRef.current) {
      await roomRef.current.localParticipant.setMicrophoneEnabled(isMuted)
      setIsMuted(!isMuted)
    }
  }

  const toggleVideo = async () => {
    if (roomRef.current) {
      await roomRef.current.localParticipant.setCameraEnabled(!isVideoEnabled)
      setIsVideoEnabled(!isVideoEnabled)
    }
  }

  const disconnect = () => {
    if (roomRef.current) {
      roomRef.current.disconnect()
    }
    onDisconnect()
  }

  if (error) {
    return (
      <div className="text-center p-8">
        <p className="text-red-600 mb-4">Error: {error}</p>
        <button
          onClick={onDisconnect}
          className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700"
        >
          Go Back
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6" spellCheck={false} data-grammarly="false">
      <audio ref={audioRef} autoPlay spellCheck={false} data-grammarly="false" />
      <div className="relative bg-black rounded-lg overflow-hidden aspect-video" spellCheck={false} data-grammarly="false">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          className="w-full h-full object-cover"
        />
        {!isVideoEnabled && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-900">
            <p className="text-white">Camera disabled</p>
          </div>
        )}
      </div>

      <div className="flex justify-center gap-4">
        <button
          onClick={toggleMute}
          className={`px-6 py-3 rounded-lg transition ${isMuted
            ? 'bg-red-600 hover:bg-red-700 text-white'
            : 'bg-green-600 hover:bg-green-700 text-white'
            }`}
        >
          {isMuted ? 'Unmute' : 'Mute'}
        </button>

        <button
          onClick={toggleVideo}
          className={`px-6 py-3 rounded-lg transition ${isVideoEnabled
            ? 'bg-blue-600 hover:bg-blue-700 text-white'
            : 'bg-gray-600 hover:bg-gray-700 text-white'
            }`}
        >
          {isVideoEnabled ? 'Disable Video' : 'Enable Video'}
        </button>

        <button
          onClick={disconnect}
          className="px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition"
        >
          End Session
        </button>
      </div>

      {isConnected && (
        <div className="text-center text-green-600">
          Connected to FlexFlow
        </div>
      )}
    </div>
  )
}
