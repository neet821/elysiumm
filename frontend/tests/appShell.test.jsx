import { MemoryRouter } from 'react-router-dom'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

let authState = { isAdmin: false, isAuthenticated: true, user: { id: 7, username: 'Test User', avatar_url: null } }

vi.mock('../src/contexts/AuthContext.jsx', () => ({ useAuth: () => authState }))

import { AppShell } from '../src/components/layout/AppShell.jsx'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function renderShell({ initialPath = '/archive' } = {}) {
  return render(
    <MemoryRouter initialEntries={[initialPath]} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <AppShell><h1>Page content</h1></AppShell>
    </MemoryRouter>,
  )
}

describe('Elysium plain service shell', () => {
  beforeEach(() => {
    authState = { isAdmin: false, isAuthenticated: true, user: { id: 7, username: 'Test User', avatar_url: null } }
  })

  it('keeps the global top bar but hides the current service label', () => {
    renderShell()
    expect(screen.getByRole('banner')).toBeInTheDocument()
    const primaryNav = screen.getByRole('navigation', { name: '主导航' })
    expect(within(primaryNav).getByRole('link', { name: '首页' })).toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: '归档' })).toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: '房间' })).toBeInTheDocument()
  })

  it('shows login instead of account to signed-out visitors', () => {
    authState = { isAdmin: false, isAuthenticated: false, user: null }
    renderShell()
    expect(screen.getByRole('banner')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '主导航' })).toBeInTheDocument()
  })

  it('uses the same compact header on the 3D home without invented service links', () => {
    const { unmount } = renderShell({ initialPath: '/archive?type=photo' })
    expect(screen.getByRole('link', { name: 'Elysium 首页' })).toBeInTheDocument()

    unmount()
    renderShell({ initialPath: '/' })
    expect(document.querySelector('.app-shell')).toHaveClass('app-shell--home')
    expect(screen.getByRole('banner')).toBeInTheDocument()
    const primaryNav = screen.getByRole('navigation', { name: '主导航' })
    expect(within(primaryNav).getByRole('link', { name: '首页' })).toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: '归档' })).toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: '房间' })).toBeInTheDocument()
    expect(within(primaryNav).queryByText('直播')).not.toBeInTheDocument()
    expect(within(primaryNav).queryByText('音乐')).not.toBeInTheDocument()
    expect(within(primaryNav).queryByText('书籍')).not.toBeInTheDocument()
    expect(screen.queryByText('© 2026 Elysium')).not.toBeInTheDocument()
  })

  it('keeps formal pages free of current-page and theme controls', () => {
    renderShell()
    expect(screen.queryByRole('button', { name: /切换到/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '打开导航' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('renders a simple footer and the specialized routes remain immersive', () => {
    const { unmount: unmountArchive } = renderShell()
    expect(screen.getByText('© 2026 Elysium')).toBeInTheDocument()
    expect(screen.queryByText(/已运行/)).not.toBeInTheDocument()

    unmountArchive()
    const { unmount } = renderShell({ initialPath: '/tools' })
    expect(screen.queryByText('© 2026 Elysium')).not.toBeInTheDocument()
    unmount()
    renderShell({ initialPath: '/music/rooms/9' })
    expect(screen.queryByRole('link', { name: 'Elysium 首页' })).not.toBeInTheDocument()
    expect(document.querySelector('.app-shell')).toHaveClass('app-shell--music-room')
    expect(document.querySelector('.app-shell')).not.toHaveClass('app-shell--immersive')
  })

  it('publishes the plain surface tokens and no decorative service background', () => {
    const css = fs.readFileSync(path.join(frontendRoot, 'src', 'index.css'), 'utf8')
    expect(css).toMatch(/--surface-page:\s*#fff/)
    expect(css).toMatch(/--shadow-card:\s*none/)
    expect(css).toMatch(/body::before\s*\{\s*display:\s*none !important/)
  })
})
