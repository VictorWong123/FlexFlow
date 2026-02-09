import { NextResponse } from 'next/server'
import { AccessToken } from 'livekit-server-sdk'

export async function POST(request: Request) {
  const apiKey = process.env.LIVEKIT_API_KEY
  const apiSecret = process.env.LIVEKIT_API_SECRET
  const livekitUrl = process.env.LIVEKIT_URL

  if (!apiKey || !apiSecret || !livekitUrl) {
    return NextResponse.json(
      { detail: 'LIVEKIT_API_KEY, LIVEKIT_API_SECRET, and LIVEKIT_URL must be set' },
      { status: 500 }
    )
  }

  let body: { room_name?: string; participant_identity?: string; participant_name?: string }
  try {
    body = await request.json()
  } catch {
    body = {}
  }

  const roomName = body.room_name || 'flexflow-room'
  const identity = body.participant_identity || `user-${Date.now()}`
  const name = body.participant_name || identity

  const token = new AccessToken(apiKey, apiSecret, {
    identity,
    name,
    ttl: '6h',
  })

  token.addGrant({
    roomJoin: true,
    room: roomName,
    canPublish: true,
    canSubscribe: true,
  })

  const jwt = await token.toJwt()

  const serverUrl = livekitUrl
    .replace('wss://', 'https://')
    .replace('ws://', 'http://')

  return NextResponse.json({
    server_url: serverUrl,
    participant_token: jwt,
  })
}
