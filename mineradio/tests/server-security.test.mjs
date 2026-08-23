import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

test('shared provider internals and audio tickets stay private', async (t) => {
  const root = await mkdtemp(join(tmpdir(), 'mineradio-security-'))
  const port = 32000 + Math.floor(Math.random() * 1000)
  const token = 'test-provider-admin-token-1234567890'
  const child = spawn(process.execPath, ['server.js'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: {
      ...process.env,
      MINERADIO_PORT: String(port),
      MUSIC_PROVIDER_ADMIN_TOKEN: token,
      BLUE_ALBUM_SECRET_KEY: 'test-secret-for-audio-tickets',
      COOKIE_FILE: join(root, 'netease.cookie'),
      QQ_COOKIE_FILE: join(root, 'qq.cookie'),
      MINERADIO_SESSION_DIR: join(root, 'users'),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  t.after(async () => {
    child.kill('SIGTERM')
    await rm(root, { recursive: true, force: true })
  })
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Mineradio did not start')), 8000)
    child.stdout.on('data', (chunk) => {
      if (String(chunk).includes('localhost:' + port)) {
        clearTimeout(timer)
        resolve()
      }
    })
    child.once('error', reject)
  })

  const publicStatus = await fetch(`http://127.0.0.1:${port}/api/room/provider-status`)
  assert.equal(publicStatus.status, 404)
  const publicLogin = await fetch(`http://127.0.0.1:${port}/api/login/qr/key`)
  assert.equal(publicLogin.status, 404)
  const internalStatus = await fetch(`http://127.0.0.1:${port}/api/internal/room/provider-status`, {
    headers: { 'X-Music-Provider-Token': token },
  })
  assert.equal(internalStatus.status, 200)
  assert.deepEqual(Object.keys(await internalStatus.json()), ['providers'])
  const invalidAudio = await fetch(`http://127.0.0.1:${port}/api/room/audio?provider=qq&id=abc&ticket=bad`)
  assert.equal(invalidAudio.status, 403)
})
