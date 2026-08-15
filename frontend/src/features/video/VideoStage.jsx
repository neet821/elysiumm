import { useEffect, useRef, useState } from 'react'
import { Maximize, Pause, Play, Volume2 } from 'lucide-react'


function formatTime(value) {
  const seconds = Math.max(0, Math.floor(Number(value) || 0))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

export default function VideoStage({ roomState }) {
  const {
    buffers,
    canControl,
    currentItem,
    onVideoEvent,
    selectSubtitle,
    session,
    setRate,
    setVideoElement,
    setVolume,
    snapshot,
    togglePlayback,
    seek,
  } = roomState
  const containerRef = useRef(null)
  const [duration, setDuration] = useState(0)
  const [position, setPosition] = useState(0)
  const [volume, setLocalVolume] = useState(1)

  useEffect(() => {
    setPosition(Number(snapshot?.position) || 0)
  }, [snapshot?.position, snapshot?.version])

  const fullscreen = async () => {
    const container = containerRef.current
    if (!container) return
    if (document.fullscreenElement && document.exitFullscreen) await document.exitFullscreen()
    else if (container.requestFullscreen) await container.requestFullscreen()
  }
  const selectedSubtitle = currentItem?.subtitles?.find(
    (subtitle) => subtitle.id === session.selected_subtitle_id,
  )
  const bufferingCount = Object.values(buffers).filter(Boolean).length
  const playing = snapshot?.state === 'playing'

  return (
    <section className="min-w-0 space-y-3" aria-label="同步视频播放器">
      <div
        ref={containerRef}
        className="relative aspect-video overflow-hidden rounded-2xl bg-black shadow-2xl"
      >
        {currentItem?.playback_url ? (
          <video
            ref={setVideoElement}
            data-testid="video-room-media"
            className="h-full w-full object-contain"
            playsInline
            preload="metadata"
            onCanPlay={onVideoEvent.onCanPlay}
            onEnded={onVideoEvent.onEnded}
            onError={onVideoEvent.onError}
            onLoadedMetadata={(event) => {
              setDuration(Number(event.currentTarget.duration) || 0)
              setPosition(Number(event.currentTarget.currentTime) || 0)
              onVideoEvent.onLoadedMetadata(event)
            }}
            onPlaying={onVideoEvent.onPlaying}
            onPause={onVideoEvent.onPause}
            onPlay={onVideoEvent.onPlay}
            onRateChange={onVideoEvent.onRateChange}
            onSeeking={onVideoEvent.onSeeking}
            onStalled={onVideoEvent.onStalled}
            onTimeUpdate={(event) => setPosition(event.currentTarget.currentTime)}
            onWaiting={onVideoEvent.onWaiting}
          />
        ) : (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-slate-400">
            {currentItem?.source_type === 'legacy_local' ? '请先选择房间要求的本地视频，文件不会上传。' : '当前还没有视频，请先选择一个视频来源。'}
          </div>
        )}
        {bufferingCount > 0 && (
          <div className="absolute left-3 top-3 rounded-full bg-black/70 px-3 py-1 text-xs text-white" role="status">
            {bufferingCount} 位成员正在缓冲
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={togglePlayback}
            disabled={!canControl || !currentItem}
            aria-label={`${playing ? '暂停' : '播放'} ${currentItem?.title || '视频'}`}
            className="rounded-full bg-sky-600 p-3 text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {playing ? <Pause size={18} /> : <Play size={18} />}
          </button>
          <label className="min-w-48 flex-1 text-xs text-slate-600 dark:text-slate-300">
            <span className="sr-only">共享播放位置</span>
            <input
              aria-label="共享播放位置"
              className="w-full accent-sky-600"
              type="range"
              min="0"
              max={duration || currentItem?.duration_seconds || 100}
              value={Math.min(position, duration || currentItem?.duration_seconds || 100)}
              disabled={!canControl || !currentItem}
              onChange={(event) => setPosition(Number(event.target.value))}
              onPointerUp={(event) => seek(event.currentTarget.value)}
              onKeyUp={(event) => ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key) && seek(event.currentTarget.value)}
            />
            <span>{formatTime(position)} / {formatTime(duration || currentItem?.duration_seconds)}</span>
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
            <Volume2 size={16} aria-hidden="true" />
            <span className="sr-only">本机音量</span>
            <input
              aria-label="本机音量"
              className="w-20 accent-sky-600"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={volume}
              onChange={(event) => {
                const value = Number(event.target.value)
                setLocalVolume(value)
                setVolume(value)
              }}
            />
          </label>
          <label className="text-xs text-slate-600 dark:text-slate-300">
            <span className="mr-2">速度</span>
            <select
              aria-label="共享播放速度"
              value={snapshot?.playback_rate || 1}
              disabled={!canControl || !currentItem}
              onChange={(event) => setRate(event.target.value)}
              className="rounded-lg border border-slate-300 bg-transparent px-2 py-1 dark:border-slate-600"
            >
              {[0.5, 0.75, 1, 1.25, 1.5, 2].map((rate) => (
                <option key={rate} value={rate}>{rate}×</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-600 dark:text-slate-300">
            <span className="mr-2">字幕</span>
            <select
              aria-label="共享字幕"
              value={selectedSubtitle?.id || ''}
              disabled={!canControl || !currentItem?.subtitles?.length}
              onChange={(event) => selectSubtitle(Number(event.target.value))}
              className="max-w-36 rounded-lg border border-slate-300 bg-transparent px-2 py-1 dark:border-slate-600"
            >
              {!currentItem?.subtitles?.length && <option value="">无字幕</option>}
              {(currentItem?.subtitles || []).map((subtitle) => (
                <option key={subtitle.id} value={subtitle.id}>{subtitle.label}</option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={fullscreen}
            aria-label="全屏播放"
            className="rounded-lg border border-slate-300 p-2 text-slate-700 dark:border-slate-600 dark:text-slate-200"
          >
            <Maximize size={18} />
          </button>
        </div>
      </div>

      {currentItem && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
          <strong className="text-slate-800 dark:text-slate-100">{currentItem.title}</strong>
          <span>{currentItem.source_type === 'upload' ? '服务器上传' : currentItem.source_type === 'legacy_local' ? '本地同步' : '网络地址'}</span>
          {currentItem.resolution && <span>{currentItem.resolution.width} × {currentItem.resolution.height}</span>}
          {selectedSubtitle && <span>字幕：{selectedSubtitle.label}</span>}
        </div>
      )}
    </section>
  )
}
