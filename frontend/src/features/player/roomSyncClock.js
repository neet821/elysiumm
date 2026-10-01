function finiteNumber(value, fallback = null) {
  if (value === null || value === undefined || value === '') return fallback
  const normalized = Number(value)
  return Number.isFinite(normalized) ? normalized : fallback
}

export function recordClockProbe(syncState, sample) {
  const clientSent = finiteNumber(sample?.clientSentAtMs)
  const clientReceived = finiteNumber(sample?.clientReceivedAtMs)
  const serverReceived = finiteNumber(sample?.serverReceivedAtMs)
  const serverSent = finiteNumber(sample?.serverSentAtMs)
  if ([clientSent, clientReceived, serverReceived, serverSent].some((value) => value === null)) {
    return null
  }
  const roundTripTimeMs = (clientReceived - clientSent) - (serverSent - serverReceived)
  if (roundTripTimeMs < 0 || clientReceived < clientSent || serverSent < serverReceived) {
    return null
  }
  const clockOffsetMs = ((serverReceived - clientSent) + (serverSent - clientReceived)) / 2
  const clockSamples = [
    ...(Array.isArray(syncState.clockSamples) ? syncState.clockSamples : []),
    { clockOffsetMs, roundTripTimeMs },
  ].slice(-8)
  const bestSample = clockSamples.reduce((best, current) => (
    current.roundTripTimeMs < best.roundTripTimeMs ? current : best
  ))
  syncState.clockSamples = clockSamples
  syncState.clockOffsetMs = bestSample.clockOffsetMs
  syncState.roundTripTimeMs = bestSample.roundTripTimeMs
  return { clockOffsetMs, roundTripTimeMs }
}

export function estimateServerOffset(snapshot, receivedAtMs) {
  const serverNow = finiteNumber(snapshot?.server_now_ms)
  const receivedAt = finiteNumber(receivedAtMs)
  if (serverNow === null || receivedAt === null) return 0
  return serverNow - receivedAt
}
