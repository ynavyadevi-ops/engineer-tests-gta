import { describe, expect, it } from "vitest";
import { findUnsafeClientEnv } from "./env-guard.ts";

describe("findUnsafeClientEnv", () => {
  it("flags secret-looking VITE_* names", () => {
    expect(
      findUnsafeClientEnv({
        VITE_YOUTUBE_API_KEY: "x",
        VITE_SECRET: "x",
        vite_auth_token: "x",
        VITE_APP_TITLE: "fine",
      }),
    ).toEqual(["VITE_SECRET", "VITE_YOUTUBE_API_KEY", "vite_auth_token"]);
  });

  it("ignores server-only variables, which Vite never inlines", () => {
    expect(findUnsafeClientEnv({ YOUTUBE_API_KEY: "x", GTA_LAB_MODE: "demo" })).toEqual([]);
  });
});
