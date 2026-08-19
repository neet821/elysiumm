import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ isAuthenticated: false, user: null }),
}))

import HomePage from '../src/pages/HomePage.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'

describe('平面公开首页', () => {
  beforeEach(() => {
    apiClient.get.mockReset()
    apiClient.get.mockResolvedValue({
      data: {
        settings: { introduction: '记录想法与生活。' },
        posts: [{ id: 1, slug: 'quiet', title: '安静地写下', content: '一段文字', created_at: '2026-08-01T00:00:00Z', tags: [] }],
        photos: [{ id: 2, url: '/uploads/quiet.jpg', caption: '窗边', created_at: '2026-07-30T00:00:00Z', tags: [] }],
        messages: [],
        scenes: [],
      },
    })
  })

  it('展示播放器、最新文字和照片，并且不再渲染三维首页', async () => {
    render(<MemoryRouter><HomePage /></MemoryRouter>)

    expect(await screen.findByRole('heading', { name: '最近写下' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '首页播放器' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '安静地写下' })).toHaveAttribute('href', '/posts/quiet')
    expect(screen.getByRole('img', { name: '窗边' })).toHaveAttribute('src', '/uploads/quiet.jpg')
    expect(screen.queryByTestId('home-experience')).not.toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.HOMEPAGE)
  })

  it('访客可以阅读留言但只能登录后发表', async () => {
    render(<MemoryRouter><HomePage /></MemoryRouter>)
    const board = await screen.findByRole('region', { name: '留言板' })
    expect(within(board).getByRole('link', { name: '登录后留言' })).toBeInTheDocument()
    expect(within(board).queryByRole('textbox', { name: '写下留言' })).not.toBeInTheDocument()
  })
})
