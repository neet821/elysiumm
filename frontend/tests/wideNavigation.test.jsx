import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { applicationStyles } from './applicationStyles.mjs'

let authState = { isAdmin: true, isAuthenticated: true, user: { id: 1, username: 'neet821', avatar_url: '/avatar.png' } }

vi.mock('../src/contexts/AuthContext.jsx', () => ({ useAuth: () => authState }))

import { AppShell } from '../src/components/layout/AppShell.jsx'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function renderShell(initialPath) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppShell><h1>Page content</h1></AppShell>
    </MemoryRouter>,
  )
}

describe('shared labelled navigation shell', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    authState = { isAdmin: true, isAuthenticated: true, user: { id: 1, username: 'neet821', avatar_url: '/avatar.png' } }
  })

  it.each(['/rooms/watch', '/rooms/music', '/live', '/account', '/admin/homepage'])('mounts shared navigation on %s', (pathName) => {
    renderShell(pathName)

    const navigation = screen.getByRole('navigation', { name: '首页导航' })
    expect(navigation.querySelector('.home-nav__action--home')).toHaveAttribute('href', '/')
    expect(within(navigation).getByRole('link', { name: '观影房' })).toHaveAttribute('href', '/rooms/watch')
    expect(within(navigation).getByRole('link', { name: '听歌房' })).toHaveAttribute('href', '/rooms/music')
    expect(within(navigation).getByRole('link', { name: '直播' })).toHaveAttribute('href', '/live')
    expect(within(navigation).getByRole('link', { name: '打开管理员控制台' })).toHaveAttribute('href', '/admin/homepage')
    expect(within(navigation).getByRole('img', { name: 'neet821' })).toHaveAttribute('src', '/avatar.png')
  })

  it('keeps route navigation real instead of switching an embedded homepage view', () => {
    const source = fs.readFileSync(path.join(frontendRoot, 'src', 'pages', 'ArticleFlowHome.jsx'), 'utf8')
    expect(source).not.toMatch(/wideView|useWideHomeViewport|home-wide-view|WideWatchPage|WideMusicPage/)
    expect(source).not.toMatch(/<WideLivePage/)
  })

  it('uses one room page wrapper without an embedded presentation branch', () => {
    const roomSource = fs.readFileSync(path.join(frontendRoot, 'src', 'pages', 'SyncRoomList.jsx'), 'utf8')
    const musicSource = fs.readFileSync(path.join(frontendRoot, 'src', 'pages', 'MusicLobbyPage.jsx'), 'utf8')
    expect(roomSource).not.toMatch(/embedded/)
    expect(musicSource).not.toMatch(/embedded/)
  })

  it('keeps the route-back action compact and does not use viewport-specific rail rules', () => {
    const css = applicationStyles
    expect(css).toMatch(/\.app-shell--wide-navigation \.route-back-button\s*\{[^}]*display:\s*none/s)
    expect(css).toMatch(/\.route-back-button\s*\{[^}]*height:\s*44px;[\s\S]*?width:\s*44px/s)
    expect(css).not.toMatch(/home-nav-rail-width|@media \(min-width:\s*1101px\)/)
  })

  it('styles one labelled top navigation on the shared content canvas', () => {
    const css = fs.readFileSync(path.join(frontendRoot, 'src', 'components', 'layout', 'homeNavigation.css'), 'utf8')
    expect(css).toMatch(/\.home-nav\s*\{[^}]*max-width:\s*1200px;[\s\S]*?min-height:\s*76px/s)
    expect(css).toMatch(/\.home-nav__action-label\s*\{[^}]*display:\s*inline/s)
    expect(css).toMatch(/\.home-nav__action\s*\{[^}]*min-height:\s*44px;[\s\S]*?min-width:\s*44px/s)
    expect(css).not.toMatch(/position:\s*fixed|home-nav-rail-width|backdrop-filter|linear-gradient|radial-gradient/)
  })

  it('uses semantic tokens for normal and live navigation states', () => {
    const css = fs.readFileSync(path.join(frontendRoot, 'src', 'components', 'layout', 'homeNavigation.css'), 'utf8')
    expect(css).toMatch(/\.home-nav__action\s*\{[^}]*color:\s*var\(--text-secondary\)/s)
    expect(css).toMatch(/\.home-nav__action--active\s*\{[^}]*color:\s*var\(--accent-blue\)/s)
    expect(css).toMatch(/\.home-nav__action--live-active\s*\{[^}]*color:\s*var\(--accent-blue\)/s)
  })
})
