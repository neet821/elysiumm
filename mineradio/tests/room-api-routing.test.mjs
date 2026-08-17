import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'

const apiScriptUrl = new URL('../public/js/modules/05-playback/00-api-quality-output.js', import.meta.url)

test('room-mode Mineradio sends native API calls through the public Mineradio proxy', async () => {
  const requestedUrls = []
  const context = {
    AbortController,
    clearTimeout,
    console,
    document: {
      body: {
        classList: {
          contains(name) {
            return name === 'blue-album-room-mode'
          },
        },
      },
    },
    fetch: async (url) => {
      requestedUrls.push(url)
      return { json: async () => ({ songs: [] }) }
    },
    setTimeout,
    window: { AbortController },
  }
  vm.createContext(context)
  vm.runInContext(await readFile(apiScriptUrl, 'utf8'), context)

  await context.apiJson('/api/search?keywords=radiohead&limit=18')

  assert.deepEqual(requestedUrls, ['/mineradio-api/search?keywords=radiohead&limit=18'])
})
