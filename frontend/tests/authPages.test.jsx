import fs from 'node:fs'

import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ login: vi.fn(), register: vi.fn() }),
}))

import LoginCard from '../src/components/auth/LoginCard.jsx'

describe('authentication form layout', () => {
  it('reserves a dedicated leading-icon gutter in both login fields', () => {
    render(
      <MemoryRouter>
        <LoginCard />
      </MemoryRouter>,
    )

    expect(screen.getByLabelText('用户名或邮箱')).toHaveClass('auth-form-field__input', 'auth-form-field__input--leading')
    expect(screen.getByLabelText('密码')).toHaveClass('auth-form-field__input', 'auth-form-field__input--leading', 'auth-form-field__input--password')
  })

  it('locks login and registration pages to the viewport without page scrolling', () => {
    const css = fs.readFileSync('src/index.css', 'utf8')
    expect(css).toMatch(/\.service-shell:has\(\.auth-page\)\s*\{[^}]*height:\s*100dvh;[^}]*overflow:\s*hidden;/s)
    expect(css).toMatch(/\.service-shell:has\(\.auth-page\) \.app-shell__main\s*\{[^}]*height:\s*100%;[^}]*overflow:\s*hidden;/s)
    expect(css).toMatch(/\.auth-page\s*\{[^}]*box-sizing:\s*border-box;[^}]*height:\s*100%;[^}]*overflow:\s*hidden;/s)
  })
})
