import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules() })

describe('transfer link base', () => {
  it('uses the local preview route without sending tokens to production', async () => {
    vi.stubEnv('DEV', true)
    vi.stubEnv('VITE_TRANSFER_PUBLIC_BASE_URL', '')
    const { transferPublicUrl } = await import('../src/utils/transfer.js')
    expect(transferPublicUrl('test-token')).toBe(`${window.location.origin}/transfer/test-token`)
  })
  it('honors an explicit public base and removes its trailing slash', async () => {
    vi.stubEnv('VITE_TRANSFER_PUBLIC_BASE_URL', 'https://share.example.com/')
    const { transferPublicUrl } = await import('../src/utils/transfer.js')
    expect(transferPublicUrl('test-token')).toBe('https://share.example.com/test-token')
  })
  it('preserves production sharing when no override is configured', async () => {
    vi.stubEnv('DEV', false)
    vi.stubEnv('VITE_TRANSFER_PUBLIC_BASE_URL', '')
    const { transferPublicUrl } = await import('../src/utils/transfer.js')
    expect(transferPublicUrl('test-token')).toBe('https://send.elysiumm.top/test-token')
  })
})
