import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import postcss from 'postcss'

const sourceDir = fileURLToPath(new URL('../src/', import.meta.url))
const globalStyles = readFileSync(`${sourceDir}index.css`, 'utf8')
const appShell = readFileSync(`${sourceDir}components/layout/AppShell.jsx`, 'utf8')
const appShellStylesPath = `${sourceDir}components/layout/appShell.css`
const appShellStyles = existsSync(appShellStylesPath) ? resolveStylesheet(appShellStylesPath) : ''
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

test('homepage surface overrides are not duplicated in the global stylesheet', () => {
  assert.match(shellStyles, /body:has\(\.app-shell--home\)::before\s*\{\s*display:\s*none\s*!important;/)
  assert.doesNotMatch(globalStyles, /body:has\(\.app-shell--home\)::before/)
  assert.doesNotMatch(globalStyles, /\.service-shell\.app-shell--home,\s*\.service-shell\.app-shell--home \.app-shell__main,\s*\.service-shell\.app-shell--home \.app-header/)
})

test('AppShell owns the shared application frame and responsive layout styles', () => {
  const appStylesImport = appShell.indexOf("import './appShell.css'")
  const plainServiceImport = appShell.indexOf("import './plainService.css'")
  const homeNavigationImport = appShell.indexOf("import './homeNavigation.css'")

  assert.ok(appStylesImport >= 0, 'AppShell must import its frame styles')
  assert.ok(appStylesImport < plainServiceImport && plainServiceImport < homeNavigationImport, 'frame styles must load before service and homepage overrides')
  for (const selector of ['.app-background {', '.app-header {', '.app-footer {', '.route-shell {', '.skip-link {']) {
    assert.ok(appShellStyles.includes(selector), `AppShell styles must own ${selector}`)
    assert.ok(!globalStyles.includes(selector), `global styles must not own ${selector}`)
  }
  assert.match(appShellStyles, /@media \(max-width: 840px\)/, 'responsive header and footer rules must stay with the shell')
  assert.match(appShellStyles, /@media \(max-width: 560px\)/, 'static header rules must stay with the shell')
})

test('AppShell styles separate background, frame, and responsive ownership in cascade order', () => {
  const parsed = postcss.parse(readFileSync(appShellStylesPath, 'utf8'))
  const imports = parsed.nodes
    .filter((node) => node.type === 'atrule' && node.name === 'import')
    .map((node) => node.params.replace(/^['"]|['"]$/g, ''))

  assert.deepEqual(imports, [
    './appShellBackground.css',
    './appShellFrame.css',
    './appShellResponsive.css',
  ])
  assert.match(appShellStyles, /\.app-background::before\s*\{[\s\S]*?\.dark \.app-background::after/s)
  assert.match(appShellStyles, /\.app-shell\s*\{[\s\S]*?\.app-header\s*\{[\s\S]*?\.route-shell\s*\{/s)
  assert.match(appShellStyles, /@media \(hover: hover\)[\s\S]*?@media \(max-width: 840px\)[\s\S]*?@media \(max-width: 560px\)/s)
})

function resolveStylesheet(filePath, stack = []) {
  assert.ok(!stack.includes(filePath), `circular stylesheet import: ${filePath}`)
  const parsed = postcss.parse(readFileSync(filePath, 'utf8'), { from: filePath })
  const resolved = postcss.root()

  for (const node of parsed.nodes) {
    if (node.type !== 'atrule' || node.name !== 'import') {
      resolved.append(node.clone())
      continue
    }
    const importedPath = node.params.replace(/^['"]|['"]$/g, '')
    assert.ok(importedPath.endsWith('.css'), `expected local CSS import: ${node.params}`)
    const childPath = path.resolve(path.dirname(filePath), importedPath)
    const child = postcss.parse(resolveStylesheet(childPath, [...stack, filePath]))
    child.nodes.forEach((childNode) => resolved.append(childNode.clone()))
  }
  return resolved.toString()
}
