import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MarkdownContent } from '../src/features/content/ContentCatalog.jsx'

describe('reader leading title', () => {
  it.each([
    { markdown: '# 我的 **文章**\n\n内容\n\n# 其他章节' },
    { html: '<h1>我的 <strong>文章</strong></h1><p>内容</p><h1>其他章节</h1>' },
  ])('omits only a duplicate first H1 in $markdown$html', (body) => {
    render(<><h1>我的 文章</h1><MarkdownContent {...body} omitLeadingTitle="我的 文章" /></>)
    expect(screen.getAllByRole('heading', { name: '我的 文章', level: 1 })).toHaveLength(1)
    expect(screen.getByRole('heading', { name: '其他章节', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('内容')).toBeInTheDocument()
  })
  it('preserves a different first title and a same title later in the body', () => {
    render(<MarkdownContent markdown={'# 序言\n\n内容\n\n# 我的文章'} omitLeadingTitle="我的文章" />)
    expect(screen.getByRole('heading', { name: '序言' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '我的文章' })).toBeInTheDocument()
  })
})
