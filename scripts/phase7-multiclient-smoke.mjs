import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import {
  CdpClient,
  api,
  authenticatePage,
  capture,
  chromeTarget,
  clickText,
  expectOk,
  fillInput,
  freePort,
  localOnlyRequests,
  registerAndLogin,
  run,
  startProcess,
  stopProcess,
  waitForUrl,
} from './native-browser-smoke-helpers.mjs'

const root = path.resolve(import.meta.dirname, '..')
const python = path.join(root, 'backend', '.venv', 'bin', 'python')
const chromeBinary = process.env.CHROME_BINARY || '/usr/bin/google-chrome-stable'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-phase7-browser'
const password = 'Phase7Browser2026!'
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

function wavBuffer(durationSeconds, frequency) {
  const sampleRate = 8000
  const samples = Math.floor(sampleRate * durationSeconds)
  const dataSize = samples * 2
  const buffer = Buffer.alloc(44 + dataSize)
  buffer.write('RIFF', 0)
  buffer.writeUInt32LE(36 + dataSize, 4)
  buffer.write('WAVEfmt ', 8)
  buffer.writeUInt32LE(16, 16)
  buffer.writeUInt16LE(1, 20)
  buffer.writeUInt16LE(1, 22)
  buffer.writeUInt32LE(sampleRate, 24)
  buffer.writeUInt32LE(sampleRate * 2, 28)
  buffer.writeUInt16LE(2, 32)
  buffer.writeUInt16LE(16, 34)
  buffer.write('data', 36)
  buffer.writeUInt32LE(dataSize, 40)
  for (let index = 0; index < samples; index += 1) {
    const sample = Math.round(Math.sin(2 * Math.PI * frequency * index / sampleRate) * 6000)
    buffer.writeInt16LE(sample, 44 + index * 2)
  }
  return buffer
}

async function uploadTrack(base, roomId, token, title, frequency) {
  const form = new FormData()
  form.set('title', title)
  form.set('artist', 'Phase 7 Fixture')
  form.set('duration_seconds', '8')
  form.set('file', new Blob([wavBuffer(8, frequency)], { type: 'audio/wav' }), `${title}.wav`)
  return expectOk(await api(base, `/api/music/rooms/${roomId}/uploads`, {
    form,
    method: 'POST',
    token,
  }), `upload ${title}`)
}

function environmentFor(rootPath, appBase) {
  const storage = path.join(rootPath, 'shared')
  return {
    ...process.env,
    ACCESS_TOKEN_EXPIRE_MINUTES: '60',
    ADMIN_FILES_STORAGE_DIR: path.join(storage, 'private-storage', 'admin_files'),
    BACKEND_LOG_FILE: path.join(rootPath, 'backend.log'),
    BACKUP_OUTPUT_DIR: path.join(storage, 'backups'),
    CORS_ORIGINS: appBase,
    DATABASE_URL: `sqlite:///${path.join(rootPath, 'phase7.sqlite')}`,
    LIVE_RECORDING_ROOT: path.join(storage, 'uploads', 'live-recordings'),
    MUSIC_PROVIDER_CREDENTIAL_DIR: path.join(storage, 'private-storage', 'music'),
    MUSIC_PROVIDER_LEGACY_COMPAT: '0',
    PRIVATE_STORAGE_DIR: path.join(storage, 'private-storage'),
    PUBLIC_SYNC_STORAGE: path.join(storage, 'sync-storage'),
    SECRET_KEY: 'phase7-browser-isolated-secret-for-tests',
    TRANSFER_STORAGE_DIR: path.join(storage, 'transfers'),
    UPLOAD_DIR: path.join(storage, 'uploads'),
  }
}

