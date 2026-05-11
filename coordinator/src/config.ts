const required = (key: string): string => {
    const value = process.env[key];
    if (!value) throw new Error(`Missing required environment variable: ${key}`);
    return value;
};

export const config = {
  QUANTDB_URL:       required("QUANTDB_URL"),
  JWT_SECRET:        required("JWT_SECRET"),
  REDIS_URL:         process.env["REDIS_URL"] ?? "redis://localhost:6379",
  PORT:              Number(process.env["PORT"] ?? 3001),
  MAX_WORKERS:       Number(process.env["MAX_WORKERS"] ?? 1),
  PYTHON_BIN:        process.env["PYTHON_BIN"] ?? "python",
  LOG_LEVEL:         process.env["LOG_LEVEL"] ?? "info",
  SHUTDOWN_GRACE_MS: Number(process.env["SHUTDOWN_GRACE_MS"] ?? 10_000),
};