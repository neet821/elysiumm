import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

let authState = { isAuthenticated: false, isAdmin: false, loading: false, user: null }

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => authState,
}))
vi.mock('../src/pages/AdminFilesPage.jsx', () => ({
  default: () => <div>Admin files</div>,
}))

import AppRoutes from '../src/routes.jsx'

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderRoute(path = '/admin/files') {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  )
}

afterEach(() => {
  authState = { isAuthenticated: false, isAdmin: false, loading: false, user: null }
})

describe('administrator route protection', () => {
  it('sends anonymous visitors to login with the complete return path', async () => {
    renderRoute('/admin/files?tab=devices')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(
      '/login?redirect=%2Fadmin%2Ffiles%3Ftab%3Ddevices',
    ))
  })

  it('denies the administrator workspace to an authenticated non-administrator', async () => {
    authState = { isAuthenticated: true, isAdmin: false, loading: false, user: { id: 7 } }
    renderRoute()
    expect(await screen.findByRole('heading', { name: '无权访问此页面' })).toBeInTheDocument()
  })

  it('renders the canonical administrator Files workspace for an administrator', async () => {
    authState = { isAuthenticated: true, isAdmin: true, loading: false, user: { id: 1 } }
    renderRoute()
    expect(await screen.findByText('Admin files')).toBeInTheDocument()
  })

  it('does not revive the removed private Collection route', async () => {
    authState = { isAuthenticated: true, isAdmin: true, loading: false, user: { id: 1 } }
    renderRoute('/account/collection')
    expect(await screen.findByRole('heading', { name: '这个页面不存在' })).toBeInTheDocument()
  })
})
