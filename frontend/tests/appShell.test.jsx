import { MemoryRouter } from 'react-router-dom'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen } from '@testing-library/react'
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

  it('does not render a global top bar on formal service pages', () => {
    renderShell()
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: '主导航' })).not.toBeInTheDocument()
  })

  it('shows login instead of account to signed-out visitors', () => {
    authState = { isAdmin: false, isAuthenticated: false, user: null }
    renderShell()
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '登录' })).not.toBeInTheDocument()
  })

  it('uses the Elysium mark as home and hides the formal shell on the 3D home', () => {
    const { unmount } = renderShell({ initialPath: '/archive?type=photo' })
    expect(screen.queryByRole('link', { name: 'Elysium 首页' })).not.toBeInTheDocument()

    unmount()
    renderShell({ initialPath: '/' })
    expect(document.querySelector('.app-shell')).toHaveClass('app-shell--home')
    expect(document.querySelector('.app-header')).not.toBeInTheDocument()
    expect(screen.queryByText('© 2026 Elysium')).not.toBeInTheDocument()
  })

  it('keeps formal pages free of navigation and theme controls', () => {
    renderShell()
    expect(screen.queryByRole('button', { name: '打开导航' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /切换到/ })).not.toBeInTheDocument()
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
  })

  it('publishes the plain surface tokens and no decorative service background', () => {
    const css = fs.readFileSync(path.join(frontendRoot, 'src', 'index.css'), 'utf8')
    expect(css).toMatch(/--surface-page:\s*#fff/)
    expect(css).toMatch(/--shadow-card:\s*none/)
    expect(css).toMatch(/body::before\s*\{\s*display:\s*none !important/)
  })
})
