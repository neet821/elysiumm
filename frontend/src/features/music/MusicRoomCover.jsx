import { useEffect, useState } from 'react'

export default function MusicRoomCover({ track, large = false }) {
  const [failed, setFailed] = useState(false)
  const source = track?.artwork_url || track?.artworkUrl || ''
  useEffect(() => setFailed(false), [source])
  if (!source || failed) return <div aria-hidden="true" className={`music-room-native__cover music-room-native__cover--empty${large ? ' is-large' : ''}`}>♫</div>
  return (
    <img
      alt=""
      className={`music-room-native__cover${large ? ' is-large' : ''}`}
      loading="lazy"
      onError={() => setFailed(true)}
      src={source}
    />
  )
}
