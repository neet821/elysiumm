import { DatabaseSync } from 'node:sqlite';

export function createMetadataStore(databasePath) {
  const database = new DatabaseSync(databasePath);
  database.exec(`
    CREATE TABLE IF NOT EXISTS metadata_cache (
      type TEXT NOT NULL,
      query TEXT NOT NULL,
      provider TEXT NOT NULL,
      provider_id TEXT,
      data_json TEXT NOT NULL,
      fetched_at TEXT NOT NULL,
      PRIMARY KEY (type, query, provider)
    ) STRICT;
  `);
  const read = database.prepare('SELECT provider, provider_id AS providerId, data_json AS dataJson, fetched_at AS fetchedAt FROM metadata_cache WHERE type = ? AND query = ? ORDER BY fetched_at DESC LIMIT 1');
  const write = database.prepare('INSERT INTO metadata_cache (type, query, provider, provider_id, data_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(type, query, provider) DO UPDATE SET provider_id = excluded.provider_id, data_json = excluded.data_json, fetched_at = excluded.fetched_at');

  return {
    get(type, query) {
      const row = read.get(type, query.trim().toLowerCase());
      return row ? { ...row, data: JSON.parse(row.dataJson) } : null;
    },
    put({ type, query, provider, providerId = '', data }) {
      write.run(type, query.trim().toLowerCase(), provider, providerId, JSON.stringify(data), new Date().toISOString());
    },
    close() {
      database.close();
    },
  };
}
