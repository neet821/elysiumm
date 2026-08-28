import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import assert from 'node:assert/strict'

const sourceRoot = path.join(process.cwd(), 'src')

test('removed administrator overview and live UI modules are not shipped', () => {
  for (const file of [
    'pages/AdminOverviewPage.jsx',
    'pages/AdminLivePage.jsx',
    'features/live/AdminLiveAudience.jsx',
    'features/live/AdminLiveRecordings.jsx',
  ]) {
    assert.equal(fs.existsSync(path.join(sourceRoot, file)), false, `${file} should be deleted`)
  }
})
