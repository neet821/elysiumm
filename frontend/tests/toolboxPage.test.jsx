import { MemoryRouter } from 'react-router-dom'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

let authState
const login = vi.fn()
const requestGet = vi.fn()

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ ...authState, login }),
}))
vi.mock('../src/utils/request.js', () => ({
  default: { get: requestGet },
}))

import ToolsPage from '../src/pages/ToolsPage.jsx'
import { TOOL_ENTRIES } from '../src/pages/toolEntries.js'

const styles = {
  accentClass: 'accent',
  bg: 'background',
  bgSecondary: 'surface',
  border: 'border',
  text: 'text',
  textMuted: 'muted',
}

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <ToolsPage styles={styles} isDark={false} />
    </MemoryRouter>,
  )
}

describe('tools dashboard access', () => {
  beforeEach(() => {
    authState = { isAdmin: false, isAuthenticated: false, user: null }
    login.mockReset()
    requestGet.mockReset()
  })

  it('未登录时只显示两个工具入口，不在卡片下方追加登录区', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: '工具箱' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '欢迎回来' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('用户名或邮箱')).not.toBeInTheDocument()
    const core = within(screen.getByLabelText('两个核心空间'))
    for (const entry of TOOL_ENTRIES) expect(core.getByText(entry.title)).toBeInTheDocument()
    for (const entry of TOOL_ENTRIES) expect(core.getByRole('button', { name: `登录后打开${entry.title}` })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '公开服务' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '协作房间' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '个人内容' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登录后打开收藏' })).toBeInTheDocument()
    expect(requestGet).not.toHaveBeenCalled()
  })

  it('点击工具后在当前单屏弹出登录框，并显示中文失败信息', async () => {
    login.mockResolvedValue({ success: false, message: '账号或密码错误' })
    const user = userEvent.setup()
    renderPage()

    await user.click(within(screen.getByLabelText('两个核心空间')).getByRole('button', { name: '登录后打开同步观影' }))
    expect(screen.getByRole('dialog', { name: '登录后打开工具箱' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('用户名或邮箱'), 'reader@example.com')
    await user.type(screen.getByLabelText('密码'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: '显示密码' }))
    expect(screen.getByLabelText('密码')).toHaveAttribute('type', 'text')
    await user.click(screen.getByRole('button', { name: '登录并打开工具箱' }))

    expect(login).toHaveBeenCalledWith('reader@example.com', 'wrong-password')
    expect(await screen.findByRole('alert')).toHaveTextContent('账号或密码错误')
  })

  it('shows exactly two core destinations to signed-in users without personal admin tools', () => {
    authState = { isAdmin: false, isAuthenticated: true, user: { id: 7, username: 'reader' } }
    renderPage()

    const destinations = TOOL_ENTRIES.map((entry) => [entry.title, entry.to])
    expect(destinations).toEqual([
      ['同步观影', '/rooms/watch'],
      ['同步听歌', '/rooms/music'],
    ])
    for (const [title, to] of destinations) {
      expect(screen.getByRole('link', { name: new RegExp(`打开${title}`) })).toHaveAttribute('href', to)
    }
    expect(screen.getByRole('heading', { name: '公开服务' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '协作房间' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '个人内容' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /打开收藏|收藏/ })).toHaveAttribute('href', '/collection')
    expect(screen.getByLabelText('两个核心空间').querySelectorAll('.toolbox-portal')).toHaveLength(2)
    expect(screen.queryByRole('heading', { name: '登录后继续' })).not.toBeInTheDocument()
  })
})
