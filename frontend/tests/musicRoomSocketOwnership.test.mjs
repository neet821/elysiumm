import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import test from 'node:test'

const sourceRoot = path.resolve(process.cwd(), 'src')
const page = readFileSync(path.join(sourceRoot, 'pages/MineradioPage.jsx'), 'utf8')
const controller = readFileSync(path.join(sourceRoot, 'features/music/useMusicRoomPageController.js'), 'utf8')
const realtime = readFileSync(path.join(sourceRoot, 'features/music/useMusicRoomRealtime.js'), 'utf8')

test('music room page delegates room coordination and Socket.IO lifecycle to the music feature', () => {
  assert.match(page, /useMusicRoomPageController/)
  assert.match(controller, /useMusicRoomRealtime/)
  assert.doesNotMatch(`${page}\n${controller}`, /from ['"]socket\.io-client['"]|socket\.on\(/)
  assert.match(realtime, /io\(WS_BASE_URL/)
  for (const event of ['connect', 'disconnect', 'join_success', 'new_message', 'music_queue_updated', 'room_snapshot']) {
    assert.ok(realtime.includes(`'${event}'`), `realtime hook must handle ${event}`)
  }
  assert.match(realtime, /stopClockProbes\(\)/)
  assert.match(realtime, /socket\.disconnect\(\)/)
})
