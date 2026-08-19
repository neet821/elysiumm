const headers = { 'user-agent': 'elysiumm-articles/1.0 (https://elysiumm.top)' };

function text(value) {
  return typeof value === 'string' ? value.trim() : '';
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

async function getJson(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { ...headers, ...options.headers } });
  if (!response.ok) throw new Error(`metadata provider returned ${response.status}`);
  return response.json();
}

export async function searchMetadata(type, query, env = process.env) {
  const q = encodeURIComponent(query.trim());
  if (type === 'book') {
    const data = await getJson(`https://openlibrary.org/search.json?q=${q}&limit=8`);
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
    const data = await getJson(`https://musicbrainz.org/ws/2/release-group/?query=${q}&fmt=json&limit=8`);
    return data['release-groups'].map((item) => normalized('musicbrainz', {
      providerId: item.id,
      title: item.title,
      year: item['first-release-date'],
      genres: item.tags?.map((tag) => tag.name),
      raw: item,
    }));
  }
  if (type === 'movie' && env.TMDB_API_KEY) {
    const data = await getJson(`https://api.themoviedb.org/3/search/movie?query=${q}&language=zh-CN`, { headers: { authorization: `Bearer ${env.TMDB_API_KEY}` } });
    return data.results.map((item) => normalized('tmdb', {
      providerId: item.id,
      title: item.title,
      description: item.overview,
      cover: item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : '',
      year: item.release_date,
      raw: item,
    }));
  }
  if (type === 'game' && env.IGDB_CLIENT_ID && env.IGDB_ACCESS_TOKEN) {
    const data = await getJson('https://api.igdb.com/v4/games', {
      method: 'POST',
      headers: { 'content-type': 'text/plain', 'Client-ID': env.IGDB_CLIENT_ID, authorization: `Bearer ${env.IGDB_ACCESS_TOKEN}` },
      body: `search "${query.replaceAll('"', '')}"; fields name,summary,first_release_date,cover.url,genres.name; limit 8;`,
    });
    return data.map((item) => normalized('igdb', {
      providerId: item.id,
      title: item.name,
      description: item.summary,
      cover: item.cover?.url ? `https:${item.cover.url.replace('t_thumb', 't_cover_big')}` : '',
      year: item.first_release_date ? new Date(item.first_release_date * 1000).getUTCFullYear() : '',
      genres: item.genres?.map((genre) => genre.name),
      raw: item,
    }));
  }
  throw Object.assign(new Error(`no provider configured for ${type}`), { code: 'UNSUPPORTED_TYPE' });
}
