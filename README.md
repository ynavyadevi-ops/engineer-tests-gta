# Engineer Tests GTA

A local-first creator intelligence tool for a GTA VI YouTube channel. It helps you find YouTube evidence, decide what to film, and plan 30 days of long-form, Shorts and Reels. It is unofficial and has no affiliation with Rockstar Games or YouTube.

**Status:** Phase 01 (scaffold). The app runs locally with a status smoke page only. Research, planner and data features arrive in later phases. See `STATUS.md`.

## Windows 11 prerequisites

Git, Windows PowerShell 5.1+, `uv` (manages Python 3.12), and Node.js 24+ LTS with npm. The checked versions and installers are listed in `docs/SYSTEM_DESIGN.md` → *Toolchain*.

## Install, run, check

Run these from the repo root. Paths with spaces are fine.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1        # locked install (uv sync --locked, npm ci)
powershell -ExecutionPolicy Bypass -File scripts\run.ps1 -Build       # packaged app: http://127.0.0.1:8765/
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1              # dev with hot reload: http://127.0.0.1:5173/
powershell -ExecutionPolicy Bypass -File scripts\check.ps1            # lint, tests, build, secret scan, audits
```

`bootstrap.ps1 -Clean` does a locked rebuild from scratch. The app starts in **demo** mode and needs no key. Full run commands and settings are in `docs/SYSTEM_DESIGN.md` → *Run commands*.

## Data location

The default is `%LOCALAPPDATA%\EngineerTestsGTA\data`, outside OneDrive, because sync can corrupt SQLite files. Override it with `GTA_LAB_DATA_DIR` or `run.ps1 -DataDir`.

## Keys

- **None are needed to build or run demo mode.**
- A YouTube Data API v3 key (on a personal Google Cloud project, restricted to that API) is needed only for live smoke and collection, from Phase 03 onward. Put it in `YOUTUBE_API_KEY` in the private file `%LOCALAPPDATA%\EngineerTestsGTA\private.env`, or set it in the process environment. The repo `.env` is deliberately not read, because this folder syncs to OneDrive. `.env.example` lists every setting with placeholders. Never put a key in chat, Git or a `VITE_*` variable.
- An AI key is optional (Phase 13 only).

## Working with a coding agent

Open a fresh session in this folder and paste the phase runner command from `AGENTS.md`, using the phase number from `STATUS.md`. Run one phase per session.
