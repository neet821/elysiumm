import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'
import test from 'node:test'

const source = (relativePath) => readFileSync(new URL(relativePath, import.meta.url), 'utf8')

test('does not expose deleted FRP or website backup routes', () => {
  const routes = source('../src/routes.jsx')

  assert.doesNotMatch(routes, /\/account\/admin\/backups/)
  assert.doesNotMatch(routes, /\/account\/admin\/services\/frp/)
  assert.doesNotMatch(routes, /\/tools\/backup/)
  assert.doesNotMatch(routes, /\/tools\/frp/)
  assert.doesNotMatch(routes, /BackupPage/)
  assert.doesNotMatch(routes, /FrpAdminPage/)
})

test('does not keep deleted website backup or FRP API constants', () => {
  const config = source('../src/config.js')

  assert.doesNotMatch(config, /ADMIN_BACKUP_/)
  assert.doesNotMatch(config, /ADMIN_FRP_/)
  assert.match(config, /BOOKMARK_BACKUPS/)
})
