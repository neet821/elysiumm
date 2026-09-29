import { createRef } from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import EssayCard from '../src/features/content/EssayCard.jsx'
import HomeSidebar from '../src/features/content/HomeSidebar.jsx'
import RecordCard from '../src/features/content/RecordCard.jsx'

describe('sidebar cards', () => {
  it('allows a long essay to expand and collapse independently', async () => {
    const user = userEvent.setup()
    render(
      <EssayCard
        item={{ excerpt: '随笔内容。'.repeat(30), slug: 'long-essay', title: '长随笔' }}
      />,
    )

    const toggle = screen.getByRole('button', { name: '展开随笔' })
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('button', { name: '收起随笔' })).toBeInTheDocument()
  })

  it('closes a full review when a pointer lands outside its card', async () => {
    const user = userEvent.setup()
    render(
      <RecordCard
        item={{ review: '一条用于检查侧栏完整评论关闭行为的长评论。'.repeat(4), slug: 'review', title: '评论记录', type: 'movie' }}
      />,
    )

    await user.click(screen.getByRole('button', { name: '展开完整评论' }))
    expect(screen.getByRole('region', { name: '完整评论' })).toBeInTheDocument()
    await user.click(document.body)
    expect(screen.queryByRole('region', { name: '完整评论' })).not.toBeInTheDocument()
  })
})

describe('HomeSidebar', () => {
  it('keeps record and essay sections, overflow cues, and drawer controls together', async () => {
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

    const { container } = render(
      <HomeSidebar
        essays={essays}
        fullEssayBySlug={{}}
        isOpen
        onClose={closeSidebar}
        records={records}
        sidebarRef={createRef()}
      />,
    )

    const drawer = screen.getByRole('dialog', { name: '侧栏内容' })
    expect(drawer).toHaveClass('home-sidebar--drawer-open')
    expect(drawer.querySelectorAll('.sidebar-section--records .record-card')).toHaveLength(3)
    expect(drawer.querySelectorAll('.sidebar-section--essays .essay-card')).toHaveLength(3)
    expect(drawer.querySelectorAll('.sidebar-scroll-cue')).toHaveLength(2)
    expect(within(drawer).getByText('首页记录1')).toBeInTheDocument()
    expect(within(drawer).getByText('首页随笔1')).toBeInTheDocument()

    await user.click(within(drawer).getByRole('button', { name: '展开完整评论' }))
    expect(within(drawer).getByRole('region', { name: '完整评论' })).toHaveTextContent('完整记录评论')
    await user.click(within(drawer).getByRole('button', { name: '收起记录和随笔' }))
    expect(closeSidebar).toHaveBeenCalledTimes(1)
    expect(container.querySelector('.home-sidebar')).toBe(drawer)
  })
})
