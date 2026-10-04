import { createRef } from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import EssayCard from '../src/features/content/EssayCard.jsx'
import HomeSidebar from '../src/features/content/HomeSidebar.jsx'
import RecordCard from '../src/features/content/RecordCard.jsx'

describe('sidebar cards', () => {
  it.each([
    ['album', '专辑类型'],
    ['movie', '电影类型'],
    ['game', '游戏类型'],
    ['book', '书籍类型'],
  ])('renders the %s record type icon outside the bounded homepage preview', (type, label) => {
    render(<MemoryRouter><RecordCard item={{ slug: type, title: `${type}记录`, type }} /></MemoryRouter>)

    expect(screen.getByLabelText(label)).toBeInTheDocument()
  })

  it('allows a long essay to expand and collapse independently', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><EssayCard item={{ excerpt: '随笔内容。'.repeat(30), slug: 'long-essay', title: '长随笔' }} /></MemoryRouter>)

    const toggle = screen.getByRole('button', { name: '展开随笔' })
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('button', { name: '收起随笔' })).toBeInTheDocument()
  })

  it('closes a full review when a pointer lands outside its card', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><RecordCard item={{ review: '一条用于检查侧栏完整评论关闭行为的长评论。'.repeat(4), slug: 'review', title: '评论记录', type: 'movie' }} /></MemoryRouter>)

    await user.click(screen.getByRole('button', { name: '展开完整评论' }))
    expect(screen.getByRole('region', { name: '完整评论' })).toBeInTheDocument()
    await user.click(document.body)
    expect(screen.queryByRole('region', { name: '完整评论' })).not.toBeInTheDocument()
  })
})

describe('HomeSidebar', () => {
  it('keeps three record and two essay previews with all-content routes and drawer controls', async () => {
    const user = userEvent.setup()
    const closeSidebar = vi.fn()
    const records = [1, 2, 3].map((number) => ({
      review: number === 1 ? '一条用于检查评论展开的完整记录评论。'.repeat(4) : '',
      slug: `record-${number}`,
      title: `首页记录${number}`,
      type: 'movie',
    }))
    const essays = [1, 2, 3].map((number) => ({
      excerpt: `随笔摘要${number}`,
      slug: `essay-${number}`,
      title: `首页随笔${number}`,
    }))

    const { container } = render(<MemoryRouter>
      <HomeSidebar
        essays={essays}
        fullEssayBySlug={{}}
        isOpen
        onClose={closeSidebar}
        records={records}
        sidebarRef={createRef()}
      />
    </MemoryRouter>)

    const drawer = screen.getByRole('dialog', { name: '侧栏内容' })
    expect(drawer).toHaveClass('home-sidebar--drawer-open')
    expect(drawer.querySelectorAll('.sidebar-section--records .record-card')).toHaveLength(3)
    expect(drawer.querySelectorAll('.sidebar-section--essays .essay-card')).toHaveLength(2)
    expect(drawer.querySelectorAll('.sidebar-scroll-cue')).toHaveLength(0)
    expect(drawer.querySelector('.sidebar-scroll-viewport')).toBeNull()
    expect(within(drawer).getByRole('link', { name: '查看全部记录' })).toHaveAttribute('href', '/content/record')
    expect(within(drawer).getByRole('link', { name: '查看全部随笔' })).toHaveAttribute('href', '/content/essay')
    expect(within(drawer).getByRole('link', { name: '首页随笔1' })).toHaveAttribute('href', '/article/essay-1')
    expect(within(drawer).getByText('首页记录1')).toBeInTheDocument()
    expect(within(drawer).getByText('首页随笔1')).toBeInTheDocument()

    await user.click(within(drawer).getByRole('button', { name: '展开完整评论' }))
    expect(within(drawer).getByRole('region', { name: '完整评论' })).toHaveTextContent('完整记录评论')
    await user.click(within(drawer).getByRole('button', { name: '收起记录和随笔' }))
    expect(closeSidebar).toHaveBeenCalledTimes(1)
    expect(container.querySelector('.home-sidebar')).toBe(drawer)
  })
})
