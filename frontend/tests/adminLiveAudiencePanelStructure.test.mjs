import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const featurePath = new URL('../src/features/live/AdminLiveAudiencePanel.jsx', import.meta.url)
const pagePath = new URL('../src/pages/AdminLivePage.jsx', import.meta.url)
const page = readFileSync(pagePath, 'utf8')

test('admin live page delegates audience display and local view state to its feature', () => {
  assert.ok(existsSync(featurePath), 'audience panel belongs in the live feature')
  assert.match(page, /<AdminLiveAudiencePanel\b/)
  assert.doesNotMatch(page, /audienceExpanded|audienceView|admin-live__audience-tabs/)

  const panel = readFileSync(featurePath, 'utf8')
  assert.match(panel, /AdminLiveAudience/)
  assert.match(panel, /loadAudienceHistory/)
  assert.match(panel, /admin-live__audience-tabs/)
  assert.doesNotMatch(panel, /API_ENDPOINTS|apiClient|utils\/request/)
})
