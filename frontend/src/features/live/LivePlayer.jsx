import { useEffect, useRef, useState } from 'react'
import Hls from 'hls.js'


export default function LivePlayer({ mediaUrl }) {
  const videoRef = useRef(null)
  const retryRef = useRef(0)
  const [message, setMessage] = useState('')
  const [muted, setMuted] = useState(true)

  useEffect(() => {
    const video = videoRef.current
    if (!video || !mediaUrl) return undefined
    setMessage('')

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = mediaUrl
      return () => {
        video.removeAttribute('src')
        video.load()
      }
    }

    if (!Hls.isSupported()) {
      setMessage('当前浏览器无法播放此直播')
      return undefined
    }

    const hls = new Hls({
      liveSyncDurationCount: 3,
      maxLiveSyncPlaybackRate: 1,
    })
    const reconnectTimers = []
    hls.loadSource(mediaUrl)
    hls.attachMedia(video)
    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (!data?.fatal) return
      if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
        if (retryRef.current >= 4) {
          setMessage('直播暂时无法播放')
          hls.stopLoad()
          return
        }
        const delay = 2 ** retryRef.current * 1000
        retryRef.current += 1
        setMessage('直播正在重新连接…')
        reconnectTimers.push(window.setTimeout(() => hls.startLoad(), delay))
      } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
        if (retryRef.current >= 4) {
          setMessage('直播暂时无法播放')
          hls.destroy()
          return
        }
        retryRef.current += 1
        setMessage('画面正在恢复…')
        hls.recoverMediaError()
      } else {
        setMessage('直播暂时无法播放')
        hls.destroy()
      }
    })
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      retryRef.current = 0
      setMessage('')
      video.play().catch(() => {})
    })
    return () => {
      reconnectTimers.forEach((timer) => window.clearTimeout(timer))
      hls.destroy()
    }
  }, [mediaUrl])

  const enableSound = () => {
    setMuted(false)
    if (videoRef.current) {
      videoRef.current.muted = false
      videoRef.current.play().catch(() => {})
    }
  }

  return (
    <div className="live-player">
      <video
        ref={videoRef}
        aria-label="直播播放器"
        autoPlay
        controls
        muted={muted}
        playsInline
      />
      {muted && (
        <button className="live-player__sound" type="button" onClick={enableSound}>
          开启声音
        </button>
      )}
      {message && <p className="live-player__message" role="status">{message}</p>}
    </div>
  )
}
