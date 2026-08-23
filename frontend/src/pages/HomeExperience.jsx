import { useState } from 'react'
import DeskRoomHome from '../components/home/desk-room/DeskRoomHome.jsx'
import ElysiumRoomHome from '../features/elysium-room/ElysiumRoomHome.jsx'
import './homeExperience.css'

const MODE_KEY = 'elysium-room-mode'

function readMode() {
  try {
    return globalThis.localStorage?.getItem(MODE_KEY) === 'lite' ? 'lite' : '3d'
  } catch {
    return '3d'
  }
}

export default function HomeExperience() {
  const [mode, setMode] = useState(readMode)
  const canUse3d = typeof globalThis.WebGLRenderingContext !== 'undefined'
  const switchMode = (next) => {
    setMode(next)
    try {
      globalThis.localStorage?.setItem(MODE_KEY, next)
    } catch {
      // A blocked storage area should not prevent the room from opening.
    }
  }

  return (
    <div className={`home-experience home-experience--${mode}`} data-room-mode={mode} data-testid="home-experience">
      <h1 className="sr-only">Elysium 首页</h1>
      {mode === '3d' ? (
        <ElysiumRoomHome onSwitchMode={() => switchMode('lite')} />
      ) : (
        <DeskRoomHome />
      )}
      {(mode === 'lite' || !canUse3d) && (
        <button
          aria-label={mode === '3d' ? '切换到轻量模式' : '切换到三维模式'}
          className="home-experience__mode-switch"
          onClick={() => switchMode(mode === '3d' ? 'lite' : '3d')}
          type="button"
        >
          {mode === '3d' ? '轻量模式' : '3D 模式'}
        </button>
      )}
    </div>
  )
}
