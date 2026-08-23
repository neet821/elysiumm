const SAMPLE_RATE = 8000
const DURATION_SECONDS = 6

let cachedDemoWav = ''

function writeAscii(view, offset, value) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index))
  }
}

function encodeBase64(bytes) {
  let binary = ''
  const chunkSize = 8192
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize))
  }
  return globalThis.btoa(binary)
}

export function makeDemoWavDataUrl() {
  if (cachedDemoWav) return cachedDemoWav

  const sampleCount = SAMPLE_RATE * DURATION_SECONDS
  const bytes = new Uint8Array(44 + sampleCount)
  const view = new DataView(bytes.buffer)

  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, 36 + sampleCount, true)
  writeAscii(view, 8, 'WAVE')
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, SAMPLE_RATE, true)
  view.setUint32(28, SAMPLE_RATE, true)
  view.setUint16(32, 1, true)
  view.setUint16(34, 8, true)
  writeAscii(view, 36, 'data')
  view.setUint32(40, sampleCount, true)

  for (let index = 0; index < sampleCount; index += 1) {
    const time = index / SAMPLE_RATE
    const fade = Math.min(1, time * 2, (DURATION_SECONDS - time) * 2)
    const pulse = 0.7 + (0.3 * Math.sin(2 * Math.PI * 0.25 * time))
    const tone = (Math.sin(2 * Math.PI * 220 * time) * 0.62)
      + (Math.sin(2 * Math.PI * 330 * time) * 0.24)
      + (Math.sin(2 * Math.PI * 440 * time) * 0.14)
    bytes[44 + index] = Math.round(128 + (tone * fade * pulse * 32))
  }

  cachedDemoWav = `data:audio/wav;base64,${encodeBase64(bytes)}`
  return cachedDemoWav
}

export const demoTrack = Object.freeze({
  album: 'Local studies',
  artist: 'Blue Album',
  artworkUrl: null,
  audioUrl: makeDemoWavDataUrl(),
  duration: DURATION_SECONDS,
  id: 'local:blue-hour-study',
  lyrics: Object.freeze([
    Object.freeze({ text: 'A tone begins at blue hour', time: 0 }),
    Object.freeze({ text: 'No account, catalog, or provider', time: 2 }),
    Object.freeze({ text: 'Only the browser and this little wave', time: 4 }),
  ]),
  title: 'Blue hour study',
})
