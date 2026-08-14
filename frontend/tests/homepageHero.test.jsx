import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn() },
}))

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ isAuthenticated: false, user: null }),
}))

import HomePage from '../src/pages/HomePage.jsx'
import apiClient from '../src/utils/request.js'

function renderHome() {
  return render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <HomePage />
    </MemoryRouter>,
  )
}

describe('Elysium 首页模式', () => {
  beforeEach(() => {
    apiClient.get.mockReset()
    globalThis.localStorage?.setItem('elysium-room-mode', 'lite')
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })))
  })

  afterEach(() => {
    globalThis.localStorage?.removeItem('elysium-room-mode')
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('默认使用三维模式，并记住手动切换到轻量模式', async () => {
    globalThis.localStorage?.removeItem('elysium-room-mode')
    renderHome()

    const experience = screen.getByTestId('home-experience')
    expect(experience).toHaveAttribute('data-room-mode', '3d')
    const switchButton = screen.getByRole('button', { name: '切换到轻量模式' })
    await userEvent.setup().click(switchButton)
    expect(screen.getByTestId('home-experience')).toHaveAttribute('data-room-mode', 'lite')
    expect(globalThis.localStorage?.getItem('elysium-room-mode')).toBe('lite')
  })

  it('首页只展示窗前书桌，不再请求旧首页内容', async () => {
    renderHome()

    const room = await screen.findByRole('region', { name: '窗前书桌房间' })
    expect(room).toBeInTheDocument()
    expect(within(room).getByRole('img', { name: '分格窗前的温馨书桌' })).toBeInTheDocument()
    expect(screen.queryByText('Blue Album')).not.toBeInTheDocument()
    expect(document.querySelector('.home-masonry')).not.toBeInTheDocument()
    expect(apiClient.get).not.toHaveBeenCalled()
  })

  it('电脑展开后提供直播、音乐和工具箱入口，Esc 可以返回房间', async () => {
    const user = userEvent.setup()
    renderHome()

    await user.click(await screen.findByRole('button', { name: '打开电脑' }))
    const desktop = screen.getByRole('dialog', { name: '电脑桌面' })
    expect(within(desktop).getByRole('link', { name: '看直播' })).toHaveAttribute('href', '/live')
    expect(within(desktop).getByRole('link', { name: '听音乐' })).toHaveAttribute('href', '/music')
    expect(within(desktop).getByRole('link', { name: '工具箱' })).toHaveAttribute('href', '/tools')

    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '电脑桌面' })).not.toBeInTheDocument())
    await waitFor(() => expect(screen.getByRole('button', { name: '打开电脑' })).toHaveFocus())
  })

  it('时间和天气预览会更新房间环境说明', async () => {
    const user = userEvent.setup()
    renderHome()

    const controls = await screen.findByRole('group', { name: '房间环境预览' })
    await user.click(within(controls).getByRole('button', { name: '夜晚' }))
    await user.click(within(controls).getByRole('button', { name: '雨' }))

    expect(screen.getByRole('status', { name: '当前房间环境' })).toHaveTextContent('夜晚 · 雨')
    expect(roomState()).toEqual({ time: 'night', weather: 'rain' })
  })

  it('窗外可以在松林、城市和云山之间切换', async () => {
    const user = userEvent.setup()
    renderHome()

    const views = await screen.findByRole('group', { name: '窗外风景' })
    await user.click(within(views).getByRole('button', { name: '城市' }))
    expect(screen.getByRole('region', { name: '窗前书桌房间' })).toHaveAttribute('data-view', 'city')

    await user.click(within(views).getByRole('button', { name: '云山' }))
    expect(screen.getByRole('region', { name: '窗前书桌房间' })).toHaveAttribute('data-view', 'mountains')
  })

  it('减少动态效果时固定使用备用画面并关闭视线漂移', async () => {
    vi.stubGlobal('matchMedia', vi.fn((query) => ({
      matches: query.includes('prefers-reduced-motion'),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })))
    renderHome()

    const room = await screen.findByRole('region', { name: '窗前书桌房间' })
    expect(room).toHaveAttribute('data-render-mode', 'layered')
    expect(room).toHaveAttribute('data-motion', 'reduced')
  })
})

function roomState() {
  const room = screen.getByRole('region', { name: '窗前书桌房间' })
  return {
    time: room.getAttribute('data-time'),
    weather: room.getAttribute('data-weather'),
  }
}
