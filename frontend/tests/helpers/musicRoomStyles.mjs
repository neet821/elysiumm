import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import postcss from 'postcss'

const featureDirectory = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../src/features/music',
)
const entryPath = path.join(featureDirectory, 'musicRoom.css')

export const MUSIC_ROOM_CSS_LAYERS = [
  './musicRoomStage.css',
  './musicRoomPanels.css',
  './musicRoomResponsive.css',
]

export function musicRoomCssImports() {
  const root = postcss.parse(readFileSync(entryPath, 'utf8'), { from: entryPath })
  return root.nodes
    .filter((node) => node.type === 'atrule' && node.name === 'import')
    .map((node) => node.params.replace(/^['"]|['"]$/g, ''))
}

export function musicRoomCssLayerContents() {
  return MUSIC_ROOM_CSS_LAYERS.map((relativePath) =>
    readFileSync(path.resolve(featureDirectory, relativePath.slice(2)), 'utf8'),
  )
}

export function resolveMusicRoomCss() {
  return musicRoomCssLayerContents().join('')
}
