import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, Bookmark, Headphones, Radio, UserRound, Wrench, X } from 'lucide-react'
import { getInitialTimePreset } from './deskRoomEnvironment.js'
import './deskRoom.css'

const TIME_OPTIONS = [
  { id: 'morning', label: '早晨' },
  { id: 'afternoon', label: '午后' },
  { id: 'sunset', label: '黄昏' },
  { id: 'night', label: '夜晚' },
]

const WEATHER_OPTIONS = [
  { id: 'clear', label: '晴' },
  { id: 'cloud', label: '阴' },
  { id: 'rain', label: '雨' },
]

const VIEW_OPTIONS = [
  { id: 'forest', label: '松林', src: '/home/desk-room/view-pines.webp' },
  { id: 'city', label: '城市', src: '/home/desk-room/view-city.webp' },
  { id: 'mountains', label: '云山', src: '/home/desk-room/view-forest.webp' },
]

const COMPUTER_LINKS = [
  { label: '看归档', to: '/archive', description: '浏览文章和照片', Icon: Bookmark },
  { label: '看直播', to: '/live', description: '进入当前直播间', Icon: Radio },
  { label: '听音乐', to: '/music', description: '进入同步听歌空间', Icon: Headphones },
  { label: '工具箱', to: '/tools', description: '打开站内公共工具', Icon: Wrench },
  { label: '收藏', to: '/collection', description: '查看个人收藏', Icon: Bookmark },
  { label: '书籍', to: '/books', description: '打开书架', Icon: BookOpen },
  { label: '账户', to: '/account', description: '管理账户和权限', Icon: UserRound },
]

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false)

  useEffect(() => {
    const media = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!media) return undefined
    const update = () => setReduced(media.matches)
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }, [])

  return reduced
}

function LayeredRoom({ rain, src }) {
  return (
    <div aria-hidden="true" className="desk-room__layers">
      <img alt="" className="desk-room__layer desk-room__view-layer" decoding="async" src={src} />
      {rain && <div className="desk-room__rain-layer" />}
      <img alt="" className="desk-room__layer desk-room__shell-layer" decoding="async" fetchPriority="high" src="/home/desk-room/room-shell.webp" />
      <img alt="" className="desk-room__layer desk-room__desk-layer" decoding="async" fetchPriority="high" src="/home/desk-room/desk-layer.webp" />
      <img alt="" className="desk-room__layer desk-room__chair-layer" decoding="async" src="/home/desk-room/chair-layer.webp" />
      <div className="desk-room__light-grade" />
    </div>
  )
}

function ChoiceRow({ label, onChange, options, value }) {
  return (
    <div aria-label={label} className="desk-room__choice-row" role="group">
      {options.map((option) => (
        <button aria-pressed={value === option.id} key={option.id} onClick={() => onChange(option.id)} type="button">
          {option.label}
        </button>
      ))}
    </div>
  )
}

function EnvironmentControls({ onTimeChange, onViewChange, onWeatherChange, time, view, weather }) {
  return (
    <div aria-label="房间环境预览" className="desk-room__environment" role="group">
      <ChoiceRow label="窗外风景" onChange={onViewChange} options={VIEW_OPTIONS} value={view} />
      <i aria-hidden="true" />
      <ChoiceRow label="时间预览" onChange={onTimeChange} options={TIME_OPTIONS} value={time} />
      <i aria-hidden="true" />
      <ChoiceRow label="天气预览" onChange={onWeatherChange} options={WEATHER_OPTIONS} value={weather} />
    </div>
  )
}

