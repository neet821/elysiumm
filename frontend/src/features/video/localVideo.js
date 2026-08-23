const SAMPLE_SIZE = 1024 * 1024

function hex(buffer) {
  return [...new Uint8Array(buffer)].map((value) => value.toString(16).padStart(2, '0')).join('')
}

export async function fingerprintLocalVideo(file) {
  if (!(file instanceof File) || file.size <= 0) throw new Error('请选择有效的本地视频文件')
  const offsets = [0, Math.max(0, Math.floor(file.size / 2) - Math.floor(SAMPLE_SIZE / 2)), Math.max(0, file.size - SAMPLE_SIZE)]
  const samples = await Promise.all(offsets.map((offset) => file.slice(offset, Math.min(file.size, offset + SAMPLE_SIZE)).arrayBuffer()))
  const size = new TextEncoder().encode(String(file.size))
  const length = size.byteLength + samples.reduce((total, sample) => total + sample.byteLength, 0)
  const merged = new Uint8Array(length)
  merged.set(size, 0)
  let cursor = size.byteLength
  for (const sample of samples) {
    merged.set(new Uint8Array(sample), cursor)
    cursor += sample.byteLength
  }
  return hex(await crypto.subtle.digest('SHA-256', merged))
}

export function localFileMatches(item, file, fingerprint) {
  return item?.source_type === 'legacy_local'
    && Number(item.file_size) === Number(file?.size)
    && item.local_fingerprint === fingerprint
}
