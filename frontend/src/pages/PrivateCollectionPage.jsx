import {
  ArrowUpRight,
  Bookmark,
  CheckSquare,
  Copy,
  FolderInput,
  LayoutGrid,
  Pencil,
  Plus,
  Search,
  Settings2,
  Star,
  Trash2,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import BookmarkDialog from '../components/collection/BookmarkDialog.jsx'
import CollectionTransferPanel from '../components/collection/CollectionTransferPanel.jsx'
import FolderDialog from '../components/collection/FolderDialog.jsx'
import FolderTree from '../components/collection/FolderTree.jsx'
import { Button, Card, EmptyState, Input, Skeleton, Tabs, Tag } from '../components/ui/index.js'
import { API_ENDPOINTS } from '../config.js'
import apiClient from '../utils/request.js'

function errorMessage(error, fallback) {
  return error?.response?.data?.detail || error?.message || fallback
}

function formatVisit(value) {
  if (!value) return '从未打开'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '从未打开'
  return new Intl.DateTimeFormat('zh-CN', { day: '2-digit', month: 'short', year: 'numeric' }).format(date)
}

function BookmarkCard({ bookmark, onEdit, onOpen, onSelect, selected }) {
  return (
    <Card as="article" className="private-bookmark-card" interactive>
      <div className="private-bookmark-card__topline">
        <label className="private-bookmark-card__select">
          <input
            type="checkbox"
            checked={selected}
            aria-label={`选择 ${bookmark.title}`}
            onChange={(event) => onSelect(bookmark.id, event.target.checked)}
          />
        </label>
        <div className="private-bookmark-card__badges">
          {bookmark.is_pinned && <Star size={14} fill="currentColor" aria-label="已置顶" />}
          <Tag tone={bookmark.is_public ? 'success' : 'neutral'}>
            {bookmark.is_public ? '公开' : '私人'}
          </Tag>
        </div>
      </div>
      <h3>{bookmark.title}</h3>
      <p className="private-bookmark-card__url">{bookmark.url}</p>
      {bookmark.description && <p className="private-bookmark-card__description">{bookmark.description}</p>}
      {bookmark.tags?.length > 0 && (
        <div className="private-bookmark-card__tags">
          {bookmark.tags.map((tag) => <Tag key={tag} tone="info">{tag}</Tag>)}
        </div>
      )}
      <div className="private-bookmark-card__stats">
        <span>访问 {bookmark.visit_count || 0} 次</span>
        <span>{formatVisit(bookmark.last_visited_at)}</span>
      </div>
      <div className="private-bookmark-card__actions">
        <Button size="sm" onClick={() => onOpen(bookmark)}>
          <ArrowUpRight size={14} aria-hidden="true" /> 打开 {bookmark.title}
        </Button>
        <Button size="sm" variant="ghost" aria-label={`编辑 ${bookmark.title}`} onClick={() => onEdit(bookmark)}>
          <Pencil size={14} aria-hidden="true" /> 编辑
        </Button>
      </div>
    </Card>
  )
}

function StartPage({ bookmarks, engines, onOpen }) {
  const [query, setQuery] = useState('')
  const enabledEngines = engines.filter((engine) => engine.is_enabled)
  const pinned = bookmarks.filter((bookmark) => bookmark.is_pinned)

  const searchWith = (engine) => {
    const normalized = query.trim()
    if (!normalized) return
    const target = engine.url_template.replaceAll('{query}', encodeURIComponent(normalized))
    window.open(target, '_blank', 'noopener,noreferrer')
  }

  return (
    <section className="collection-start-page" aria-labelledby="collection-start-title">
      <div className="collection-start-page__search">
        <div>
          <p className="route-shell__eyebrow">私人起始页</p>
          <h2 id="collection-start-title">起始页</h2>
        </div>
        <Input
          label="起始页搜索"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索网络"
        />
        <div className="collection-start-page__engines">
          {enabledEngines.map((engine) => (
            <Button key={engine.id} variant="secondary" onClick={() => searchWith(engine)}>
              <Search size={15} aria-hidden="true" /> 使用 {engine.name} 搜索
            </Button>
          ))}
          {enabledEngines.length === 0 && <p>还没有启用的搜索引擎。</p>}
        </div>
      </div>
      <div className="collection-start-page__pinned">
        <h3>置顶收藏</h3>
        {pinned.length > 0 ? (
          <div className="collection-start-page__grid">
            {pinned.map((bookmark) => (
              <Card key={bookmark.id} className="collection-start-card">
                <Star size={16} fill="currentColor" aria-hidden="true" />
                <strong>{bookmark.title}</strong>
                <span>{bookmark.description || bookmark.url}</span>
                <Button size="sm" onClick={() => onOpen(bookmark)}>
                  打开 {bookmark.title}
                </Button>
              </Card>
            ))}
          </div>
        ) : (
          <p>将收藏设为置顶后会显示在这里。</p>
        )}
      </div>
    </section>
  )
}

function SearchEnginesPanel({ engines, error, onDelete, onSave }) {
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)

  const openForm = (engine = null) => {
    setEditing(engine)
    setForm({
      name: engine?.name || '',
      url_template: engine?.url_template || '',
      category: engine?.category || 'general',
      category_label: engine?.category_label || '',
      icon: engine?.icon || '',
      is_enabled: engine ? Boolean(engine.is_enabled) : true,
    })
  }

  const setField = (field, value) => setForm((current) => ({ ...current, [field]: value }))

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    try {
      const saved = await onSave(editing, {
        ...form,
        name: form.name.trim(),
        url_template: form.url_template.trim(),
        category: form.category.trim(),
        category_label: form.category_label.trim() || null,
        icon: form.icon.trim() || null,
      })
      if (saved) {
        setEditing(null)
        setForm(null)
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="collection-engines" aria-labelledby="collection-engines-title">
      <header>
        <div>
          <p className="route-shell__eyebrow">仅自己可见的设置</p>
          <h2 id="collection-engines-title">搜索引擎</h2>
          <p>搜索模板保持私密，并且必须包含 <code>{'{query}'}</code>。</p>
        </div>
        <Button onClick={() => openForm()}><Plus size={15} aria-hidden="true" /> 添加搜索引擎</Button>
      </header>
      {error && <p className="collection-action-error" role="alert">{error}</p>}
      {form && (
        <form className="collection-engine-form" onSubmit={submit}>
          <Input label="搜索引擎名称" aria-label="搜索引擎名称" required value={form.name} onChange={(event) => setField('name', event.target.value)} />
          <Input label="搜索网址模板" aria-label="搜索网址模板" required hint="例如：https://example.com/search?q={query}" value={form.url_template} onChange={(event) => setField('url_template', event.target.value)} />
          <Input label="分类" aria-label="分类" required value={form.category} onChange={(event) => setField('category', event.target.value)} />
          <Input label="分类显示名称" value={form.category_label} onChange={(event) => setField('category_label', event.target.value)} />
          <label className="collection-checkbox-field">
            <input type="checkbox" checked={form.is_enabled} onChange={(event) => setField('is_enabled', event.target.checked)} />
            <span>在起始页启用</span>
          </label>
          <div className="collection-engine-form__actions">
            <Button type="submit" isLoading={saving}>保存搜索引擎</Button>
            <Button variant="ghost" onClick={() => setForm(null)}>取消</Button>
          </div>
        </form>
      )}
      <div className="collection-engines__list">
        {engines.map((engine) => (
          <Card key={engine.id} as="article" className="collection-engine-card">
            <div>
              <strong>{engine.name}</strong>
              <span>{engine.category_label || engine.category}</span>
            </div>
            <code>{engine.url_template}</code>
            <Tag tone={engine.is_enabled ? 'success' : 'neutral'}>{engine.is_enabled ? '已启用' : '已停用'}</Tag>
            <span className="collection-engine-card__actions">
              <Button size="sm" variant="ghost" onClick={() => openForm(engine)}>编辑</Button>
              <Button size="sm" variant="danger" onClick={() => onDelete(engine)}>删除</Button>
            </span>
          </Card>
        ))}
        {engines.length === 0 && <p>还没有配置搜索引擎。</p>}
      </div>
    </section>
  )
}

export default function PrivateCollectionPage() {
  const [folders, setFolders] = useState([])
  const [bookmarks, setBookmarks] = useState([])
  const [engines, setEngines] = useState([])
  const [selectedFolderId, setSelectedFolderId] = useState(null)
  const [selectedIds, setSelectedIds] = useState([])
  const [bulkDestination, setBulkDestination] = useState('')
  const [sort, setSort] = useState('manual')
  const [draftQuery, setDraftQuery] = useState('')
  const [query, setQuery] = useState('')
  const [view, setView] = useState('workspace')
  const [loading, setLoading] = useState(true)
  const [bookmarksLoading, setBookmarksLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const [bookmarkDialogOpen, setBookmarkDialogOpen] = useState(false)
  const [editingBookmark, setEditingBookmark] = useState(null)
  const [bookmarkError, setBookmarkError] = useState('')
  const [folderDialogOpen, setFolderDialogOpen] = useState(false)
  const [editingFolder, setEditingFolder] = useState(null)
  const [folderError, setFolderError] = useState('')
  const [reloadVersion, setReloadVersion] = useState(0)

  const loadFoldersAndEngines = useCallback(async () => {
    const [folderResponse, engineResponse] = await Promise.all([
      apiClient.get(API_ENDPOINTS.BOOKMARK_FOLDERS),
      apiClient.get(API_ENDPOINTS.SEARCH_ENGINES),
    ])
    setFolders(Array.isArray(folderResponse.data) ? folderResponse.data : [])
    setEngines(Array.isArray(engineResponse.data) ? engineResponse.data : [])
  }, [])

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError('')
    loadFoldersAndEngines().catch((error) => {
      if (active) setLoadError(errorMessage(error, '收藏设置暂时无法载入。'))
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => {
      active = false
    }
  }, [loadFoldersAndEngines, reloadVersion])

  useEffect(() => {
    let active = true
    setBookmarksLoading(true)
    setLoadError('')
    const params = {
      ...(query ? { q: query } : {}),
      ...(selectedFolderId ? { folder_id: selectedFolderId } : {}),
      sort,
    }
    apiClient.get(API_ENDPOINTS.BOOKMARKS, { params }).then((response) => {
      if (!active) return
      const next = Array.isArray(response.data) ? response.data : []
      setBookmarks(next)
      setSelectedIds((current) => current.filter((id) => next.some((bookmark) => bookmark.id === id)))
    }).catch((error) => {
      if (active) setLoadError(errorMessage(error, '收藏暂时无法载入。'))
    }).finally(() => {
      if (active) setBookmarksLoading(false)
    })
    return () => {
      active = false
    }
  }, [query, reloadVersion, selectedFolderId, sort])

  const refresh = () => setReloadVersion((value) => value + 1)

  const openNewBookmark = () => {
    setEditingBookmark(null)
    setBookmarkError('')
    setBookmarkDialogOpen(true)
  }

  const openEditBookmark = (bookmark) => {
    setEditingBookmark(bookmark)
    setBookmarkError('')
    setBookmarkDialogOpen(true)
  }

  const saveBookmark = async (payload) => {
    setBookmarkError('')
    try {
      if (editingBookmark) {
        await apiClient.put(API_ENDPOINTS.BOOKMARK_DETAIL(editingBookmark.id), payload)
      } else {
        await apiClient.post(API_ENDPOINTS.BOOKMARKS, payload)
      }
      setBookmarkDialogOpen(false)
      setEditingBookmark(null)
      setActionMessage(editingBookmark ? '收藏已更新。' : '收藏已创建。')
      refresh()
    } catch (error) {
      setBookmarkError(errorMessage(error, '收藏无法保存。'))
    }
  }

  const openNewFolder = () => {
    setEditingFolder(null)
    setFolderError('')
    setFolderDialogOpen(true)
  }

  const openEditFolder = (folder) => {
    setEditingFolder(folder)
    setFolderError('')
    setFolderDialogOpen(true)
  }

  const saveFolder = async (payload) => {
    setFolderError('')
    try {
      if (editingFolder) {
        await apiClient.put(API_ENDPOINTS.BOOKMARK_FOLDER_DETAIL(editingFolder.id), payload)
      } else {
        await apiClient.post(API_ENDPOINTS.BOOKMARK_FOLDERS, payload)
      }
      setFolderDialogOpen(false)
      setEditingFolder(null)
      setActionMessage(editingFolder ? '文件夹已更新。' : '文件夹已创建。')
      refresh()
    } catch (error) {
      setFolderError(errorMessage(error, '文件夹无法保存。'))
    }
  }

  const deleteFolder = async (folder) => {
    if (!window.confirm(`确定删除 ${folder.name} 吗？其中的内容会移动到上一级。`)) return
    setActionError('')
    try {
      await apiClient.delete(API_ENDPOINTS.BOOKMARK_FOLDER_DETAIL(folder.id))
      if (selectedFolderId === folder.id) setSelectedFolderId(null)
      setActionMessage('文件夹已删除，其中的收藏仍然保留。')
      refresh()
    } catch (error) {
      setActionError(errorMessage(error, '文件夹无法删除。'))
    }
  }

  const openBookmark = async (bookmark) => {
    setActionError('')
    try {
      const response = await apiClient.post(API_ENDPOINTS.BOOKMARK_VISIT(bookmark.id))
      if (response.data?.id === bookmark.id) {
        setBookmarks((current) => current.map((item) => (item.id === bookmark.id ? response.data : item)))
      }
      window.open(bookmark.url, '_blank', 'noopener,noreferrer')
    } catch (error) {
      setActionError(errorMessage(error, '访问记录失败，因此未打开这项收藏。'))
    }
  }

  const setSelected = (id, checked) => {
    setSelectedIds((current) => (
      checked ? [...new Set([...current, id])] : current.filter((item) => item !== id)
    ))
  }

  const runBulk = async (action) => {
    if (selectedIds.length === 0) return
    if (action === 'delete' && !window.confirm(`确定删除选中的 ${selectedIds.length} 项收藏吗？`)) return
    setActionError('')
    setActionMessage('')
    const payload = {
      action,
      ids: selectedIds,
      ...(action === 'move' || action === 'copy'
        ? { folder_id: bulkDestination ? Number(bulkDestination) : null }
        : {}),
    }
    try {
      await apiClient.post(API_ENDPOINTS.BOOKMARK_BULK, payload)
      setActionMessage(`已${action === 'copy' ? '复制' : action === 'move' ? '移动' : '删除'} ${selectedIds.length} 项收藏。`)
      setSelectedIds([])
      refresh()
    } catch (error) {
      setActionError(errorMessage(error, '整组操作已被拒绝，未修改任何内容。'))
    }
  }

  const saveEngine = async (editing, payload) => {
    setActionError('')
    try {
      const response = editing
        ? await apiClient.put(API_ENDPOINTS.SEARCH_ENGINE_DETAIL(editing.id), payload)
        : await apiClient.post(API_ENDPOINTS.SEARCH_ENGINES, payload)
      setEngines((current) => (
        editing
          ? current.map((engine) => (engine.id === editing.id ? response.data : engine))
          : [...current, response.data]
      ))
      setActionMessage(editing ? '搜索引擎已更新。' : '搜索引擎已创建。')
      return true
    } catch (error) {
      setActionError(errorMessage(error, '搜索引擎无法保存。'))
      return false
    }
  }

  const deleteEngine = async (engine) => {
    if (!window.confirm(`确定删除搜索引擎 ${engine.name} 吗？`)) return
    setActionError('')
    try {
      await apiClient.delete(API_ENDPOINTS.SEARCH_ENGINE_DETAIL(engine.id))
      setEngines((current) => current.filter((item) => item.id !== engine.id))
      setActionMessage('搜索引擎已删除。')
    } catch (error) {
      setActionError(errorMessage(error, '搜索引擎无法删除。'))
    }
  }

  const selectedFolder = folders.find((folder) => folder.id === selectedFolderId)
  const submitSearch = (event) => {
    event.preventDefault()
    setQuery(draftQuery.trim())
  }

  const workspace = (
    <div className="private-collection__workspace">
      <aside className="private-collection__sidebar">
        <div className="private-collection__sidebar-title">
          <h2>文件夹</h2>
          <Button size="sm" variant="ghost" aria-label="新建文件夹" onClick={openNewFolder}>
            <Plus size={15} aria-hidden="true" />
          </Button>
        </div>
        <button
          type="button"
          className={`private-collection__all ${selectedFolderId === null ? 'is-active' : ''}`}
          onClick={() => setSelectedFolderId(null)}
        >
          <Bookmark size={15} aria-hidden="true" /> 全部收藏
        </button>
        <FolderTree
          folders={folders}
          selectedId={selectedFolderId}
          onSelect={setSelectedFolderId}
          onEdit={openEditFolder}
          onDelete={deleteFolder}
        />
      </aside>

      <main className="private-collection__main">
        <div className="private-collection__toolbar">
          <div>
            <p className="route-shell__eyebrow">{selectedFolder ? '文件夹' : '全部私人收藏'}</p>
            <h2>{selectedFolder?.name || '收藏'}</h2>
          </div>
          <div className="private-collection__create-actions">
            <Button variant="secondary" onClick={openNewFolder}><Plus size={15} aria-hidden="true" /> 新建文件夹</Button>
            <Button onClick={openNewBookmark}><Plus size={15} aria-hidden="true" /> 新建收藏</Button>
          </div>
        </div>

        <form className="private-collection__filters" onSubmit={submitSearch}>
          <Input label="搜索我的收藏" value={draftQuery} maxLength={200} onChange={(event) => setDraftQuery(event.target.value)} />
          <label className="collection-select-field">
            <span>收藏排序</span>
            <select value={sort} onChange={(event) => setSort(event.target.value)}>
              <option value="manual">手动排序</option>
              <option value="recent">最近访问</option>
              <option value="popular">访问最多</option>
              <option value="newest">最近添加</option>
            </select>
          </label>
          <Button type="submit" variant="secondary"><Search size={15} aria-hidden="true" /> 搜索</Button>
        </form>

        {selectedIds.length > 0 && (
          <div className="private-collection__bulk" aria-label="批量操作">
            <strong>已选择 {selectedIds.length} 项</strong>
            <label className="collection-select-field">
              <span>批量操作目标</span>
              <select value={bulkDestination} onChange={(event) => setBulkDestination(event.target.value)}>
                <option value="">未归档</option>
                {folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}
              </select>
            </label>
            <Button size="sm" variant="secondary" onClick={() => runBulk('move')}><FolderInput size={14} aria-hidden="true" /> 移动所选</Button>
            <Button size="sm" variant="secondary" onClick={() => runBulk('copy')}><Copy size={14} aria-hidden="true" /> 复制所选</Button>
            <Button size="sm" variant="danger" onClick={() => runBulk('delete')}><Trash2 size={14} aria-hidden="true" /> 删除所选</Button>
          </div>
        )}

        {bookmarksLoading && (
          <div className="private-collection__loading" aria-label="正在载入收藏">
            {[0, 1, 2].map((item) => <Skeleton key={item} className="private-collection__skeleton" />)}
          </div>
        )}
        {!bookmarksLoading && bookmarks.length === 0 && !loadError && (
          <EmptyState
            className="private-collection__empty"
            icon={<Bookmark size={32} />}
            title="当前视图中没有收藏"
            description="请更换搜索词或文件夹，也可以新建收藏。"
            action={<Button onClick={openNewBookmark}>新建收藏</Button>}
          />
        )}
        {!bookmarksLoading && bookmarks.length > 0 && (
          <div className="private-collection__grid">
            {bookmarks.map((bookmark) => (
              <BookmarkCard
                key={bookmark.id}
                bookmark={bookmark}
                selected={selectedIds.includes(bookmark.id)}
                onSelect={setSelected}
                onOpen={openBookmark}
                onEdit={openEditBookmark}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  )

  const tabs = [
    { value: 'workspace', label: '工作区', content: workspace },
    { value: 'start', label: '起始页', content: <StartPage bookmarks={bookmarks} engines={engines} onOpen={openBookmark} /> },
    { value: 'engines', label: '搜索引擎', content: <SearchEnginesPanel engines={engines} error={actionError} onSave={saveEngine} onDelete={deleteEngine} /> },
    { value: 'transfer', label: '导入导出与备份', content: <CollectionTransferPanel onCollectionChanged={refresh} /> },
  ]

  return (
    <section className="route-shell private-collection">
      <header className="route-shell__intro private-collection__intro">
        <div>
          <p className="route-shell__eyebrow">私人工作区</p>
          <h1>我的收藏</h1>
          <p>管理多层文件夹、访问记录、公开状态、批量操作和私人起始页。</p>
        </div>
        <div className="private-collection__summary" aria-label="收藏概况">
          <span><CheckSquare size={15} aria-hidden="true" /> {bookmarks.length} 项收藏</span>
          <span><LayoutGrid size={15} aria-hidden="true" /> {folders.length} 个文件夹</span>
          <span><Settings2 size={15} aria-hidden="true" /> {engines.length} 个搜索引擎</span>
        </div>
      </header>

      {loadError && (
        <div className="collection-action-error" role="alert">
          <p>{loadError}</p>
          <Button variant="secondary" onClick={refresh}>重试</Button>
        </div>
      )}
      {actionError && view !== 'engines' && <p className="collection-action-error" role="alert">{actionError}</p>}
      {actionMessage && <p className="collection-action-message" role="status">{actionMessage}</p>}

      {loading ? (
        <Skeleton className="private-collection__page-skeleton" label="正在载入私人收藏" />
      ) : (
        <Tabs items={tabs} value={view} onChange={setView} label="私人收藏视图" />
      )}

      <BookmarkDialog
        bookmark={editingBookmark}
        error={bookmarkError}
        folders={folders}
        open={bookmarkDialogOpen}
        selectedFolderId={selectedFolderId}
        onOpenChange={(open) => {
          setBookmarkDialogOpen(open)
          if (!open) setBookmarkError('')
        }}
        onSave={saveBookmark}
      />
      <FolderDialog
        error={folderError}
        folder={editingFolder}
        folders={folders}
        open={folderDialogOpen}
        onOpenChange={(open) => {
          setFolderDialogOpen(open)
          if (!open) setFolderError('')
        }}
        onSave={saveFolder}
      />
    </section>
  )
}
