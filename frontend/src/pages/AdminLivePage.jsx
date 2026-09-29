import { useState } from 'react'
import {
  Copy,
  Link2,
  Radio,
  Save,
  Unplug,
} from 'lucide-react'

import AdminLiveAudiencePanel from '../features/live/AdminLiveAudiencePanel'
import LiveMessageBoard from '../features/live/LiveMessageBoard'
import LivePlayer from '../features/live/LivePlayer'
import useAdminLiveConsole from '../features/live/useAdminLiveConsole'
import useLiveSession from '../features/live/useLiveSession'
import { Button, Dialog, Input } from '../components/ui'


const dateTime = (value) => (
  value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
)


export default function AdminLivePage() {
  const [confirmation, setConfirmation] = useState(null)
  const [inviteHours, setInviteHours] = useState(24)
  const preview = useLiveSession()
  const {
    audienceRefreshedAt,
    busy,
    createInvite,
    data,
    error,
    form,
    historyLoading,
    kickPublisher,
    loadAudienceHistory,
    oneTimeSecret,
    revokeInvite,
    rotateStreamKey,
    runConfirmed: runAction,
    saveSettings,
    selectedUsers,
    setForm,
    setOneTimeSecret,
    setSelectedUsers,
  } = useAdminLiveConsole()

  const runConfirmed = async () => {
    const action = confirmation?.action
    setConfirmation(null)
    await runAction(action)
  }

  const ask = (title, description, confirmLabel, action) => {
    setConfirmation({ action, confirmLabel, description, title })
  }

  const rotateKey = () => ask(
    '确认更换推流密钥',
    '旧密钥会立即失效，正在推流的 OBS 需要填写新密钥。',
    '确认更换',
    rotateStreamKey,
  )

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

      <div className="admin-live__grid">
        <section className="admin-live__card admin-live__card--settings">
          <header><Save aria-hidden="true" /><div><h2>开播设置</h2><p>保存后下一位访客立即按新规则进入。</p></div></header>
          {form && (
            <form onSubmit={saveSettings}>
              <div className="admin-live__title-editor">
                <label className="admin-live__field" htmlFor="admin-live-title">
                  <span>直播名称</span>
                  <input id="admin-live-title" value={form.title || ''} maxLength={160} onChange={(event) => setForm({ ...form, title: event.target.value })} />
                </label>
                <Button type="button" variant="secondary" onClick={() => document.getElementById('admin-live-title')?.focus()}>
                  自定义直播名称
                </Button>
              </div>
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
                      kickPublisher,
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
            <Button onClick={() => createInvite(inviteHours)} isLoading={busy}>创建邀请</Button>
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
                    () => revokeInvite(activeInvite.id),
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

      <div className="admin-live__below-preview">
        <section className="admin-live__card admin-live__admin-messages" aria-label="管理员直播留言">
          <LiveMessageBoard liveSessionId={preview.liveSessionId} readOnly />
        </section>
        <AdminLiveAudiencePanel
          activeViewers={data.status?.active_viewers ?? 0}
          audience={data.audience}
          audienceHistory={data.audienceHistory}
          refreshedAt={audienceRefreshedAt}
          historyLoading={historyLoading}
          loadAudienceHistory={loadAudienceHistory}
        />
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
