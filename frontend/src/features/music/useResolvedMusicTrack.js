import { useEffect, useState } from 'react'

import { API_ENDPOINTS } from '../../config'
import apiClient from '../../utils/request'

export function useResolvedMusicTrack(current) {
  const [resolvedCurrent, setResolvedCurrent] = useState(null)
  const [currentUnavailableReason, setCurrentUnavailableReason] = useState('')

  useEffect(() => {
    let active = true
    setCurrentUnavailableReason('')
    if (!current) {
      setResolvedCurrent(null)
      return () => { active = false }
    }
    if (!current.canonical_track_id) {
      setResolvedCurrent(current)
      return () => { active = false }
    }
    setResolvedCurrent(null)
    apiClient.get(API_ENDPOINTS.MUSIC_AUDIO(current.canonical_track_id), {
      params: {
        provider: current.provider,
        provider_track_id: current.provider_track_id,
        refresh: true,
      },
    }).then((audioResponse) => {
      if (!active) return
      const audio = audioResponse.data || {}
      if (!audio.playback_url || audio.availability === 'unavailable') {
        setCurrentUnavailableReason(audio.unavailable_reason || '当前配置的曲库都无法播放这首歌')
        return
      }
      setResolvedCurrent({
        ...current,
        active_provider: audio.provider || current.provider,
        stream_url: audio.playback_url,
      })
    }).catch((error) => {
      if (!active) return
      setResolvedCurrent(null)
      setCurrentUnavailableReason(
        error.response?.data?.unavailable_reason
        || error.response?.data?.detail
        || '曲库暂时无法提供这首歌的播放地址',
      )
    })
    return () => { active = false }
  }, [current])

  return { resolvedCurrent, currentUnavailableReason }
}
