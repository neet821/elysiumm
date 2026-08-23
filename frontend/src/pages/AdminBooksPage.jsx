import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, BookOpen, ExternalLink, ListPlus, Pencil, Plus, RotateCcw, Save, Trash2, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button, Card, EmptyState, Input, Skeleton, Tabs, Tag } from '../components/ui/index.js'
import { API_ENDPOINTS } from '../config.js'
import apiClient from '../utils/request.js'

const EMPTY_BOOK = {
  author: '',
  category: '',
  cover_url: '',
  description: '',
  display_order: 0,
  is_featured: false,
  is_public: false,
  reader_path: '',
  reading_status: 'unread',
  slug: '',
  tags: '',
  title: '',
}

const EMPTY_LIST = {
  description: '',
  display_order: 0,
  is_public: false,
  slug: '',
  title: '',
}

const errorDetail = (error, fallback) => {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => item.msg || String(item)).join(', ')
  return fallback
}

const tagsFromText = (value) => [...new Set(
  value.split(',').map((tag) => tag.trim()).filter(Boolean),
)]

const nullable = (value) => value.trim() || null

function bookToDraft(book) {
  return {
    author: book.author || '',
    category: book.category || '',
    cover_url: book.cover_url || '',
    description: book.description || '',
    display_order: book.display_order || 0,
    is_featured: Boolean(book.is_featured),
    is_public: Boolean(book.is_public),
    reader_path: book.reader_path || '',
    reading_status: book.reading_status || 'unread',
    slug: book.slug,
    tags: (book.tags || []).join(', '),
    title: book.title,
  }
}

function listToDraft(bookList) {
  return {
    description: bookList.description || '',
    display_order: bookList.display_order || 0,
    is_public: Boolean(bookList.is_public),
    slug: bookList.slug,
    title: bookList.title,
  }
}

function BookEditor({ draft, editingBook, onChange, onClose, onSubmit, saving }) {
  return (
    <form className="ui-card admin-books__editor" onSubmit={onSubmit}>
      <header><div><p>书籍资料</p><h2>{editingBook ? `编辑 ${editingBook.title}` : '添加书籍'}</h2></div><Button variant="ghost" size="icon" aria-label="关闭书籍编辑器" onClick={onClose}><X size={18} /></Button></header>
      <div className="admin-books__form-grid">
        <Input label="书名" value={draft.title} maxLength={255} required onChange={(event) => onChange('title', event.target.value)} />
        <Input label="网址标识" value={draft.slug} maxLength={120} required hint="使用小写字母、数字和连字符。" onChange={(event) => onChange('slug', event.target.value)} />
        <Input label="作者" value={draft.author} maxLength={255} onChange={(event) => onChange('author', event.target.value)} />
        <Input label="分类" value={draft.category} maxLength={80} onChange={(event) => onChange('category', event.target.value)} />
        <Input label="封面地址" value={draft.cover_url} maxLength={500} hint="使用站内相对路径或 HTTPS 地址。" onChange={(event) => onChange('cover_url', event.target.value)} />
        <Input label="Kavita 相对路径" value={draft.reader_path} maxLength={1000} onChange={(event) => onChange('reader_path', event.target.value)} />
        <Input label="书籍标签" value={draft.tags} hint="用逗号分隔，最多 12 个。" onChange={(event) => onChange('tags', event.target.value)} />
        <Input label="显示顺序" type="number" min="0" value={draft.display_order} onChange={(event) => onChange('display_order', event.target.value)} />
        <label className="ui-field"><span className="ui-field__label">阅读状态</span><select className="ui-input" value={draft.reading_status} onChange={(event) => onChange('reading_status', event.target.value)}><option value="unread">未读</option><option value="reading">阅读中</option><option value="paused">已暂停</option><option value="completed">已读完</option></select></label>
      </div>
      <label className="ui-field"><span className="ui-field__label">简介</span><textarea className="ui-input admin-books__textarea" value={draft.description} maxLength={4000} onChange={(event) => onChange('description', event.target.value)} /></label>
      <div className="admin-books__checks"><label><input type="checkbox" checked={draft.is_public} onChange={(event) => onChange('is_public', event.target.checked)} /> 公开书籍</label><label><input type="checkbox" checked={draft.is_featured} onChange={(event) => onChange('is_featured', event.target.checked)} /> 设为精选</label></div>
      <footer><span>{editingBook ? `修订号 ${editingBook.revision}` : '新建资料记录'}</span><Button type="submit" isLoading={saving}><Save size={15} aria-hidden="true" /> {editingBook ? '保存书籍' : '创建书籍'}</Button></footer>
    </form>
  )
}

