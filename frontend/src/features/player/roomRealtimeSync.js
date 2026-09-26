import { recordClockProbe } from './roomSyncEngine.js'

function createInstanceId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16)
    return (character === 'x' ? random : (random & 0x3) | 0x8).toString(16)
  })
}

export function createRoomOperationSequencer({ createInstanceId: makeInstanceId = createInstanceId } = {}) {
  const instanceId = makeInstanceId()
  let sequence = 0

  return {
    attach(payload) {
      sequence = Math.min(Number.MAX_SAFE_INTEGER, sequence + 1)
      return {
        ...payload,
        client_instance_id: instanceId,
        operation_seq: sequence,
      }
    },
  }
}

export const roomOperationSequencer = createRoomOperationSequencer()

export function attachRoomOperation(payload) {
  return roomOperationSequencer.attach(payload)
}

export function startRoomClockProbes(socket, roomId, syncState, options = {}) {
  if (!socket || !syncState || !roomId) return () => {}
  const now = options.now || Date.now
  const setIntervalFn = options.setInterval || setInterval
  const clearIntervalFn = options.clearInterval || clearInterval
  const intervalMs = options.intervalMs || 30_000
  const pending = new Map()
  let joined = false
  let nextProbeId = 0

  const sendProbe = () => {
    if (!joined || !socket.connected) return
    const clientSentAtMs = now()
    const probeId = `${clientSentAtMs}:${++nextProbeId}`
    pending.set(probeId, clientSentAtMs)
    while (pending.size > 4) pending.delete(pending.keys().next().value)
    socket.emit('clock_probe', {
      client_sent_at_ms: clientSentAtMs,
      probe_id: probeId,
      room_id: Number(roomId),
    })
  }
  const onJoin = () => {
    joined = true
    pending.clear()
    sendProbe()
  }
  const onDisconnect = () => {
    joined = false
    pending.clear()
  }
  const onAck = (payload) => {
    const sentAt = pending.get(payload?.probe_id)
    if (sentAt === undefined || Number(payload?.client_sent_at_ms) !== sentAt) return
    pending.delete(payload.probe_id)
    recordClockProbe(syncState, {
      clientSentAtMs: sentAt,
      clientReceivedAtMs: now(),
      serverReceivedAtMs: payload.server_received_at_ms,
      serverSentAtMs: payload.server_sent_at_ms,
    })
  }

  socket.on('join_success', onJoin)
  socket.on('disconnect', onDisconnect)
  socket.on('clock_probe_ack', onAck)
  const timer = setIntervalFn(sendProbe, intervalMs)
  return () => {
    clearIntervalFn(timer)
    socket.off?.('join_success', onJoin)
    socket.off?.('disconnect', onDisconnect)
    socket.off?.('clock_probe_ack', onAck)
    pending.clear()
  }
}
