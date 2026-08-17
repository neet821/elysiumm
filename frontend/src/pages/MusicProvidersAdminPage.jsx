import { useCallback, useEffect, useRef, useState } from 'react'
import { LogIn, LogOut, RefreshCw } from 'lucide-react'

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
  const [login, setLogin] = useState(null)
  const [busy, setBusy] = useState('')
  const [imageUrl, setImageUrl] = useState('')
  const timerRef = useRef(null)
  const imageUrlRef = useRef('')

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
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current)
      if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current)
    }
  }, [loadStatus])

  const stopLogin = useCallback(() => {
    if (timerRef.current) window.clearInterval(timerRef.current)
    timerRef.current = null
    setLogin(null)
    setImageUrl((current) => {
      if (current) URL.revokeObjectURL(current)
      imageUrlRef.current = ''
      return ''
    })
  }, [])

  const pollLogin = useCallback((provider, sessionId) => {
    const poll = async () => {
      try {
        const response = await apiClient.get(API_ENDPOINTS.MUSIC_PROVIDER_LOGIN_STATUS(provider, sessionId))
        const next = response.data
        setLogin(next)
        if (next.status === 'ready' || next.status === 'expired' || next.status === 'error') {
          if (timerRef.current) window.clearInterval(timerRef.current)
          timerRef.current = null
          await loadStatus()
        }
      } catch {
        stopLogin()
        setError('登录任务已失效，请重新开始。')
      }
    }
    poll()
    timerRef.current = window.setInterval(poll, 1500)
  }, [loadStatus, stopLogin])

  const startLogin = async (provider) => {
    stopLogin()
    setBusy(provider)
    setError('')
    try {
      const response = await apiClient.post(API_ENDPOINTS.MUSIC_PROVIDER_LOGIN_START(provider))
      const next = response.data
      setLogin(next)
      if (provider === 'netease' || provider === 'qq') {
        const imageResponse = await apiClient.get(API_ENDPOINTS.MUSIC_PROVIDER_LOGIN_IMAGE(provider, next.session_id), { responseType: 'blob' })
        const nextImageUrl = URL.createObjectURL(imageResponse.data)
        imageUrlRef.current = nextImageUrl
        setImageUrl(nextImageUrl)
      }
      pollLogin(provider, next.session_id)
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '登录任务无法启动，请检查 Mineradio 和受控浏览器。')
    } finally {
      setBusy('')
    }
  }

  const logout = async (provider) => {
    setBusy(provider)
    try {
      await apiClient.delete(API_ENDPOINTS.MUSIC_PROVIDER_CREDENTIAL(provider))
      await loadStatus()
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '退出共享账号失败。')
    } finally {
      setBusy('')
    }
  }

  if (loading) return <Skeleton className="admin-dashboard__loading" label="正在载入共享曲库状态" />

  return (
    <section className="admin-dashboard">
      <header className="admin-dashboard__intro">
        <div><p>管理员空间</p><h1>共享曲库</h1><p>网易云和 QQ 音乐使用服务器共享账号。登录信息只保存在 Mineradio，页面不会显示 Cookie。</p></div>
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
              <div className="admin-live__actions">
                <Button size="sm" onClick={() => startLogin(id)} isLoading={busy === id}><LogIn size={15} aria-hidden="true" /> 重新登录</Button>
                <Button size="sm" variant="danger" onClick={() => logout(id)} isLoading={busy === id}><LogOut size={15} aria-hidden="true" /> 退出</Button>
              </div>
            </Card>
          )
        })}
      </div>
      {login && (
        <Card className="admin-dashboard__evidence" aria-live="polite">
          <header><div><h2>{login.provider === 'qq' ? 'QQ 音乐' : '网易云音乐'} 登录</h2><p>{login.message || '请扫码登录'} · {login.status}</p></div><Button variant="secondary" onClick={stopLogin}>关闭</Button></header>
          {imageUrl && login.status === 'pending' && <img src={imageUrl} alt="登录二维码" style={{ width: 280, maxWidth: '100%', imageRendering: 'auto' }} />}
          {login.status === 'pending' && <p>二维码五分钟内有效。登录成功后会自动关闭任务。</p>}
        </Card>
      )}
    </section>
  )
}
