import { randomUUID } from 'node:crypto'
import { AccessToken, RoomAgentDispatch, RoomConfiguration } from 'livekit-server-sdk'

export interface TokenEnvironment { apiKey: string; apiSecret: string; serverUrl: string }

export async function createSessionToken(env: TokenEnvironment, sessionId: string = randomUUID(), roomName: string = `flexflow-${sessionId}`) {
  const token = new AccessToken(env.apiKey, env.apiSecret, {
    identity: `participant-${randomUUID()}`,
    name: 'FlexFlow User',
    ttl: '2h',
  })
  token.addGrant({ roomJoin: true, room: roomName, canPublish: true, canSubscribe: true })
  token.roomConfig = new RoomConfiguration({
    name: roomName,
    agents: [new RoomAgentDispatch({ agentName: 'flexflow-coach' })],
  })
  return { server_url: env.serverUrl, participant_token: await token.toJwt(), session_id: sessionId }
}
