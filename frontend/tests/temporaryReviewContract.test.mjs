import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const routes = readFileSync(new URL('../src/routes.jsx', import.meta.url), 'utf8')
const adminShell = readFileSync(new URL('../src/components/admin/AdminShell.jsx', import.meta.url), 'utf8')

test('admin-only temporary review hub exposes the five legacy pages', () => {
  assert.match(routes, /path="temporary-review"/)
  for (const page of ['posts', 'photos', 'messages', 'links', 'player']) {
    assert.match(routes, new RegExp(`path="${page}"`))
  }
  assert.match(adminShell, /临时页面检查/)
})

test('temporary review pages are explicitly marked as non-production', () => {
  const source = readFileSync(new URL('../src/pages/TemporaryReviewPage.jsx', import.meta.url), 'utf8')
  assert.match(source, /临时审阅页面/)
  assert.match(source, /不属于正式站点/)
})
