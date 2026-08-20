import { afterEach, describe, expect, it } from 'vitest';
import { mkdtemp, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createCachedMetadataSearch, createMetadataStore } from '../server/metadata-store.js';
import { searchMetadata } from '../server/metadata-providers.js';

const roots = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe('metadata store', () => {
  it('stores and retrieves normalized provider metadata', async () => {
    const root = await mkdtemp(join(tmpdir(), 'elysiumm-metadata-'));
    roots.push(root);
    const store = createMetadataStore(join(root, 'metadata.sqlite'));

    store.put({ type: 'book', query: 'Dune', provider: 'openlibrary', providerId: 'OL123', data: { title: 'Dune' } });

    expect(store.get('book', 'Dune')).toMatchObject({ provider: 'openlibrary', providerId: 'OL123', data: { title: 'Dune' } });
    store.close();
  });

  it('searches Steam games without credentials', async () => {
    const results = await searchMetadata('game', 'Portal', {}, async () => new Response(JSON.stringify({ items: [{ id: 400, name: 'Portal', tiny_image: 'https://cdn.test/portal.jpg' }] }), { status: 200 }));

    expect(results[0]).toMatchObject({ provider: 'steam', providerId: '400', title: 'Portal', cover: 'https://cdn.akamai.steamstatic.com/steam/apps/400/header.jpg' });
  });

  it('preserves all provider candidates when a search result is cached', async () => {
    const root = await mkdtemp(join(tmpdir(), 'elysiumm-metadata-'));
    roots.push(root);
    const store = createMetadataStore(join(root, 'metadata.sqlite'));
    const providerResults = [
      { provider: 'steam', providerId: '632470', title: 'Disco Elysium - The Final Cut' },
      { provider: 'steam', providerId: '1173140', title: 'Disco Elysium - Soundtrack and Artbooklet' },
    ];
    let calls = 0;
    const search = createCachedMetadataSearch(store, async () => {
      calls += 1;
      return providerResults;
    });

    expect(await search('game', '极乐迪斯科')).toEqual(providerResults);
    expect(await search('game', '极乐迪斯科')).toEqual(providerResults);
    expect(calls).toBe(1);
    store.close();
  });
});
