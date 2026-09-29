import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import test from 'node:test'

const source = new URL('../src/', import.meta.url)
const read = (path) => readFileSync(new URL(path, source), 'utf8')

test('content routes delegate presentation to their page and feature modules', () => {
  const catalogPage = read('pages/ContentHomePage.jsx')
  const articleFlowPage = read('pages/ArticleFlowHome.jsx')

  assert.match(catalogPage, /from '\.\.\/features\/content\/ContentCatalog\.jsx'/)
  assert.match(catalogPage, /<ContentListing/)
  assert.match(catalogPage, /<ContentDetail/)
  assert.doesNotMatch(catalogPage, /ArticleFlowContent|LegacyArticlePage/)
  assert.match(articleFlowPage, /from '\.\.\/features\/content\/ArticleFlowCards\.jsx'/)
  assert.match(articleFlowPage, /<ArticleFlowContent/)
  assert.doesNotMatch(articleFlowPage, /function (?:LegacyArticleCard|LegacyEssayCard|RecordCard|ContentCard|ContentListing|ContentDetail)\s*\(/)
})
