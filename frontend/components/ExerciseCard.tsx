'use client'

import { AnimatePresence, motion } from 'framer-motion'
import { XCircle, ArrowRight, Play } from 'lucide-react'
import { useEffect, useState } from 'react'

export interface ExerciseData {
  type: string
  title: string
  image_url?: string
  image_url_end?: string
  gif_url?: string
  thumbnail_url?: string
  youtube_url?: string
  body_part?: string
  target?: string
  equipment?: string
  instructions?: string[]
}

interface ExerciseCardProps {
  data: ExerciseData | null
  onClose: () => void
}

export default function ExerciseCard({ data, onClose }: ExerciseCardProps) {
  const [showVideo, setShowVideo] = useState(false)
  const [imgError, setImgError] = useState(false)
  const [showAlt, setShowAlt] = useState(false)

  const hasYoutube = !!data?.youtube_url
  const startImg = data?.image_url || data?.gif_url || data?.thumbnail_url || ''
  const endImg = data?.image_url_end || ''
  const hasImages = !!startImg && !imgError
  const hasAlt = !!endImg && !imgError
  const animatedSrc = hasAlt && showAlt ? endImg : startImg

  useEffect(() => {
    if (!hasAlt) return
    const interval = setInterval(() => {
      setShowAlt(prev => !prev)
    }, 1200)
    return () => clearInterval(interval)
  }, [hasAlt])

  return (
    <AnimatePresence>
      {data && (
        <motion.div
          key={data.title}
          initial={{ y: 40, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 40, opacity: 0 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          className="bg-slate-800 rounded-2xl overflow-hidden border border-slate-700 shadow-lg"
          onAnimationStart={() => {
            setShowVideo(false)
            setImgError(false)
            setShowAlt(false)
          }}
        >
          <div className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-2 min-w-0">
              <h4 className="text-sm font-semibold text-slate-50 truncate">
                {data.title}
              </h4>
              {data.body_part && (
                <span className="text-[10px] bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded-full shrink-0">
                  {data.body_part}
                </span>
              )}
            </div>
            <button
              onClick={onClose}
              className="text-slate-500 hover:text-slate-300 transition shrink-0 ml-2"
            >
              <XCircle className="w-5 h-5" />
            </button>
          </div>

          {hasImages && (
            <>
              <div className="relative bg-slate-900">
                <img
                  src={animatedSrc}
                  alt={`${data.title} — preview`}
                  className="aspect-video object-contain w-full"
                  loading="eager"
                  onError={() => setImgError(true)}
                />
                {hasAlt && (
                  <span className="absolute top-2 left-2 text-[9px] font-semibold bg-slate-950/70 text-emerald-400 px-1.5 py-0.5 rounded">
                    Preview
                  </span>
                )}
              </div>
              {hasAlt && (
                <div className="flex items-stretch border-t border-slate-700">
                <div className="flex-1 relative bg-slate-900">
                    <img
                      src={startImg}
                      alt={`${data.title} — start position`}
                    className="w-full h-28 object-contain"
                      loading="eager"
                      onError={() => setImgError(true)}
                    />
                    <span className="absolute bottom-1 left-1 text-[9px] font-semibold bg-slate-950/70 text-emerald-400 px-1.5 py-0.5 rounded">
                      Start
                    </span>
                  </div>
                  <div className="flex items-center px-1 bg-slate-900">
                    <ArrowRight className="w-3 h-3 text-slate-500" />
                  </div>
                  <div className="flex-1 relative bg-slate-900">
                    <img
                      src={endImg}
                      alt={`${data.title} — end position`}
                      className="w-full h-28 object-contain"
                      loading="eager"
                    />
                    <span className="absolute bottom-1 left-1 text-[9px] font-semibold bg-slate-950/70 text-emerald-400 px-1.5 py-0.5 rounded">
                      End
                    </span>
                  </div>
                </div>
              )}
            </>
          )}

          {data.instructions && data.instructions.length > 0 && (
            <ul className="px-4 py-3 space-y-1.5">
              {data.instructions.slice(0, 4).map((step, i) => (
                <li
                  key={i}
                  className="text-xs text-slate-400 leading-snug flex gap-2"
                >
                  <span className="text-emerald-400 shrink-0">{i + 1}.</span>
                  {step}
                </li>
              ))}
            </ul>
          )}

          {hasYoutube && (
            <div className="border-t border-slate-700">
              {showVideo ? (
                <div className="aspect-video w-full">
                  <iframe
                    src={`${data.youtube_url}?autoplay=1&rel=0`}
                    title={data.title}
                    allow="autoplay; encrypted-media"
                    allowFullScreen
                    className="w-full h-full border-0"
                  />
                </div>
              ) : (
                <button
                  onClick={() => setShowVideo(true)}
                  className="w-full px-4 py-2.5 flex items-center justify-center gap-2 hover:bg-slate-700/50 transition"
                >
                  <Play className="w-4 h-4 text-emerald-400" />
                  <span className="text-xs font-medium text-emerald-400">
                    Watch video tutorial
                  </span>
                </button>
              )}
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
