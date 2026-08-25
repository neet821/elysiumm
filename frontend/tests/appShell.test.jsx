import { MemoryRouter } from 'react-router-dom'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen, within } from '@testing-library/react'
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

  it('places the mobile sidebar control in the homepage top bar', async () => {
    const user = userEvent.setup()
    renderShell({ initialPath: '/' })

    const toggle = screen.getByRole('button', { name: '展开记录和随笔' })
    expect(toggle.closest('header')).toBe(screen.getByRole('banner'))
    await user.click(toggle)
    expect(screen.getByRole('button', { name: '收起记录和随笔' })).toBeInTheDocument()
  })

  it('renders the configured custom text in the desktop homepage top bar', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ settings: { hero_prefix: '我的顶栏文字' } }),
    })

    renderShell({ initialPath: '/' })

    const label = await screen.findByText('我的顶栏文字')
    expect(screen.getByRole('banner')).toContainElement(label)
  })

  it('shows login instead of account to signed-out visitors', () => {
    authState = { isAdmin: false, isAuthenticated: false, user: null }
    renderShell()
    expect(screen.getByRole('banner')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '主导航' })).toBeInTheDocument()
  })

  it('routes every authenticated avatar to the user account', () => {
    const { unmount } = renderShell({ initialPath: '/' })
    expect(screen.getByRole('link', { name: '账户' })).toHaveAttribute('href', '/account')

    unmount()
    authState = { isAdmin: true, isAuthenticated: true, user: { id: 1, username: 'Admin', avatar_url: null } }
    renderShell({ initialPath: '/' })
    expect(screen.getByRole('link', { name: '账户' })).toHaveAttribute('href', '/account')
  })

  it('keeps the administrator route free of public chrome', () => {
    renderShell({ initialPath: '/admin' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.queryByRole('contentinfo')).not.toBeInTheDocument()
  })

  it('keeps icon-only home navigation and restores the admin control entry', () => {
    const { unmount } = renderShell({ initialPath: '/archive?type=photo' })
    expect(screen.getByRole('banner')).toBeInTheDocument()

    unmount()
    renderShell({ initialPath: '/' })
    expect(document.querySelector('.app-shell')).toHaveClass('app-shell--home')
    expect(screen.getByRole('banner')).toBeInTheDocument()
    const homeNav = screen.getByRole('navigation', { name: '主导航' })
    expect(within(homeNav).getByRole('link', { name: '房间' })).toBeInTheDocument()
    expect(within(homeNav).getByRole('link', { name: '直播' })).toBeInTheDocument()
    expect(within(homeNav).getByRole('link', { name: '账户' })).toBeInTheDocument()
    expect(homeNav.querySelectorAll('.app-header__action > span')).toHaveLength(0)
    expect(screen.queryByText('© 2026 Elysium')).not.toBeInTheDocument()

    unmount()
    authState = { isAdmin: true, isAuthenticated: true, user: { id: 1, username: 'Admin', avatar_url: null } }
    renderShell({ initialPath: '/' })
    const adminLink = screen.getByRole('link', { name: '打开管理员控制台' })
    expect(adminLink).toHaveAttribute('href', '/admin')
    const roomLink = within(adminLink.closest('nav')).getByRole('link', { name: '房间' })
    expect(adminLink.compareDocumentPosition(roomLink) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('keeps formal pages free of current-page and theme controls', () => {
    renderShell()
    expect(screen.queryByRole('button', { name: /切换到/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '打开导航' })).not.toBeInTheDocument()
  })

  it('removes global chrome from the article reader and branding from rooms', () => {
    const { unmount } = renderShell({ initialPath: '/article/hello' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.queryByRole('contentinfo')).not.toBeInTheDocument()

    unmount()
    renderShell({ initialPath: '/rooms/music/9' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '返回首页' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Elysium/i)).not.toBeInTheDocument()
    expect(screen.queryByText('© 2026 Elysium')).not.toBeInTheDocument()

    unmount()
    renderShell({ initialPath: '/account' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '返回首页' })).toHaveAttribute('href', '/')
  })

  it('keeps login and registration pages free of the global top bar', () => {
    const { unmount } = renderShell({ initialPath: '/login' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()

    unmount()
    renderShell({ initialPath: '/register' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
  })

  it('uses only the home arrow on the room hub and live page', () => {
    const { unmount } = renderShell({ initialPath: '/rooms' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '返回首页' })).toHaveAttribute('href', '/')

    unmount()
    renderShell({ initialPath: '/live' })
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '返回首页' })).toHaveAttribute('href', '/')
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
    expect(screen.queryByText('© 2026 Elysium')).not.toBeInTheDocument()
  })

  it('publishes the plain surface tokens and no decorative service background', () => {
    const css = fs.readFileSync(path.join(frontendRoot, 'src', 'index.css'), 'utf8')
    expect(css).toMatch(/--surface-page:\s*#fff/)
    expect(css).toMatch(/--shadow-card:\s*none/)
    expect(css).toMatch(/body::before\s*\{\s*display:\s*none !important/)
  })
})
