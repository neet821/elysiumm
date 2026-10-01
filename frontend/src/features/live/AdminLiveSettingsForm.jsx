import { Save, Unplug } from 'lucide-react'

import { Button, Input } from '../../components/ui'

export default function AdminLiveSettingsForm({
  busy,
  data,
  form,
  onKickPublisher,
  onRotateKey,
  onSave,
  selectedUsers,
  setForm,
  setSelectedUsers,
}) {
  if (!form) return null

  return (
    <section className="admin-live__card admin-live__card--settings">
      <header><Save aria-hidden="true" /><div><h2>开播设置</h2><p>保存后下一位访客立即按新规则进入。</p></div></header>
      <form onSubmit={onSave}>
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
            <Button type="button" onClick={onRotateKey}>更换推流密钥</Button>
            <Button type="button" variant="danger" onClick={onKickPublisher}>
              <Unplug aria-hidden="true" /> 强制断流
            </Button>
          </div>
        </div>
        <Button type="submit" isLoading={busy}>保存设置</Button>
      </form>
    </section>
  )
}