function ComputerDesktop({ onClose }) {
  const closeRef = useRef(null)

  useEffect(() => {
    closeRef.current?.focus()
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose()
    }
    globalThis.addEventListener?.('keydown', handleKeyDown)
    return () => globalThis.removeEventListener?.('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div className="desk-room__computer" role="dialog" aria-label="电脑桌面" aria-modal="true">
      <div className="desk-room__computer-bar">
        <span>ROOM DESK</span>
        <button ref={closeRef} type="button" onClick={onClose} aria-label="关闭电脑"><X aria-hidden="true" /></button>
      </div>
      <div className="desk-room__computer-links desk-room__computer-links--all">
        {COMPUTER_LINKS.map(({ label, to, description, Icon }) => (
          <Link aria-label={label} key={to} to={to}>
            <Icon aria-hidden="true" />
            <strong>{label}</strong>
            <small>{description}</small>
          </Link>
        ))}
      </div>
      <p>选择一个入口进入。按 Esc 回到房间。</p>
    </div>
  )
}

export default function DeskRoomHome() {
  const [time, setTime] = useState(getInitialTimePreset)
  const [weather, setWeather] = useState('clear')
  const [view, setView] = useState('forest')
  const [computerOpen, setComputerOpen] = useState(false)
  const computerTriggerRef = useRef(null)
  const sceneRef = useRef(null)
  const reducedMotion = useReducedMotion()
  const selectedView = VIEW_OPTIONS.find((option) => option.id === view) || VIEW_OPTIONS[0]
  const timeLabel = TIME_OPTIONS.find((option) => option.id === time)?.label
  const weatherLabel = WEATHER_OPTIONS.find((option) => option.id === weather)?.label
  const viewLabel = VIEW_OPTIONS.find((option) => option.id === view)?.label

  const resetParallax = useCallback(() => {
    const scene = sceneRef.current
    scene?.style.setProperty('--room-x', '0px')
    scene?.style.setProperty('--room-y', '0px')
    scene?.style.setProperty('--view-x', '0px')
    scene?.style.setProperty('--view-y', '0px')
    scene?.style.setProperty('--desk-x', '0px')
    scene?.style.setProperty('--desk-y', '0px')
    scene?.style.setProperty('--chair-x', '0px')
    scene?.style.setProperty('--chair-y', '0px')
  }, [])

  const moveParallax = (event) => {
    if (reducedMotion || computerOpen) return
    const scene = sceneRef.current
    const rect = scene?.getBoundingClientRect()
    if (!scene || !rect) return
    const x = (event.clientX - rect.left) / rect.width - 0.5
    const y = (event.clientY - rect.top) / rect.height - 0.5
    scene.style.setProperty('--room-x', `${(x * 3).toFixed(2)}px`)
    scene.style.setProperty('--room-y', `${(y * 2).toFixed(2)}px`)
    scene.style.setProperty('--view-x', `${(x * -10).toFixed(2)}px`)
    scene.style.setProperty('--view-y', `${(y * -6).toFixed(2)}px`)
    scene.style.setProperty('--desk-x', `${(x * 8).toFixed(2)}px`)
    scene.style.setProperty('--desk-y', `${(y * 5).toFixed(2)}px`)
    scene.style.setProperty('--chair-x', `${(x * 14).toFixed(2)}px`)
    scene.style.setProperty('--chair-y', `${(y * 9).toFixed(2)}px`)
  }

  const closeComputer = useCallback(() => {
    setComputerOpen(false)
    globalThis.requestAnimationFrame?.(() => computerTriggerRef.current?.focus())
  }, [])

  return (
    <section
      aria-label="窗前书桌房间"
      className={`desk-room${computerOpen ? ' desk-room--computer-open' : ''}`}
      data-motion={reducedMotion ? 'reduced' : 'full'}
      data-render-mode="layered"
      data-time={time}
      data-view={view}
      data-weather={weather}
    >
      <div
        aria-label="分格窗前的温馨书桌"
        className="desk-room__visual"
        onPointerLeave={resetParallax}
        onPointerMove={moveParallax}
        ref={sceneRef}
        role="img"
      >
        <div className="desk-room__scene"><LayeredRoom rain={weather === 'rain'} src={selectedView.src} /></div>
      </div>

      <button
        aria-expanded={computerOpen}
        aria-label="打开电脑"
        className="desk-room__computer-trigger"
        onClick={() => setComputerOpen(true)}
        ref={computerTriggerRef}
        type="button"
      ><span aria-hidden="true">进入电脑</span></button>

      <div className="desk-room__status" role="status" aria-label="当前房间环境">
        {viewLabel} · {timeLabel} · {weatherLabel}
      </div>

      <EnvironmentControls
        onTimeChange={setTime}
        onViewChange={setView}
        onWeatherChange={setWeather}
        time={time}
        view={view}
        weather={weather}
      />

      {computerOpen && <ComputerDesktop onClose={closeComputer} />}
    </section>
  )
}
