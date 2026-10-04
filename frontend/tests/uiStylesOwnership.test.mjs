import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import postcss from 'postcss'

const sourceDir = new URL('../src/', import.meta.url)
const globalStyles = readFileSync(new URL('index.css', sourceDir), 'utf8')
const uiEntry = readFileSync(new URL('components/ui/index.js', sourceDir), 'utf8')
const uiStylesPath = new URL('components/ui/ui.css', sourceDir)
const uiStyles = existsSync(uiStylesPath) ? resolveStylesheet(fileURLToPath(uiStylesPath)) : ''

test('shared UI primitives load their styles through the UI entrypoint', () => {
  assert.match(uiEntry, /import ['"]\.\/ui\.css['"]/, 'the shared UI entrypoint must load its stylesheet')
  assert.match(uiStyles, /@tailwind components;/, 'the UI stylesheet must include the Tailwind component layer directive it expands')
  assert.doesNotMatch(globalStyles, /^@tailwind components;/m, 'the Tailwind component layer must be expanded only once')

  for (const selector of [
    '.ui-button {',
    '.ui-input {',
    '.ui-card {',
    '.ui-avatar {',
    '.ui-room-status {',
    '.ui-empty-state {',
    '.ui-dialog {',
    '.ui-drawer {',
    '.ui-toast {',
    '.ui-command-palette {',
  ]) {
    assert.ok(uiStyles.includes(selector), `the UI stylesheet must own ${selector}`)
  }
  assert.match(uiStyles, /@layer components\s*\{/, 'component styles must preserve their cascade layer')
  assert.match(uiStyles, /@media \(hover: hover\)/, 'interactive hover states must stay with shared UI components')
  assert.match(uiStyles, /@media \(prefers-reduced-motion: reduce\)/, 'motion preferences must stay with shared UI components')
  assert.doesNotMatch(globalStyles, /^\s*\.ui-[\w-]+/m, 'the global entry must not own shared UI component selectors')
  assert.doesNotMatch(globalStyles, /@keyframes ui-/, 'UI component animations must not remain global')
})

test('shared UI styles split into ordered responsibility layers', () => {
  const layerOwners = {
    './uiControls.css': ['.ui-button {', '.ui-input {', '.ui-card {'],
    './uiIdentity.css': ['.ui-tag {', '.ui-avatar {', '.ui-room-status {'],
    './uiFeedback.css': ['.ui-skeleton {', '.ui-empty-state {', '.ui-tabs__list {'],
    './uiOverlays.css': ['.ui-dialog {', '.ui-drawer {', '.ui-toast {', '.ui-command-palette {'],
    './uiMotion.css': ['@keyframes ui-loading-spin', '.ui-button__spinner'],
  }
  const parsed = postcss.parse(readFileSync(uiStylesPath, 'utf8'))
  const imports = parsed.nodes
    .filter((node) => node.type === 'atrule' && node.name === 'import')
    .map((node) => node.params.replace(/^['"]|['"]$/g, ''))

  assert.deepEqual(imports, Object.keys(layerOwners))
  for (const [file, selectors] of Object.entries(layerOwners)) {
    const styles = resolveStylesheet(fileURLToPath(new URL(file, uiStylesPath)))
    for (const selector of selectors) {
      assert.ok(styles.includes(selector), `${file} must own ${selector}`)
    }
  }
  assert.equal([...uiStyles.matchAll(/@tailwind components;/g)].length, 1, 'the Tailwind component layer must expand exactly once')
  assert.doesNotMatch(uiStyles, /@keyframes ui-skeleton-pulse|@keyframes ui-overlay-enter/, 'decorative motion is retired, not relocated')
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
