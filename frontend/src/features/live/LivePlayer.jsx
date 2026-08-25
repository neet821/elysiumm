import { useEffect, useRef, useState } from 'react'
import Hls from 'hls.js'
import { Maximize, Pause, Play, Volume2 } from 'lucide-react'


export default function LivePlayer({ mediaUrl, minimal = false }) {
  const videoRef = useRef(null)
  const retryRef = useRef(0)
  const [message, setMessage] = useState('')
  const [muted, setMuted] = useState(true)
  const [playing, setPlaying] = useState(false)
  const [volume, setVolume] = useState(1)
  const containerRef = useRef(null)

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

  const togglePlayback = () => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) video.play().catch(() => {})
    else video.pause()
  }

  const toggleFullscreen = async () => {
    const container = containerRef.current
    if (!container) return
    if (document.fullscreenElement && document.exitFullscreen) await document.exitFullscreen()
    else if (container.requestFullscreen) await container.requestFullscreen()
  }

  return (
    <div className={`live-player${minimal ? ' live-player--minimal' : ''}`} ref={containerRef}>
      <video
        ref={videoRef}
        aria-label="直播播放器"
        autoPlay
        controls={!minimal}
        muted={muted}
        playsInline
        onPause={() => setPlaying(false)}
        onPlay={() => setPlaying(true)}
        onVolumeChange={(event) => setVolume(Number(event.currentTarget.volume) || 0)}
      />
      {minimal && (
        <div className="live-player__controls" aria-label="直播播放控件">
          <button type="button" onClick={togglePlayback} aria-label={playing ? '暂停直播' : '播放直播'}>
            {playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
          </button>
          <label>
            <Volume2 aria-hidden="true" />
            <span className="sr-only">直播音量</span>
            <input aria-label="直播音量" type="range" min="0" max="1" step="0.05" value={volume} onChange={(event) => { const value = Number(event.target.value); setVolume(value); if (videoRef.current) { videoRef.current.volume = value; videoRef.current.muted = value === 0; setMuted(value === 0) } }} />
          </label>
          <button type="button" onClick={toggleFullscreen} aria-label="直播全屏">
            <Maximize aria-hidden="true" />
          </button>
        </div>
      )}
      {muted && (
        <button className="live-player__sound" type="button" onClick={enableSound}>
          开启声音
        </button>
      )}
      {message && <p className="live-player__message" role="status">{message}</p>}
    </div>
  )
}
