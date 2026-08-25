import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, LayoutDashboard, Save } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button, Card, Input, Skeleton } from '../components/ui/index.js'
import { DEFAULT_HOMEPAGE_SETTINGS } from '../components/home/homepageModel.js'
import { API_ENDPOINTS } from '../config.js'
import apiClient from '../utils/request.js'

const CARD_IDS = new Set(['index', 'writing', 'photography', 'collection', 'messages', 'history', 'quote', 'status'])
const CARD_SIZES = new Set(['small', 'medium', 'wide'])
const CARD_THEMES = new Set(['archive', 'paper', 'film', 'note', 'midnight'])

const errorDetail = (error, fallback) => {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => item.msg || String(item)).join(', ')
  return fallback
}

const parseIdentifiers = (value) => [...new Set(
  value
    .split(/[\s,]+/)
    .filter(Boolean)
    .map(Number)
    .filter((item) => Number.isInteger(item) && item > 0),
)]

const identifiersToText = (values = []) => values.join(', ')

function validateCards(value) {
  let cards
  try {
    cards = JSON.parse(value)
  } catch {
    throw new Error('卡片布局必须是有效的 JSON。')
  }
  if (!Array.isArray(cards) || cards.length === 0) {
    throw new Error('卡片布局必须是非空 JSON 数组。')
  }
  const identifiers = cards.map((card) => card?.id)
  if (
    identifiers.some((id) => !CARD_IDS.has(id))
    || new Set(identifiers).size !== identifiers.length
    || cards.some((card) => !CARD_SIZES.has(card?.size) || !CARD_THEMES.has(card?.theme))
  ) {
    throw new Error('每张卡片都需要唯一且受支持的编号、尺寸和主题。')
  }
  return cards
}

