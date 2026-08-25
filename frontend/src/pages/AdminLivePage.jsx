import { useCallback, useEffect, useState } from 'react'
import {
  Copy,
  Link2,
  Radio,
  Save,
  Unplug,
  Users,
} from 'lucide-react'

import { API_ENDPOINTS } from '../config'
import AdminLiveAudience from '../features/live/AdminLiveAudience'
import LiveMessageBoard from '../features/live/LiveMessageBoard'
import LivePlayer from '../features/live/LivePlayer'
import useLiveSession from '../features/live/useLiveSession'
import apiClient from '../utils/request'
import { Button, Dialog, Input } from '../components/ui'


const endpointEntries = [
  ['settings', API_ENDPOINTS.ADMIN_LIVE_SETTINGS],
  ['status', API_ENDPOINTS.ADMIN_LIVE_STATUS],
  ['allowedUsers', API_ENDPOINTS.ADMIN_LIVE_ALLOWED_USERS],
  ['invites', API_ENDPOINTS.ADMIN_LIVE_INVITES],
  ['audience', API_ENDPOINTS.ADMIN_LIVE_AUDIENCE],
  ['sessions', API_ENDPOINTS.ADMIN_LIVE_SESSIONS],
  ['users', API_ENDPOINTS.ADMIN_USERS],
]

const dateTime = (value) => (
  value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
)


