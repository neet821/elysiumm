"""Server-side metadata lookup for books, movies, and albums.

The browser never receives provider credentials. Results are normalized before
they enter the database and manual entry remains available after provider
failures.
"""

from __future__ import annotations

from typing import Any

import httpx

import schemas


class MediaMetadataClient:
    def __init__(
        self,
        *,
        tmdb_token: str,
        user_agent: str,
        timeout_seconds: float,
        mineradio_base_url: str = "",
        mineradio_admin_token: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.tmdb_token = tmdb_token.strip()
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
        if kind == "book":
            return await self._search_open_library(normalized_query)
        if kind == "movie":
            return await self._search_tmdb(normalized_query)
        if kind == "album":
            return await self._search_albums(normalized_query)
        raise ValueError("unsupported media kind")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds, connect=min(self.timeout_seconds, 5.0)),
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
            follow_redirects=False,
            transport=self.transport,
        )

    async def _search_open_library(self, query: str) -> schemas.MediaSearchResponse:
        provider = schemas.MediaProviderStatus(provider="openlibrary", available=True)
        try:
            async with self._client() as client:
                response = await client.get(
                    "https://openlibrary.org/search.json",
                    params={
                        "q": query,
                        "limit": 12,
                        "fields": "key,title,author_name,first_publish_year,isbn,cover_i,subject",
                    },
                )
                response.raise_for_status()
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
            async with self._client() as client:
                response = await client.get(
                    "https://api.themoviedb.org/3/search/movie",
                    params={"query": query, "include_adult": "false", "language": "zh-CN"},
                    headers={"Authorization": f"Bearer {self.tmdb_token}"},
                )
                response.raise_for_status()
                rows = response.json().get("results", [])
            results = [self._tmdb_candidate(item) for item in rows[:12]]
            results = [item for item in results if item is not None]
            provider.available = True
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            provider.message = self._safe_error_message(exc)
            results = []
        return schemas.MediaSearchResponse(
            kind="movie",
            query=query,
            providers=[provider],
            results=results,
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

    async def _search_albums(self, query: str) -> schemas.MediaSearchResponse:
        providers: list[schemas.MediaProviderStatus] = []
        results: list[schemas.MediaMetadataCandidate] = []
        musicbrainz_status = schemas.MediaProviderStatus(
            provider="musicbrainz",
            available=True,
        )
        try:
            async with self._client() as client:
                response = await client.get(
                    "https://musicbrainz.org/ws/2/release-group/",
                    params={"query": f'releasegroup:"{query}"', "fmt": "json", "limit": 12},
                )
                response.raise_for_status()
                rows = response.json().get("release-groups", [])
            for item in rows[:12]:
                candidate = self._musicbrainz_candidate(item)
                if candidate is not None:
                    results.append(candidate)
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
        return schemas.MediaSearchResponse(
            kind="album",
            query=query,
            providers=providers,
            results=deduplicated[:20],
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

    @staticmethod
    def _safe_error_message(exc: Exception) -> str:
        if isinstance(exc, httpx.TimeoutException):
            return "资料服务响应超时"
        if isinstance(exc, httpx.HTTPStatusError):
            return f"资料服务暂时不可用（{exc.response.status_code}）"
        return "资料服务返回了无法识别的结果"