export default function AdminHomepagePage() {
  const [draft, setDraft] = useState(DEFAULT_HOMEPAGE_SETTINGS)
  const [layoutJson, setLayoutJson] = useState(JSON.stringify(DEFAULT_HOMEPAGE_SETTINGS.cards, null, 2))
  const [postIds, setPostIds] = useState('')
  const [photoIds, setPhotoIds] = useState('')
  const [collectionIds, setCollectionIds] = useState('')
  const [trackIds, setTrackIds] = useState('')
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const applySettings = useCallback((settings) => {
    const normalized = { ...DEFAULT_HOMEPAGE_SETTINGS, ...settings }
    setDraft(normalized)
    setRevision(normalized.revision || 0)
    setLayoutJson(JSON.stringify(normalized.cards, null, 2))
    setPostIds(identifiersToText(normalized.featured_post_ids))
    setPhotoIds(identifiersToText(normalized.featured_photo_ids))
    setCollectionIds(identifiersToText(normalized.featured_collection_ids))
    setTrackIds(identifiersToText(normalized.featured_track_ids))
  }, [])

  const loadSettings = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_HOMEPAGE)
      applySettings(response.data)
    } catch (requestError) {
      setError(errorDetail(requestError, '首页设置暂时无法载入。'))
    } finally {
      setLoading(false)
    }
  }, [applySettings])

  useEffect(() => {
    loadSettings()
  }, [loadSettings])

  const updateDraft = (field, value) => {
    setDraft((current) => ({ ...current, [field]: value }))
    setSuccess('')
  }

  const saveSettings = async (event) => {
    event.preventDefault()
    setError('')
    setSuccess('')

    let cards
    try {
      cards = validateCards(layoutJson)
    } catch (validationError) {
      setError(validationError.message)
      return
    }

    const settings = {
      hero_prefix: draft.hero_prefix,
      hero_title: draft.hero_title,
      german_line: draft.german_line,
      introduction: draft.introduction,
      short_quote: draft.short_quote,
      featured_post_ids: parseIdentifiers(postIds),
      featured_photo_ids: parseIdentifiers(photoIds),
      featured_collection_ids: parseIdentifiers(collectionIds),
      featured_track_ids: parseIdentifiers(trackIds).slice(0, 5),
      show_messages: draft.show_messages,
      show_history: draft.show_history,
      background_mode: draft.background_mode,
      cards,
    }

    setSaving(true)
    try {
      const response = await apiClient.put(API_ENDPOINTS.ADMIN_HOMEPAGE, { revision, settings })
      applySettings(response.data)
      setSuccess('首页设置已保存。')
    } catch (requestError) {
      setError(errorDetail(requestError, '首页设置保存失败。'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="admin-homepage route-shell">
      <header className="admin-homepage__intro">
        <div>
          <p className="route-shell__eyebrow"><LayoutDashboard size={15} aria-hidden="true" /> 管理控制台</p>
          <h1>首页设置</h1>
          <p>配置公开介绍、精选内容和卡片顺序。</p>
        </div>
        <Link className="ui-button ui-button--secondary ui-button--md" to="/" aria-label="查看公开首页">
          <ExternalLink size={16} aria-hidden="true" />
          查看公开首页
        </Link>
      </header>

      {loading ? (
        <Skeleton className="admin-homepage__loading" label="正在载入首页设置" />
      ) : (
        <form className="admin-homepage__form" onSubmit={saveSettings}>
          <Card as="fieldset" className="admin-homepage__section">
            <legend>首页内容</legend>
            <div className="admin-homepage__two-column">
              <Input
                label="首页左上角文字"
                aria-label="首页左上角文字"
                value={draft.hero_prefix}
                maxLength={80}
                required
                onChange={(event) => updateDraft('hero_prefix', event.target.value)}
              />
              <Input
                label="首屏标题"
                aria-label="首屏标题"
                value={draft.hero_title}
                maxLength={120}
                required
                onChange={(event) => updateDraft('hero_title', event.target.value)}
              />
            </div>
            <Input
              label="德文副标题（当前不显示）"
              value={draft.german_line}
              maxLength={240}
              required
              onChange={(event) => updateDraft('german_line', event.target.value)}
            />
            <label className="ui-field">
              <span className="ui-field__label">首页介绍</span>
              <textarea
                className="ui-input admin-homepage__textarea"
                aria-label="首页介绍"
                value={draft.introduction}
                maxLength={1200}
                required
                onChange={(event) => updateDraft('introduction', event.target.value)}
              />
            </label>
            <Input
              label="短句"
              value={draft.short_quote}
              maxLength={300}
              onChange={(event) => updateDraft('short_quote', event.target.value)}
            />
          </Card>

          <Card as="fieldset" className="admin-homepage__section">
            <legend>精选内容</legend>
            <Input label="精选文章编号" value={postIds} hint="用逗号分隔正整数；留空时使用最近公开文章。" onChange={(event) => setPostIds(event.target.value)} />
            <Input label="精选照片编号" value={photoIds} hint="仅显示已经标记为精选的照片。" onChange={(event) => setPhotoIds(event.target.value)} />
            <Input label="精选收藏编号" value={collectionIds} hint="填写要在首页展示的公开收藏编号。" onChange={(event) => setCollectionIds(event.target.value)} />
            <Input label="首页播放器歌曲编号" value={trackIds} hint="用逗号分隔曲库编号，最多 5 首；播放器不会自动播放。" onChange={(event) => setTrackIds(event.target.value)} />
            <div className="admin-homepage__switches">
              <label><input type="checkbox" checked={draft.show_messages} onChange={(event) => updateDraft('show_messages', event.target.checked)} /> 显示留言板</label>
              <label><input type="checkbox" checked={draft.show_history} onChange={(event) => updateDraft('show_history', event.target.checked)} /> 显示历史记录</label>
            </div>
            <label className="ui-field">
              <span className="ui-field__label">背景模式</span>
              <select className="ui-input" value={draft.background_mode} onChange={(event) => updateDraft('background_mode', event.target.value)}>
                <option value="auto">跟随主题</option>
                <option value="paper">纸张</option>
                <option value="midnight">午夜</option>
              </select>
            </label>
          </Card>

          <Card as="fieldset" className="admin-homepage__section admin-homepage__layout">
            <legend>内容布局</legend>
            <label className="ui-field">
              <span className="ui-field__label">卡片布局 JSON</span>
              <textarea
                className="ui-input admin-homepage__json"
                aria-label="卡片布局 JSON"
                value={layoutJson}
                spellCheck="false"
                onChange={(event) => {
                  setLayoutJson(event.target.value)
                  setSuccess('')
                }}
              />
              <span className="ui-field__hint">尺寸可用 small、medium、wide；主题可用 archive、paper、film、note、midnight。</span>
            </label>
          </Card>

          {error && <p className="admin-homepage__message admin-homepage__message--error" role="alert">{error}</p>}
          {success && <p className="admin-homepage__message admin-homepage__message--success" role="status">{success}</p>}

          <footer className="admin-homepage__actions">
            <span>修订号 {revision}</span>
            <Button type="submit" isLoading={saving} aria-label="保存首页设置">
              <Save size={16} aria-hidden="true" />
              保存首页设置
            </Button>
          </footer>
        </form>
      )}
    </section>
  )
}
