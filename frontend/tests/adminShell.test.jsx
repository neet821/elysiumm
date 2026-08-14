import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import AdminShell from '../src/components/admin/AdminShell.jsx'

function renderShell(path = '/account/admin/files') {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <Routes>
        <Route path="/account/admin" element={<AdminShell />}>
          <Route path="files" element={<h1>File workspace</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('canonical administrator shell', () => {
  it('provides one labelled navigation with every canonical administration area', () => {
    renderShell()

    const navigation = screen.getByRole('navigation', { name: '管理导航' })
    const expectedLinks = [
      ['总览', '/account/admin'],
      ['首页', '/account/admin/content/homepage'],
      ['文章', '/archive?type=writing'],
      ['收藏', '/account/admin/content/collection'],
      ['书籍', '/account/admin/content/books'],
      ['照片', '/account/admin/content/photos'],
      ['用户', '/account/admin/users'],
      ['房间', '/account/admin/rooms'],
      ['文件', '/account/admin/files'],
      ['服务状态', '/account/admin/services'],
      ['FRP', '/account/admin/services/frp'],
      ['备份', '/account/admin/backups'],
      ['安全', '/account/admin/security'],
    ]
    for (const [name, href] of expectedLinks) {
      expect(screen.getByRole('link', { name })).toHaveAttribute('href', href)
    }
    expect(screen.getByRole('link', { name: '文件' })).toHaveAttribute('aria-current', 'page')
    expect(navigation).toContainElement(screen.getByRole('link', { name: '安全' }))
    expect(screen.getByRole('heading', { name: 'File workspace' })).toBeInTheDocument()
  })

  it('opens and closes its compact navigation without losing keyboard semantics', async () => {
    const user = userEvent.setup()
    renderShell()

    const toggle = screen.getByRole('button', { name: '打开管理导航' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('navigation', { name: '管理导航' })).toHaveClass('admin-shell__navigation--open')
    await user.click(screen.getByRole('link', { name: '文件' }))
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })
})
