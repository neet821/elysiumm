import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import postcss from 'postcss'

const layoutDirectory = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../src/components/layout',
)
const entryPath = path.join(layoutDirectory, 'plainService.css')

export const PLAIN_SERVICE_CSS_LAYERS = [
  './plainServiceTokens.css',
  './plainServiceShell.css',
  './plainServiceComponents.css',
  './plainServiceDirectory.css',
  './plainServiceResponsive.css',
]

export function plainServiceCssImports() {
  const root = postcss.parse(readFileSync(entryPath, 'utf8'), { from: entryPath })
  return root.nodes
    .filter((node) => node.type === 'atrule' && node.name === 'import')
    .map((node) => node.params.replace(/^['"]|['"]$/g, ''))
}

export function resolvePlainServiceCss(filePath = entryPath, importStack = []) {
  if (importStack.includes(filePath)) {
    throw new Error(`circular stylesheet import: ${filePath}`)
  }

  const parsed = postcss.parse(readFileSync(filePath, 'utf8'), { from: filePath })
  const resolved = postcss.root()

  for (const node of parsed.nodes) {
    if (node.type === 'atrule' && node.name === 'import') {
      const importedPath = node.params.replace(/^['"]|['"]$/g, '')
      if (!importedPath.endsWith('.css')) {
        throw new Error(`expected a local CSS import: ${node.params}`)
      }
      const childPath = path.resolve(path.dirname(filePath), importedPath)
      const child = postcss.parse(resolvePlainServiceCss(childPath, [...importStack, filePath]))
      child.nodes.forEach((childNode) => resolved.append(childNode.clone()))
    } else {
      resolved.append(node.clone())
    }
  }

  return resolved.toString()
}
