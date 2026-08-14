import { MemoryRouter } from 'react-router-dom'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

let authState = {
  isAdmin: false,
  isAuthenticated: true,
  user: { id: 7, username: 'Test User', avatar_url: null },
}

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => authState,
}))

import { AppShell } from '../src/components/layout/AppShell.jsx'
import { PUBLIC_NAV_ITEMS } from '../src/components/Header.jsx'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function renderShell({ initialPath = '/archive', isDark = false, toggleTheme = vi.fn() } = {}) {
  return {
    toggleTheme,
    ...render(
      <MemoryRouter initialEntries={[initialPath]} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <AppShell isDark={isDark} toggleTheme={toggleTheme}>
          <h1>Page content</h1>
        </AppShell>
      </MemoryRouter>,
    ),
  }
}

describe('Blue Album app shell', () => {
  beforeEach(() => {
    authState = {
      isAdmin: false,
      isAuthenticated: true,
      user: { id: 7, username: 'Test User', avatar_url: null },
    }
  })

  it('renders the signed-in Chinese navigation in the approved order', () => {
    authState = {
      isAdmin: false,
      isAuthenticated: true,
      user: { id: 7, username: 'Test User', avatar_url: null },
    }
    renderShell()
    const primaryNav = screen.getByRole('navigation', { name: '主导航' })
    const labels = within(primaryNav).getAllByRole('link').map((link) => link.getAttribute('aria-label'))

    expect(PUBLIC_NAV_ITEMS.map((item) => item.label)).toEqual([
      '归档',
      '工具箱',
      '账户',
    ])
    expect(labels).toEqual(['归档', '工具箱', 'Test User'])
    expect(within(primaryNav).queryByRole('link', { name: '首页' })).not.toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: 'Test User' })).toHaveTextContent('')
  })

  it('shows tools and login to signed-out visitors without exposing account navigation', () => {
    authState = { isAdmin: false, isAuthenticated: false, user: null }
    renderShell()
    const primaryNav = screen.getByRole('navigation', { name: '主导航' })

    expect(within(primaryNav).getAllByRole('link').map((link) => link.textContent.trim())).toEqual([
      '归档',
      '工具箱',
      '登录',
    ])
    expect(within(primaryNav).queryByText('账户')).not.toBeInTheDocument()
  })

  it('uses the approved logo as home and marks the active destination', () => {
    authState = {
      isAdmin: false,
      isAuthenticated: true,
      user: { id: 7, username: 'Test User', avatar_url: null },
    }
    renderShell({ initialPath: '/archive?type=photo' })
    const brandLink = screen.getByRole('link', { name: 'Blue Album 首页' })
    const brandImage = brandLink.querySelector('img')

    expect(brandLink).toHaveAttribute('href', '/')
    expect(brandImage).toHaveAttribute('src', '/brand/blue-album-logo-color.svg')
    expect(brandImage).toHaveAttribute('alt', '')
    expect(within(brandLink).getByText('Blue Album')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '归档' })).toHaveAttribute('aria-current', 'page')
    const accountLink = screen.getByRole('link', { name: 'Test User' })
    expect(accountLink).toContainElement(within(accountLink).getByRole('img', { name: 'Test User' }))
    expect(accountLink).toHaveAttribute('title', '账户')
  })

  it('首页交由独立首屏处理并隐藏全站顶栏', () => {
    authState = { isAdmin: false, isAuthenticated: false, user: null }
    renderShell({ initialPath: '/' })

    const header = document.querySelector('.app-header')
    const shell = document.querySelector('.app-shell')
    expect(shell).toHaveClass('app-shell--home')
    expect(header).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: '主导航' })).not.toBeInTheDocument()
    expect(screen.queryByText('© 2026 Blue Album')).not.toBeInTheDocument()
  })

  it('opens an accessible mobile drawer and closes it after navigation', async () => {
    const user = userEvent.setup()
    authState = {
      isAdmin: false,
      isAuthenticated: true,
      user: { id: 7, username: 'Test User', avatar_url: null },
    }
    renderShell()
    await user.click(screen.getByRole('button', { name: '打开导航' }))
    const drawer = screen.getByRole('dialog', { name: '导航' })
    expect(drawer).toHaveAttribute('aria-modal', 'true')
    expect(within(drawer).getByRole('navigation', { name: '移动导航' })).toBeInTheDocument()

    await user.click(within(drawer).getByRole('link', { name: '工具箱' }))
    expect(screen.queryByRole('dialog', { name: '导航' })).not.toBeInTheDocument()
  })

  it('forwards the theme click and opens the command palette with Ctrl+K', async () => {
    const toggleTheme = vi.fn()
    const user = userEvent.setup()
    renderShell({ toggleTheme })

    await user.click(screen.getByRole('button', { name: '切换到深色模式' }))
    expect(toggleTheme).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(screen.getByRole('dialog', { name: '快捷导航' })).toBeInTheDocument()
  })

  it('renders a skip link and the required 2026 footer metadata', () => {
    renderShell({ isDark: true })

    expect(screen.getByRole('link', { name: '跳到主要内容' })).toHaveAttribute('href', '#main-content')
    expect(screen.getByText('© 2026 Blue Album')).toBeInTheDocument()
    expect(screen.getByText('深色模式')).toBeInTheDocument()
    expect(screen.getByText(/^已运行 /)).toHaveAttribute('datetime', '2025-12-10T00:00:00')
  })

  it('工具箱隐藏页脚，听歌房同时隐藏外层顶栏和页脚', () => {
    const toolbox = renderShell({ initialPath: '/tools' })
    expect(screen.queryByText('© 2026 Blue Album')).not.toBeInTheDocument()
    toolbox.unmount()

    renderShell({ initialPath: '/music/rooms/9' })
    expect(screen.queryByRole('link', { name: 'Blue Album 首页' })).not.toBeInTheDocument()
    expect(screen.queryByText('© 2026 Blue Album')).not.toBeInTheDocument()
  })

  it('keeps focus visible, mobile controls touch-sized, and reduced motion quiet', () => {
    const css = fs.readFileSync(path.join(frontendRoot, 'src', 'index.css'), 'utf8')

    expect(css).toMatch(/button:focus-visible[\s\S]*?outline:\s*3px/)
    expect(css).toMatch(/@media \(max-width: 840px\)[\s\S]*?\.app-header__menu\s*\{[\s\S]*?height:\s*2\.75rem;[\s\S]*?width:\s*2\.75rem;/)
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.app-background::before[\s\S]*?animation:\s*none/)
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*?::view-transition-new\(root\)[\s\S]*?animation-duration:\s*0\.001ms/)
  })
})
