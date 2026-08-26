import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import AdminShell from '../src/components/admin/AdminShell.jsx'

function renderShell(path = '/admin/files') {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <Routes>
        <Route path="/admin" element={<AdminShell />}>
          <Route path="files" element={<h1>File workspace</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('responsive administrator shell', () => {
  it('provides the compact administrator navigation and active page state', () => {
    renderShell()

    const navigation = screen.getByRole('navigation', { name: '管理控制台导航' })
    const expectedLinks = [
      ['总览', '/admin'],
      ['用户', '/admin/users'],
      ['文件', '/admin/files'],
      ['直播', '/admin/live'],
      ['曲库账户', '/admin/music'],
      ['服务器状态', '/admin/services'],
    ]
    for (const [name, href] of expectedLinks) {
      expect(within(navigation).getByRole('link', { name })).toHaveAttribute('href', href)
    }
    expect(within(navigation).queryByRole('link', { name: '房间' })).not.toBeInTheDocument()
    expect(within(navigation).getByRole('link', { name: '文件' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getAllByRole('link', { name: '返回首页' })[0]).toHaveAttribute('href', '/')
    expect(screen.getByRole('heading', { name: 'File workspace' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: '管理控制台页签' })).not.toBeInTheDocument()
  })

  it('opens and closes the mobile navigation without losing keyboard semantics', async () => {
    const user = userEvent.setup()
    renderShell()

    const toggle = screen.getByRole('button', { name: '打开管理导航' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const mobileNavigation = screen.getByRole('navigation', { name: '移动管理控制台导航' })
    expect(mobileNavigation).toHaveClass('admin-shell__navigation--open')
    await user.click(within(mobileNavigation).getByRole('link', { name: '文件' }))
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })
})