async function inspectPage(page, appBase) {
  const state = await page.evaluate(`(() => ({
    audio: Boolean(document.querySelector('audio[aria-label="听歌房音频播放器"]')),
    canvas: Boolean(document.querySelector('.music-room-native__particles')),
    iframeCount: document.querySelectorAll('iframe').length,
    lyrics: Boolean(document.querySelector('.music-room-native__lyrics')),
    nativePlayer: Boolean(document.querySelector('.music-room-native[data-room-sync-ready="true"]')),
    overflow: document.documentElement.scrollWidth - innerWidth,
    path: location.pathname,
    search: Boolean(document.querySelector('.music-room-native__search')),
    syncStatus: document.querySelector('.music-room-native__room-meta [data-sync-status]')?.dataset.syncStatus || null,
  }))()`)
  assert.equal(state.iframeCount, 0, `${page.label} rendered a legacy iframe`)
  assert.equal(state.nativePlayer, true, `${page.label} did not render the native room player`)
  assert.equal(state.audio, true, `${page.label} did not render the native audio element`)
  assert.equal(state.canvas, true, `${page.label} did not render the particle field`)
  assert.equal(state.lyrics, true, `${page.label} did not render the lyrics surface`)
  assert.equal(state.search, true, `${page.label} did not render the room search surface`)
  assert.equal(state.syncStatus, 'synced', `${page.label} did not reach the synced state`)
  assert(state.overflow <= 1, `${page.label} has horizontal overflow: ${state.overflow}px`)
  assert.deepEqual(localOnlyRequests(page.requests, appBase), [], `${page.label} contacted an external origin`)
  assert.deepEqual(page.errors, [], `${page.label} emitted browser errors`)
  return state
}

