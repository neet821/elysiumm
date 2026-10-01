import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const sourceDir = new URL('../src/', import.meta.url)
const pagePath = new URL('pages/AdminLivePage.jsx', sourceDir)
const consolePath = new URL('features/live/useAdminLiveConsole.js', sourceDir)
const page = readFileSync(pagePath, 'utf8')

test('admin live page delegates API state and requests to its feature hook', () => {
  assert.ok(existsSync(consolePath), 'the live feature must own its administrator console hook')
  assert.match(page, /useAdminLiveConsole/)
  assert.doesNotMatch(page, /API_ENDPOINTS|apiClient|utils\/request/)

  const consoleHook = readFileSync(consolePath, 'utf8')
  assert.match(consoleHook, /API_ENDPOINTS\.ADMIN_LIVE_SETTINGS/)
  assert.match(consoleHook, /apiClient\.get/)
  assert.doesNotMatch(consoleHook, /from ['"].*pages\//)
})
