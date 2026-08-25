export const DEFAULT_HOMEPAGE_SETTINGS = Object.freeze({
  hero_prefix: 'Hello, this is',
  article_title_scale: 0.8,
  hero_title: 'Blue Album.',
  german_line: 'Wovon man nicht sprechen kann, darüber muss man schweigen.',
  introduction: '文字、照片与沿途收藏，都留在这本私人相册里。',
  short_quote: '把安静的部分留下来。',
  featured_post_ids: [],
  featured_photo_ids: [],
  featured_collection_ids: [],
  featured_track_ids: [],
  show_messages: true,
  show_history: true,
  background_mode: 'auto',
  cards: [
    { id: 'index', size: 'small', theme: 'archive' },
    { id: 'writing', size: 'wide', theme: 'paper' },
    { id: 'photography', size: 'medium', theme: 'film' },
    { id: 'collection', size: 'medium', theme: 'archive' },
    { id: 'messages', size: 'medium', theme: 'note' },
    { id: 'history', size: 'medium', theme: 'archive' },
    { id: 'quote', size: 'small', theme: 'paper' },
  ],
  revision: 0,
  updated_at: null,
})

const asArray = (value) => (Array.isArray(value) ? value : [])

export function normalizeHomepagePayload(payload) {
  const settings = payload?.settings && typeof payload.settings === 'object'
    ? { ...DEFAULT_HOMEPAGE_SETTINGS, ...payload.settings }
    : { ...DEFAULT_HOMEPAGE_SETTINGS }

  settings.cards = asArray(settings.cards).length
    ? settings.cards
    : DEFAULT_HOMEPAGE_SETTINGS.cards

  return {
    settings,
    posts: asArray(payload?.posts),
    photos: asArray(payload?.photos),
    messages: asArray(payload?.messages),
    collections: asArray(payload?.collections),
  }
}
