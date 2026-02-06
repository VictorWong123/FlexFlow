'use client'

import { useCallback, useState } from 'react'
import VideoSession from '@/components/VideoSession'

export default function Home() {
  const [isConnected, setIsConnected] = useState(false)
  const handleDisconnect = useCallback(() => setIsConnected(false), [])

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl font-bold mb-8 text-center">
          FlexFlow - AI Physical Therapist
        </h1>

        {!isConnected ? (
          <div className="text-center">
            <p className="text-lg mb-6">
              Connect to start your PT session with FlexFlow
            </p>
            <button
              onClick={() => setIsConnected(true)}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
            >
              Start Session
            </button>
          </div>
        ) : (
          <VideoSession onDisconnect={handleDisconnect} />
        )}
      </div>
    </main>
  )
}
