// Preload via `bunfig.toml` -> ensures env vars exist before any module
// (including src/config.ts) is imported. The postgres pool is lazy, so a
// fake URL is fine as long as tests never actually issue a query against
// the real `sql` instance.
process.env["QUANTDB_URL"] ??= "postgres://test:test@localhost:5432/test";
process.env["JWT_SECRET"] ??= "test-secret";
