import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const sourceDir = new URL('../src/', import.meta.url)
const read = (relativePath) => readFileSync(new URL(relativePath, sourceDir), 'utf8')

test('content catalog, article stream, and legacy reader have separate page entrypoints', () => {
  const articleFlowPath = new URL('pages/ArticleFlowHome.jsx', sourceDir)
  const legacyArticlePath = new URL('pages/LegacyArticlePage.jsx', sourceDir)
  const articleFlowDataPath = new URL('features/content/useArticleFlowData.js', sourceDir)

  assert.ok(existsSync(articleFlowPath), 'article stream has a dedicated route module')
  assert.ok(existsSync(legacyArticlePath), 'legacy article reader has a dedicated route module')
  assert.ok(existsSync(articleFlowDataPath), 'article stream API state has a dedicated feature hook')

  const catalogPage = read('pages/ContentHomePage.jsx')
  const articleFlowPage = read('pages/ArticleFlowHome.jsx')
  const legacyArticlePage = read('pages/LegacyArticlePage.jsx')
  const articleFlowData = read('features/content/useArticleFlowData.js')
  const routes = read('routes.jsx')

  assert.match(catalogPage, /<ContentListing/)
  assert.match(catalogPage, /<ContentDetail/)
  assert.doesNotMatch(catalogPage, /ArticleFlowContent|HomeNavigation|LegacyArticlePage/)
  assert.match(articleFlowPage, /<ArticleFlowContent/)
  assert.match(articleFlowPage, /useHomeSidebar/)
  assert.match(articleFlowPage, /useArticleFlowData/)
  assert.doesNotMatch(articleFlowPage, /fetch\('\/api\/(?:articles|homepage)/)
  assert.match(articleFlowData, /fetch\('\/api\/articles'/)
  assert.match(articleFlowData, /fetch\('\/api\/homepage'/)
  assert.doesNotMatch(articleFlowPage, /ContentListing|ContentDetail|LegacyArticlePage/)
  assert.match(legacyArticlePage, /<MarkdownContent/)
  assert.doesNotMatch(legacyArticlePage, /ArticleFlowContent|ContentListing/)
  assert.match(routes, /import\('\.\/pages\/ArticleFlowHome\.jsx'\)/)
  assert.match(routes, /import\('\.\/pages\/LegacyArticlePage\.jsx'\)/)
})
