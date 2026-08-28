import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import assert from 'node:assert/strict'

const sourceRoot = path.join(process.cwd(), 'src')

test('removed administrator overview and admin live route are not shipped', () => {
  assert.equal(fs.existsSync(path.join(sourceRoot, 'pages/AdminOverviewPage.jsx')), false, 'AdminOverviewPage.jsx should be deleted')

  const routes = fs.readFileSync(path.join(sourceRoot, 'routes.jsx'), 'utf8')
  assert.doesNotMatch(routes, /path=["']live["'][^>]*AdminLivePage/)
  assert.doesNotMatch(routes, /label: ['"]直播['"]/)
})
