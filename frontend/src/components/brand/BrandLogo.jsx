import { Link } from 'react-router-dom'

export function BrandLogo({ className }) {
  return (
    <Link
      aria-label="Elysium 首页"
      className={['brand-logo', className].filter(Boolean).join(' ')}
      to="/"
    >
      <img className="brand-logo__image" src="/brand/elysium-mark.svg" alt="" aria-hidden="true" />
      <span className="brand-logo__text">Elysium</span>
    </Link>
  )
}
