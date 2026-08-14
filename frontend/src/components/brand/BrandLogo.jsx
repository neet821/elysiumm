import { Link } from 'react-router-dom'

export function BrandLogo({ className }) {
  return (
    <Link
      className={['brand-logo', className].filter(Boolean).join(' ')}
      to="/"
      aria-label="Blue Album 首页"
    >
      <img
        className="brand-logo__image"
        src="/brand/blue-album-logo-color.svg"
        alt=""
        aria-hidden="true"
      />
      <span className="brand-logo__text">Blue Album</span>
    </Link>
  )
}
