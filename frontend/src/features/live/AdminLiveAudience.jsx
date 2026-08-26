const deviceNames = {
  mobile: '手机',
  tablet: '平板',
  desktop: '电脑',
  computer: '电脑',
  bot: '自动程序',
}

const formatDuration = (seconds = 0) => {
  const whole = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(whole / 60)
  const remainder = whole % 60
  if (!minutes) return `${remainder} 秒`
  return `${minutes} 分 ${remainder} 秒`
}

const formatTime = (value) => (
  value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
)

const formatLocation = (viewer) => (
  [viewer.country, viewer.region, viewer.city].filter(Boolean).join(' · ') || '未知'
)

export default function AdminLiveAudience({ audience, refreshedAt, history = false }) {
  return (
    <div className="admin-live__table-wrap">
      <div className="admin-live__summary" aria-live="polite">
        <strong>{history ? `历史观看：${audience.length} 条` : `当前在线：${audience.length} 人`}</strong>
        <span>最近刷新：{refreshedAt ? formatTime(refreshedAt) : '等待刷新'}</span>
      </div>
      <table className="admin-live__table">
        <thead>
          <tr>
            {history && <th>场次</th>}
            <th>身份</th>
            <th>IP 与地区</th>
            <th>访问环境</th>
            <th>观看状态</th>
          </tr>
        </thead>
        <tbody>
            {audience.map((viewer) => (
            <tr key={viewer.id}>
              {history && (
                <td data-label="场次">
                  <div className="admin-live__cell-stack">
                    <strong>{viewer.session_title || `场次 #${viewer.live_session_id}`}</strong>
                    <span>{viewer.session_status === 'live' ? '直播中' : '已结束'}</span>
                  </div>
                </td>
              )}
              <td data-label="身份">
                <div className="admin-live__cell-stack">
                  <strong>{viewer.user_id ? (viewer.username || `用户 #${viewer.user_id}`) : '未登录访客'}</strong>
                  {viewer.user_id && <span>{viewer.email || '未填写邮箱'}</span>}
                  {viewer.user_id && <span>用户 #{viewer.user_id}</span>}
                </div>
              </td>
              <td data-label="IP 与地区">
                <div className="admin-live__cell-stack">
                  <strong>{viewer.ip_address}</strong>
                  <span>{formatLocation(viewer)}</span>
                </div>
              </td>
              <td data-label="访问环境">
                {deviceNames[viewer.device_type] || '未知设备'} · {viewer.operating_system || '未知系统'} · {viewer.browser || '未知浏览器'}
              </td>
              <td data-label="观看状态">
                <div className="admin-live__cell-stack">
                  <strong>{formatDuration(viewer.watched_seconds)}</strong>
                  <span>进入：{formatTime(viewer.first_seen_at)}</span>
                  <span>最后活动：{formatTime(viewer.last_seen_at)}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!audience.length && <p className="admin-live__empty">{history ? '还没有历史观看记录。' : '当前没有人观看直播。'}</p>}
    </div>
  )
}
