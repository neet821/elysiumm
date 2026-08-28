import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

describe('shared wide navigation shell', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    authState = { isAdmin: true, isAuthenticated: true, user: { id: 1, username: 'neet821', avatar_url: '/avatar.png' } }
  })

  it.each(['/rooms/watch', '/rooms/music', '/live'])('mounts the same navigation on %s as on the homepage', (pathName) => {
    renderShell(pathName)

    const navigation = screen.getByRole('navigation', { name: '首页导航' })
    expect(navigation.querySelector('.home-nav__action--home')).toHaveAttribute('href', '/')
    expect(within(navigation).getByRole('link', { name: '观影房' })).toHaveAttribute('href', '/rooms/watch')
    expect(within(navigation).getByRole('link', { name: '听歌房' })).toHaveAttribute('href', '/rooms/music')
    expect(within(navigation).getByRole('link', { name: '直播' })).toHaveAttribute('href', '/live')
    expect(within(navigation).getByRole('link', { name: '打开管理员控制台' })).toHaveAttribute('href', '/admin/homepage')
    expect(screen.getByTestId('home-identity')).toHaveTextContent('neet821')
  })

  it('keeps route navigation real instead of switching an embedded homepage view', () => {
    const source = fs.readFileSync(path.join(frontendRoot, 'src', 'pages', 'ContentHomePage.jsx'), 'utf8')
    expect(source).not.toMatch(/wideView|useWideHomeViewport|home-wide-view|WideWatchPage|WideMusicPage/)
    expect(source).not.toMatch(/<WideLivePage/)
  })

  it('uses one room page wrapper without an embedded presentation branch', () => {
    const roomSource = fs.readFileSync(path.join(frontendRoot, 'src', 'pages', 'SyncRoomList.jsx'), 'utf8')
    const musicSource = fs.readFileSync(path.join(frontendRoot, 'src', 'pages', 'MusicLobbyPage.jsx'), 'utf8')
    expect(roomSource).not.toMatch(/embedded/)
    expect(musicSource).not.toMatch(/embedded/)
  })

  it('keeps the back link for compact layouts and hides it only in the wide shell', () => {
    const css = fs.readFileSync(path.join(frontendRoot, 'src', 'index.css'), 'utf8')
    expect(css).toMatch(/@media \(min-width:\s*1101px\)[\s\S]*?\.app-shell--wide-navigation \.route-back-button\s*\{[^}]*display:\s*none/s)
    expect(css).toMatch(/@media \(max-width:\s*1100px\)[\s\S]*?\.app-shell--wide-navigation \.route-back-button\s*\{[^}]*display:\s*flex/s)
  })

  it('styles the shared wide rail with a square avatar and no burgundy surface', () => {
    const css = fs.readFileSync(path.join(frontendRoot, 'src', 'pages', 'contentHome.css'), 'utf8')
    expect(css).toMatch(/\.home-nav--global[\s\S]*?\.home-nav__identity-avatar[\s\S]*?border-radius:\s*0/s)
    expect(css).toMatch(/\.home-nav--global[\s\S]*?\.home-nav__admin-action[\s\S]*?margin-top:\s*auto/s)
    expect(css).not.toMatch(/\.home-nav--global[^}]*#(?:6e|7a|8b|9a)[0-9a-f]{4,6}/i)
  })
})
