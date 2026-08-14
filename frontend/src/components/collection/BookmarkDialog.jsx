import { useEffect, useState } from 'react'

import { Button, Dialog, Input } from '../ui/index.js'

const emptyBookmark = {
  title: '',
  url: '',
  description: '',
  folder_id: '',
  preview_url: '',
  tags: '',
  is_public: false,
  is_pinned: false,
  show_description: true,
  show_preview: true,
  show_visit_count: false,
  allow_indexing: false,
}

function initialValue(bookmark, selectedFolderId) {
  if (!bookmark) {
    return { ...emptyBookmark, folder_id: selectedFolderId ? String(selectedFolderId) : '' }
  }
  return {
    title: bookmark.title || '',
    url: bookmark.url || '',
    description: bookmark.description || '',
    folder_id: bookmark.folder_id ? String(bookmark.folder_id) : '',
    preview_url: bookmark.preview_url || '',
    tags: (bookmark.tags || []).join(', '),
    is_public: Boolean(bookmark.is_public),
    is_pinned: Boolean(bookmark.is_pinned),
    show_description: Boolean(bookmark.show_description),
    show_preview: Boolean(bookmark.show_preview),
    show_visit_count: Boolean(bookmark.show_visit_count),
    allow_indexing: Boolean(bookmark.allow_indexing),
  }
}

function splitTags(value) {
  return [...new Set(value.split(/[,，\n]/).map((tag) => tag.trim()).filter(Boolean))]
}

export default function BookmarkDialog({ bookmark, error, folders, onOpenChange, onSave, open, selectedFolderId }) {
  const [form, setForm] = useState(emptyBookmark)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) setForm(initialValue(bookmark, selectedFolderId))
  }, [bookmark, open, selectedFolderId])

  const setField = (field, value) => setForm((current) => ({ ...current, [field]: value }))

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    try {
      await onSave({
        title: form.title.trim(),
        url: form.url.trim(),
        description: form.description.trim() || null,
        folder_id: form.folder_id ? Number(form.folder_id) : null,
        preview_url: form.preview_url.trim() || null,
        tags: splitTags(form.tags),
        is_public: form.is_public,
        is_pinned: form.is_pinned,
        show_description: form.show_description,
        show_preview: form.show_preview,
        show_visit_count: form.show_visit_count,
        allow_indexing: form.allow_indexing,
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
      title={bookmark ? '编辑收藏' : '新建收藏'}
      description="默认私密，公开范围需要明确开启。"
    >
      <form className="collection-form" onSubmit={submit}>
        {error && <p className="collection-form__error" role="alert">{error}</p>}
        <div className="collection-form__grid">
          <Input label="标题" aria-label="标题" required maxLength={200} value={form.title} onChange={(event) => setField('title', event.target.value)} />
          <Input label="网址" aria-label="网址" required type="url" maxLength={1000} value={form.url} onChange={(event) => setField('url', event.target.value)} />
          <label className="collection-select-field">
            <span>文件夹</span>
            <select value={form.folder_id} onChange={(event) => setField('folder_id', event.target.value)}>
              <option value="">未归档</option>
              {folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}
            </select>
          </label>
          <Input label="预览图地址" type="url" maxLength={1000} value={form.preview_url} onChange={(event) => setField('preview_url', event.target.value)} />
          <Input className="collection-form__wide" label="标签" hint="用逗号分隔标签。" value={form.tags} onChange={(event) => setField('tags', event.target.value)} />
          <label className="collection-textarea-field collection-form__wide">
            <span>描述</span>
            <textarea rows="4" maxLength={4000} value={form.description} onChange={(event) => setField('description', event.target.value)} />
          </label>
        </div>
        <fieldset className="collection-form__toggles">
          <legend>可见范围与显示方式</legend>
          {[
            ['is_public', '设为公开'],
            ['is_pinned', '固定在首页'],
            ['show_description', '显示描述'],
            ['show_preview', '显示预览图'],
            ['show_visit_count', '显示访问次数'],
            ['allow_indexing', '允许搜索引擎收录'],
          ].map(([field, label]) => (
            <label key={field}>
              <input type="checkbox" checked={form[field]} onChange={(event) => setField(field, event.target.checked)} />
              <span>{label}</span>
            </label>
          ))}
        </fieldset>
        <div className="collection-form__actions">
          <Button type="submit" isLoading={saving}>保存收藏</Button>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
        </div>
      </form>
    </Dialog>
  )
}
