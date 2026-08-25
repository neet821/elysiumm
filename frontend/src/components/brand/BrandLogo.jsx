import { Link } from 'react-router-dom'

export function BrandLogo({ className }) {
  return (
    <Link
      aria-label="首页"
      className={['brand-logo', className].filter(Boolean).join(' ')}
      to="/"
    />
  )
}
