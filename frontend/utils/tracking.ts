const STATUSES = new Set(['unsupported', 'calibrating', 'stale', 'lost_visibility', 'wrong_view', 'tracking', 'halted'])

export interface TrackingState {
  status: 'unsupported' | 'calibrating' | 'stale' | 'lost_visibility' | 'wrong_view' | 'tracking' | 'halted'
  protocol_id: string | null
  tracking_supported: boolean
  required_view: 'front' | 'side' | null
  reps: number
  hold_seconds: number
  issues: string[]
  cue: string | null
  halted: boolean
  calibration_required: boolean
  calibrated: boolean
}

export function shouldAcceptTrackingUpdate(previous: TrackingState | null, next: TrackingState, resumeRequested: boolean): boolean {
  return !(previous?.halted && !next.halted && !resumeRequested)
}

export function isSafetyHaltTransition(previous: TrackingState | null, next: TrackingState): boolean {
  return !previous?.halted && next.halted
}

export function parseTrackingState(value: unknown): TrackingState | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const data = value as Record<string, unknown>
  const nullableText = (field: unknown) => field === null || (typeof field === 'string' && field.length <= 200)
  if (
    typeof data.status !== 'string' || !STATUSES.has(data.status)
    || !nullableText(data.protocol_id)
    || typeof data.tracking_supported !== 'boolean'
    || (data.required_view !== null && data.required_view !== 'front' && data.required_view !== 'side')
    || typeof data.reps !== 'number' || !Number.isInteger(data.reps) || data.reps < 0
    || typeof data.hold_seconds !== 'number' || !Number.isInteger(data.hold_seconds) || data.hold_seconds < 0
    || !Array.isArray(data.issues) || data.issues.length > 10 || data.issues.some(item => typeof item !== 'string' || item.length > 200)
    || !nullableText(data.cue)
    || typeof data.halted !== 'boolean'
    || typeof data.calibration_required !== 'boolean'
    || typeof data.calibrated !== 'boolean'
  ) return null
  return {
    status: data.status as TrackingState['status'],
    protocol_id: data.protocol_id as string | null,
    tracking_supported: data.tracking_supported,
    required_view: data.required_view as 'front' | 'side' | null,
    reps: data.reps,
    hold_seconds: data.hold_seconds,
    issues: data.issues as string[],
    cue: data.cue as string | null,
    halted: data.halted,
    calibration_required: data.calibration_required,
    calibrated: data.calibrated,
  }
}
