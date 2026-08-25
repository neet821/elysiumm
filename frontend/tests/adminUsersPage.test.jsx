import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn() },
}))

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ user: { id: 1, role: 'admin' } }),
}))

import AdminUsersPage from '../src/pages/AdminUsersPage.jsx'
import apiClient from '../src/utils/request.js'

describe('administrator user list', () => {
  beforeEach(() => {
    apiClient.get.mockResolvedValue({
      data: [{ id: 2, username: 'member', email: 'member@example.com', avatar: '/uploads/very-tall-photo.jpg', role: 'user' }],
    })
  })

  it('keeps uploaded avatars on the compact user-cell surface', async () => {
    render(<MemoryRouter><AdminUsersPage /></MemoryRouter>)

    const avatar = await screen.findByAltText('member')
    expect(avatar).toHaveClass('ui-avatar__image')
    expect(avatar.closest('.ui-avatar')).toHaveClass('admin-user-cell__avatar')
  })
})
