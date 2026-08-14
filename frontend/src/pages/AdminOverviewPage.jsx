import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, BookOpen, Database, Files, Music2, RefreshCw, Server, Users, Video } from 'lucide-react'

import { API_ENDPOINTS } from '../config'
import { Button, Card, Skeleton, Tag } from '../components/ui'
import apiClient from '../utils/request'

const formatBytes = (value = 0) => {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

const formatDate = (value) => value ? new Date(value).toLocaleString('zh-CN') : '暂无'
const statusLabel = (value) => ({
  connected: '已连接',
  'database metadata available': '数据库元数据可用',
  healthy: '正常',
  ok: '正常',
  success: '成功',
  completed: '已完成',
  failed: '失败',
  online: '在线',
  offline: '离线',
}[value] || value || '未知')
const failureActionLabel = (value) => ({ upload_rejected: '上传被拒绝' }[value] || '管理员操作失败')
const failureResourceLabel = (value) => ({ sync: '同步服务', sync_device: '同步设备' }[value] || '管理资源')

export default function AdminOverviewPage() {
  const [overview, setOverview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [providerStatus, setProviderStatus] = useState(null)

  const loadOverview = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_OVERVIEW)
      setOverview(response.data)
      Promise.resolve(apiClient.get(API_ENDPOINTS.MUSIC_PROVIDER_STATUS))
        .then((musicStatus) => setProviderStatus(musicStatus?.data || null))
        .catch(() => setProviderStatus(null))
    } catch {
      setError('管理总览暂时无法载入。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadOverview() }, [loadOverview])

  if (loading) return <Skeleton className="admin-dashboard__loading" label="正在载入管理总览" />

  if (error || !overview) {
    return (
      <section className="admin-dashboard admin-dashboard--message">
        <p role="alert">{error || '管理总览暂时无法载入。'}</p>
        <Button onClick={loadOverview} aria-label="重新载入管理总览">重试</Button>
      </section>
    )
  }

  const cards = [
    { label: '用户', value: `${overview.users.total} 位用户`, detail: `${overview.users.active} 位启用 · ${overview.users.administrators} 位管理员`, icon: Users },
    { label: '房间', value: `${overview.rooms.media_active + overview.rooms.game_active} 个活跃房间`, detail: `${overview.rooms.media_active} 个媒体房 · ${overview.rooms.game_active} 个游戏房`, icon: Video },
    { label: '文件', value: `${overview.files.manual_count + overview.files.synced_count} 个受管文件`, detail: `${formatBytes(overview.files.manual_bytes + overview.files.synced_bytes)} · ${overview.files.active_uploads} 个上传任务`, icon: Files },
    { label: '同步', value: `${overview.sync.devices} 台同步设备`, detail: `${overview.sync.online} 台在线 · ${overview.sync.revoked} 台已撤销`, icon: Server },
    { label: '书籍', value: `${overview.books.total} 本书`, detail: `${overview.books.published} 本已发布 · ${overview.books.lists} 个书单`, icon: BookOpen },
    { label: '备份', value: `${overview.backups.jobs} 个备份任务`, detail: overview.backups.latest_status ? `最近状态：${statusLabel(overview.backups.latest_status)}` : '暂无备份任务', icon: Database },
    {
      label: '曲库服务',
      value: providerStatus?.service_available ? 'Mineradio 已连接' : 'Mineradio 未连接',
      detail: `网易云 ${providerStatus?.providers?.netease?.configured ? '已配置' : '未配置'} · QQ 音乐 ${providerStatus?.providers?.qq?.configured ? '已配置' : '未配置'}`,
      icon: Music2,
    },
  ]

  return (
    <section className="admin-dashboard">
      <header className="admin-dashboard__intro">
        <div><p>私有管理空间</p><h1>管理总览</h1><p>查看当前 Blue Album 的用户、房间、文件和服务概况。</p></div>
        <Button variant="secondary" onClick={loadOverview}><RefreshCw size={16} aria-hidden="true" /> 刷新</Button>
      </header>

      <Card className="admin-dashboard__health">
        <div><Server size={20} aria-hidden="true" /><strong>服务状态</strong></div>
        <Tag tone="success">{statusLabel(overview.health.status)}</Tag>
        <span>数据库：{statusLabel(overview.health.database)}</span>
        <span>存储：{statusLabel(overview.health.storage)}</span>
      </Card>

      <div className="admin-dashboard__cards">
        {cards.map(({ label, value, detail, icon: Icon }) => (
          <Card as="article" className="admin-dashboard__card" key={label}>
            <Icon size={19} aria-hidden="true" />
            <p>{label}</p><h2>{value}</h2><span>{detail}</span>
          </Card>
        ))}
      </div>

      <section className="admin-dashboard__evidence" aria-labelledby="recent-failures-heading">
        <header><div><h2 id="recent-failures-heading">最近失败记录</h2><p>最多显示十条经过处理的管理员审计摘要。</p></div><AlertTriangle size={20} aria-hidden="true" /></header>
        {overview.recent_failures.length === 0 ? <p className="admin-dashboard__empty">最近没有失败记录。</p> : (
          <ol>{overview.recent_failures.map((item) => <li key={item.id}><div><strong>{failureActionLabel(item.action)}</strong><span>{failureResourceLabel(item.resource_type)}{item.resource_id ? ` · ${item.resource_id}` : ''}</span></div><div><Tag tone="danger">{statusLabel(item.outcome)}</Tag><time dateTime={item.created_at}>{formatDate(item.created_at)}</time></div></li>)}</ol>
        )}
      </section>
    </section>
  )
}
