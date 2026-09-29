import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const sourceDir = new URL('../src/', import.meta.url)
const read = (relativePath) => readFileSync(new URL(relativePath, sourceDir), 'utf8')

test('content catalog, article stream, and legacy reader have separate page entrypoints', () => {
  const articleFlowPath = new URL('pages/ArticleFlowHome.jsx', sourceDir)
  const legacyArticlePath = new URL('pages/LegacyArticlePage.jsx', sourceDir)

  assert.ok(existsSync(articleFlowPath), 'article stream has a dedicated route module')
  assert.ok(existsSync(legacyArticlePath), 'legacy article reader has a dedicated route module')

  const catalogPage = read('pages/ContentHomePage.jsx')
  const articleFlowPage = read('pages/ArticleFlowHome.jsx')
  const legacyArticlePage = read('pages/LegacyArticlePage.jsx')
  const routes = read('routes.jsx')

  assert.match(catalogPage, /<ContentListing/)
  assert.match(catalogPage, /<ContentDetail/)
  assert.doesNotMatch(catalogPage, /ArticleFlowContent|HomeNavigation|LegacyArticlePage/)
  assert.match(articleFlowPage, /<ArticleFlowContent/)
  assert.match(articleFlowPage, /useHomeSidebar/)
  assert.doesNotMatch(articleFlowPage, /ContentListing|ContentDetail|LegacyArticlePage/)
  assert.match(legacyArticlePage, /<MarkdownContent/)
  assert.doesNotMatch(legacyArticlePage, /ArticleFlowContent|ContentListing/)
  assert.match(routes, /import\('\.\/pages\/ArticleFlowHome\.jsx'\)/)
  assert.match(routes, /import\('\.\/pages\/LegacyArticlePage\.jsx'\)/)
})
