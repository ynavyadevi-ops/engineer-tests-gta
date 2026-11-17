/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { CLIENT_ENV_PREFIX, findUnsafeClientEnv } from "./env-guard.ts";

const BACKEND = `http://127.0.0.1:${process.env.GTA_LAB_PORT ?? "8765"}`;

export default defineConfig(({ mode }) => {
  const unsafe = findUnsafeClientEnv({
    ...process.env,
    ...loadEnv(mode, process.cwd(), CLIENT_ENV_PREFIX),
  });
  if (unsafe.length > 0) {
    // Names only, never values.
    throw new Error(
      `Refusing to build: secret-looking client env vars would be inlined: ${unsafe.join(", ")}`,
    );
  }
  return {
    plugins: [react()],
    envPrefix: CLIENT_ENV_PREFIX,
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      // Dev only: keeps API calls same-origin from the browser's point of view.
      proxy: { "/api": { target: BACKEND, changeOrigin: false } },
    },
    preview: { host: "127.0.0.1", port: 4173, strictPort: true },
    build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
    test: { environment: "node", include: ["src/**/*.test.{ts,tsx}", "*.test.ts"] },
  };
});
