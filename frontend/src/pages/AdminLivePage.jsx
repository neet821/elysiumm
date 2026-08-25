import { useCallback, useEffect, useState } from 'react'
import {
  Copy,
  ExternalLink,
  KeyRound,
  Link2,
  Radio,
  RefreshCw,
  Save,
  Unplug,
  Users,
  Video,
} from 'lucide-react'

import { API_ENDPOINTS } from '../config'
import AdminLiveAudience from '../features/live/AdminLiveAudience'
import AdminLiveRecordings from '../features/live/AdminLiveRecordings'
import apiClient from '../utils/request'
import { Button, Dialog, Input } from '../components/ui'


const endpointEntries = [
  ['settings', API_ENDPOINTS.ADMIN_LIVE_SETTINGS],
  ['status', API_ENDPOINTS.ADMIN_LIVE_STATUS],
  ['allowedUsers', API_ENDPOINTS.ADMIN_LIVE_ALLOWED_USERS],
  ['invites', API_ENDPOINTS.ADMIN_LIVE_INVITES],
  ['audience', API_ENDPOINTS.ADMIN_LIVE_AUDIENCE],
  ['sessions', API_ENDPOINTS.ADMIN_LIVE_SESSIONS],
  ['recordings', API_ENDPOINTS.ADMIN_LIVE_RECORDINGS],
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
    recordings: [],
    sessions: [],
    settings: null,
    status: null,
    users: [],
  })
  const [form, setForm] = useState(null)
  const [selectedUsers, setSelectedUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmation, setConfirmation] = useState(null)
  const [oneTimeSecret, setOneTimeSecret] = useState(null)
  const [inviteHours, setInviteHours] = useState(24)
  const [renameTarget, setRenameTarget] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [recordingPreview, setRecordingPreview] = useState(null)
  const [audienceRefreshTick, setAudienceRefreshTick] = useState(0)
  const [audienceRefreshedAt, setAudienceRefreshedAt] = useState(null)

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

  const downloadRecording = async (recording) => {
    setBusy(true)
    try {
      const response = await apiClient.get(recording.download_url, {
        responseType: 'blob',
      })
      const objectUrl = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = recording.display_name
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(objectUrl)
    } catch {
      setError('录像下载失败。')
    } finally {
      setBusy(false)
    }
  }

  const previewRecording = async (recording) => {
    setBusy(true)
    try {
      const response = await apiClient.get(recording.download_url, {
        responseType: 'blob',
      })
      setRecordingPreview({
        name: recording.display_name,
        url: URL.createObjectURL(response.data),
      })
    } catch {
      setError('录像播放失败。')
    } finally {
      setBusy(false)
    }
  }

  const closeRecordingPreview = () => {
    if (recordingPreview?.url) URL.revokeObjectURL(recordingPreview.url)
    setRecordingPreview(null)
  }

  const session = data.status?.session

  return (
    <div className="admin-live">
      <header className="admin-live__intro">
        <div>
          <p>直播管理</p>
          <h1>单直播间</h1>
          <span>设置 OBS、观看权限、访客记录和自动录像。</span>
        </div>
        <div>
          <a href="/live?watch=1" target="_blank" rel="noreferrer">
            打开观看页 <ExternalLink aria-hidden="true" />
          </a>
          <Button aria-label="刷新直播管理信息" variant="secondary" onClick={load} isLoading={loading}>
            <RefreshCw aria-hidden="true" /> 刷新
          </Button>
        </div>
      </header>

      {error && <p className="admin-live__error" role="alert">{error}</p>}

      <section className="admin-live__status">
        <div>
          <span className={`admin-live__dot${data.status?.is_live ? ' admin-live__dot--online' : ''}`} />
          <div>
            <p>当前状态</p>
            <strong>{data.status?.is_live ? '正在直播' : '尚未开播'}</strong>
          </div>
        </div>
        <dl>
          <div><dt>观看人数</dt><dd>{data.status?.active_viewers ?? 0}</dd></div>
          <div><dt>开始时间</dt><dd>{dateTime(session?.started_at)}</dd></div>
          <div><dt>画面</dt><dd>{session?.width ? `${session.width} × ${session.height} · ${session.frame_rate || '—'} fps` : '—'}</dd></div>
          <div><dt>编码</dt><dd>{session?.video_codec ? `${session.video_codec} · ${session.audio_codec || '无音频'}` : '—'}</dd></div>
        </dl>
      </section>

      <div className="admin-live__grid">
        <section className="admin-live__card admin-live__card--settings">
          <header><Save aria-hidden="true" /><div><h2>开播设置</h2><p>保存后下一位访客立即按新规则进入。</p></div></header>
          {form && (
            <form onSubmit={saveSettings}>
              <Input label="直播标题" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required />
              <label className="admin-live__field">
                <span>直播简介</span>
                <textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
              </label>
              <Input label="封面地址" type="url" value={form.cover_url || ''} onChange={(event) => setForm({ ...form, cover_url: event.target.value })} />
              <label className="admin-live__field">
                <span>推流画质</span>
                <select value={form.stream_quality || 'balanced'} onChange={(event) => setForm({ ...form, stream_quality: event.target.value })}>
                  <option value="smooth">流畅（优先稳定）</option>
                  <option value="balanced">均衡（推荐）</option>
                  <option value="clear">清晰（优先画面）</option>
                  <option value="source">原画（高带宽）</option>
                </select>
              </label>
              <Input
                label="目标码率（kbps）"
                type="number"
                min="300"
                max="50000"
                value={form.target_bitrate_kbps ?? ''}
                onChange={(event) => setForm({
                  ...form,
                  target_bitrate_kbps: event.target.value,
                })}
                hint="留空时使用 OBS 当前场景默认码率。"
              />
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
              <label className="admin-live__check">
                <input type="checkbox" checked={form.recording_enabled} onChange={(event) => setForm({ ...form, recording_enabled: event.target.checked })} />
                自动录制直播
              </label>
              <p className="admin-live__hint">关闭后当前和后续直播都不会自动录像；磁盘空间不足时会自动暂停。</p>
              <Button type="submit" isLoading={busy}>保存设置</Button>
            </form>
          )}
        </section>

        <section className="admin-live__card">
          <header><KeyRound aria-hidden="true" /><div><h2>OBS 推流</h2><p>永久密钥只显示末六位。</p></div></header>
          <div className="admin-live__credentials">
            <Input label="服务器" value={data.settings?.rtmp_server || ''} readOnly />
            <Input label="当前密钥" value={data.settings?.stream_key_hint ? `••••••${data.settings.stream_key_hint}` : '尚未生成'} readOnly />
          </div>
          <p className="admin-live__hint">
            当前主播配置：{data.settings?.stream_quality || 'balanced'} 画质
            {data.settings?.target_bitrate_kbps ? ` · ${data.settings.target_bitrate_kbps} kbps` : ' · 码率按 OBS 设置'}
            {' · '}
            {data.settings?.latency_mode === 'ultra_low' ? '超低延时' : data.settings?.latency_mode === 'low' ? '低延时' : '标准延时'}
          </p>
          <div className="admin-live__actions">
            <Button onClick={rotateKey}>更换推流密钥</Button>
            <Button
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
        </section>

        <section className="admin-live__card admin-live__card--wide">
          <header><Link2 aria-hidden="true" /><div><h2>邀请链接</h2><p>新链接的完整地址只显示一次。</p></div></header>
          <div className="admin-live__invite-create">
            <Input label="有效小时数" min="1" max="8760" type="number" value={inviteHours} onChange={(event) => setInviteHours(event.target.value)} />
            <Button onClick={createInvite} isLoading={busy}>创建邀请</Button>
          </div>
          <ul className="admin-live__invites">
            {data.invites.map((invite) => (
              <li key={invite.id}>
                <div><strong>尾号 {invite.token_hint}</strong><span>{invite.status} · 到期 {dateTime(invite.expires_at)}</span></div>
                {invite.status === 'active' && (
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => ask(
                      '确认停用邀请',
                      `尾号 ${invite.token_hint} 的链接会立即失效。`,
                      '确认停用',
                      async () => {
                        await apiClient.post(API_ENDPOINTS.ADMIN_LIVE_INVITE_REVOKE(invite.id))
                        await load()
                      },
                    )}
                  >
                    停用
                  </Button>
                )}
              </li>
            ))}
            {!data.invites.length && <li className="admin-live__empty">还没有邀请链接。</li>}
          </ul>
        </section>

        <section className="admin-live__card admin-live__card--wide">
          <header>
            <Users aria-hidden="true" />
            <div><h2>当前在线观众</h2><p>实时刷新当前仍在观看的访客信息和人数。</p></div>
            <Button
              size="sm"
              variant="danger"
              onClick={() => ask(
                '确认清除访客记录',
                '当前列出的观众历史将从数据库删除。',
                '确认清除',
                async () => {
                  await apiClient.delete(API_ENDPOINTS.ADMIN_LIVE_AUDIENCE_HISTORY)
                  await load()
                },
              )}
            >
              清除记录
            </Button>
          </header>
          <AdminLiveAudience audience={data.audience} refreshedAt={audienceRefreshedAt} />
          <p className="admin-live__attribution">
            <a href="https://db-ip.com" target="_blank" rel="noreferrer">
              地区数据由 DB-IP 提供
            </a>
          </p>
        </section>

        <section className="admin-live__card admin-live__card--wide">
          <header><Video aria-hidden="true" /><div><h2>自动录像</h2><p>录像保存在服务器；网盘接入位置已经预留。</p></div></header>
          <AdminLiveRecordings
            recordings={data.recordings}
            onDownload={downloadRecording}
            onPreview={previewRecording}
            onRename={(recording) => {
              setRenameTarget(recording)
              setRenameValue(recording.display_name)
            }}
            onDelete={(recording) => ask(
              '确认删除录像',
              `${recording.display_name} 会从服务器永久删除。`,
              '确认删除',
              async () => {
                await apiClient.delete(API_ENDPOINTS.ADMIN_LIVE_RECORDING(recording.id))
                await load()
              },
            )}
          />
        </section>

        <section className="admin-live__card admin-live__card--wide">
          <header><Radio aria-hidden="true" /><div><h2>直播场次</h2><p>短暂断流会归入同一场，正式结束后才生成下一场。</p></div></header>
          <ul className="admin-live__sessions">
            {data.sessions.map((entry) => (
              <li key={entry.id}>
                <strong>{entry.title}</strong>
                <span>{entry.status === 'live' ? '直播中' : '已结束'} · {dateTime(entry.started_at)} 至 {dateTime(entry.ended_at)}</span>
              </li>
            ))}
            {!data.sessions.length && <li className="admin-live__empty">还没有历史场次。</li>}
          </ul>
        </section>
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

      <Dialog
        open={Boolean(renameTarget)}
        onOpenChange={(open) => !open && setRenameTarget(null)}
        title="修改录像名称"
      >
        <Input label="录像名称" value={renameValue} onChange={(event) => setRenameValue(event.target.value)} />
        <div className="admin-live__dialog-actions">
          <Button variant="secondary" onClick={() => setRenameTarget(null)}>取消</Button>
          <Button onClick={async () => {
            setBusy(true)
            try {
              await apiClient.put(API_ENDPOINTS.ADMIN_LIVE_RECORDING(renameTarget.id), { display_name: renameValue })
              setRenameTarget(null)
              await load()
            } catch {
              setError('录像名称修改失败。')
            } finally {
              setBusy(false)
            }
          }}>保存名称</Button>
        </div>
      </Dialog>

      <Dialog
        open={Boolean(recordingPreview)}
        onOpenChange={(open) => !open && closeRecordingPreview()}
        title={recordingPreview?.name || '录像播放'}
      >
        {recordingPreview && (
          <video
            aria-label={`播放录像 ${recordingPreview.name}`}
            className="admin-live__recording-player"
            controls
            src={recordingPreview.url}
          />
        )}
        <div className="admin-live__dialog-actions">
          <Button onClick={closeRecordingPreview}>关闭</Button>
        </div>
      </Dialog>
    </div>
  )
}
