import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App.tsx";
import { parseStatus, type AppStatus } from "./api.ts";
import { StatusView } from "./StatusView.tsx";

// Synthetic payload shaped like /api/status. No real data.
const STATUS: AppStatus = {
  app: "engineer-tests-gta",
  version: "0.1.0",
  mode: "demo",
  api: "ok",
  youtube_api_key: "not configured",
  youtube_requests: "disabled",
  database: "not yet created",
  data_dir: "C:\\Users\\example\\AppData\\Local\\EngineerTestsGTA\\data",
  data_dir_cloud_synced: false,
  ui_build: "present",
  advanced_analytics: "off",
  ai: "off",
  server_time_utc: "2026-01-01T00:00:00+00:00",
};

describe("smoke page", () => {
  it("renders the app shell in its loading state", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain("Engineer Tests GTA");
    expect(html).toContain("Checking the local API");
  });

  it("renders status values exactly as reported", () => {
    const html = renderToStaticMarkup(<StatusView state={{ kind: "ready", status: STATUS }} />);
    expect(html).toContain("demo mode");
    expect(html).toContain("not configured");
    expect(html).toContain("disabled");
    expect(html).not.toContain("OneDrive-synced");
  });

  it("warns when the data folder is cloud-synced", () => {
    const status = { ...STATUS, data_dir_cloud_synced: true };
    const html = renderToStaticMarkup(<StatusView state={{ kind: "ready", status }} />);
    expect(html).toContain("OneDrive-synced");
  });

  it("shows an honest error state when the backend is unreachable", () => {
    const html = renderToStaticMarkup(
      <StatusView state={{ kind: "error", message: "status: HTTP 502" }} />,
    );
    expect(html).toContain("Backend unavailable");
    expect(html).toContain("status: HTTP 502");
  });
});

describe("parseStatus", () => {
  it("accepts a valid payload", () => {
    expect(parseStatus(STATUS)).toEqual(STATUS);
  });

  it("rejects malformed payloads instead of guessing", () => {
    expect(() => parseStatus(null)).toThrow();
    expect(() => parseStatus({ ...STATUS, mode: "prod" })).toThrow();
    expect(() => parseStatus({ ...STATUS, data_dir_cloud_synced: "no" })).toThrow();
  });
});
