import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

let authState = { isAuthenticated: false, isAdmin: false, loading: false, user: null }

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => authState,
}))
vi.mock('../src/pages/PrivateCollectionPage.jsx', () => ({
  default: () => <div>Protected private collection</div>,
}))
vi.mock('../src/pages/LoginPage.jsx', () => ({
  default: () => <div>Login page</div>,
}))

import AppRoutes from '../src/routes.jsx'

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderRoute() {
  return render(
    <MemoryRouter
      initialEntries={['/account/collection']}
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <AppRoutes styles={{}} isDark={false} />
      <LocationProbe />
    </MemoryRouter>,
  )
}

afterEach(() => {
  authState = { isAuthenticated: false, isAdmin: false, loading: false, user: null }
  window.localStorage.clear()
})

describe('private Collection route protection', () => {
  it('sends anonymous visitors to login with the complete return path', async () => {
    renderRoute()
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(
      '/login?redirect=%2Faccount%2Fcollection',
    ))
    expect(screen.queryByText('Protected private collection')).not.toBeInTheDocument()
  })

  it('denies the workspace to an authenticated non-administrator', async () => {
    authState = { isAuthenticated: true, isAdmin: false, loading: false, user: { id: 7 } }
    renderRoute()
    expect(await screen.findByRole('heading', { name: '无权访问此页面' })).toBeInTheDocument()
    expect(screen.queryByText('Protected private collection')).not.toBeInTheDocument()
  })

  it('redirects an administrator to the canonical collection workspace', async () => {
    authState = { isAuthenticated: true, isAdmin: true, loading: false, user: { id: 1 } }
    renderRoute()
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(
      '/account/admin/content/collection',
    ))
    expect(await screen.findByText('Protected private collection')).toBeInTheDocument()
  })
})
