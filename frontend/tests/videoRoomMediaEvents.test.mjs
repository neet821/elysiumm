import assert from 'node:assert/strict'
import test from 'node:test'
import { createVideoRoomMediaEvents } from '../src/features/video/videoRoomMediaEvents.js'

function fixture(overrides = {}) {
  const socketEvents = []
  const calls = {
    handleNativePlaybackControl: [],
    recoverPlayback: 0,
    refreshMediaSource: 0,
    reportBuffering: [],
    saveMetadata: [],
    setNotice: [],
  }
  const dependencies = {
    canControl: true,
    currentItem: {
      duration_seconds: 60,
      id: 7,
      resolution: { height: 360, width: 640 },
    },
    endedKeyRef: { current: null },
    handleNativePlaybackControl: (action) => calls.handleNativePlaybackControl.push(action),
    latestSnapshotRef: { current: { snapshot: { version: 5 } } },
    metadataKeyRef: { current: null },
    numericRoomId: 4,
    playbackUnlockedRef: { current: false },
    recoverPlayback: () => { calls.recoverPlayback += 1 },
    refreshMediaSource: () => { calls.refreshMediaSource += 1 },
    reportBuffering: (buffering) => calls.reportBuffering.push(buffering),
    saveMetadata: (metadata) => {
      calls.saveMetadata.push(metadata)
      return Promise.resolve()
    },
    setNotice: (message) => calls.setNotice.push(message),
    socketRef: { current: { emit: (...event) => socketEvents.push(event) } },
    ...overrides,
  }
  return {
    calls,
    dependencies,
    events: createVideoRoomMediaEvents(dependencies),
    socketEvents,
  }
}

test('video media events delegate native controls and buffering to the playback owner', () => {
  const { calls, events } = fixture()

  events.onPause()
  events.onPlay()
  events.onRateChange()
  events.onSeeking()
  events.onCanPlay()
  events.onWaiting()
  events.onStalled()

  assert.deepEqual(calls.handleNativePlaybackControl, ['pause', 'play', 'rate', 'seek'])
  assert.deepEqual(calls.reportBuffering, [false])
  assert.equal(calls.recoverPlayback, 2)
})

test('video ended events are permission-checked and emitted once per media version', () => {
  const { events, socketEvents } = fixture()

  events.onEnded()
  events.onEnded()

  assert.equal(socketEvents.length, 1)
  assert.equal(socketEvents[0][0], 'video_ended')
  assert.deepEqual(
    {
      expected_version: socketEvents[0][1].expected_version,
      item_id: socketEvents[0][1].item_id,
      room_id: socketEvents[0][1].room_id,
    },
    { expected_version: 5, item_id: 7, room_id: 4 },
  )

  const restricted = fixture({ canControl: false })
  restricted.events.onEnded()
  assert.equal(restricted.socketEvents.length, 0)
})

test('natural completion sends only the ended transition, not a racing native pause', () => {
  const { calls, events, socketEvents } = fixture()
  events.onPause({ currentTarget: { ended: true } })
  events.onEnded()
  assert.deepEqual(calls.handleNativePlaybackControl, [])
  assert.equal(socketEvents.length, 1)
  events.onPause({ currentTarget: { ended: false } })
  assert.deepEqual(calls.handleNativePlaybackControl, ['pause'])
})

test('video metadata is validated, deduplicated, and reports persistence errors', async () => {
  const { calls, events } = fixture()

  events.onLoadedMetadata({ currentTarget: { duration: Number.NaN, videoHeight: 360, videoWidth: 640 } })
  events.onLoadedMetadata({ currentTarget: { duration: 90, videoHeight: 1080, videoWidth: 0 } })
  events.onLoadedMetadata({ currentTarget: { duration: 60, videoHeight: 360, videoWidth: 640 } })
  events.onLoadedMetadata({ currentTarget: { duration: 90, videoHeight: 1080, videoWidth: 1920 } })
  events.onLoadedMetadata({ currentTarget: { duration: 90, videoHeight: 1080, videoWidth: 1920 } })

  assert.deepEqual(calls.saveMetadata, [{
    duration: 90,
    height: 1080,
    itemId: 7,
    roomId: 4,
    width: 1920,
  }])

  const failed = fixture({
    saveMetadata: () => Promise.reject(new Error('database unavailable')),
  })
  failed.events.onLoadedMetadata({ currentTarget: { duration: 90, videoHeight: 1080, videoWidth: 1920 } })
  await new Promise((resolve) => setImmediate(resolve))
  assert.deepEqual(failed.calls.setNotice, ['视频信息暂时无法保存'])
})

test('video media failures request signed source refresh and unlock confirmed playback', () => {
  const { calls, dependencies, events } = fixture()

  events.onError()
  events.onPlaying()

  assert.deepEqual(calls.setNotice, ['视频源加载失败，正在刷新播放凭据…'])
  assert.equal(calls.refreshMediaSource, 1)
  assert.deepEqual(calls.reportBuffering, [false])
  assert.equal(dependencies.playbackUnlockedRef.current, true)
})
