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

function renderShell({ initialPath = '/content' } = {}) {
  return render(
    <MemoryRouter initialEntries={[initialPath]} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <AppShell><h1>Page content</h1></AppShell>
    </MemoryRouter>,
  )
}

describe('Elysium plain service shell', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    authState = { isAdmin: false, isAuthenticated: true, user: { id: 7, username: 'Test User', avatar_url: null } }
  })

  it('keeps a small global bar on formal pages', () => {
    renderShell()
    expect(screen.getByRole('banner')).toBeInTheDocument()
    const primaryNav = screen.getByRole('navigation', { name: '主导航' })
    expect(within(primaryNav).getByRole('link', { name: '房间' })).toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: '直播' })).toBeInTheDocument()
  })

  it('keeps homepage controls out of the global shell header', () => {
    renderShell({ initialPath: '/' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(document.querySelector('.home-header-portal')).not.toBeInTheDocument()
  })

  it('only polls the live indicator from the shared navigation shell', () => {
    const fetch = vi.spyOn(globalThis, 'fetch')
    renderShell({ initialPath: '/' })
    expect(fetch).toHaveBeenCalledWith('/api/live/status', { cache: 'no-store' })
  })

  it('shows login instead of account to signed-out visitors', () => {
    authState = { isAdmin: false, isAuthenticated: false, user: null }
    renderShell()
    expect(screen.getByRole('banner')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '主导航' })).toBeInTheDocument()
  })

  it('routes every authenticated avatar to the user account', () => {
    const { unmount } = renderShell({ initialPath: '/content' })
    expect(screen.getByRole('link', { name: '账户' })).toHaveAttribute('href', '/account')

    unmount()
    authState = { isAdmin: true, isAuthenticated: true, user: { id: 1, username: 'Admin', avatar_url: null } }
    renderShell({ initialPath: '/content' })
    expect(screen.getByRole('link', { name: '账户' })).toHaveAttribute('href', '/account')
  })

  it('keeps the administrator route free of public chrome', () => {
    renderShell({ initialPath: '/admin' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.queryByRole('contentinfo')).not.toBeInTheDocument()
  })

  it('keeps icon-only home navigation and restores the admin control entry', () => {
    const { unmount } = renderShell({ initialPath: '/content?type=photo' })
    expect(screen.getByRole('banner')).toBeInTheDocument()

    unmount()
    renderShell({ initialPath: '/' })
    expect(document.querySelector('.app-shell')).toHaveClass('app-shell--home')
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: '主导航' })).not.toBeInTheDocument()
    expect(screen.queryByText('© 2026')).not.toBeInTheDocument()

    unmount()
    authState = { isAdmin: true, isAuthenticated: true, user: { id: 1, username: 'Admin', avatar_url: null } }
    renderShell({ initialPath: '/' })
    expect(screen.getByRole('link', { name: '打开管理员控制台' })).toHaveAttribute('href', '/admin/homepage')
  })

  it('keeps formal pages free of current-page and theme controls', () => {
    renderShell()
    expect(screen.queryByRole('button', { name: /切换到/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '打开导航' })).not.toBeInTheDocument()
  })

  it('removes global chrome from the article reader and provides an icon-only home link for rooms', () => {
    const { unmount } = renderShell({ initialPath: '/article/hello' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.queryByRole('contentinfo')).not.toBeInTheDocument()

    unmount()
    const roomView = renderShell({ initialPath: '/rooms/music/9' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    const roomHomeLink = screen.getByRole('link', { name: '返回首页' })
    expect(roomHomeLink).toHaveAttribute('href', '/')
    expect(roomHomeLink).toHaveTextContent('')
    expect(roomHomeLink.querySelector('svg')).toBeInTheDocument()
    expect(screen.queryByText(/Elysium/i)).not.toBeInTheDocument()
    expect(screen.queryByText('© 2026')).not.toBeInTheDocument()

    roomView.unmount()
    renderShell({ initialPath: '/account' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '返回首页' })).toHaveAttribute('href', '/')
  })

  it('keeps the top-level viewport scrollable while a room is mounted', () => {
    const { unmount } = renderShell({ initialPath: '/rooms/music/9' })
    expect(document.querySelector('.app-shell')).not.toHaveClass('app-shell--immersive')
    expect(document.documentElement).not.toHaveClass('app-immersive-locked')
    expect(document.body).not.toHaveClass('app-immersive-locked')

    unmount()
  })

  it('keeps login and registration pages free of the global top bar', () => {
    const { unmount } = renderShell({ initialPath: '/login' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()

    unmount()
    renderShell({ initialPath: '/register' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
  })

  it('uses only one icon-only home link on the room hub and live page', () => {
    const roomHubView = renderShell({ initialPath: '/rooms' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    const roomHubHomeLink = screen.getByRole('link', { name: '返回首页' })
    expect(roomHubHomeLink).toHaveAttribute('href', '/')
    expect(roomHubHomeLink).toHaveTextContent('')
    expect(roomHubHomeLink.querySelector('svg')).toBeInTheDocument()

    roomHubView.unmount()
    renderShell({ initialPath: '/live' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    const liveHomeLink = screen.getByRole('link', { name: '返回首页' })
    expect(liveHomeLink).toHaveAttribute('href', '/')
    expect(liveHomeLink).toHaveTextContent('')
    expect(liveHomeLink.querySelector('svg')).toBeInTheDocument()
  })

  it('renders a simple footer and the specialized routes remain immersive', () => {
    const { unmount: unmountArchive } = renderShell()
    expect(screen.getByText('© 2026')).toBeInTheDocument()
    expect(screen.queryByText(/已运行/)).not.toBeInTheDocument()

    unmountArchive()
    const { unmount } = renderShell({ initialPath: '/tools' })
    expect(screen.queryByText('© 2026')).not.toBeInTheDocument()
    unmount()
    renderShell({ initialPath: '/music/rooms/9' })
    expect(screen.queryByText('© 2026')).not.toBeInTheDocument()
  })

  it('publishes the plain surface tokens and no decorative service background', () => {
    const css = fs.readFileSync(path.join(frontendRoot, 'src', 'index.css'), 'utf8')
    expect(css).toMatch(/--surface-page:\s*#fff/)
    expect(css).toMatch(/--shadow-card:\s*none/)
    expect(css).toMatch(/body::before\s*\{\s*display:\s*none !important/)
  })
})
