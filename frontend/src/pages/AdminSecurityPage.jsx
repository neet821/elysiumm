import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, ShieldAlert, ShieldCheck } from 'lucide-react'

import { API_ENDPOINTS } from '../config'
import { Button, Card, Skeleton, Tag } from '../components/ui'
import apiClient from '../utils/request'

const formatDate = (value) => value ? new Date(value).toLocaleString('zh-CN') : '时间未知'
const outcomeLabel = (value) => ({ success: '成功', failed: '失败', rate_limited: '已限速', denied: '已拒绝' }[value] || value)
const auditActionLabel = (value) => ({ device_rotate: '更新设备凭据', sync_device_create: '创建设备', sync_device_pause: '暂停设备', sync_device_resume: '恢复设备', sync_device_revoke: '撤销设备', sync_device_rotate: '更新设备凭据', sync_device_scan: '扫描设备' }[value] || '管理员操作')
const realtimeEventLabel = (value) => ({ join_room: '加入房间', playback_control: '播放控制', send_message: '发送消息', video_local_ready: '本地视频就绪' }[value] || '实时连接操作')
const resourceLabel = (value) => ({ room: '房间', sync_device: '同步设备', user: '用户' }[value] || '管理资源')

function EvidenceList({ items, type }) {
  if (items.length === 0) return <p className="admin-dashboard__empty">最近没有{type === 'administrator' ? '管理员' : '实时连接'}审计记录。</p>
  return (
    <ol className="admin-security__audit-list">
      {items.map((item) => (
        <li key={item.id}>
          <div><strong>{type === 'administrator' ? auditActionLabel(item.action) : realtimeEventLabel(item.event_name)}</strong><span>{item.actor_username || '系统'}{item.resource_type ? ` · ${resourceLabel(item.resource_type)}` : ''}{item.room_id ? ` · 房间 ${item.room_id}` : ''}</span></div>
          <div><Tag tone={item.outcome === 'success' ? 'success' : item.outcome === 'rate_limited' ? 'neutral' : 'danger'}>{outcomeLabel(item.outcome)}</Tag><time dateTime={item.created_at}>{formatDate(item.created_at)}</time></div>
        </li>
      ))}
    </ol>
  )
}

export default function AdminSecurityPage() {
  const [security, setSecurity] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadSecurity = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_SECURITY, { params: { limit: 50 } })
      setSecurity(response.data)
    } catch {
      setError('安全记录暂时无法载入。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadSecurity() }, [loadSecurity])

  if (loading) return <Skeleton className="admin-dashboard__loading" label="正在载入安全记录" />
  if (error || !security) return <section className="admin-dashboard admin-dashboard--message"><p role="alert">{error || '安全记录暂时无法载入。'}</p><Button onClick={loadSecurity}>重试</Button></section>

  return (
    <section className="admin-dashboard admin-security">
      <header className="admin-dashboard__intro"><div><p>仅显示已保存记录</p><h1>安全记录</h1><p>查看有限范围的审计摘要和当前身份验证配置。</p></div><Button variant="secondary" onClick={loadSecurity}><RefreshCw size={16} aria-hidden="true" /> 刷新</Button></header>

      <Card className="admin-security__capability">
        <ShieldAlert size={21} aria-hidden="true" />
        <div><h2>暂不提供网页会话清单</h2><p>{security.capabilities.web_session_inventory_reason}</p></div>
      </Card>

      <div className="admin-security__summary">
        <Card><h2>账户与设备</h2><p>{security.counts.inactive_users} 个停用账户</p><p>{security.counts.revoked_devices} 台已撤销设备</p><p>{security.counts.expired_devices} 台凭据过期设备</p></Card>
        <Card><h2>管理员控制</h2><p>{security.counts.admin_failed} 次管理员操作失败</p><p>{security.counts.admin_rate_limited} 次管理员操作限速</p></Card>
        <Card><h2>实时连接控制</h2><p>{security.counts.realtime_failed} 次实时操作失败</p><p>{security.counts.realtime_rate_limited} 次实时操作限速</p></Card>
        <Card><h2>配置</h2><p><ShieldCheck size={16} aria-hidden="true" /> 实时连接验证：{security.configuration.socket_auth_required ? '必须' : '非必须'}</p><p>CORS 通配来源：{security.configuration.cors_wildcard_configured ? '已配置' : '未配置'}</p><p>{security.configuration.cors_allowed_origin_count} 个允许的 CORS 来源</p></Card>
      </div>

      <section className="admin-dashboard__evidence" aria-labelledby="administrator-audit-heading"><header><div><h2 id="administrator-audit-heading">管理员审计</h2><p>最多显示最近五十条明确记录。</p></div></header><EvidenceList items={security.admin_audit} type="administrator" /></section>
      <section className="admin-dashboard__evidence" aria-labelledby="realtime-audit-heading"><header><div><h2 id="realtime-audit-heading">实时连接审计</h2><p>最多显示最近五十条房间和连接决策。</p></div></header><EvidenceList items={security.realtime_audit} type="realtime" /></section>
    </section>
  )
}
