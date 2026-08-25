import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

let authState = { isAdmin: true, isAuthenticated: true, loading: false, user: { id: 1 } }

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => authState,
}))
vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn(() => new Promise(() => {})) },
}))
vi.mock('../src/pages/HomePage.jsx', () => ({ default: () => <div>Home page</div> }))
vi.mock('../src/pages/PostsPage.jsx', () => ({ default: () => <div>Writings view</div> }))
vi.mock('../src/pages/PhotosPage.jsx', () => ({ default: () => <div>Photos view</div> }))
vi.mock('../src/pages/LinkDashboard.jsx', () => ({ default: () => <div>Collection dashboard</div> }))
vi.mock('../src/pages/PrivateCollectionPage.jsx', () => ({ default: () => <div>Private collection</div> }))
vi.mock('../src/pages/AccountPage.jsx', () => ({ default: () => <div>Account page</div> }))
vi.mock('../src/pages/PostDetailPage.jsx', () => ({ default: () => <div>Post detail</div> }))
vi.mock('../src/pages/PostEditorPage.jsx', () => ({ default: () => <div>Post editor</div> }))
vi.mock('../src/pages/AdminUsersPage.jsx', () => ({ default: () => <div>Admin users</div> }))
vi.mock('../src/pages/AdminHomepagePage.jsx', () => ({ default: () => <div>Admin homepage</div> }))
vi.mock('../src/pages/AdminRoomsPage.jsx', () => ({ default: () => <div>Admin rooms</div> }))
vi.mock('../src/pages/AdminFilesPage.jsx', () => ({ default: () => <div>Admin files</div> }))
vi.mock('../src/pages/AgentConsolePage.jsx', () => ({ default: () => <div>Server status</div> }))
vi.mock('../src/pages/PhotoManagePage.jsx', () => ({ default: () => <div>Admin photos</div> }))
vi.mock('../src/pages/BackupPage.jsx', () => ({ default: () => <div>Admin backups</div> }))
vi.mock('../src/pages/FrpAdminPage.jsx', () => ({ default: () => <div>Admin FRP</div> }))
vi.mock('../src/pages/ToolsPage.jsx', () => ({ default: () => <div>Tools page</div> }))
vi.mock('../src/pages/MusicLobbyPage.jsx', () => ({ default: () => <div>Music lobby</div> }))

import LegacyRedirect from '../src/components/LegacyRedirect.jsx'
import AppRoutes from '../src/routes.jsx'

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}{location.hash}</output>
}

function renderAppRoute(path) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <AppRoutes styles={{}} isDark={false} />
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('stable public routes', () => {
  beforeEach(() => {
    authState = { isAdmin: true, isAuthenticated: true, loading: false, user: { id: 1 } }
  })

  it('keeps the migrated single-page article flow as the root route', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [] }),
    })
    renderAppRoute('/')
    expect(await screen.findByText('还没有照片。')).toBeInTheDocument()
  })

  it.each([
    ['/archive?type=writing', '归档'],
    ['/archive?type=photo', '归档'],
    ['/collection', '收藏'],
    ['/books', '书籍'],
  ])('renders %s', async (path, content) => {
    renderAppRoute(path)
    expect(await screen.findByText(content)).toBeInTheDocument()
  })

  it.each([
    ['/posts', '/archive?type=writing'],
    ['/photos', '/archive?type=photo'],
    ['/messages', '/#messages'],
    ['/tools/links', '/account/admin/content/collection'],
  ])('redirects legacy %s to %s', async (from, destination) => {
    renderAppRoute(from)
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(destination))
  })

  it('keeps the public tools shell and the authenticated music lobby reachable', async () => {
    renderAppRoute('/tools')
    expect(await screen.findByText('Tools page')).toBeInTheDocument()

    renderAppRoute('/music')
    expect(await screen.findByText('Music lobby')).toBeInTheDocument()
  })

  it.each([
    ['/posts/42', 'Post detail'],
    ['/posts/new', 'Post editor'],
    ['/posts/42/edit', 'Post editor'],
    ['/admin/homepage', 'Admin homepage'],
    ['/admin/users', 'Admin users'],
    ['/account/admin/homepage', 'Admin homepage'],
    ['/account/collection', 'Private collection'],
  ])('keeps %s available', async (path, content) => {
    renderAppRoute(path)
    expect(await screen.findByText(content)).toBeInTheDocument()
  })

  it('can preserve a legacy query and attach a destination hash', async () => {
    render(
      <MemoryRouter initialEntries={['/legacy?from=old']}>
        <Routes>
          <Route path="/legacy" element={<LegacyRedirect to="/target" preserveSearch hash="archive" />} />
          <Route path="/target" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/target?from=old#archive'))
  })

  it.each([
    ['/account/admin/homepage', '/account/admin/content/homepage'],
    ['/admin/users', '/account/admin/users'],
    ['/admin/rooms', '/account/admin/rooms'],
    ['/admin/photos', '/account/admin/content/photos'],
    ['/admin/files', '/account/admin/files'],
    ['/admin/agent-console', '/account/admin/services'],
    ['/tools/backup', '/account/admin/backups'],
    ['/tools/frp', '/account/admin/services/frp'],
    ['/tools/public-sync', '/account/admin/files'],
  ])('redirects administrator legacy path %s to %s', async (from, destination) => {
    renderAppRoute(`${from}?phase10=legacy`)
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(`${destination}?phase10=legacy`))
  })

  it('rejects authenticated non-administrators from the complete administrator shell', async () => {
    authState = { isAdmin: false, isAuthenticated: true, loading: false, user: { id: 2 } }
    renderAppRoute('/account/admin/security')
    expect(await screen.findByRole('heading', { name: '无权访问此页面' })).toBeInTheDocument()
    expect(document.querySelectorAll('main')).toHaveLength(0)
    expect(screen.getByTestId('location')).toHaveTextContent('/account/admin/security')
  })

  it('keeps tools public but protects private content routes', async () => {
    authState = { isAdmin: false, isAuthenticated: false, loading: false, user: null }
    renderAppRoute('/tools')
    expect(await screen.findByText('Tools page')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/tools')

    renderAppRoute('/books?from=tools#recent')
    await waitFor(() => expect(screen.getAllByTestId('location').at(-1)).toHaveTextContent('/login?redirect=%2Fbooks%3Ffrom%3Dtools%23recent'))
  })

  it('preserves the intended administrator path when login is required', async () => {
    authState = { isAdmin: false, isAuthenticated: false, loading: false, user: null }
    renderAppRoute('/account/admin/files?tab=devices')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/login?redirect=%2Faccount%2Fadmin%2Ffiles%3Ftab%3Ddevices'))
  })
})
