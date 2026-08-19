import { afterEach, describe, expect, it } from 'vitest';
import { mkdtemp, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createMetadataStore } from '../server/metadata-store.js';

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
});
