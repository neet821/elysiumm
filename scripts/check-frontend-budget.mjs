#!/usr/bin/env node

import { gzipSync } from 'node:zlib'
import { readFile, readdir, stat } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'


const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(SCRIPT_DIR, '..')
const args = process.argv.slice(2)
const distArgument = args.indexOf('--dist')
const DIST = path.resolve(
  distArgument >= 0 ? args[distArgument + 1] : path.join(ROOT, 'frontend/dist'),
)
const JSON_OUTPUT = args.includes('--json')

const budgets = {
  initialJavaScriptBytes: 360_000,
  initialJavaScriptGzipBytes: 120_000,
  // The existing application bundle is intentionally split into many route
  // chunks and measures about 1.92 MB; keep a small headroom while retaining
  // the guard against accidental bundle growth.
  totalJavaScriptBytes: 2_000_000,
  largestJavaScriptBytes: 600_000,
  totalCssBytes: 230_000,
  minimumAsyncJavaScriptChunks: 5,
}

async function filesBelow(directory, prefix = '') {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const relative = path.posix.join(prefix, entry.name)
    if (entry.isDirectory()) files.push(...await filesBelow(path.join(directory, entry.name), relative))
    else if (entry.isFile()) files.push(relative)
  }
  return files
}

function assetReferences(html) {
  const refs = new Set()
  for (const match of html.matchAll(/<(?:script|link)\b[^>]*(?:src|href)=["']([^"']+)["'][^>]*>/g)) {
    const value = match[1].split(/[?#]/, 1)[0]
    if (value.endsWith('.js')) refs.add(value.replace(/^\//, ''))
  }
  return refs
}

async function size(relative) {
  return (await stat(path.join(DIST, relative))).size
}

async function main() {
  const index = await readFile(path.join(DIST, 'index.html'), 'utf8')
  const files = await filesBelow(DIST)
  const javascript = files.filter((file) => file.endsWith('.js'))
  const css = files.filter((file) => file.endsWith('.css'))
  const initial = [...assetReferences(index)]
  if (!initial.length) throw new Error('production index has no initial JavaScript entry')
  for (const relative of initial) {
    if (!javascript.includes(relative)) throw new Error(`initial asset is missing: ${relative}`)
  }

  const jsSizes = await Promise.all(javascript.map(async (file) => ({ file, bytes: await size(file) })))
  const initialMetrics = await Promise.all(initial.map(async (file) => {
    const contents = await readFile(path.join(DIST, file))
    return { file, bytes: contents.length, gzipBytes: gzipSync(contents).length }
  }))
  const metrics = {
    initialJavaScriptBytes: initialMetrics.reduce((sum, item) => sum + item.bytes, 0),
    initialJavaScriptGzipBytes: initialMetrics.reduce((sum, item) => sum + item.gzipBytes, 0),
    totalJavaScriptBytes: jsSizes.reduce((sum, item) => sum + item.bytes, 0),
    largestJavaScriptBytes: Math.max(...jsSizes.map((item) => item.bytes)),
    totalCssBytes: (await Promise.all(css.map(size))).reduce((sum, bytes) => sum + bytes, 0),
    asyncJavaScriptChunks: javascript.length - initial.length,
    initialFiles: initialMetrics,
    largestJavaScriptFile: jsSizes.toSorted((left, right) => right.bytes - left.bytes)[0]?.file,
  }

  const failures = []
  for (const key of (
    ['initialJavaScriptBytes', 'initialJavaScriptGzipBytes', 'totalJavaScriptBytes',
      'largestJavaScriptBytes', 'totalCssBytes']
  )) {
    if (metrics[key] > budgets[key]) failures.push(`${key} ${metrics[key]} exceeds ${budgets[key]}`)
  }
  if (metrics.asyncJavaScriptChunks < budgets.minimumAsyncJavaScriptChunks) {
    failures.push(
      `asyncJavaScriptChunks ${metrics.asyncJavaScriptChunks} is below ${budgets.minimumAsyncJavaScriptChunks}`,
    )
  }

  const report = { budgets, metrics, passed: failures.length === 0, failures }
  if (JSON_OUTPUT) console.log(JSON.stringify(report, null, 2))
  else {
    console.log('Frontend budget report:', JSON.stringify(metrics, null, 2))
    if (failures.length) failures.forEach((failure) => console.error(`- ${failure}`))
  }
  return failures.length ? 1 : 0
}

main()
  .then((code) => { process.exitCode = code })
  .catch((error) => {
    console.error(`Frontend budget check failed: ${error.message}`)
    process.exitCode = 1
  })
