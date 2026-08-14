import { describe, expect, it, vi } from 'vitest'

import { fingerprintLocalVideo, localFileMatches } from '../src/features/video/localVideo.js'

function sampledFile(name, bytes) {
  const file = new File([bytes], name, { type: 'video/mp4' })
  Object.defineProperty(file, 'slice', {
    configurable: true,
    value: vi.fn(() => ({
      arrayBuffer: async () => Uint8Array.from(bytes).buffer,
    })),
  })
  return file
}

describe('本地视频指纹', () => {
  it('生成稳定的 64 位十六进制 SHA-256 指纹', async () => {
    const file = sampledFile('同一视频.mp4', [1, 2, 3, 4])
    const first = await fingerprintLocalVideo(file)
    const second = await fingerprintLocalVideo(file)

    expect(first).toMatch(/^[0-9a-f]{64}$/)
    expect(second).toBe(first)
    expect(file.slice).toHaveBeenCalled()
  })

  it('只接受大小和指纹都匹配的本地文件', async () => {
    const expectedFile = sampledFile('电影.mp4', [5, 6, 7])
    const fingerprint = await fingerprintLocalVideo(expectedFile)
    const item = { file_size: expectedFile.size, local_fingerprint: fingerprint, source_type: 'legacy_local' }

    expect(localFileMatches(item, expectedFile, fingerprint)).toBe(true)
    expect(localFileMatches(item, sampledFile('另一份.mp4', [5, 6]), fingerprint)).toBe(false)
    expect(localFileMatches({ ...item, local_fingerprint: '0'.repeat(64) }, expectedFile, fingerprint)).toBe(false)
    expect(localFileMatches({ ...item, source_type: 'upload' }, expectedFile, fingerprint)).toBe(false)
  })
})
