const PAPER_VARIANTS = Object.freeze(['plain', 'ruled', 'dotted', 'grid', 'fiber'])
const PAPER_TONES = Object.freeze(['warm', 'neutral', 'cool', 'ivory'])
const EDGE_VARIANTS = Object.freeze(['clean', 'soft', 'deckle', 'folded'])
const TAPE_COLORS = Object.freeze([
  'rgba(190, 216, 232, 0.82)',
  'rgba(230, 193, 174, 0.8)',
  'rgba(201, 218, 193, 0.82)',
  'rgba(231, 211, 165, 0.8)',
  'rgba(188, 197, 207, 0.72)',
  'rgba(255, 255, 255, 0.68)',
])

function hashChannel(key, channel) {
  const text = `${String(key || 'card')}::${channel}`
  let hash = 2166136261
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function pick(values, hash) {
  return values[hash % values.length]
}

function between(minimum, maximum, hash, precision = 2) {
  const ratio = hash / 0xffffffff
  return Number((minimum + ((maximum - minimum) * ratio)).toFixed(precision))
}

function tapeStyle(key, tapeNumber) {
  const prefix = `--tape-${tapeNumber}`
  return {
    [`${prefix}-color`]: pick(TAPE_COLORS, hashChannel(key, `${prefix}-color`)),
    [`${prefix}-left`]: `${between(18, 82, hashChannel(key, `${prefix}-left`), 1)}%`,
    [`${prefix}-top`]: `${between(-0.7, 0.45, hashChannel(key, `${prefix}-top`))}rem`,
    [`${prefix}-width`]: `${between(3.8, 7.8, hashChannel(key, `${prefix}-width`))}rem`,
    [`${prefix}-height`]: `${between(0.9, 1.65, hashChannel(key, `${prefix}-height`))}rem`,
    [`${prefix}-rotate`]: `${between(-7, 7, hashChannel(key, `${prefix}-rotate`), 1)}deg`,
  }
}

export function createCardAppearance(key, kind = 'note') {
  const normalizedKind = kind === 'photo' ? 'photo' : 'note'
  const tapeCount = 1 + (hashChannel(key, 'tape-count') % 2)

  return {
    paperVariant: pick(PAPER_VARIANTS, hashChannel(key, 'paper-variant')),
    paperTone: pick(PAPER_TONES, hashChannel(key, 'paper-tone')),
    edgeVariant: pick(EDGE_VARIANTS, hashChannel(key, 'edge-variant')),
    tapeCount,
    style: {
      '--card-rotate': `${between(-2.4, 2.4, hashChannel(key, `${normalizedKind}-rotate`), 2)}deg`,
      '--card-scale': between(0.97, 1.02, hashChannel(key, `${normalizedKind}-scale`), 3),
      '--card-depth': `${between(14, 28, hashChannel(key, `${normalizedKind}-depth`), 1)}px`,
      ...tapeStyle(key, 1),
      ...tapeStyle(key, 2),
    },
  }
}

export { EDGE_VARIANTS, PAPER_TONES, PAPER_VARIANTS, TAPE_COLORS }
