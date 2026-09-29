import { useState } from 'react'
import {
  Copy,
  Link2,
  Radio,
} from 'lucide-react'

import AdminLiveAudiencePanel from '../features/live/AdminLiveAudiencePanel'
import AdminLiveSettingsForm from '../features/live/AdminLiveSettingsForm'
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
        <AdminLiveSettingsForm
          busy={busy}
          data={data}
          form={form}
          onKickPublisher={() => ask(
            '确认强制断流',
            'OBS 会立即与服务器断开。',
            '确认断流',
            kickPublisher,
          )}
          onRotateKey={rotateKey}
          onSave={saveSettings}
          selectedUsers={selectedUsers}
          setForm={setForm}
          setSelectedUsers={setSelectedUsers}
        />

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
