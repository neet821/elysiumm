"""Server-side metadata lookup for books, movies, and albums.

The browser never receives provider credentials. Results are normalized before
they enter the database and manual entry remains available after provider
failures.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

import schemas
from media_matching import rank_candidates, search_queries


_SEARCH_CACHE: dict[tuple[str, str, object], tuple[float, schemas.MediaSearchResponse]] = {}
_SEARCH_CACHE_TTL_SECONDS = 600.0


class MediaMetadataClient:
    def __init__(
        self,
        *,
        tmdb_token: str,
        google_books_api_key: str = "",
        igdb_client_id: str = "",
        igdb_client_secret: str = "",
        user_agent: str,
        timeout_seconds: float,
        mineradio_base_url: str = "",
        mineradio_admin_token: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.tmdb_token = tmdb_token.strip()
        self.google_books_api_key = google_books_api_key.strip()
        self.igdb_client_id = igdb_client_id.strip()
        self.igdb_client_secret = igdb_client_secret.strip()
        self.user_agent = user_agent.strip() or "Elysium/1.0"
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 20.0))
        self.mineradio_base_url = mineradio_base_url.strip().rstrip("/")
        self.mineradio_admin_token = mineradio_admin_token.strip()
        self.transport = transport

    async def search(
        self,
        kind: str,
        query: str,
    ) -> schemas.MediaSearchResponse:
        normalized_query = query.strip()
        # Tests and local callers may provide a transport; keep those isolated
        # while production requests share the short-lived server cache.
        cache_namespace: object = id(self.transport) if self.transport is not None else "production"
        cache_key = (kind, normalized_query.casefold(), cache_namespace)
        cached = _SEARCH_CACHE.get(cache_key)
        now = asyncio.get_running_loop().time()
        if cached and now - cached[0] < _SEARCH_CACHE_TTL_SECONDS:
            return cached[1].model_copy(deep=True)
        if kind == "book":
            result = await self._search_books(normalized_query)
        elif kind == "movie":
            tmdb = await self._search_tmdb(normalized_query)
            if tmdb.results:
                result = tmdb
            else:
                wikidata = await self._search_wikidata_movies(normalized_query)
                result = schemas.MediaSearchResponse(
                    kind="movie",
                    query=normalized_query,
                    providers=[*tmdb.providers, *wikidata.providers],
                    results=wikidata.results,
                    recommended_result=wikidata.recommended_result,
                )
        elif kind == "album":
            result = await self._search_albums(normalized_query)
        elif kind == "game":
            result = await self._search_games(normalized_query)
        else:
            raise ValueError("unsupported media kind")
        if result.results:
            _SEARCH_CACHE[cache_key] = (now, result.model_copy(deep=True))
        return result

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds, connect=min(self.timeout_seconds, 5.0)),
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
            follow_redirects=True,
            transport=self.transport,
        )

    async def _get_with_retry(self, client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        last_error: httpx.HTTPError | None = None
        for attempt in range(2):
            try:
                response = await client.get(url, **kwargs)
                if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                # A timeout should move to the configured fallback promptly;
                # retry only transient HTTP/network errors that returned a
                # response or failed before a timeout.
                if attempt == 0 and not isinstance(exc, httpx.TimeoutException):
                    await asyncio.sleep(0.25)
                    continue
                raise
        raise last_error or httpx.HTTPError("资料服务请求失败")

    async def _search_books(self, query: str) -> schemas.MediaSearchResponse:
        google_results: list[schemas.MediaMetadataCandidate] = []
        google_providers: list[schemas.MediaProviderStatus] = []
        for candidate_query in search_queries("book", query):
            response = await self._search_google_books(candidate_query)
            google_providers.extend(response.providers)
            google_results.extend(response.results)
            if response.providers and not response.providers[0].available:
                break
            if google_results and candidate_query == query:
                break
        ranked, recommended = rank_candidates("book", query, google_results)
        if ranked:
            return schemas.MediaSearchResponse(
                kind="book", query=query, providers=google_providers,
                results=ranked[:20], recommended_result=recommended,
            )

        open_results: list[schemas.MediaMetadataCandidate] = []
        open_providers: list[schemas.MediaProviderStatus] = []
        for candidate_query in search_queries("book", query):
            response = await self._search_open_library(candidate_query)
            open_providers.extend(response.providers)
            open_results.extend(response.results)
            if response.providers and not response.providers[0].available:
                break
            if open_results and candidate_query == query:
                break
        ranked, recommended = rank_candidates("book", query, open_results)
        return schemas.MediaSearchResponse(
            kind="book", query=query,
            providers=[*google_providers, *open_providers],
            results=ranked[:20], recommended_result=recommended,
        )

    async def _search_google_books(self, query: str) -> schemas.MediaSearchResponse:
        provider = schemas.MediaProviderStatus(provider="googlebooks", available=True)
        try:
            params = {"q": query, "maxResults": 12, "printType": "books"}
            if self.google_books_api_key:
                params["key"] = self.google_books_api_key
            async with self._client() as client:
                response = await self._get_with_retry(client,
                    "https://www.googleapis.com/books/v1/volumes",
                    params=params,
                )
                rows = response.json().get("items", [])
            results = [self._google_books_candidate(item) for item in rows[:12]]
            results = [item for item in results if item is not None]
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            provider.available = False
            provider.message = self._safe_error_message(exc)
            results = []
        return schemas.MediaSearchResponse(
            kind="book",
            query=query,
            providers=[provider],
            results=results,
        )

    @staticmethod
    def _google_books_candidate(item: dict[str, Any]) -> schemas.MediaMetadataCandidate | None:
        info = item.get("volumeInfo") or {}
        source_id = str(item.get("id") or "").strip()
        title = str(info.get("title") or "").strip()
        if not source_id or not title:
            return None
        published = str(info.get("publishedDate") or "")
        year_match = published[:4]
        cover = str((info.get("imageLinks") or {}).get("thumbnail") or "").strip()
        cover = cover.replace("http://", "https://", 1) if cover else None
        return schemas.MediaMetadataCandidate(
            kind="book",
            title=title,
            creator=", ".join(str(value).strip() for value in info.get("authors") or [] if str(value).strip()) or None,
            cover_url=cover,
            year=int(year_match) if year_match.isdigit() else None,
            summary=str(info.get("description") or "").strip() or None,
            tags=[str(value).strip() for value in info.get("categories") or [] if str(value).strip()][:12],
            source="googlebooks",
            source_id=source_id,
            external_url=str(info.get("infoLink") or f"https://books.google.com/books?id={source_id}"),
            metadata={
                "isbn": next(
                    (
                        str(identifier.get("identifier") or "").strip()
                        for identifier in info.get("industryIdentifiers") or []
                        if isinstance(identifier, dict) and identifier.get("identifier")
                    ),
                    None,
                ),
                "language": str(info.get("language") or "").strip() or None,
            },
            raw_metadata={
                "id": source_id,
                "publishedDate": published or None,
                "language": str(info.get("language") or "").strip() or None,
            },
        )

    async def _search_open_library(self, query: str) -> schemas.MediaSearchResponse:
        provider = schemas.MediaProviderStatus(provider="openlibrary", available=True)
        try:
            async with self._client() as client:
                response = await self._get_with_retry(client,
                    "https://openlibrary.org/search.json",
                    params={
                        "q": query,
                        "limit": 12,
                        "fields": "key,title,author_name,first_publish_year,isbn,cover_i,subject",
                    },
                )
                docs = response.json().get("docs", [])
            results = [self._open_library_candidate(item) for item in docs[:12]]
            results = [item for item in results if item is not None]
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            provider.available = False
            provider.message = self._safe_error_message(exc)
            results = []
        return schemas.MediaSearchResponse(
            kind="book",
            query=query,
            providers=[provider],
            results=results,
        )

    @staticmethod
    def _open_library_candidate(item: dict[str, Any]) -> schemas.MediaMetadataCandidate | None:
        key = str(item.get("key") or "").strip()
        source_id = key.rsplit("/", 1)[-1] if key else None
        title = str(item.get("title") or "").strip()
        if not title:
            return None
        authors = [str(value).strip() for value in item.get("author_name") or [] if str(value).strip()]
        isbns = [str(value).strip() for value in item.get("isbn") or [] if str(value).strip()]
        subjects = [str(value).strip() for value in item.get("subject") or [] if str(value).strip()]
        cover_id = item.get("cover_i")
        return schemas.MediaMetadataCandidate(
            kind="book",
            title=title,
            creator=", ".join(authors[:3]) or None,
            cover_url=(
                f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                if isinstance(cover_id, int)
                else None
            ),
            year=item.get("first_publish_year"),
            tags=subjects[:12],
            source="openlibrary",
            source_id=source_id,
            external_url=(f"https://openlibrary.org/works/{source_id}" if source_id else None),
            metadata={"isbn": isbns[0] if isbns else None},
            raw_metadata={
                "key": key or None,
                "author_name": authors[:6],
                "first_publish_year": item.get("first_publish_year"),
                "isbn": isbns[:12],
                "cover_i": cover_id,
                "subject": subjects[:30],
            },
        )

    async def _search_tmdb(self, query: str) -> schemas.MediaSearchResponse:
        provider = schemas.MediaProviderStatus(provider="tmdb", available=False)
        if not self.tmdb_token:
            provider.message = "未配置 TMDB 资料服务"
            return schemas.MediaSearchResponse(
                kind="movie",
                query=query,
                providers=[provider],
                results=[],
            )
        try:
            results: list[schemas.MediaMetadataCandidate] = []
            async with self._client() as client:
                for candidate_query in search_queries("movie", query):
                    response = await self._get_with_retry(
                        client,
                        "https://api.themoviedb.org/3/search/movie",
                        params={"query": candidate_query, "include_adult": "false", "language": "zh-CN"},
                        headers={"Authorization": f"Bearer {self.tmdb_token}"},
                    )
                    rows = response.json().get("results", [])
                    results.extend(
                        candidate for item in rows[:12]
                        if (candidate := self._tmdb_candidate(item)) is not None
                    )
                    if results and candidate_query == query:
                        break
            results, recommended = rank_candidates("movie", query, results)
            provider.available = True
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            provider.message = self._safe_error_message(exc)
            results = []
        return schemas.MediaSearchResponse(
            kind="movie",
            query=query,
            providers=[provider],
            results=results[:20],
            recommended_result=recommended if 'recommended' in locals() else None,
        )

    @staticmethod
    def _tmdb_candidate(item: dict[str, Any]) -> schemas.MediaMetadataCandidate | None:
        title = str(item.get("title") or "").strip()
        source_id = str(item.get("id") or "").strip()
        if not title or not source_id:
            return None
        release_date = str(item.get("release_date") or "")
        year = int(release_date[:4]) if len(release_date) >= 4 and release_date[:4].isdigit() else None
        poster_path = str(item.get("poster_path") or "").strip()
        genres = [str(value) for value in item.get("genre_ids") or []][:12]
        return schemas.MediaMetadataCandidate(
            kind="movie",
            title=title,
            cover_url=(f"https://image.tmdb.org/t/p/w780{poster_path}" if poster_path.startswith("/") else None),
            year=year,
            summary=str(item.get("overview") or "").strip() or None,
            tags=genres,
            source="tmdb",
            source_id=source_id,
            external_url=f"https://www.themoviedb.org/movie/{source_id}",
            metadata={
                "original_title": str(item.get("original_title") or "").strip() or None,
                "original_language": str(item.get("original_language") or "").strip() or None,
            },
            raw_metadata={
                key: item.get(key)
                for key in (
                    "id", "title", "original_title", "original_language", "overview",
                    "poster_path", "release_date", "genre_ids", "vote_average", "vote_count",
                )
            },
        )

    async def _search_wikidata_movies(self, query: str) -> schemas.MediaSearchResponse:
        provider = schemas.MediaProviderStatus(provider="wikidata", available=True)
        try:
            hits: list[dict[str, Any]] = []
            async with self._client() as client:
                for candidate_query in search_queries("movie", query):
                    search_response = await self._get_with_retry(
                        client,
                        "https://www.wikidata.org/w/api.php",
                        params={
                            "action": "wbsearchentities",
                            "search": candidate_query,
                            "language": "zh",
                            "uselang": "zh",
                            "format": "json",
                            "limit": 8,
                        },
                    )
                    hits.extend(search_response.json().get("search", []))
                    if hits:
                        break
                ids = [str(item.get("id") or "").strip() for item in hits if item.get("id")]
                if not ids:
                    return schemas.MediaSearchResponse(kind="movie", query=query, providers=[provider], results=[])
                entity_response = await self._get_with_retry(
                    client,
                    "https://www.wikidata.org/w/api.php",
                    params={
                        "action": "wbgetentities",
                        "ids": "|".join(ids),
                        "props": "claims|labels|sitelinks",
                        "languages": "zh|en",
                        "format": "json",
                    },
                )
                entities = entity_response.json().get("entities", {})
            results = []
            for hit in hits:
                entity = entities.get(hit.get("id"), {})
                claims = entity.get("claims") or {}
                types = [
                    (((item.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}).get("id")
                    for item in claims.get("P31") or []
                ]
                if types and "Q11424" not in types:
                    continue
                title = str(
                    ((entity.get("labels") or {}).get("zh") or {}).get("value")
                    or ((entity.get("labels") or {}).get("en") or {}).get("value")
                    or hit.get("label")
                    or ""
                ).strip()
                if not title:
                    continue
                date_value = self._wikidata_claim_value(claims, "P577")
                date_text = str((date_value or {}).get("time") or "")
                image = str(self._wikidata_claim_value(claims, "P18") or "").strip()
                wikipedia_title = str(
                    (((entity.get("sitelinks") or {}).get("enwiki") or {}).get("title") or "")
                ).strip()
                cover = (
                    f"https://commons.wikimedia.org/wiki/Special:FilePath/{image}?width=800"
                    if image else None
                )
                if not cover and wikipedia_title:
                    cover = await self._wikipedia_cover_url(wikipedia_title)
                results.append(
                    schemas.MediaMetadataCandidate(
                        kind="movie",
                        title=title,
                        cover_url=cover,
                        year=int(date_text[1:5]) if len(date_text) >= 5 and date_text[1:5].isdigit() else None,
                        summary=str(hit.get("description") or "").strip() or None,
                        source="wikidata",
                        source_id=str(hit.get("id") or "").strip(),
                        external_url=f"https://www.wikidata.org/wiki/{hit.get('id')}",
                        metadata={"wikipedia_title": wikipedia_title or None},
                        raw_metadata={"id": hit.get("id"), "types": types},
                    )
                )
            ranked, recommended = rank_candidates("movie", query, results)
            return schemas.MediaSearchResponse(
                kind="movie", query=query, providers=[provider], results=ranked[:12],
                recommended_result=recommended,
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            provider.available = False
            provider.message = self._safe_error_message(exc)
            return schemas.MediaSearchResponse(kind="movie", query=query, providers=[provider], results=[])

    @staticmethod
    def _wikidata_claim_value(claims: dict[str, Any], property_name: str) -> Any:
        statements = claims.get(property_name) or []
        if not statements or not isinstance(statements[0], dict):
            return None
        return (((statements[0].get("mainsnak") or {}).get("datavalue") or {}).get("value"))

    async def _wikipedia_cover_url(self, title: str) -> str | None:
        try:
            async with self._client() as client:
                response = await client.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
                )
                response.raise_for_status()
                payload = response.json()
            return str(
                ((payload.get("originalimage") or {}).get("source")
                 or (payload.get("thumbnail") or {}).get("source") or "")
            ).strip() or None
        except (httpx.HTTPError, ValueError, TypeError):
            return None

    async def _search_games(self, query: str) -> schemas.MediaSearchResponse:
        igdb_status, igdb_results = await self._search_igdb(query)
        if igdb_results:
            igdb_results, recommended = rank_candidates("game", query, igdb_results)
            return schemas.MediaSearchResponse(
                kind="game",
                query=query,
                providers=[igdb_status],
                results=igdb_results[:20],
                recommended_result=recommended,
            )

        steam_status, steam_results = await self._search_steam(query)
        steam_results, recommended = rank_candidates("game", query, steam_results)
        return schemas.MediaSearchResponse(
            kind="game",
            query=query,
            providers=[igdb_status, steam_status],
            results=steam_results[:20],
            recommended_result=recommended,
        )

    async def _search_igdb(
        self,
        query: str,
    ) -> tuple[schemas.MediaProviderStatus, list[schemas.MediaMetadataCandidate]]:
        status = schemas.MediaProviderStatus(provider="igdb", available=False)
        if not self.igdb_client_id or not self.igdb_client_secret:
            status.message = "未配置 IGDB 资料服务"
            return status, []
        try:
            async with self._client() as client:
                token_response = await client.post(
                    "https://id.twitch.tv/oauth2/token",
                    data={
                        "client_id": self.igdb_client_id,
                        "client_secret": self.igdb_client_secret,
                        "grant_type": "client_credentials",
                    },
                )
                token_response.raise_for_status()
                access_token = str(token_response.json().get("access_token") or "").strip()
                if not access_token:
                    raise ValueError("IGDB token missing")
                rows: list[dict[str, Any]] = []
                for candidate_query in search_queries("game", query):
                    query_body = (
                        f'search "{candidate_query.replace(chr(34), chr(39))}"; '
                        "fields name,first_release_date,summary,genres.name,platforms.name,"
                        "involved_companies.company.name,cover.image_id,url; limit 12;"
                    )
                    response = await client.post(
                        "https://api.igdb.com/v4/games",
                        content=query_body,
                        headers={
                            "Client-ID": self.igdb_client_id,
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "text/plain",
                        },
                    )
                    response.raise_for_status()
                    rows.extend(response.json())
                    if rows and candidate_query == query:
                        break
            results = [self._igdb_candidate(item) for item in rows[:12]]
            results = [item for item in results if item is not None]
            status.available = True
            return status, results
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            status.message = self._safe_error_message(exc)
            return status, []

    @staticmethod
    def _igdb_candidate(item: dict[str, Any]) -> schemas.MediaMetadataCandidate | None:
        source_id = str(item.get("id") or "").strip()
        title = str(item.get("name") or "").strip()
        if not source_id or not title:
            return None
        timestamp = item.get("first_release_date")
        year = None
        if isinstance(timestamp, (int, float)):
            year = datetime.fromtimestamp(timestamp, tz=timezone.utc).year
        platforms = [
            str(value.get("name") or "").strip()
            for value in item.get("platforms") or []
            if isinstance(value, dict) and str(value.get("name") or "").strip()
        ]
        genres = [
            str(value.get("name") or "").strip()
            for value in item.get("genres") or []
            if isinstance(value, dict) and str(value.get("name") or "").strip()
        ]
        developers = [
            str((value.get("company") or {}).get("name") or "").strip()
            for value in item.get("involved_companies") or []
            if isinstance(value, dict)
            and isinstance(value.get("company"), dict)
            and str((value.get("company") or {}).get("name") or "").strip()
        ]
        image_id = str((item.get("cover") or {}).get("image_id") or "").strip()
        return schemas.MediaMetadataCandidate(
            kind="game",
            title=title,
            creator=", ".join(dict.fromkeys(developers[:4])) or None,
            cover_url=(
                f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg"
                if image_id else None
            ),
            year=year,
            summary=str(item.get("summary") or "").strip() or None,
            tags=(genres + platforms)[:12],
            source="igdb",
            source_id=source_id,
            external_url=str(item.get("url") or f"https://www.igdb.com/games/{source_id}"),
            metadata={"platforms": platforms, "genres": genres, "cover_image_id": image_id or None},
            raw_metadata={"id": source_id, "first_release_date": timestamp, "platforms": platforms},
        )

    async def _search_steam(
        self,
        query: str,
    ) -> tuple[schemas.MediaProviderStatus, list[schemas.MediaMetadataCandidate]]:
        status = schemas.MediaProviderStatus(provider="steam", available=True)
        try:
            async with self._client() as client:
                response = await client.get(
                    "https://store.steampowered.com/api/storesearch/",
                    params={"term": query, "l": "schinese", "cc": "CN"},
                )
                response.raise_for_status()
                rows = response.json().get("items", [])
            results = []
            for item in rows[:12]:
                source_id = str(item.get("id") or "").strip()
                title = str(item.get("name") or "").strip()
                if not source_id or not title:
                    continue
                results.append(
                    schemas.MediaMetadataCandidate(
                        kind="game",
                        title=title,
                        cover_url=str(item.get("tiny_image") or "").strip() or None,
                        source="steam",
                        source_id=source_id,
                        external_url=f"https://store.steampowered.com/app/{source_id}/",
                        metadata={},
                        raw_metadata={"id": source_id, "name": title},
                    )
                )
            return status, results
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            status.available = False
            status.message = self._safe_error_message(exc)
            return status, []

    async def _search_albums(self, query: str) -> schemas.MediaSearchResponse:
        providers: list[schemas.MediaProviderStatus] = []
        results: list[schemas.MediaMetadataCandidate] = []
        musicbrainz_status = schemas.MediaProviderStatus(
            provider="musicbrainz",
            available=True,
        )
        try:
            async with self._client() as client:
                for candidate_query in search_queries("album", query):
                    response = await self._get_with_retry(
                        client,
                        "https://musicbrainz.org/ws/2/release-group/",
                        params={"query": f'releasegroup:"{candidate_query}"', "fmt": "json", "limit": 12},
                    )
                    rows = response.json().get("release-groups", [])
                    for item in rows[:12]:
                        candidate = self._musicbrainz_candidate(item)
                        if candidate is not None:
                            results.append(candidate)
                    if results and candidate_query == query:
                        break
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            musicbrainz_status.available = False
            musicbrainz_status.message = self._safe_error_message(exc)
        providers.append(musicbrainz_status)

        if self.mineradio_base_url and self.mineradio_admin_token:
            netease_status, netease_results = await self._search_netease_albums(query)
            providers.append(netease_status)
            results.extend(netease_results)
        else:
            providers.append(
                schemas.MediaProviderStatus(
                    provider="netease",
                    available=False,
                    message="网易云补充搜索未配置",
                )
            )

        seen: set[tuple[str, str | None]] = set()
        deduplicated: list[schemas.MediaMetadataCandidate] = []
        for candidate in results:
            identity = (candidate.source, candidate.source_id)
            if identity in seen:
                continue
            seen.add(identity)
            deduplicated.append(candidate)
        ranked, recommended = rank_candidates("album", query, deduplicated)
        return schemas.MediaSearchResponse(
            kind="album",
            query=query,
            providers=providers,
            results=ranked[:20],
            recommended_result=recommended,
        )

    @staticmethod
    def _musicbrainz_candidate(item: dict[str, Any]) -> schemas.MediaMetadataCandidate | None:
        title = str(item.get("title") or "").strip()
        source_id = str(item.get("id") or "").strip()
        if not title or not source_id:
            return None
        artist_credit = item.get("artist-credit") or []
        artists = [
            str((credit.get("artist") or {}).get("name") or credit.get("name") or "").strip()
            for credit in artist_credit
            if isinstance(credit, dict)
        ]
        artists = [artist for artist in artists if artist]
        first_release_date = str(item.get("first-release-date") or "")
        year = int(first_release_date[:4]) if len(first_release_date) >= 4 and first_release_date[:4].isdigit() else None
        primary_type = str(item.get("primary-type") or "").strip()
        secondary_types = [str(value).strip() for value in item.get("secondary-types") or [] if str(value).strip()]
        return schemas.MediaMetadataCandidate(
            kind="album",
            title=title,
            creator=", ".join(artists[:4]) or None,
            cover_url=f"https://coverartarchive.org/release-group/{source_id}/front-500",
            year=year,
            tags=[value for value in [primary_type, *secondary_types] if value][:12],
            source="musicbrainz",
            source_id=source_id,
            external_url=f"https://musicbrainz.org/release-group/{source_id}",
            metadata={"primary_type": primary_type or None, "secondary_types": secondary_types},
            raw_metadata={
                "id": source_id,
                "title": title,
                "first-release-date": first_release_date or None,
                "primary-type": primary_type or None,
                "secondary-types": secondary_types,
                "artist-credit": artists[:8],
            },
        )

    async def _search_netease_albums(
        self,
        query: str,
    ) -> tuple[schemas.MediaProviderStatus, list[schemas.MediaMetadataCandidate]]:
        status = schemas.MediaProviderStatus(provider="netease", available=True)
        try:
            async with self._client() as client:
                response = await client.get(
                    f"{self.mineradio_base_url}/api/search",
                    params={"keywords": query, "type": 10, "limit": 8},
                    headers={"X-Music-Provider-Token": self.mineradio_admin_token},
                )
                response.raise_for_status()
                payload = response.json()
            rows = (payload.get("result") or {}).get("albums") or payload.get("albums") or []
            results = []
            for item in rows[:8]:
                title = str(item.get("name") or item.get("title") or "").strip()
                source_id = str(item.get("id") or "").strip()
                if not title or not source_id:
                    continue
                artists = item.get("artists") or []
                creator = ", ".join(
                    str(artist.get("name") or "").strip()
                    for artist in artists[:4]
                    if isinstance(artist, dict) and str(artist.get("name") or "").strip()
                ) or None
                cover = str(item.get("picUrl") or item.get("cover") or "").strip() or None
                if cover and cover.startswith("http://"):
                    cover = "https://" + cover[len("http://"):]
                results.append(
                    schemas.MediaMetadataCandidate(
                        kind="album",
                        title=title,
                        creator=creator,
                        cover_url=cover,
                        source="netease",
                        source_id=source_id,
                        external_url=f"https://music.163.com/#/album?id={source_id}",
                        metadata={},
                        raw_metadata={
                            "id": source_id,
                            "name": title,
                            "artists": [creator] if creator else [],
                            "picUrl": cover,
                        },
                    )
                )
            return status, results
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            status.available = False
            status.message = self._safe_error_message(exc)
            return status, []

    async def fetch_cover(
        self,
        kind: str,
        source: str,
        source_id: str,
    ) -> tuple[bytes, str] | None:
        """Fetch one provider cover without persisting it server-side."""
        normalized_source = source.strip().lower()
        normalized_id = source_id.strip()
        if not normalized_id or not normalized_id.isascii() or len(normalized_id) > 255:
            return None
        url: str | None = None
        headers: dict[str, str] = {}
        params: dict[str, str] = {}
        if normalized_source == "musicbrainz" and kind == "album":
            url = f"https://coverartarchive.org/release-group/{normalized_id}/front-500"
        elif normalized_source == "netease" and kind == "album":
            url = await self._netease_cover_url(normalized_id)
        elif normalized_source == "steam" and kind == "game":
            url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{normalized_id}/header.jpg"
        elif normalized_source == "igdb" and kind == "game":
            url = await self._igdb_cover_url(normalized_id)
        elif normalized_source == "tmdb" and kind == "movie":
            url = await self._tmdb_cover_url(normalized_id)
        elif normalized_source == "googlebooks" and kind == "book":
            url = await self._google_books_cover_url(normalized_id)
        elif normalized_source == "openlibrary" and kind == "book":
            url = await self._open_library_cover_url(normalized_id)
        elif normalized_source == "wikidata" and kind == "movie":
            url = await self._wikidata_cover_url(normalized_id)
        if not url or not url.startswith("https://"):
            return None
        try:
            async with self._client() as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
            content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
            if not content_type.startswith("image/") or len(response.content) > 10 * 1024 * 1024:
                return None
            return response.content, content_type
        except (httpx.HTTPError, ValueError, TypeError):
            return None

    async def _google_books_cover_url(self, source_id: str) -> str | None:
        try:
            params = {}
            if self.google_books_api_key:
                params["key"] = self.google_books_api_key
            async with self._client() as client:
                response = await client.get(
                    f"https://www.googleapis.com/books/v1/volumes/{source_id}",
                    params=params,
                )
                response.raise_for_status()
                return str((response.json().get("volumeInfo") or {}).get("imageLinks", {}).get("thumbnail") or "").replace("http://", "https://", 1) or None
        except (httpx.HTTPError, ValueError, TypeError):
            return None

    async def _open_library_cover_url(self, source_id: str) -> str | None:
        try:
            async with self._client() as client:
                response = await client.get(f"https://openlibrary.org/works/{source_id}.json")
                response.raise_for_status()
                cover_id = (response.json().get("covers") or [None])[0]
            return f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if isinstance(cover_id, int) else None
        except (httpx.HTTPError, ValueError, TypeError):
            return None

    async def _netease_cover_url(self, source_id: str) -> str | None:
        if not self.mineradio_base_url or not self.mineradio_admin_token:
            return None
        try:
            async with self._client() as client:
                response = await self._get_with_retry(
                    client,
                    f"{self.mineradio_base_url}/api/album",
                    params={"id": source_id},
                    headers={"X-Music-Provider-Token": self.mineradio_admin_token},
                )
                payload = response.json()
            album = payload.get("album") or payload.get("result") or payload
            cover = (album or {}).get("picUrl") or (album or {}).get("cover")
            return str(cover or "").replace("http://", "https://", 1) or None
        except (httpx.HTTPError, ValueError, TypeError):
            return None

    async def _tmdb_cover_url(self, source_id: str) -> str | None:
        if not self.tmdb_token:
            return None
        try:
            async with self._client() as client:
                response = await client.get(
                    f"https://api.themoviedb.org/3/movie/{source_id}",
                    params={"language": "zh-CN"},
                    headers={"Authorization": f"Bearer {self.tmdb_token}"},
                )
                response.raise_for_status()
                poster = str(response.json().get("poster_path") or "")
            return f"https://image.tmdb.org/t/p/w780{poster}" if poster.startswith("/") else None
        except (httpx.HTTPError, ValueError, TypeError):
            return None

    async def _igdb_cover_url(self, source_id: str) -> str | None:
        if not self.igdb_client_id or not self.igdb_client_secret:
            return None
        try:
            async with self._client() as client:
                token_response = await client.post(
                    "https://id.twitch.tv/oauth2/token",
                    data={
                        "client_id": self.igdb_client_id,
                        "client_secret": self.igdb_client_secret,
                        "grant_type": "client_credentials",
                    },
                )
                token_response.raise_for_status()
                token = str(token_response.json().get("access_token") or "").strip()
                response = await client.post(
                    "https://api.igdb.com/v4/games",
                    content=f"fields cover.image_id; where id = {int(source_id)}; limit 1;",
                    headers={
                        "Client-ID": self.igdb_client_id,
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "text/plain",
                    },
                )
                response.raise_for_status()
                image_id = str(((response.json() or [{}])[0].get("cover") or {}).get("image_id") or "").strip()
            return f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg" if image_id else None
        except (httpx.HTTPError, ValueError, TypeError):
            return None

    async def _wikidata_cover_url(self, source_id: str) -> str | None:
        try:
            async with self._client() as client:
                response = await client.get(
                    "https://www.wikidata.org/w/api.php",
                    params={
                        "action": "wbgetentities",
                        "ids": source_id,
                        "props": "claims|sitelinks",
                        "format": "json",
                    },
                )
                response.raise_for_status()
                entity = (response.json().get("entities") or {}).get(source_id) or {}
                claims = entity.get("claims") or {}
                value = (((claims.get("P18") or [])[0].get("mainsnak") or {}).get("datavalue") or {}).get("value")
                image = str(value or "").strip()
                if image:
                    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{image}?width=800"
                sitelinks = entity.get("sitelinks") or {}
                wikipedia_title = str((sitelinks.get("enwiki") or {}).get("title") or "").strip()
                if wikipedia_title:
                    return await self._wikipedia_cover_url(wikipedia_title)
            return None
        except (httpx.HTTPError, ValueError, TypeError):
            return None

    @staticmethod
    def _safe_error_message(exc: Exception) -> str:
        if isinstance(exc, httpx.TimeoutException):
            return "资料服务响应超时"
        if isinstance(exc, httpx.HTTPStatusError):
            return f"资料服务暂时不可用（{exc.response.status_code}）"
        return "资料服务返回了无法识别的结果"
