import { describe, expect, it } from 'vitest'
import { isSafetyHaltTransition, parseTrackingState, shouldAcceptTrackingUpdate, type TrackingState } from './tracking'

describe('parseTrackingState', () => {
  it('rejects non-object packets', () => expect(parseTrackingState('tracking')).toBeNull())

  it('rejects malformed or incomplete participant data', () => {
    expect(parseTrackingState({ status: 'evil', reps: -3 })).toBeNull()
    expect(parseTrackingState({ status: 'tracking' })).toBeNull()
  })

  it('normalizes valid tracking data', () => {
    expect(parseTrackingState({
      status: 'tracking', protocol_id: 'squat', tracking_supported: true, required_view: 'side',
      reps: 2, hold_seconds: 3, issues: [], cue: null, halted: false,
      calibration_required: true, calibrated: true,
    })?.reps).toBe(2)
  })

  it('latches halted state until explicit resume and announces only transition', () => {
    const base: TrackingState = {
      status: 'tracking', protocol_id: 'squat', tracking_supported: true, required_view: 'side',
      reps: 0, hold_seconds: 0, issues: [], cue: null, halted: false,
      calibration_required: true, calibrated: true,
    }
    const halted = { ...base, status: 'halted' as const, halted: true }
    expect(shouldAcceptTrackingUpdate(halted, base, false)).toBe(false)
    expect(shouldAcceptTrackingUpdate(halted, base, true)).toBe(true)
    expect(isSafetyHaltTransition(base, halted)).toBe(true)
    expect(isSafetyHaltTransition(halted, halted)).toBe(false)
  })
})
