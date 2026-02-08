'use client'

interface MetricsGaugeProps {
  angle: number
}

const ARC_PATH = 'M 20 100 A 80 80 0 0 1 180 100'
const ARC_LENGTH = Math.PI * 80

const EMERALD = '#10b981'
const AMBER = '#f59e0b'
const ROSE = '#f43f5e'

export default function MetricsGauge({ angle }: MetricsGaugeProps) {
  const clamped = Math.min(Math.abs(angle), 90)
  const fill = (clamped / 90) * ARC_LENGTH

  let color = EMERALD
  let label = 'Good'
  if (clamped > 35) {
    color = ROSE
    label = 'Warning'
  } else if (clamped > 20) {
    color = AMBER
    label = 'Moderate'
  }

  return (
    <div className="bg-slate-900 rounded-2xl p-6 border border-slate-800">
      <svg viewBox="0 0 200 120" className="w-full">
        <path
          d={ARC_PATH}
          fill="none"
          stroke="#1e293b"
          strokeWidth="8"
          strokeLinecap="round"
        />
        <path
          d={ARC_PATH}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={ARC_LENGTH.toString()}
          strokeDashoffset={ARC_LENGTH - fill}
          style={{ transition: 'stroke-dashoffset 0.3s ease, stroke 0.3s ease' }}
        />
        <text
          x="100"
          y="78"
          textAnchor="middle"
          fill={color}
          fontSize="30"
          fontWeight="bold"
          style={{ transition: 'fill 0.3s ease' }}
        >
          {clamped}°
        </text>
        <text
          x="100"
          y="98"
          textAnchor="middle"
          fill="#94a3b8"
          fontSize="11"
          fontWeight="500"
        >
          Neck Tilt
        </text>
        <text
          x="100"
          y="114"
          textAnchor="middle"
          fill={color}
          fontSize="9"
          style={{ transition: 'fill 0.3s ease' }}
        >
          {label}
        </text>
      </svg>
    </div>
  )
}
