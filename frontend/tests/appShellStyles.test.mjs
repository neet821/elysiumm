import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const sourceDir = fileURLToPath(new URL('../src/', import.meta.url))
const globalStyles = readFileSync(`${sourceDir}index.css`, 'utf8')
const shellStyles = readFileSync(
  `${sourceDir}components/layout/homeNavigation.css`,
  'utf8',
)

const appShellOverrideSections = [
  'Final homepage override: the fixed bar and the writing stream are one surface.',
  'The article stream owns its small navigation; it is not a site-wide bar.',
  'Homepage navigation is icon-only and lives in the upper-right corner.',
  'Rooms and live keep only one square home arrow, with no global chrome.',
  'Keep the homepage trigger and its top bar in one stable positioning context.',
  'The homepage has no global header. Its controls are rendered by the page itself.',
]

test('AppShell owns homepage and route-back overrides instead of the global stylesheet', () => {
  for (const section of appShellOverrideSections) {
    assert.ok(shellStyles.includes(section), `missing AppShell style section: ${section}`)
    assert.ok(!globalStyles.includes(section), `section remains global: ${section}`)
  }
})
