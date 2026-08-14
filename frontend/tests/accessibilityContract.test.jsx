import { readFileSync } from 'node:fs'
import path from 'node:path'
import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ErrorBoundary from '../src/components/ErrorBoundary.jsx'
import { AppShell } from '../src/components/layout/AppShell.jsx'

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ user: null }),
}))

afterEach(() => {
  vi.restoreAllMocks()
})

describe('application accessibility contract', () => {
  it('provides one named main region, a skip link and named navigation controls', () => {
    render(
      <MemoryRouter initialEntries={['/archive']}>
        <AppShell isDark={false} toggleTheme={() => {}}>
          <h1>Acceptance fixture</h1>
        </AppShell>
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: '跳到主要内容' })).toHaveAttribute('href', '#main-content')
    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content')
    expect(screen.getByRole('main')).toHaveAttribute('tabindex', '-1')
    expect(screen.getByRole('navigation', { name: '主导航' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /切换到/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '打开导航' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('shows a generic named alert without disclosing runtime details', () => {
    const boundary = new ErrorBoundary({ children: null })
    boundary.state = { hasError: true, error: new Error('database-password=do-not-display') }
    render(boundary.render())

    expect(screen.getByRole('alert')).toHaveAccessibleName('页面暂时不可用')
    expect(screen.getByRole('heading', { name: '页面暂时不可用' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument()
    expect(screen.queryByText(/database-password/)).not.toBeInTheDocument()
  })

  it('keeps visible focus and reduced-motion fallbacks in the production stylesheet', () => {
    const css = readFileSync(path.join(process.cwd(), 'src/index.css'), 'utf8')
    expect(css).toMatch(/:focus-visible\s*\{[\s\S]*?outline:/)
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*?--motion-normal:\s*0ms/)
    expect(css).toMatch(/\.route-loading__spinner\s*\{\s*animation:\s*none/)
  })
})
