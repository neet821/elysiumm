import { useCallback, useEffect, useState } from 'react'
import { Save } from 'lucide-react'
import { Button, Card, Input, Skeleton } from '../components/ui/index.js'
import { DEFAULT_HOMEPAGE_SETTINGS } from '../components/home/homepageModel.js'
import { API_ENDPOINTS } from '../config.js'
import apiClient from '../utils/request.js'

const errorDetail = (error, fallback) => {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => item.msg || String(item)).join(', ')
  return fallback
}

export default function AdminHomepagePage() {
  const [storedSettings, setStoredSettings] = useState(DEFAULT_HOMEPAGE_SETTINGS)
  const [draftPrefix, setDraftPrefix] = useState(DEFAULT_HOMEPAGE_SETTINGS.hero_prefix)
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const applySettings = useCallback((settings) => {
    const normalized = { ...DEFAULT_HOMEPAGE_SETTINGS, ...settings }
    setStoredSettings(normalized)
    setDraftPrefix(normalized.hero_prefix)
    setRevision(normalized.revision || 0)
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

  const saveSettings = async (event) => {
    event.preventDefault()
    setError('')
    setSuccess('')

    const settings = Object.fromEntries(
      Object.entries(storedSettings).filter(([key]) => !['revision', 'updated_at'].includes(key)),
    )
    settings.hero_prefix = draftPrefix

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
        <h1>首页设置</h1>
      </header>

      {loading ? (
        <Skeleton className="admin-homepage__loading" label="正在载入首页设置" />
      ) : (
        <form className="admin-homepage__form" onSubmit={saveSettings}>
          <Card as="fieldset" className="admin-homepage__section">
            <legend>顶栏文字</legend>
            <Input
              label="首页顶栏文字"
              aria-label="首页顶栏文字"
              value={draftPrefix}
              maxLength={80}
              required
              onChange={(event) => {
                setDraftPrefix(event.target.value)
                setSuccess('')
              }}
            />
          </Card>

          {error && <p className="admin-homepage__message admin-homepage__message--error" role="alert">{error}</p>}
          {success && <p className="admin-homepage__message admin-homepage__message--success" role="status">{success}</p>}

          <footer className="admin-homepage__actions">
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
