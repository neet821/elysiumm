import { articleType } from './articleFlowUtils.js'

const ARTICLES_PER_PAGE = 3

function homeContentType(item) {
  const mediaRecordTypes = ['movie', 'album', 'book', 'game']
  if (
    mediaRecordTypes.includes(item.type) ||
    mediaRecordTypes.includes(item.category) ||
    mediaRecordTypes.includes(item.contentType)
  ) {
    return 'record'
  }
  if (item.contentType) return item.contentType
  return articleType(item) === 'image' ? 'photo' : articleType(item)
}

export function organizeHomeContent(items) {
  const sorted = [...items].sort(
    (a, b) =>
      new Date(b.createdAt || b.date || b.updatedAt || 0) -
      new Date(a.createdAt || a.date || a.updatedAt || 0),
  )

  return {
    sorted,
    articleItems: sorted.filter((item) => homeContentType(item) === 'article'),
    essays: sorted.filter((item) => homeContentType(item) === 'essay'),
    records: sorted.filter((item) => homeContentType(item) === 'record'),
    photos: sorted.filter((item) => homeContentType(item) === 'photo'),
  }
}

export function paginateHomeArticles(items, pageParam) {
  const totalPages = Math.max(1, Math.ceil(items.length / ARTICLES_PER_PAGE))
  const requestedPage = Number.parseInt(pageParam || '1', 10)
  const currentPage = Number.isFinite(requestedPage)
    ? Math.min(Math.max(requestedPage, 1), totalPages)
    : 1
  const visibleArticles = items.slice(
    (currentPage - 1) * ARTICLES_PER_PAGE,
    currentPage * ARTICLES_PER_PAGE,
  )
  const paginationItems = Array.from(
    new Set([1, totalPages, currentPage - 1, currentPage, currentPage + 1]
      .filter((page) => page >= 1 && page <= totalPages)),
  )
    .sort((a, b) => a - b)
    .reduce((pages, page, index, allPages) => {
      if (index > 0 && page - allPages[index - 1] > 1) {
        pages.push(`ellipsis-${page}`)
      }
      pages.push(page)
      return pages
    }, [])

  return { totalPages, currentPage, visibleArticles, paginationItems }
}
