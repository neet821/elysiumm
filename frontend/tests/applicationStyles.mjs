import { readFileSync } from 'node:fs'
import path from 'node:path'
import { resolvePlainServiceCss } from './helpers/plainServiceStyles.mjs'

const sourceDir = path.join(process.cwd(), 'src')

export const applicationStyles = [
  readFileSync(path.join(sourceDir, 'index.css'), 'utf8'),
  resolvePlainServiceCss(),
  readFileSync(path.join(sourceDir, 'components/layout/homeNavigation.css'), 'utf8'),
].join('\n')
