import { useEffect, useState } from 'react'

export const START_TIME = '2025-12-10T00:00:00'

function formatRuntime(now = Date.now()) {
  const elapsedSeconds = Math.max(0, Math.floor((now - new Date(START_TIME).getTime()) / 1000))
  const days = Math.floor(elapsedSeconds / 86400)
  const hours = Math.floor((elapsedSeconds % 86400) / 3600)
  const minutes = Math.floor((elapsedSeconds % 3600) / 60)
  const seconds = elapsedSeconds % 60
  return `${days}天 ${hours}小时 ${minutes}分 ${seconds}秒`
}

export function Footer({ isDark }) {
  const [runtime, setRuntime] = useState(formatRuntime)

  useEffect(() => {
    const timer = window.setInterval(() => setRuntime(formatRuntime()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <footer className="app-footer">
      <div className="app-footer__inner">
        <span>© 2026 Blue Album</span>
        <span className="app-footer__divider" aria-hidden="true">/</span>
        <span>{isDark ? '深色模式' : '浅色模式'}</span>
        <span className="app-footer__divider" aria-hidden="true">/</span>
        <time dateTime={START_TIME}>已运行 {runtime}</time>
      </div>
    </footer>
  )
}

export default Footer
