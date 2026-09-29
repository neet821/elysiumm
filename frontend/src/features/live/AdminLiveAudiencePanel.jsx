import { useState } from 'react'
import { Users } from 'lucide-react'

import AdminLiveAudience from './AdminLiveAudience'


export default function AdminLiveAudiencePanel({
  audience,
  audienceHistory,
  activeViewers,
  refreshedAt,
  historyLoading,
  loadAudienceHistory,
}) {
  const [expanded, setExpanded] = useState(false)
  const [view, setView] = useState('current')

  const openHistory = async () => {
    setView('history')
    await loadAudienceHistory()
  }

  return (
    <section className="admin-live__card admin-live__audience-card" aria-label="在线人数">
      <header>
        <Users aria-hidden="true" />
        <div><h2>在线人数</h2><p>当前 {activeViewers} 人</p></div>
      </header>
      <button
        type="button"
        className="admin-live__secondary-trigger"
        aria-expanded={expanded}
        aria-label={`观看人数：${activeViewers}`}
        onClick={() => setExpanded((open) => !open)}
      >
        <span>观看人数</span>
        <strong>{activeViewers}</strong>
      </button>
      {expanded && (
        <div className="admin-live__audience-menu">
          <div className="admin-live__audience-tabs" role="tablist" aria-label="观看数据">
            <button type="button" role="tab" aria-selected={view === 'current'} onClick={() => setView('current')}>当前在线</button>
            <button type="button" role="tab" aria-selected={view === 'history'} onClick={openHistory}>历史观看</button>
          </div>
          {historyLoading ? <p className="admin-live__empty">加载中…</p> : (
            <AdminLiveAudience
              audience={view === 'history' ? audienceHistory : audience}
              history={view === 'history'}
              refreshedAt={refreshedAt}
            />
          )}
          <p className="admin-live__attribution">
            <a href="https://db-ip.com" target="_blank" rel="noreferrer">地区数据由 DB-IP 提供</a>
          </p>
        </div>
      )}
    </section>
  )
}
