# Obsidian Collection Capture and Metadata Design

## Goal

Allow the owner to record essays, images, movies, albums, books, and games in Obsidian with one consistent frontmatter format, while the site renders image-only entries and the server caches external metadata locally.

## Decisions

- Markdown remains the source of truth; the database is only a rebuildable metadata cache.
- `type` identifies the content kind: `essay`, `image`, `movie`, `album`, `book`, `game`, or `note`.
- `link: false` makes a homepage card non-navigating.
- `created_at` and `updated_at` are explicit ISO timestamps; file modification time remains the fallback.
- Metadata providers are server-side adapters: Open Library and MusicBrainz work without credentials; TMDB and IGDB use optional environment credentials.
- QuickAdd templates provide fast capture without changing the vault's existing LiveSync model.

## Frontmatter contract

```yaml
type: movie
title: Interstellar
created_at: 2026-08-19T21:30:00+08:00
tags: [电影, 科幻]
source: tmdb
source_id: 157336
link: true
cover: https://...
preview: 我的观后感
```

## Acceptance

- Image entries render their image directly on the homepage.
- `link: false` entries have no article navigation.
- Empty `preview` remains empty.
- `/api/metadata/search?type=...&q=...` returns normalized provider data and caches successful results in SQLite.
- Capture templates create timestamped notes in the configured vault folders.
