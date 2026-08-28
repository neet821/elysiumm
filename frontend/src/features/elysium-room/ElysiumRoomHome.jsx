import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import './room.css'
import './elysiumRoom.css'

const LAUNCHER_ITEMS = [
  ['看归档', '/archive'],
  ['看直播', '/live'],
  ['听音乐', '/music'],
  ['工具箱', '/tools'],
  ['收藏', '/collection'],
  ['书籍', '/books'],
  ['账户', '/account'],
]

export default function ElysiumRoomHome({ onSwitchMode }) {
  const mountRef = useRef(null)
  const navigate = useNavigate()
  const navigateRef = useRef(navigate)
  const onSwitchModeRef = useRef(onSwitchMode)
  const instanceRef = useRef(null)
  const [status, setStatus] = useState('正在载入三维房间…')
  const [launcherClose, setLauncherClose] = useState(null)

  navigateRef.current = navigate
  onSwitchModeRef.current = onSwitchMode

  useEffect(() => {
    let active = true
    const instance = instanceRef.current ?? { promise: null, cleanup: null, token: 0 }
    instanceRef.current = instance
    const token = ++instance.token
    if (typeof globalThis.WebGLRenderingContext === 'undefined') {
      setStatus('三维房间需要 WebGL，请切换到轻量模式。')
      return () => { active = false }
    }
    instance.promise ??= import('./runtime.js')
      .then(({ mountElysiumRoom }) => mountElysiumRoom(mountRef.current, {
        onNavigate: (path) => navigateRef.current(path),
        onOpenLauncher: (close) => setLauncherClose(() => close),
        onModeSwitch: () => onSwitchModeRef.current?.(),
      }))
    instance.promise
      .then((dispose) => {
        if (!active || instance.token !== token) return
        instance.cleanup = dispose
        if (active) {
          setStatus('')
        }
      })
      .catch((error) => {
        console.error('3D room failed to load', error)
        if (active) setStatus('三维房间暂时无法载入，请切换到轻量模式。')
      })
    return () => {
      active = false
      if (instance.token === token) {
        instance.token += 1
        instance.cleanup?.()
        instance.cleanup = null
      }
    }
  }, [])

  return (
    <section aria-label="三维房间" className="elysium-room-home">
      <div className="elysium-room-home__mount" ref={mountRef} />
      <div className="elysium-room-home__fallback" role={status ? 'status' : undefined}>
        {status}
      </div>
      {launcherClose && (
        <div className="elysium-room-home__launcher-backdrop">
          <section aria-label="电脑桌面" aria-modal="true" className="elysium-room-home__launcher" role="dialog">
            <div className="elysium-room-home__launcher-bar">
              <strong>ROOM DESK</strong>
              <button onClick={() => { launcherClose(); setLauncherClose(null) }} type="button">返回房间</button>
            </div>
            <div className="elysium-room-home__launcher-links">
              {LAUNCHER_ITEMS.map(([label, to]) => (
                <Link key={to} onClick={() => setLauncherClose(null)} to={to}>{label}</Link>
              ))}
            </div>
          </section>
        </div>
      )}
    </section>
  )
}
