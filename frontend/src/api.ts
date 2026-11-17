export type AppMode = "demo" | "live";

export interface AppStatus {
  app: string;
  version: string;
  mode: AppMode;
  api: "ok";
  youtube_api_key: "configured" | "not configured";
  youtube_requests: "disabled";
  database: "not yet created" | "present";
  data_dir: string;
  data_dir_cloud_synced: boolean;
  ui_build: "present" | "not built";
  advanced_analytics: "off";
  ai: "off";
  server_time_utc: string;
}

const STRING_FIELDS = [
  "app",
  "version",
  "mode",
  "api",
  "youtube_api_key",
  "youtube_requests",
  "database",
  "data_dir",
  "ui_build",
  "advanced_analytics",
  "ai",
  "server_time_utc",
] as const;

/** Validate the payload shape; anything unexpected is an error, never a guess. */
export function parseStatus(value: unknown): AppStatus {
  if (typeof value !== "object" || value === null) throw new Error("status: not an object");
  const record = value as Record<string, unknown>;
  for (const field of STRING_FIELDS) {
    if (typeof record[field] !== "string") throw new Error(`status: bad field ${field}`);
  }
  if (typeof record.data_dir_cloud_synced !== "boolean") {
    throw new Error("status: bad field data_dir_cloud_synced");
  }
  if (record.mode !== "demo" && record.mode !== "live") throw new Error("status: bad mode");
  return record as unknown as AppStatus;
}

export async function fetchStatus(signal?: AbortSignal): Promise<AppStatus> {
  const response = await fetch("/api/status", {
    signal,
    headers: { Accept: "application/json" },
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error(`status: HTTP ${response.status}`);
  return parseStatus(await response.json());
}
