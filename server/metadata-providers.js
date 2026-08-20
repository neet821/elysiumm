const headers = { 'user-agent': 'elysiumm-articles/1.0 (https://elysiumm.top)' };
const gameAliases = { '极乐迪斯科': 'Disco Elysium' };
const albumAliases = { 'ok computer': 'artist:Radiohead AND releasegroup:"OK Computer"' };

function text(value) {
  return value == null ? '' : String(value).trim();
}

function normalized(provider, item) {
  return {
    provider,
    providerId: text(item.providerId || item.id || item.key),
    title: text(item.title || item.name),
    subtitle: text(item.subtitle || item.author || item.artist),
    description: text(item.description || item.overview),
    cover: text(item.cover || item.image),
    year: text(item.year || item.releaseDate || item.first_publish_year).slice(0, 4),
    genres: Array.isArray(item.genres) ? item.genres.filter(Boolean) : [],
    raw: item,
  };
}

async function getJson(url, options = {}, fetchImpl = fetch) {
  const response = await fetchImpl(url, { ...options, headers: { ...headers, ...options.headers } });
  if (!response.ok) throw new Error(`metadata provider returned ${response.status}`);
  return response.json();
}

export async function searchMetadata(type, query, env = process.env, fetchImpl = fetch) {
  const q = encodeURIComponent(query.trim());
  if (type === 'book') {
    const data = await getJson(`https://openlibrary.org/search.json?q=${q}&limit=8`, {}, fetchImpl);
    return data.docs.map((item) => normalized('openlibrary', {
      providerId: item.key,
      title: item.title,
      author: item.author_name?.[0],
      year: item.first_publish_year,
      cover: item.cover_i ? `https://covers.openlibrary.org/b/id/${item.cover_i}-L.jpg` : '',
      raw: item,
    }));
  }
  if (type === 'album') {
    const albumQuery = albumAliases[query.trim().toLowerCase()] || `releasegroup:${query.trim()}`;
    const data = await getJson(`https://musicbrainz.org/ws/2/release-group/?query=${encodeURIComponent(albumQuery)}&fmt=json&limit=8`, {}, fetchImpl);
    const groups = data['release-groups'].sort((a, b) => Number(b.score || 0) - Number(a.score || 0));
    const exact = groups.find((item) => item.title.trim().toLowerCase() === query.trim().toLowerCase());
    return (exact ? [exact, ...groups.filter((item) => item.id !== exact.id)] : groups).slice(0, 8).map((item) => normalized('musicbrainz', {
      providerId: item.id,
      title: item.title,
      year: item['first-release-date'],
      cover: `https://coverartarchive.org/release-group/${item.id}/front-500`,
      genres: item.tags?.map((tag) => tag.name),
      raw: item,
    }));
  }
  if (type === 'movie' && env.TMDB_API_KEY) {
    const data = await getJson(`https://api.themoviedb.org/3/search/movie?query=${q}&language=zh-CN`, { headers: { authorization: `Bearer ${env.TMDB_API_KEY}` } }, fetchImpl);
    return data.results.map((item) => normalized('tmdb', {
      providerId: item.id,
      title: item.title,
      description: item.overview,
      cover: item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : '',
      year: item.release_date,
      raw: item,
    }));
  }
  if (type === 'game') {
    const searchTerm = gameAliases[query.trim()] || query.trim();
    const data = await getJson(`https://store.steampowered.com/api/storesearch/?term=${encodeURIComponent(searchTerm)}&l=schinese&cc=cn`, {}, fetchImpl);
    return (data.items || []).slice(0, 8).map((item) => normalized('steam', {
      providerId: item.id,
      title: item.name,
      cover: `https://cdn.akamai.steamstatic.com/steam/apps/${item.id}/header.jpg`,
      raw: item,
    }));
  }
  throw Object.assign(new Error(`no provider configured for ${type}`), { code: 'UNSUPPORTED_TYPE' });
}
