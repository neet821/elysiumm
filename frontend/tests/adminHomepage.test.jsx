import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn(), put: vi.fn() },
}))

import AdminHomepagePage from '../src/pages/AdminHomepagePage.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'
import { DEFAULT_HOMEPAGE_SETTINGS } from '../src/components/home/homepageModel.js'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

const savedSettings = {
  ...DEFAULT_HOMEPAGE_SETTINGS,
  revision: 3,
  updated_at: '2026-07-15T11:00:00Z',
}

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <AdminHomepagePage />
    </MemoryRouter>,
  )
}

describe('administrator homepage editor', () => {
  beforeEach(() => {
    apiClient.get.mockReset()
    apiClient.put.mockReset()
    apiClient.get.mockResolvedValue({ data: savedSettings })
  })

  it('loads structured fields, layout JSON, revision, and a public preview link', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { name: '首页设置' })).toBeInTheDocument()
    expect(screen.getByLabelText('首屏前缀')).toHaveValue(savedSettings.hero_prefix)
    expect(screen.getByLabelText('首屏标题')).toHaveValue(savedSettings.hero_title)
    expect(screen.getByLabelText('首页介绍')).toHaveValue(savedSettings.introduction)
    expect(JSON.parse(screen.getByLabelText('卡片布局 JSON').value)).toEqual(savedSettings.cards)
    expect(screen.getByText('修订号 3')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '查看公开首页' })).toHaveAttribute('href', '/')
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_HOMEPAGE)
  })

  it('saves a validated structured draft and adopts the returned revision', async () => {
    const user = userEvent.setup()
    apiClient.put.mockImplementation(async (_url, payload) => ({
      data: { ...payload.settings, revision: 4, updated_at: '2026-07-15T12:00:00Z' },
    }))
    renderPage()

    const title = await screen.findByLabelText('首屏标题')
    await user.clear(title)
    await user.type(title, 'A configured album.')
    await user.click(screen.getByLabelText('显示留言板'))
    await user.click(screen.getByRole('button', { name: '保存首页设置' }))

    await waitFor(() => expect(apiClient.put).toHaveBeenCalledTimes(1))
    const [, payload] = apiClient.put.mock.calls[0]
    expect(apiClient.put.mock.calls[0][0]).toBe(API_ENDPOINTS.ADMIN_HOMEPAGE)
    expect(payload.revision).toBe(3)
    expect(payload.settings.hero_title).toBe('A configured album.')
    expect(payload.settings.show_messages).toBe(false)
    expect(payload.settings.cards).toEqual(savedSettings.cards)
    expect(await screen.findByText('首页设置已保存。')).toBeInTheDocument()
    expect(screen.getByText('修订号 4')).toBeInTheDocument()
  })

  it('rejects invalid card JSON locally without discarding the draft', async () => {
    const user = userEvent.setup()
    renderPage()

    const layout = await screen.findByLabelText('卡片布局 JSON')
    fireEvent.change(layout, { target: { value: '[invalid' } })
    await user.click(screen.getByRole('button', { name: '保存首页设置' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('卡片布局必须是有效的 JSON')
    expect(layout).toHaveValue('[invalid')
    expect(apiClient.put).not.toHaveBeenCalled()
  })

  it('keeps edited values when the server rejects a save', async () => {
    const user = userEvent.setup()
    apiClient.put.mockRejectedValue({ response: { data: { detail: 'revision conflict' } } })
    renderPage()

    const prefix = await screen.findByLabelText('首屏前缀')
    await user.clear(prefix)
    await user.type(prefix, 'Still here')
    await user.click(screen.getByRole('button', { name: '保存首页设置' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('revision conflict')
    expect(prefix).toHaveValue('Still here')
  })

  it('is reachable from the account administrator console', () => {
    const source = fs.readFileSync(path.join(frontendRoot, 'src', 'pages', 'AccountPage.jsx'), 'utf8')
    expect(source).toContain('navigate("/account/admin")')
    expect(source).not.toMatch(/navigate\("\/(?:admin|tools)\//)
    expect(source).not.toContain('我的收藏')
    expect(source).not.toContain('管理私人文件夹、公开收藏、访问记录和个人起始页')
  })
})
