import { Navigate, useLocation } from 'react-router-dom'

function buildDestination(to, location, preserveSearch, hash) {
  const [withoutHash, suppliedHash = ''] = String(to).split('#', 2)
  const [pathname, suppliedSearch = ''] = withoutHash.split('?', 2)
  const search = new URLSearchParams(suppliedSearch)

  if (preserveSearch) {
    const legacySearch = new URLSearchParams(location.search)
    legacySearch.forEach((value, key) => {
      if (!search.has(key)) search.append(key, value)
    })
  }

  const query = search.toString()
  const nextHash = hash === true
    ? location.hash.replace(/^#/, '')
    : hash === undefined
      ? suppliedHash
      : String(hash).replace(/^#/, '')

  return `${pathname || '/'}${query ? `?${query}` : ''}${nextHash ? `#${nextHash}` : ''}`
}

export function LegacyRedirect({ hash, preserveSearch = false, to }) {
  const location = useLocation()
  const destination = buildDestination(to, location, preserveSearch, hash)
  return <Navigate replace to={destination} />
}

export default LegacyRedirect
