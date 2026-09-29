import { readFileSync } from 'node:fs'
import path from 'node:path'

const sourceDir = path.join(process.cwd(), 'src')

export const applicationStyles = [
  'index.css',
  'components/layout/plainService.css',
  'components/layout/homeNavigation.css',
]
  .map((relativePath) => readFileSync(path.join(sourceDir, relativePath), 'utf8'))
  .join('\n')