async function main() {
  assert(fs.existsSync(python), 'backend/.venv is required for the browser gate')
  assert(fs.existsSync(chromeBinary), `Chrome is unavailable: ${chromeBinary}`)
  fs.rmSync(screenshotDir, { force: true, recursive: true })
  fs.mkdirSync(screenshotDir, { recursive: true })

  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'elysium-phase7-native-'))
  const processes = []
  const clients = []
  let roomId
  try {
    const [backendPort, frontendPort, hostDebugPort, memberDebugPort] = await Promise.all([
      freePort(), freePort(), freePort(), freePort(),
    ])
    const appBase = `http://127.0.0.1:${frontendPort}`
    const backendBase = `http://127.0.0.1:${backendPort}`
    const environment = environmentFor(temporaryRoot, appBase)
    fs.mkdirSync(environment.PUBLIC_SYNC_STORAGE, { recursive: true })

    await run(python, [path.join(root, 'backend', 'run_migrations.py')], { cwd: root, env: environment })
    processes.push(startProcess(python, [
      '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(backendPort), '--log-level', 'warning',
    ], {
      cwd: path.join(root, 'backend'),
      env: environment,
      logPath: path.join(temporaryRoot, 'backend.log'),
    }))
    await waitForUrl(`${backendBase}/api/health`)

    processes.push(startProcess('npm', [
      'run', 'dev', '--', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort',
    ], {
      cwd: path.join(root, 'frontend'),
      env: { ...process.env, VITE_BACKEND_PROXY_TARGET: backendBase },
      logPath: path.join(temporaryRoot, 'frontend.log'),
    }))
    await waitForUrl(appBase)

    const hostAuth = await registerAndLogin(appBase, 'phase7_native_host', password)
    const memberAuth = await registerAndLogin(appBase, 'phase7_native_member', password)
    const room = expectOk(await api(appBase, '/api/sync-rooms', {
      body: { control_mode: 'host_only', mode: 'music', room_name: 'Phase 7 Native Room', type: 'audio' },
      method: 'POST',
      token: hostAuth.access_token,
    }), 'create music room')
    roomId = room.id
    expectOk(await api(appBase, `/api/sync-rooms/${roomId}/join`, {
      method: 'POST',
      token: memberAuth.access_token,
    }), 'member join')
    const first = await uploadTrack(appBase, roomId, hostAuth.access_token, 'Fixture Alpha', 330)
    assert(first.queue.some((item) => item.title === 'Fixture Alpha' && item.status === 'playing'))
    const second = await uploadTrack(appBase, roomId, memberAuth.access_token, 'Fixture Beta', 440)
    assert(second.queue.some((item) => item.title === 'Fixture Beta' && item.status !== 'playing'))

    for (const [label, debugPort] of [['host', hostDebugPort], ['member', memberDebugPort]]) {
      processes.push(startProcess(chromeBinary, [
        '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--mute-audio',
        '--autoplay-policy=no-user-gesture-required', '--no-first-run', '--no-default-browser-check',
        `--remote-debugging-port=${debugPort}`, `--user-data-dir=${path.join(temporaryRoot, `${label}-chrome`)}`, 'about:blank',
      ], { cwd: root, env: process.env, logPath: path.join(temporaryRoot, `${label}-chrome.log`) }))
    }
    const host = new CdpClient(await chromeTarget(`http://127.0.0.1:${hostDebugPort}`), 'host')
    const member = new CdpClient(await chromeTarget(`http://127.0.0.1:${memberDebugPort}`), 'member')
    clients.push(host, member)
    await Promise.all([host.connect(), member.connect()])
    await Promise.all([
      authenticatePage(host, appBase, hostAuth),
      authenticatePage(member, appBase, memberAuth),
    ])
    await Promise.all([
      host.setViewport(1440, 1000),
      member.setViewport(390, 844, true),
    ])
    const roomUrl = `${appBase}/rooms/music/${roomId}`
    await Promise.all([host.navigate(roomUrl), member.navigate(roomUrl)])
    await Promise.all([
      host.waitFor("Boolean(document.querySelector('.music-room-native') && document.querySelector('.music-room-native__room-meta [data-sync-status=\\\"synced\\\"]'))", 30000),
      member.waitFor("Boolean(document.querySelector('.music-room-native') && document.querySelector('.music-room-native__room-meta [data-sync-status=\\\"synced\\\"]'))", 30000),
    ])
    await Promise.all([
      host.waitFor("document.body.textContent.includes('Fixture Beta')", 20000),
      member.waitFor("document.body.textContent.includes('Fixture Beta')", 20000),
    ])

    await clickText(host, '下一首')
    await Promise.all([
      host.waitFor("document.querySelector('.music-room-native__visual h1')?.textContent === 'Fixture Beta'", 20000),
      member.waitFor("document.querySelector('.music-room-native__visual h1')?.textContent === 'Fixture Beta'", 20000),
    ])

    await fillInput(member, '[aria-label="聊天消息"]', 'Phase 7 native room hello')
    await clickText(member, '发送')
    await host.waitFor("document.body.textContent.includes('Phase 7 native room hello')", 15000)
    const history = expectOk(await api(appBase, `/api/music/rooms/${roomId}/history?limit=100`, {
      token: hostAuth.access_token,
    }), 'room history')
    assert(Array.isArray(history.items) && history.items.length > 0, 'native room did not preserve history')

    const states = await Promise.all([inspectPage(host, appBase), inspectPage(member, appBase)])
    const screenshots = [
      await capture(host, screenshotDir, 'phase7-host-desktop.png'),
      await capture(member, screenshotDir, 'phase7-member-mobile.png'),
    ]
    console.log(JSON.stringify({
      historyItems: history.items.length,
      nativePlayer: true,
      roomId,
      screenshots,
      states,
    }, null, 2))
  } catch (error) {
    const logs = fs.existsSync(temporaryRoot)
      ? fs.readdirSync(temporaryRoot).filter((name) => name.endsWith('.log')).map((name) => (
        `\n--- ${name} ---\n${fs.readFileSync(path.join(temporaryRoot, name), 'utf8').slice(-5000)}`
      )).join('')
      : ''
    throw new Error(`${error.stack || error.message}${logs}`)
  } finally {
    clients.forEach((client) => client.close())
    await Promise.all(processes.reverse().map(stopProcess))
    fs.rmSync(temporaryRoot, { force: true, recursive: true })
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
