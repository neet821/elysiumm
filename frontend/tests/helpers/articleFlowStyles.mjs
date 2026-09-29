import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import postcss from 'postcss'

const contentDirectory = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../src/features/content',
)
const entryPath = path.join(contentDirectory, 'articleFlow.css')

export const ARTICLE_FLOW_CSS_LAYERS = [
  './articleFlowFeed.css',
  './articleFlowLayout.css',
  './articleFlowNavigation.css',
]

export function articleFlowCssImports() {
  const root = postcss.parse(readFileSync(entryPath, 'utf8'), { from: entryPath })
  return root.nodes
    .filter((node) => node.type === 'atrule' && node.name === 'import')
    .map((node) => node.params.replace(/^['"]|['"]$/g, ''))
}

export function resolveArticleFlowCss(filePath = entryPath, importStack = []) {
  assertNoCircularImport(filePath, importStack)
  const parsed = postcss.parse(readFileSync(filePath, 'utf8'), { from: filePath })
  const resolved = postcss.root()

  for (const node of parsed.nodes) {
    if (node.type === 'atrule' && node.name === 'import') {
      const importedPath = node.params.replace(/^['"]|['"]$/g, '')
      if (!importedPath.endsWith('.css')) {
        throw new Error(`expected a local CSS import: ${node.params}`)
      }
      const childPath = path.resolve(path.dirname(filePath), importedPath)
      const child = postcss.parse(resolveArticleFlowCss(childPath, [...importStack, filePath]))
      child.nodes.forEach((childNode) => resolved.append(childNode.clone()))
    } else {
      resolved.append(node.clone())
    }
  }
  return resolved.toString()
}

function assertNoCircularImport(filePath, importStack) {
  if (importStack.includes(filePath)) {
    throw new Error(`circular stylesheet import: ${filePath}`)
  }
}
