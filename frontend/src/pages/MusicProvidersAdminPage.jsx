import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'

import { API_ENDPOINTS } from '../config'
import { Button, Card, Skeleton, Tag } from '../components/ui'
import apiClient from '../utils/request'

const PROVIDERS = [
  { id: 'netease', label: '网易云音乐' },
  { id: 'qq', label: 'QQ 音乐' },
]

const statusLabel = { missing: '未登录', connecting: '连接中', ready: '可用', expired: '已过期', error: '异常' }

export default function MusicProvidersAdminPage() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadStatus = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await apiClient.get(API_ENDPOINTS.MUSIC_PROVIDER_STATUS)
      setStatus(response.data)
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '共享曲库状态暂时无法载入。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadStatus()
  }, [loadStatus])

  if (loading) return <Skeleton className="admin-dashboard__loading" label="正在载入共享曲库状态" />

  return (
    <section className="admin-dashboard">
      <header className="admin-dashboard__intro">
        <div><p>管理员空间</p><h1>共享曲库</h1><p>网易云和 QQ 音乐使用服务器共享账号。凭据由 root 管理的受保护配置文件维护，页面不会显示或删除 Cookie。</p></div>
        <Button variant="secondary" onClick={loadStatus}><RefreshCw size={16} aria-hidden="true" /> 刷新</Button>
      </header>
      {error && <p className="admin-homepage__message admin-homepage__message--error" role="alert">{error}</p>}
      <div className="admin-dashboard__cards">
        {PROVIDERS.map(({ id, label }) => {
          const item = status?.providers?.[id] || {}
          const state = item.status || (item.configured ? 'ready' : 'missing')
          return (
            <Card as="article" className="admin-dashboard__card" key={id}>
              <p>{label}</p>
              <h2><Tag tone={state === 'ready' ? 'success' : state === 'error' ? 'danger' : 'neutral'}>{statusLabel[state] || state}</Tag></h2>
              <span>播放权限会按每首歌实时检查；最近检查：{item.checked_at ? new Date(item.checked_at).toLocaleString('zh-CN') : '暂无'}</span>
              <p className="admin-dashboard__muted">凭据轮换由运维流程执行</p>
            </Card>
          )
        })}
      </div>
    </section>
  )
}
