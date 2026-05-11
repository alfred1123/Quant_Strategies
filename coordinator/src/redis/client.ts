import { createClient, type RedisClientType } from "redis";

import { config } from "../config";

let _client: RedisClientType | null = null;

/** Lazy singleton — first call connects, subsequent calls reuse the socket. */
export async function getRedis(): Promise<RedisClientType> {
  if (_client && _client.isOpen) return _client;
  const c: RedisClientType = createClient({ url: config.REDIS_URL });
  c.on("error", (err) => console.error("[redis] client error:", err));
  await c.connect();
  _client = c;
  return c;
}

export async function closeRedis(): Promise<void> {
  if (_client?.isOpen) await _client.quit();
  _client = null;
}

/** Key naming — single source of truth across coordinator + Python readers. */
export const REFDATA_KEY = (table: string): string => `refdata:${table}`;
export const REFDATA_VERSION_KEY = "refdata:version";
export const REFDATA_INVALIDATE_CHANNEL = "refdata:invalidate";
