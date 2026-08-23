import { useEffect, useState } from 'react'

import { Button, Dialog, Input } from '../ui/index.js'

function initialValue(folder) {
  return {
    name: folder?.name || '',
    parent_id: folder?.parent_id ? String(folder.parent_id) : '',
    icon: folder?.icon || '',
    color: folder?.color || '',
    is_sensitive: Boolean(folder?.is_sensitive),
    is_public: Boolean(folder?.is_public),
  }
}

export default function FolderDialog({ error, folder, folders, onOpenChange, onSave, open }) {
  const [form, setForm] = useState(initialValue(null))
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) setForm(initialValue(folder))
  }, [folder, open])

  const setField = (field, value) => setForm((current) => ({ ...current, [field]: value }))
  const availableParents = folders.filter((candidate) => candidate.id !== folder?.id)

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    try {
      await onSave({
        name: form.name.trim(),
        parent_id: form.parent_id ? Number(form.parent_id) : null,
        icon: form.icon.trim() || null,
        color: form.color.trim() || null,
        is_sensitive: form.is_sensitive,
        is_public: form.is_public,
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog
      className="collection-form-dialog"
      open={open}
      onOpenChange={onOpenChange}
      title={folder ? '编辑文件夹' : '新建文件夹'}
      description="子文件夹会继承敏感内容保护。"
    >
      <form className="collection-form" onSubmit={submit}>
        {error && <p className="collection-form__error" role="alert">{error}</p>}
        <div className="collection-form__grid">
          <Input label="名称" required maxLength={100} value={form.name} onChange={(event) => setField('name', event.target.value)} />
          <label className="collection-select-field">
            <span>上级文件夹</span>
            <select value={form.parent_id} onChange={(event) => setField('parent_id', event.target.value)}>
              <option value="">根目录</option>
              {availableParents.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}
            </select>
          </label>
          <Input label="图标" maxLength={50} value={form.icon} onChange={(event) => setField('icon', event.target.value)} />
          <Input label="颜色" type="text" pattern="#[0-9A-Fa-f]{6}" placeholder="#315B7D" value={form.color} onChange={(event) => setField('color', event.target.value)} />
        </div>
        <fieldset className="collection-form__toggles">
          <legend>文件夹可见范围</legend>
          <label>
            <input type="checkbox" checked={form.is_sensitive} onChange={(event) => setField('is_sensitive', event.target.checked)} />
            <span>敏感文件夹</span>
          </label>
          <label>
            <input type="checkbox" checked={form.is_public} onChange={(event) => setField('is_public', event.target.checked)} />
            <span>公开文件夹名称</span>
          </label>
        </fieldset>
        <div className="collection-form__actions">
          <Button type="submit" isLoading={saving}>保存文件夹</Button>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
        </div>
      </form>
    </Dialog>
  )
}
