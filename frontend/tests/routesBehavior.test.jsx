import { MemoryRouter, Outlet, useLocation } from 'react-router-dom'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'

let authState = { isAdmin: true, isAuthenticated: true, loading: false, user: { id: 1 } }

vi.mock('../src/contexts/AuthContext.jsx', () => ({ useAuth: () => authState }))
vi.mock('../src/components/admin/AdminShell.jsx', () => ({ default: () => <Outlet /> }))
vi.mock('../src/pages/AdminHomepagePage.jsx', () => ({ default: () => <div>Admin homepage</div> }))
vi.mock('../src/pages/AdminFilesPage.jsx', () => ({ default: () => <div>Admin files</div> }))
vi.mock('../src/pages/AgentConsolePage.jsx', () => ({ default: () => <div>Server status</div> }))
vi.mock('../src/pages/AdminUsersPage.jsx', () => ({ default: () => <div>Admin users</div> }))
vi.mock('../src/pages/MusicProvidersAdminPage.jsx', () => ({ default: () => <div>Music providers</div> }))
vi.mock('../src/pages/SyncRoomList.jsx', () => ({ default: () => <div>Shared room list</div> }))
vi.mock('../src/pages/MineradioPage.jsx', () => ({ default: () => <div>Music room</div> }))
vi.mock('../src/pages/SyncRoomPlayer.jsx', () => ({ default: () => <div>Watch room</div> }))
vi.mock('../src/pages/LivePage.jsx', () => ({ default: () => <div>Live page</div> }))
vi.mock('../src/pages/LoginPage.jsx', () => ({ default: () => <div>Login page</div> }))
vi.mock('../src/pages/RegisterPage.jsx', () => ({ default: () => <div>Register page</div> }))

import AppRoutes from '../src/routes.jsx'
import { isTransferHost } from '../src/config.js'

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}{location.hash}</output>
}

function renderAppRoute(path) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('current route contract', () => {
  beforeEach(() => {
    authState = { isAdmin: true, isAuthenticated: true, loading: false, user: { id: 1 } }
  })

  it('recognizes the fixed transfer host as the administrator inbox host', () => {
    expect(isTransferHost('send.elysiumm.top')).toBe(true)
    expect(isTransferHost('elysiumm.top')).toBe(false)
  })

  it('does not turn arbitrary main-site paths into transfer links', async () => {
    renderAppRoute('/not-a-transfer-token')
    expect(await screen.findByRole('heading', { name: '这个页面不存在' })).toBeInTheDocument()
  })

  it('keeps the current public, room, live, and administrator routes', () => {
    const source = readFileSync('src/routes.jsx', 'utf8')
    for (const path of ['/content/*', '/rooms/music', '/rooms/watch', '/live', '/admin/*']) {
      expect(source).toContain(`path="${path}"`)
    }
    for (const path of ['homepage', 'users', 'rooms', 'files', 'music', 'services']) {
      expect(source).toContain(`path="${path}"`)
    }
    expect(source).not.toContain('AdminOverviewPage')
    expect(source).not.toContain('AdminLivePage')
    expect(source).not.toContain('GamesPage')
  })

  it('redirects the remaining legacy room links to the shared room pages', async () => {
    renderAppRoute('/music')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/rooms/music'))

    renderAppRoute('/tools/sync-room')
    await waitFor(() => expect(screen.getAllByTestId('location').at(-1)).toHaveTextContent('/rooms/watch'))
  })

  it('redirects the administrator index to homepage settings', async () => {
    renderAppRoute('/admin')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/admin/homepage'))
    expect(await screen.findByText('Admin homepage')).toBeInTheDocument()
  })

  it('protects administrator routes for anonymous users and non-administrators', async () => {
    authState = { isAdmin: false, isAuthenticated: false, loading: false, user: null }
    renderAppRoute('/admin/files?tab=devices')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/login?redirect=%2Fadmin%2Ffiles%3Ftab%3Ddevices'))

    authState = { isAdmin: false, isAuthenticated: true, loading: false, user: { id: 2 } }
    renderAppRoute('/admin/files')
    expect(await screen.findByRole('heading', { name: '无权访问此页面' })).toBeInTheDocument()
  })

  it('renders the retained room and live destinations', async () => {
    renderAppRoute('/rooms/watch')
    expect(await screen.findByText('Shared room list')).toBeInTheDocument()

    renderAppRoute('/live')
    expect(await screen.findByText('Live page')).toBeInTheDocument()
  })
})
