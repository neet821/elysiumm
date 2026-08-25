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

  it('loads only the homepage top-bar text editor', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { name: '首页设置' })).toBeInTheDocument()
    expect(screen.getByLabelText('首页顶栏文字')).toHaveValue(savedSettings.hero_prefix)
    expect(screen.getByLabelText('文章标题字号')).toHaveValue(String(savedSettings.article_title_scale))
    expect(screen.queryByLabelText('首屏标题')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('首页介绍')).not.toBeInTheDocument()
    expect(screen.queryByText('精选内容')).not.toBeInTheDocument()
    expect(screen.queryByText('内容布局')).not.toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_HOMEPAGE)
  })

  it('saves only the custom text while preserving the other homepage settings', async () => {
    const user = userEvent.setup()
    apiClient.put.mockImplementation(async (_url, payload) => ({
      data: { ...payload.settings, revision: 4, updated_at: '2026-07-15T12:00:00Z' },
    }))
    renderPage()

    const prefix = await screen.findByLabelText('首页顶栏文字')
    const titleScale = await screen.findByLabelText('文章标题字号')
    await user.clear(prefix)
    await user.type(prefix, '新的顶栏文字')
    fireEvent.change(titleScale, { target: { value: '0.95' } })
    await user.click(screen.getByRole('button', { name: '保存首页设置' }))

    await waitFor(() => expect(apiClient.put).toHaveBeenCalledTimes(1))
    const [, payload] = apiClient.put.mock.calls[0]
    expect(apiClient.put.mock.calls[0][0]).toBe(API_ENDPOINTS.ADMIN_HOMEPAGE)
    expect(payload.revision).toBe(3)
    expect(payload.settings.hero_prefix).toBe('新的顶栏文字')
    expect(payload.settings.article_title_scale).toBe(0.95)
    expect(payload.settings.hero_title).toBe(savedSettings.hero_title)
    expect(payload.settings.show_messages).toBe(savedSettings.show_messages)
    expect(payload.settings.cards).toEqual(savedSettings.cards)
    expect(await screen.findByText('首页设置已保存。')).toBeInTheDocument()
  })

  it('keeps edited values when the server rejects a save', async () => {
    const user = userEvent.setup()
    apiClient.put.mockRejectedValue({ response: { data: { detail: 'revision conflict' } } })
    renderPage()

    const prefix = await screen.findByLabelText('首页顶栏文字')
    await user.clear(prefix)
    await user.type(prefix, 'Still here')
    await user.click(screen.getByRole('button', { name: '保存首页设置' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('revision conflict')
    expect(prefix).toHaveValue('Still here')
  })

  it('is reachable from the current administrator console', () => {
    const routes = fs.readFileSync(path.join(frontendRoot, 'src', 'routes.jsx'), 'utf8')
    const shell = fs.readFileSync(path.join(frontendRoot, 'src', 'components', 'admin', 'AdminShell.jsx'), 'utf8')
    expect(routes).toContain('path="homepage" element={<AdminHomepagePage />}')
    expect(shell).toContain("to: '/admin/homepage'")
  })
})
