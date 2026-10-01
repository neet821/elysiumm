import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import postcss from 'postcss'

const featureDirectory = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../src/features/live',
)
const entryPath = path.join(featureDirectory, 'live.css')

export const LIVE_CSS_LAYERS = ['./liveWatch.css', './liveAdmin.css', './liveSurface.css']

export function liveCssImports() {
  const root = postcss.parse(readFileSync(entryPath, 'utf8'), { from: entryPath })
  return root.nodes
    .filter((node) => node.type === 'atrule' && node.name === 'import')
    .map((node) => node.params.replace(/^['"]|['"]$/g, ''))
}

export function liveCssLayerContents() {
  return LIVE_CSS_LAYERS.map((relativePath) =>
    readFileSync(path.resolve(featureDirectory, relativePath.slice(2)), 'utf8'),
  )
}

export function resolveLiveCss() {
  return liveCssLayerContents().join('')
}
