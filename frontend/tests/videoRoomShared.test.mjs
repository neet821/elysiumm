import assert from 'node:assert/strict'
import test from 'node:test'
import { formatVideoRoomError, sameVideoRoomUserId } from '../src/features/video/videoRoomShared.js'

test('video room API error formatting preserves server, exception, and fallback priority', () => {
  assert.equal(formatVideoRoomError({ response: { data: { detail: 'server detail' } } }, 'fallback'), 'server detail')
  assert.equal(formatVideoRoomError({ response: { data: { detail: { message: 'structured detail' } } } }, 'fallback'), 'structured detail')
  assert.equal(formatVideoRoomError(new Error('exception message'), 'fallback'), 'exception message')
  assert.equal(formatVideoRoomError({}, 'fallback'), 'fallback')
})

test('video room user identity accepts equivalent numeric and string IDs but not missing IDs', () => {
  assert.equal(sameVideoRoomUserId(42, '42'), true)
  assert.equal(sameVideoRoomUserId('guest', 'guest'), true)
  assert.equal(sameVideoRoomUserId(null, null), false)
  assert.equal(sameVideoRoomUserId(undefined, 'undefined'), false)
})
