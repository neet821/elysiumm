import { describe, expect, it } from 'vitest'
import { organizeHomeContent, paginateHomeArticles } from '../src/features/content/articleFlowModel.js'

describe('article flow page model', () => {
  it('sorts homepage content and groups media records before generic types', async () => {
    const groups = organizeHomeContent([
      { slug: 'older-article', type: 'article', createdAt: '2026-08-10' },
      { slug: 'newer-record', type: 'movie', contentType: 'article', createdAt: '2026-08-20' },
      { slug: 'essay', contentType: 'essay', date: '2026-08-15' },
      { slug: 'photo', type: 'image', createdAt: '2026-08-18' },
      { slug: 'generic-photo', contentType: 'photo', date: '2026-08-17' },
    ])

    expect(groups.sorted.map((item) => item.slug)).toEqual([
      'newer-record', 'photo', 'generic-photo', 'essay', 'older-article',
    ])
    expect(groups.articleItems.map((item) => item.slug)).toEqual(['older-article'])
    expect(groups.essays.map((item) => item.slug)).toEqual(['essay'])
    expect(groups.records.map((item) => item.slug)).toEqual(['newer-record'])
    expect(groups.photos.map((item) => item.slug)).toEqual(['photo', 'generic-photo'])
  })

  it('clamps invalid and out-of-range pages while preserving visible article order', async () => {
    const articles = Array.from({ length: 30 }, (_, index) => ({ slug: `article-${index + 1}` }))

    const middle = paginateHomeArticles(articles, '5')
    expect(middle.totalPages).toBe(10)
    expect(middle.currentPage).toBe(5)
    expect(middle.visibleArticles.map((item) => item.slug)).toEqual([
      'article-13', 'article-14', 'article-15',
    ])
    expect(middle.paginationItems).toEqual([1, 'ellipsis-4', 4, 5, 6, 'ellipsis-10', 10])

    const invalid = paginateHomeArticles(articles, 'not-a-number')
    expect(invalid.currentPage).toBe(1)
    expect(invalid.visibleArticles.map((item) => item.slug)).toEqual([
      'article-1', 'article-2', 'article-3',
    ])
  })
})