export default function AdminLivePage() {
  const [data, setData] = useState({
    allowedUsers: [],
    audience: [],
    invites: [],
    sessions: [],
    settings: null,
    status: null,
    users: [],
  })
  const [form, setForm] = useState(null)
  const [selectedUsers, setSelectedUsers] = useState([])
  const [, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmation, setConfirmation] = useState(null)
  const [oneTimeSecret, setOneTimeSecret] = useState(null)
  const [inviteHours, setInviteHours] = useState(24)
  const [audienceRefreshTick, setAudienceRefreshTick] = useState(0)
  const [audienceRefreshedAt, setAudienceRefreshedAt] = useState(null)
  const [audienceExpanded, setAudienceExpanded] = useState(false)
  const [messagesExpanded, setMessagesExpanded] = useState(false)
  const preview = useLiveSession()

  const load = useCallback(async () => {
    setLoading(true)
    const results = await Promise.allSettled(
      endpointEntries.map(([, endpoint]) => apiClient.get(endpoint)),
    )
    const failures = []
    setData((current) => {
      const next = { ...current }
      results.forEach((result, index) => {
        const [key] = endpointEntries[index]
        if (result.status === 'fulfilled') next[key] = result.value.data
        else failures.push(key)
      })
      return next
    })
    const audienceIndex = endpointEntries.findIndex(([key]) => key === 'audience')
    if (results[audienceIndex]?.status === 'fulfilled') {
      setAudienceRefreshedAt(new Date())
    }
    setError(failures.length ? `部分信息刷新失败（${new Date().toLocaleTimeString('zh-CN', { hour12: false })}）` : '')
    setLoading(false)
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const timer = window.setInterval(() => {
      setAudienceRefreshTick((value) => value + 1)
    }, 5000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    let cancelled = false
    const refreshAudience = async () => {
      try {
        const response = await apiClient.get(API_ENDPOINTS.ADMIN_LIVE_AUDIENCE, {
          params: {
            session_id: data.status?.session?.id || undefined,
            limit: 200,
          },
        })
        if (!cancelled) {
          setData((current) => ({ ...current, audience: response.data }))
          setAudienceRefreshedAt(new Date())
        }
      } catch {
        if (!cancelled) setError('在线观众刷新失败。')
      }
    }
    refreshAudience()
    return () => {
      cancelled = true
    }
  }, [audienceRefreshTick, data.status?.session?.id])

  useEffect(() => {
    if (data.settings) setForm({ ...data.settings })
  }, [data.settings])

  useEffect(() => {
    setSelectedUsers(data.allowedUsers.map((entry) => entry.user_id))
  }, [data.allowedUsers])

  const runConfirmed = async () => {
    const action = confirmation?.action
    setConfirmation(null)
    if (!action) return
    setBusy(true)
    try {
      await action()
    } catch {
      setError('操作没有完成，请稍后重试。')
    } finally {
      setBusy(false)
    }
  }

  const ask = (title, description, confirmLabel, action) => {
    setConfirmation({ action, confirmLabel, description, title })
  }

  const rotateKey = () => ask(
    '确认更换推流密钥',
    '旧密钥会立即失效，正在推流的 OBS 需要填写新密钥。',
    '确认更换',
    async () => {
      const response = await apiClient.post(API_ENDPOINTS.ADMIN_LIVE_STREAM_KEY_ROTATE)
      setOneTimeSecret({
        label: 'OBS 推流密钥',
        title: '新推流密钥',
        value: response.data.obs_stream_key,
      })
      await load()
    },
  )

  const saveSettings = async (event) => {
    event.preventDefault()
    if (!form) return
    setBusy(true)
    try {
      await apiClient.put(API_ENDPOINTS.ADMIN_LIVE_SETTINGS, {
        access_mode: form.access_mode,
        cover_url: form.cover_url || null,
        description: form.description,
        latency_mode: form.latency_mode,
        recording_enabled: form.recording_enabled,
        revision: form.revision,
        stream_quality: form.stream_quality,
        target_bitrate_kbps: form.target_bitrate_kbps ? Number(form.target_bitrate_kbps) : null,
        title: form.title,
        viewing_enabled: form.viewing_enabled,
      })
      await apiClient.put(API_ENDPOINTS.ADMIN_LIVE_ALLOWED_USERS, {
        user_ids: selectedUsers,
      })
      await load()
    } catch (requestError) {
      setError(requestError?.response?.status === 409 ? '设置已在其他页面更新，请刷新后再保存。' : '设置保存失败。')
    } finally {
      setBusy(false)
    }
  }

  const createInvite = async () => {
    setBusy(true)
    try {
      const response = await apiClient.post(API_ENDPOINTS.ADMIN_LIVE_INVITES, {
        expires_in_hours: Number(inviteHours),
      })
      setOneTimeSecret({
        label: '邀请链接',
        title: '新邀请链接',
        value: response.data.invite_url,
      })
      await load()
    } catch {
      setError('邀请链接创建失败。')
    } finally {
      setBusy(false)
    }
  }

  const copySecret = async () => {
    if (!oneTimeSecret?.value) return
    await navigator.clipboard?.writeText(oneTimeSecret.value)
  }

  const activeInvite = data.invites.find((invite) => invite.status === 'active')

  return (
    <div className="admin-live">
      {error && <p className="admin-live__error" role="alert">{error}</p>}

      <section className="admin-live__preview" aria-label="直播预览">
        {preview.state === 'live' && preview.mediaUrl ? (
          <LivePlayer mediaUrl={preview.mediaUrl} minimal onRefresh={preview.retry} />
        ) : (
          <div className="admin-live__preview-empty">未开播</div>
        )}
      </section>

      <section className="admin-live__status">
        <div>
          <span className={`admin-live__dot${data.status?.is_live ? ' admin-live__dot--online' : ''}`} />
          <div>
            <p>当前状态</p>
            <strong>{data.status?.is_live ? '正在直播' : '尚未开播'}</strong>
          </div>
        </div>
        <dl>
          <div>
            <button
              type="button"
              className="admin-live__viewer-toggle"
              aria-expanded={audienceExpanded}
              aria-label={`观看人数：${data.status?.active_viewers ?? 0}`}
              onClick={() => setAudienceExpanded((open) => !open)}
            >
              <dt>观看人数</dt>
              <dd>{data.status?.active_viewers ?? 0}</dd>
            </button>
          </div>
        </dl>
      </section>

      <div className="admin-live__grid">
        <section className="admin-live__card admin-live__card--wide admin-live__messages-control">
          <Button
            type="button"
            aria-expanded={messagesExpanded}
            aria-pressed={messagesExpanded}
            onClick={() => setMessagesExpanded((open) => !open)}
          >
            留言
          </Button>
          {messagesExpanded && <LiveMessageBoard />}
        </section>
        {audienceExpanded && (
          <section className="admin-live__card admin-live__card--wide" aria-label="当前在线观众">
            <header>
              <Users aria-hidden="true" />
              <div><h2>当前在线观众</h2><p>实时查看正在观看的用户信息。</p></div>
            </header>
            <AdminLiveAudience audience={data.audience} refreshedAt={audienceRefreshedAt} />
            <p className="admin-live__attribution">
              <a href="https://db-ip.com" target="_blank" rel="noreferrer">
                地区数据由 DB-IP 提供
              </a>
            </p>
          </section>
        )}
        <section className="admin-live__card admin-live__card--settings">
          <header><Save aria-hidden="true" /><div><h2>开播设置</h2><p>保存后下一位访客立即按新规则进入。</p></div></header>
          {form && (
            <form onSubmit={saveSettings}>
              <label className="admin-live__field">
                <span>推流画质</span>
                <select value={form.stream_quality || 'balanced'} onChange={(event) => setForm({ ...form, stream_quality: event.target.value })}>
                  <option value="smooth">流畅（优先稳定）</option>
                  <option value="balanced">均衡（推荐）</option>
                  <option value="clear">清晰（优先画面）</option>
                  <option value="source">原画（高带宽）</option>
                </select>
              </label>
              <label className="admin-live__field">
                <span>直播延时</span>
                <select value={form.latency_mode || 'normal'} onChange={(event) => setForm({ ...form, latency_mode: event.target.value })}>
                  <option value="normal">标准（约 5–10 秒）</option>
                  <option value="low">低延时（约 4–8 秒）</option>
                  <option value="ultra_low">超低延时（约 2–4 秒）</option>
                </select>
              </label>
              <label className="admin-live__field">
                <span>观看方式</span>
                <select value={form.access_mode} onChange={(event) => setForm({ ...form, access_mode: event.target.value })}>
                  <option value="public">公开观看</option>
                  <option value="allowlist">仅指定用户</option>
                  <option value="invite">仅邀请链接</option>
                </select>
              </label>
              {form.access_mode === 'allowlist' && (
                <fieldset className="admin-live__users">
                  <legend>开放用户</legend>
                  {data.users.filter((user) => user.is_active).map((user) => (
                    <label key={user.id}>
                      <input
                        type="checkbox"
                        checked={selectedUsers.includes(user.id)}
                        onChange={(event) => setSelectedUsers((current) => (
                          event.target.checked
                            ? [...current, user.id]
                            : current.filter((id) => id !== user.id)
                        ))}
                      />
                      {user.username}
                    </label>
                  ))}
                </fieldset>
              )}
              <label className="admin-live__check">
                <input type="checkbox" checked={form.viewing_enabled} onChange={(event) => setForm({ ...form, viewing_enabled: event.target.checked })} />
                允许访客观看
              </label>
              <div className="admin-live__credentials admin-live__credentials--embedded">
                <Input label="OBS 服务器" value={data.settings?.rtmp_server || ''} readOnly />
                <Input label="OBS 当前密钥" value={data.settings?.stream_key_hint ? `••••••${data.settings.stream_key_hint}` : '尚未生成'} readOnly />
                <div className="admin-live__actions">
                  <Button type="button" onClick={rotateKey}>更换推流密钥</Button>
                  <Button
                    type="button"
                    variant="danger"
                    onClick={() => ask(
                      '确认强制断流',
                      'OBS 会立即与服务器断开。',
                      '确认断流',
                      async () => {
                        await apiClient.post(API_ENDPOINTS.ADMIN_LIVE_KICK)
                        await load()
                      },
                    )}
                  >
                    <Unplug aria-hidden="true" /> 强制断流
                  </Button>
                </div>
              </div>
              <Button type="submit" isLoading={busy}>保存设置</Button>
            </form>
          )}
        </section>

        {form?.access_mode === 'invite' && (
        <section className="admin-live__card admin-live__card--wide">
          <header><Link2 aria-hidden="true" /><div><h2>邀请链接</h2><p>新链接的完整地址只显示一次。</p></div></header>
          {!activeInvite && <div className="admin-live__invite-create">
            <Input label="有效小时数" min="1" max="8760" type="number" value={inviteHours} onChange={(event) => setInviteHours(event.target.value)} />
            <Button onClick={createInvite} isLoading={busy}>创建邀请</Button>
          </div>}
          <ul className="admin-live__invites">
            {activeInvite && (
              <li key={activeInvite.id}>
                <div><strong>尾号 {activeInvite.token_hint}</strong><span>有效 · 到期 {dateTime(activeInvite.expires_at)}</span></div>
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() => ask(
                    '确认停用邀请',
                    `尾号 ${activeInvite.token_hint} 的链接会立即失效。`,
                    '确认停用',
                    async () => {
                      await apiClient.post(API_ENDPOINTS.ADMIN_LIVE_INVITE_REVOKE(activeInvite.id))
                      await load()
                    },
                  )}
                >
                  停用
                </Button>
              </li>
            )}
            {!activeInvite && (
              <li className="admin-live__empty">还没有有效邀请链接。</li>
            )}
          </ul>
        </section>
        )}

        <details className="admin-live__card admin-live__card--sessions admin-live__sessions-card">
          <summary><Radio aria-hidden="true" /><div><strong>直播场次</strong><span>短暂断流会归入同一场，正式结束后才生成下一场。</span></div></summary>
          <ul className="admin-live__sessions">
            {data.sessions.map((entry) => (
              <li key={entry.id}>
                <strong>{entry.title}</strong>
                <span>{entry.status === 'live' ? '直播中' : '已结束'} · {dateTime(entry.started_at)} 至 {dateTime(entry.ended_at)}</span>
              </li>
            ))}
            {!data.sessions.length && <li className="admin-live__empty">还没有历史场次。</li>}
          </ul>
        </details>
      </div>

      <Dialog
        open={Boolean(confirmation)}
        onOpenChange={(open) => !open && setConfirmation(null)}
        title={confirmation?.title || ''}
        description={confirmation?.description}
      >
        <div className="admin-live__dialog-actions">
          <Button variant="secondary" onClick={() => setConfirmation(null)}>取消</Button>
          <Button variant="danger" onClick={runConfirmed}>{confirmation?.confirmLabel}</Button>
        </div>
      </Dialog>

      <Dialog
        open={Boolean(oneTimeSecret)}
        onOpenChange={(open) => !open && setOneTimeSecret(null)}
        title={oneTimeSecret?.title || ''}
        description="请立即复制并保存；完整内容仅显示这一次。"
      >
        <Input label={oneTimeSecret?.label} value={oneTimeSecret?.value || ''} readOnly />
        <div className="admin-live__dialog-actions">
          <Button variant="secondary" aria-label={`复制${oneTimeSecret?.label || '内容'}`} onClick={copySecret}>
            <Copy aria-hidden="true" /> 复制
          </Button>
          <Button onClick={() => setOneTimeSecret(null)}>关闭</Button>
        </div>
      </Dialog>

    </div>
  )
}