export default function AdminBooksPage() {
  const [catalog, setCatalog] = useState({ books: [], lists: [], reader_available: false })
  const [activeTab, setActiveTab] = useState('books')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const [bookDraft, setBookDraft] = useState(EMPTY_BOOK)
  const [editingBook, setEditingBook] = useState(null)
  const [bookFormOpen, setBookFormOpen] = useState(false)
  const [listDraft, setListDraft] = useState(EMPTY_LIST)
  const [editingList, setEditingList] = useState(null)
  const [listFormOpen, setListFormOpen] = useState(false)
  const [orderedBookIds, setOrderedBookIds] = useState([])

  const loadCatalog = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setLoading(true)
    setError('')
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_BOOKS)
      setCatalog({ books: [], lists: [], reader_available: false, ...response.data })
    } catch (requestError) {
      setError(errorDetail(requestError, '书籍内容暂时无法载入。'))
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadCatalog()
  }, [loadCatalog])

  const orderedBooks = useMemo(() => orderedBookIds
    .map((id) => catalog.books.find((book) => book.id === id))
    .filter(Boolean), [catalog.books, orderedBookIds])

  const openNewBook = () => {
    setEditingBook(null)
    setBookDraft(EMPTY_BOOK)
    setBookFormOpen(true)
    setError('')
    setNotice('')
  }

  const openBook = (book) => {
    setEditingBook(book)
    setBookDraft(bookToDraft(book))
    setBookFormOpen(true)
    setError('')
    setNotice('')
  }

  const updateBookDraft = (field, value) => {
    setBookDraft((current) => ({ ...current, [field]: value }))
    setNotice('')
  }

  const saveBook = async (event) => {
    event.preventDefault()
    setError('')
    setNotice('')
    const tags = tagsFromText(bookDraft.tags)
    if (!bookDraft.title.trim() || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(bookDraft.slug)) {
      setError('必须填写书名，并使用小写字母、数字和连字符组成网址标识。')
      return
    }
    if (tags.length > 12 || tags.some((tag) => tag.length > 40)) {
      setError('最多使用 12 个标签，每个标签不超过 40 个字符。')
      return
    }
    const payload = {
      author: nullable(bookDraft.author),
      category: nullable(bookDraft.category),
      cover_url: nullable(bookDraft.cover_url),
      description: nullable(bookDraft.description),
      display_order: Number(bookDraft.display_order) || 0,
      is_featured: bookDraft.is_featured,
      is_public: bookDraft.is_public,
      reader_path: nullable(bookDraft.reader_path),
      reading_status: bookDraft.reading_status,
      slug: bookDraft.slug,
      tags,
      title: bookDraft.title.trim(),
    }
    setSaving(true)
    try {
      if (editingBook) {
        await apiClient.put(API_ENDPOINTS.ADMIN_BOOK(editingBook.id), {
          revision: editingBook.revision,
          ...payload,
        })
        setNotice('书籍已保存。')
      } else {
        await apiClient.post(API_ENDPOINTS.ADMIN_BOOKS, payload)
        setNotice('书籍已创建。')
      }
      setBookFormOpen(false)
      setEditingBook(null)
      await loadCatalog({ quiet: true })
    } catch (requestError) {
      setError(errorDetail(requestError, '书籍保存失败。'))
    } finally {
      setSaving(false)
    }
  }

  const deleteBook = async (book) => {
    if (!window.confirm(`确定删除《${book.title}》吗？`)) return
    setError('')
    setNotice('')
    try {
      await apiClient.delete(API_ENDPOINTS.ADMIN_BOOK(book.id), { params: { revision: book.revision } })
      setNotice('书籍已删除。')
      await loadCatalog({ quiet: true })
    } catch (requestError) {
      setError(errorDetail(requestError, '书籍删除失败。'))
    }
  }

  const openNewList = () => {
    setEditingList(null)
    setListDraft(EMPTY_LIST)
    setOrderedBookIds([])
    setListFormOpen(true)
    setError('')
    setNotice('')
  }

  const openList = (bookList) => {
    setEditingList(bookList)
    setListDraft(listToDraft(bookList))
    setOrderedBookIds(bookList.books.map((book) => book.id))
    setListFormOpen(true)
    setError('')
    setNotice('')
  }

  const deleteList = async (bookList) => {
    if (!window.confirm(`确定删除书单“${bookList.title}”吗？`)) return
    setError('')
    setNotice('')
    try {
      await apiClient.delete(API_ENDPOINTS.ADMIN_BOOK_LIST(bookList.id), {
        params: { revision: bookList.revision },
      })
      if (editingList?.id === bookList.id) {
        setListFormOpen(false)
        setEditingList(null)
      }
      setNotice('书单已删除。')
      await loadCatalog({ quiet: true })
    } catch (requestError) {
      setError(errorDetail(requestError, '书单删除失败。'))
    }
  }

  const saveListDetails = async (event) => {
    event.preventDefault()
    setError('')
    setNotice('')
    if (!listDraft.title.trim() || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(listDraft.slug)) {
      setError('必须填写书单名称，并使用小写字母、数字和连字符组成网址标识。')
      return
    }
    const payload = {
      description: nullable(listDraft.description),
      display_order: Number(listDraft.display_order) || 0,
      is_public: listDraft.is_public,
      slug: listDraft.slug,
      title: listDraft.title.trim(),
    }
    setSaving(true)
    try {
      if (editingList) {
        const response = await apiClient.put(API_ENDPOINTS.ADMIN_BOOK_LIST(editingList.id), {
          revision: editingList.revision,
          ...payload,
        })
        setEditingList(response.data)
        setNotice('书单已保存。')
      } else {
        const response = await apiClient.post(API_ENDPOINTS.ADMIN_BOOK_LISTS, payload)
        setEditingList(response.data)
        setOrderedBookIds([])
        setNotice('书单已创建。')
      }
      await loadCatalog({ quiet: true })
    } catch (requestError) {
      setError(errorDetail(requestError, '书单保存失败。'))
    } finally {
      setSaving(false)
    }
  }

  const moveOrderedBook = (index, direction) => {
    const target = index + direction
    if (target < 0 || target >= orderedBookIds.length) return
    setOrderedBookIds((current) => {
      const next = [...current]
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
    setNotice('')
  }

  const saveListOrder = async () => {
    if (!editingList) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const response = await apiClient.put(API_ENDPOINTS.ADMIN_BOOK_LIST_ITEMS(editingList.id), {
        revision: editingList.revision,
        book_ids: orderedBookIds,
      })
      setEditingList(response.data)
      setOrderedBookIds(response.data.books.map((book) => book.id))
      setNotice('书单顺序已保存。')
      await loadCatalog({ quiet: true })
    } catch (requestError) {
      setError(errorDetail(requestError, '书单顺序保存失败。'))
    } finally {
      setSaving(false)
    }
  }

  const booksPanel = (
    <div className="admin-books__panel">
      <div className="admin-books__toolbar">
        <p>{catalog.books.length} 本书籍</p>
        <Button aria-expanded={bookFormOpen} onClick={openNewBook}><Plus size={15} aria-hidden="true" /> 添加书籍</Button>
      </div>
      {catalog.books.length === 0 ? (
        <EmptyState title="还没有书籍" description="创建第一条书籍资料。" icon={<BookOpen size={32} />} />
      ) : (
        <div className="admin-books__records">
          {catalog.books.map((book) => (
            <Card as="article" className="admin-books__record" key={book.id}>
              <div>
                <div className="admin-books__record-meta">
                  <Tag tone={book.is_public ? 'success' : 'neutral'}>{book.is_public ? '公开' : '私密'}</Tag>
                  {book.is_featured && <Tag tone="warning">精选</Tag>}
                  <span>修订号 {book.revision}</span>
                </div>
                <h2>{book.title}</h2>
                <p>{book.author || '作者未知'} · {book.category || '未分类'}</p>
              </div>
              <div className="admin-books__record-actions">
                <Button variant="secondary" size="sm" aria-label={`编辑 ${book.title}`} onClick={() => openBook(book)}><Pencil size={14} aria-hidden="true" /> 编辑</Button>
                <Button variant="ghost" size="sm" aria-label={`删除 ${book.title}`} onClick={() => deleteBook(book)}><Trash2 size={14} aria-hidden="true" /> 删除</Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )

  const listsPanel = (
    <div className="admin-books__panel">
      <div className="admin-books__toolbar">
        <p>{catalog.lists.length} 个书单</p>
        <Button onClick={openNewList}><ListPlus size={15} aria-hidden="true" /> 添加书单</Button>
      </div>
      {catalog.lists.length === 0 ? (
        <EmptyState title="还没有书单" description="把书籍整理成有序书单。" icon={<ListPlus size={32} />} />
      ) : (
        <div className="admin-books__records">
          {catalog.lists.map((bookList) => (
            <Card as="article" className="admin-books__record" key={bookList.id}>
              <div>
                <div className="admin-books__record-meta">
                  <Tag tone={bookList.is_public ? 'success' : 'neutral'}>{bookList.is_public ? '公开' : '私密'}</Tag>
                  <span>修订号 {bookList.revision}</span>
                </div>
                <h2>{bookList.title}</h2>
                <p>{bookList.books.length} 本书</p>
              </div>
              <div className="admin-books__record-actions">
                <Button variant="secondary" size="sm" aria-label={`编辑 ${bookList.title}`} onClick={() => openList(bookList)}><Pencil size={14} aria-hidden="true" /> 编辑</Button>
                <Button variant="ghost" size="sm" aria-label={`删除 ${bookList.title}`} onClick={() => deleteList(bookList)}><Trash2 size={14} aria-hidden="true" /> 删除</Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )

  return (
    <section className="route-shell admin-books">
      <header className="admin-books__intro">
        <div>
          <p className="route-shell__eyebrow"><BookOpen size={15} aria-hidden="true" /> 内容管理</p>
          <h1>书籍内容</h1>
          <p>管理公开书籍资料和有序书单，不保存 Kavita 凭据。</p>
        </div>
        <Link className="ui-button ui-button--secondary ui-button--md" to="/books" aria-label="查看公开书籍">
          <ExternalLink size={16} aria-hidden="true" /> 查看公开书籍
        </Link>
      </header>

      {loading ? (
        <Skeleton className="admin-books__loading" label="正在载入书籍内容" />
      ) : error && catalog.books.length === 0 && catalog.lists.length === 0 ? (
        <div className="admin-books__message admin-books__message--error" role="alert">
          <p>{error}</p>
          <Button variant="secondary" onClick={() => loadCatalog()}><RotateCcw size={15} aria-hidden="true" /> 重试</Button>
        </div>
      ) : (
        <>
          {error && <p className="admin-books__message admin-books__message--error" role="alert">{error}</p>}
          {notice && <p className="admin-books__message admin-books__message--success" role="status">{notice}</p>}
          <Tabs
            label="书籍内容分区"
            value={activeTab}
            onChange={(value) => {
              setActiveTab(value)
              setError('')
              setNotice('')
            }}
            items={[
              { value: 'books', label: '书籍', content: booksPanel },
              { value: 'lists', label: '书单', content: listsPanel },
            ]}
          />
        </>
      )}

      {bookFormOpen && (
        <BookEditor
          draft={bookDraft}
          editingBook={editingBook}
          onChange={updateBookDraft}
          onClose={() => setBookFormOpen(false)}
          onSubmit={saveBook}
          saving={saving}
        />
      )}

      {listFormOpen && (
        <Card className="admin-books__editor">
          <form onSubmit={saveListDetails}>
            <header><div><p>书单</p><h2>{editingList ? `编辑 ${editingList.title}` : '添加书单'}</h2></div><Button variant="ghost" size="icon" aria-label="关闭书单编辑器" onClick={() => setListFormOpen(false)}><X size={18} /></Button></header>
            <div className="admin-books__form-grid">
              <Input label="书单名称" value={listDraft.title} maxLength={255} required onChange={(event) => setListDraft((current) => ({ ...current, title: event.target.value }))} />
              <Input label="网址标识" value={listDraft.slug} maxLength={120} required onChange={(event) => setListDraft((current) => ({ ...current, slug: event.target.value }))} />
              <Input label="显示顺序" type="number" min="0" value={listDraft.display_order} onChange={(event) => setListDraft((current) => ({ ...current, display_order: event.target.value }))} />
              <label className="admin-books__check"><input type="checkbox" checked={listDraft.is_public} onChange={(event) => setListDraft((current) => ({ ...current, is_public: event.target.checked }))} /> 公开书单</label>
            </div>
            <label className="ui-field"><span className="ui-field__label">书单简介</span><textarea className="ui-input admin-books__textarea" value={listDraft.description} maxLength={2000} onChange={(event) => setListDraft((current) => ({ ...current, description: event.target.value }))} /></label>
            <div className="admin-books__editor-actions"><Button type="submit" isLoading={saving}><Save size={15} /> {editingList ? '保存书单资料' : '创建书单'}</Button></div>
          </form>

          {editingList && (
            <section className="admin-books__order" aria-labelledby="book-list-order-heading">
              <div><h3 id="book-list-order-heading">书籍顺序</h3><p>添加公开或私密书籍资料，再按需要调整顺序。</p></div>
              <label className="ui-field"><span className="ui-field__label">添加书籍</span><select className="ui-input" value="" onChange={(event) => { const id = Number(event.target.value); if (id && !orderedBookIds.includes(id)) setOrderedBookIds((current) => [...current, id]) }}><option value="">选择书籍</option>{catalog.books.filter((book) => !orderedBookIds.includes(book.id)).map((book) => <option key={book.id} value={book.id}>{book.title}</option>)}</select></label>
              <ol data-testid="book-list-order">
                {orderedBooks.map((book, index) => (
                  <li data-testid="ordered-book" key={book.id}><span>{index + 1}. {book.title}</span><div><Button size="icon" variant="ghost" aria-label={`上移 ${book.title}`} disabled={index === 0} onClick={() => moveOrderedBook(index, -1)}><ArrowUp size={15} /></Button><Button size="icon" variant="ghost" aria-label={`下移 ${book.title}`} disabled={index === orderedBooks.length - 1} onClick={() => moveOrderedBook(index, 1)}><ArrowDown size={15} /></Button><Button size="icon" variant="ghost" aria-label={`从书单移除 ${book.title}`} onClick={() => setOrderedBookIds((current) => current.filter((id) => id !== book.id))}><X size={15} /></Button></div></li>
                ))}
              </ol>
              <Button onClick={saveListOrder} isLoading={saving}>保存书单顺序</Button>
            </section>
          )}
        </Card>
      )}
    </section>
  )
}
