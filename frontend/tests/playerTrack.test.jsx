import { describe, expect, it } from 'vitest'

import {
  activeLyricIndex,
  normalizeLyrics,
  normalizePlayerTrack,
  parseLrc,
} from '../src/features/player/index.js'

describe('PlayerTrack normalization', () => {
  it('normalizes a host-supplied local track without provider semantics', () => {
    const track = normalizePlayerTrack({
      album: '  Local studies ',
      artist: ' Blue Album ',
      artworkUrl: '/brand/blue-album-logo.png',
      audioUrl: 'data:audio/wav;base64,UklGRg==',
      duration: '42.5',
      id: ' local:tone ',
      lyrics: [{ text: ' First line ', time: 0 }],
      title: ' Quiet tone ',
    })

    expect(track).toEqual({
      album: 'Local studies',
      artist: 'Blue Album',
      artworkUrl: '/brand/blue-album-logo.png',
      audioUrl: 'data:audio/wav;base64,UklGRg==',
      duration: 42.5,
      id: 'local:tone',
      lyrics: [{ text: 'First line', time: 0 }],
      title: 'Quiet tone',
    })
    expect(track).not.toHaveProperty('provider')
    expect(track).not.toHaveProperty('cookie')
  })

  it('requires identity, title, and an explicitly safe audio source', () => {
    const base = { audioUrl: '/audio/test.wav', id: 'test', title: 'Test' }

    expect(() => normalizePlayerTrack({ ...base, id: ' ' })).toThrow('id')
    expect(() => normalizePlayerTrack({ ...base, title: '' })).toThrow('title')
    expect(() => normalizePlayerTrack({ ...base, audioUrl: '' })).toThrow('audioUrl')
    expect(() => normalizePlayerTrack({ ...base, audioUrl: 'javascript:alert(1)' })).toThrow('audioUrl')
    expect(() => normalizePlayerTrack({ ...base, audioUrl: 'data:text/html;base64,PGgxPg==' })).toThrow('audioUrl')
    expect(() => normalizePlayerTrack({ ...base, audioUrl: '//evil.example/audio.mp3' })).toThrow('audioUrl')
  })

  it('accepts local, blob, data-audio, and http sources while rejecting invalid metadata', () => {
    for (const audioUrl of [
      '/uploads/local.wav',
      'blob:http://localhost/audio-id',
      'data:audio/ogg;base64,T2dnUw==',
      'https://media.example.com/track.mp3',
      'http://127.0.0.1:8000/test.wav',
    ]) {
      expect(normalizePlayerTrack({ audioUrl, id: audioUrl, title: 'Allowed' }).audioUrl).toBe(audioUrl)
    }

    expect(() => normalizePlayerTrack({
      artworkUrl: 'javascript:alert(1)',
      audioUrl: '/test.wav',
      id: 'bad-artwork',
      title: 'Bad artwork',
    })).toThrow('artworkUrl')
    expect(() => normalizePlayerTrack({ audioUrl: '/test.wav', duration: -1, id: 'bad-duration', title: 'Bad' })).toThrow('duration')
  })
})

describe('player lyrics', () => {
  it('parses LRC timestamps, multiple timestamps, fractions, and ignores metadata', () => {
    const lyrics = parseLrc(`
[ar:Blue Album]
[00:10.50]Second line
[00:02.5][00:04.00]Repeated line
not timestamped
[bad]Ignored
`)

    expect(lyrics).toEqual([
      { text: 'Repeated line', time: 2.5 },
      { text: 'Repeated line', time: 4 },
      { text: 'Second line', time: 10.5 },
    ])
  })

  it('sorts timestamped lyrics, removes invalid lines, and lets the last duplicate win', () => {
    expect(normalizeLyrics([
      { time: 8, text: 'Later' },
      { time: -1, text: 'Invalid' },
      { time: 2, text: 'First version' },
      { time: 2, text: 'Replacement' },
      { time: 4, text: '   ' },
      { time: Number.NaN, text: 'Invalid time' },
    ])).toEqual([
      { text: 'Replacement', time: 2 },
      { text: 'Later', time: 8 },
    ])
  })

  it('finds the active lyric at boundaries and before/after the lyric range', () => {
    const lyrics = [
      { text: 'One', time: 2 },
      { text: 'Two', time: 5.5 },
      { text: 'Three', time: 9 },
    ]

    expect(activeLyricIndex(lyrics, 0)).toBe(-1)
    expect(activeLyricIndex(lyrics, 2)).toBe(0)
    expect(activeLyricIndex(lyrics, 5.49)).toBe(0)
    expect(activeLyricIndex(lyrics, 5.5)).toBe(1)
    expect(activeLyricIndex(lyrics, 999)).toBe(2)
    expect(activeLyricIndex(lyrics, Number.NaN)).toBe(-1)
    expect(activeLyricIndex([], 3)).toBe(-1)
  })
})
