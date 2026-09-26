import { useState } from 'react'

import { API_ENDPOINTS } from '../../config'
import apiClient from '../../utils/request'
import MusicRoomCover from './MusicRoomCover.jsx'

const PROVIDERS = [
  { id: 'netease', label: '网易云' },
  { id: 'qq', label: 'QQ 音乐' },
  { id: 'audius', label: 'Audius' },
]

export default function MusicRoomSearchPanel({ onAction }) {
  const [provider, setProvider] = useState('netease')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const search = (event) => {
    event.preventDefault()
    const value = query.trim()
    if (!value || busy) return
    setBusy(true)
    setError('')
    void (async () => {
      try {
        const response = await apiClient.get(API_ENDPOINTS.MUSIC_SEARCH, {
          params: { limit: 12, provider, q: value },
        })
        setResults(response.data?.items || [])
      } catch (requestError) {
        setResults([])
        setError(requestError.response?.data?.detail || '曲库暂时无法搜索')
      } finally {
        setBusy(false)
      }
    })()
  }

  const choose = (result) => {
    const selected = result?.providers?.find((item) => item.provider === provider)
      || result?.providers?.[0]
    if (!selected) return
    onAction({
      action: 'propose-native-search',
      track: {
        album: result.album,
        artist: result.artist,
        artwork_url: result.artwork_url,
        canonical_track_id: result.id,
        duration_seconds: result.duration_seconds,
        media_mid: selected.media_mid,
        provider: selected.provider,
        provider_track_id: selected.provider_track_id,
        title: result.title,
      },
    })
    setResults((items) => items.filter((item) => item.id !== result.id))
  }

  return (
    <section aria-labelledby="music-room-search-title" className="music-room-native__search">
      <div className="music-room-native__section-heading">
        <h2 id="music-room-search-title">点歌</h2>
        <span>加入公共歌单</span>
      </div>
      <form className="music-room-native__search-form" onSubmit={search}>
        <select aria-label="搜索曲库" onChange={(event) => setProvider(event.target.value)} value={provider}>
          {PROVIDERS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
        <input aria-label="搜索歌曲" onChange={(event) => setQuery(event.target.value)} placeholder="搜索歌曲、歌手或专辑" value={query} />
        <button disabled={busy || !query.trim()} type="submit">{busy ? '搜索中…' : '搜索'}</button>
      </form>
      {error && <p className="music-room-native__error" role="alert">{error}</p>}
      {results.length > 0 && (
        <ul className="music-room-native__search-results">
          {results.map((result) => (
            <li key={result.id}>
              <MusicRoomCover track={result} />
              <span>
                <strong>{result.title}</strong>
                <small>{result.artist}{result.album ? ` · ${result.album}` : ''}</small>
              </span>
              <button aria-label={`将《${result.title}》加入歌单`} onClick={() => choose(result)} type="button">加入</button>
            </li>
          ))}
        </ul>
      )}
      {!busy && query.trim() && !error && results.length === 0 && <p className="music-room-native__muted">没有找到可加入的歌曲</p>}
    </section>
  )
}
