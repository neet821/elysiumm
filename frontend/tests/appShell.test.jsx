import { MemoryRouter } from 'react-router-dom'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

  it('renders the compact signed-in navigation and current service', () => {
    renderShell()
    const primaryNav = screen.getByRole('navigation', { name: '主导航' })
    expect(within(primaryNav).getByRole('link', { name: '首页' })).toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: '工具箱' })).toBeInTheDocument()
    expect(within(primaryNav).getByText('归档')).toHaveAttribute('aria-current', 'page')
    expect(within(primaryNav).getByRole('link', { name: 'Test User' })).toHaveAttribute('href', '/account')
  })

  it('shows login instead of account to signed-out visitors', () => {
    authState = { isAdmin: false, isAuthenticated: false, user: null }
    renderShell()
    const primaryNav = screen.getByRole('navigation', { name: '主导航' })
    expect(within(primaryNav).getByRole('link', { name: '登录' })).toHaveAttribute('href', '/login')
    expect(within(primaryNav).queryByText('账户')).not.toBeInTheDocument()
  })

  it('uses the Elysium mark as home and hides the formal shell on the 3D home', () => {
    const { unmount } = renderShell({ initialPath: '/archive?type=photo' })
    const brandLink = screen.getByRole('link', { name: 'Elysium 首页' })
    expect(brandLink).toHaveAttribute('href', '/')
    expect(brandLink.querySelector('img')).toHaveAttribute('src', '/brand/elysium-mark.svg')

    unmount()
    renderShell({ initialPath: '/' })
    expect(document.querySelector('.app-shell')).toHaveClass('app-shell--home')
    expect(document.querySelector('.app-header')).not.toBeInTheDocument()
    expect(screen.queryByText('© 2026 Elysium')).not.toBeInTheDocument()
  })

  it('opens the mobile drawer and keeps command navigation available without a theme control', async () => {
    const user = userEvent.setup()
    renderShell()
    await user.click(screen.getByRole('button', { name: '打开导航' }))
    expect(screen.getByRole('dialog', { name: '导航' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(screen.getByRole('dialog', { name: '快捷导航' })).toBeInTheDocument()
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
