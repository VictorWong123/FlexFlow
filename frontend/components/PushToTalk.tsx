'use client'

import { Mic } from 'lucide-react'

interface PushToTalkProps {
  isMuted: boolean
  onToggle: () => void
}

export default function PushToTalk({ isMuted, onToggle }: PushToTalkProps) {
  return (
    <div className="mt-auto flex justify-center pb-4">
      <div className="relative">
        {!isMuted && (
          <span className="absolute inset-0 rounded-full border-2 border-emerald-500 animate-pulse-ring" />
        )}
        <button
          onClick={onToggle}
          className={`relative w-20 h-20 rounded-full flex items-center justify-center transition-all hover:scale-105 active:scale-95 ${
            isMuted
              ? 'bg-slate-800 border-2 border-slate-600'
              : 'bg-emerald-500/10 border-2 border-emerald-500'
          }`}
        >
          <Mic
            className={`w-8 h-8 ${
              isMuted ? 'text-slate-500' : 'text-emerald-500'
            }`}
          />
        </button>
      </div>
    </div>
  )
}
