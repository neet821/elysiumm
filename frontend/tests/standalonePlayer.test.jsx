import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeAll, describe, expect, it, vi } from 'vitest'

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ isAdmin: false, isAuthenticated: true, loading: false, user: { id: 7 } }),
}))

import { demoTrack, makeDemoWavDataUrl } from '../src/features/player/demoTrack.js'
import StandalonePlayerPage from '../src/pages/StandalonePlayerPage.jsx'
import AppRoutes from '../src/routes.jsx'

beforeAll(() => {
  Object.defineProperty(window.HTMLMediaElement.prototype, 'load', {
    configurable: true,
    value: vi.fn(),
  })
  Object.defineProperty(window.HTMLMediaElement.prototype, 'pause', {
    configurable: true,
    value: vi.fn(),
  })
})

describe('standalone local player', () => {
  it('builds one deterministic, valid local WAV track without a remote provider', () => {
    const first = makeDemoWavDataUrl()
    const second = makeDemoWavDataUrl()
    const bytes = window.atob(first.split(',')[1])

    expect(first).toBe(second)
    expect(first).toMatch(/^data:audio\/wav;base64,/)
    expect(bytes.slice(0, 4)).toBe('RIFF')
    expect(bytes.slice(8, 12)).toBe('WAVE')
    expect(demoTrack).toEqual(expect.objectContaining({
      artist: 'Blue Album',
      audioUrl: first,
      id: expect.stringMatching(/^local:/),
      title: expect.any(String),
    }))
    expect(demoTrack.lyrics.length).toBeGreaterThan(2)
    expect(first).not.toMatch(/^https?:/)
  })

  it('renders the direct player and visible GPL attribution without an iframe', async () => {
    render(<StandalonePlayerPage />)

    expect(screen.getByRole('heading', { name: '无需音乐平台的本地试听' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: `播放 ${demoTrack.title}` })).toBeInTheDocument()
    expect(document.querySelector('audio')).toHaveAttribute('src', demoTrack.audioUrl)
    expect(document.querySelector('iframe')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Mineradio.*GPL-3.0/i })).toBeInTheDocument()
    expect(screen.getByText(/完全使用本地生成的 WAV 音频/)).toBeInTheDocument()
  })

  it('does not map the authenticated /music route to the standalone demo player', async () => {
    render(
      <MemoryRouter initialEntries={['/music']} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <AppRoutes styles={{}} isDark={false} />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.queryByRole('heading', { name: '无需音乐平台的本地试听' })).not.toBeInTheDocument())
    expect(document.querySelector('audio')).not.toBeInTheDocument()
  })
})
