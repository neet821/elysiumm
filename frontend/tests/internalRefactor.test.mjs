import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import test from 'node:test'

const source = new URL('../src/', import.meta.url)
const read = (path) => readFileSync(new URL(path, source), 'utf8')

test('content page delegates presentation to the content feature modules', () => {
  const page = read('pages/ContentHomePage.jsx')

  assert.match(page, /from '\.\.\/features\/content\/ArticleFlowCards\.jsx'/)
  assert.match(page, /from '\.\.\/features\/content\/ContentCatalog\.jsx'/)
  assert.match(page, /<ArticleFlowContent/)
  assert.match(page, /<ContentListing/)
  assert.match(page, /<ContentDetail/)
  assert.doesNotMatch(page, /function (?:LegacyArticleCard|LegacyEssayCard|RecordCard|ContentCard|ContentListing|ContentDetail)\s*\(/)
})
