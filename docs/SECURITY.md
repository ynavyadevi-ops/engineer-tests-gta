# Security

## Threat model (local MVP)

| Asset | Threat | Control |
|---|---|---|
| YouTube API key | Leak via Git, logs, frontend bundle, status endpoint, chat | Process env or gitignored private config only; backend/CLI reads it; redaction in logs and errors; never `VITE_*`; tests check the bundle and `/api/status` |
| Local DB / raw API data | Leak via Git, exports, backups, prompts, sync | `local-data/` gitignored; no raw bodies persisted; no DB snapshots leave the machine by default; non-synced data dir recommended (OneDrive) |
| Local app | LAN exposure, CSRF, DNS rebinding | Bind `127.0.0.1`; restrict origins and host headers; reject cross-origin state-changing requests |
| Imported strings (titles, descriptions) | Injection into SQL, HTML or agent prompts | Treated as data, never instructions; parameterized SQL; safe escaping; strict payload schemas and lengths |
| Outbound network | SSRF, arbitrary fetch | Only preconfigured Google API destinations over HTTPS; no arbitrary URL fetch; live calls are explicit and budgeted |
| Dependencies | Malicious or vulnerable packages | Supply-chain rules below |

## Runtime controls

- Bounded pagination and queries, timeouts and rate limits.
- Minimal security headers. CSP allows only the documented asset and player hosts.
- Validated server-side inputs.
- Fixtures contain no real IDs or metrics.

## Credentials

| Credential | When | Notes |
|---|---|---|
| Coding-agent access | Phase 00 onward | Separate from the app runtime. A Claude Code login is not an app API key |
| YouTube Data API key | Phase 03 (live smoke) and Phase 04 (collection) | The only external runtime credential the live core needs. Restricted to YouTube Data API v3, personal Google Cloud project |
| YouTube owner OAuth | Not required for the MVP | Later only, with least privilege, secure token storage, revocation and deletion |
| Gemini **or** Anthropic API key | Optional, Phase 13 only | One provider, server-only, `AI_MODE=off` by default |

Never ask the user to paste a secret into chat. `.env.example` holds placeholders only.

## Supply chain

- Verify current package versions against official maintainers and registries, plus advisories, **at install time**. "Latest" means latest compatible, supported, stable release that passes checks.
- Commit `uv.lock` and `package-lock.json`. Install with `uv sync --locked` and `npm ci`. Record runtimes.
- Review publisher, repository, release provenance, licenses, transitive changes and install scripts. Avoid unnecessary postinstall scripts, and document and review any that are required. Never blindly rename packages or run downloaded scripts from unknown sources.
- Audit both dependency graphs, including dev dependencies: `npm audit`, plus OSV-Scanner or `pip-audit` on the resolved locked environment. Add secret scanning and an SBOM for releases.
- **A stopped or failed scan is not a clean scan.** Block release on known exploitable high/critical findings until remediated. Record lower-severity findings with their mitigation. Report the time, tool, actual result and limitations.
- Never run `npm audit fix --force` or auto-run arbitrary upstream code.
- **No scanner can certify zero vulnerabilities or malware.** Never make a blanket "safe" claim.

## AI controls (Phase 13)

- Provider disabled by default (`AI_MODE=off`). Server-only config, one provider.
- **Allowed fields:** creator-authored, explicitly selected, non-sensitive fields only (own test idea, rough hook, shot list, constraints).
- **Forbidden:** YouTube API data, competitor titles or thumbnails, captions, screenshots, IDs, private Studio metrics, tokens, raw DB rows, full app context. No image upload at first. Never train or fine-tune.
- Strict structured output, size, time, cost and request caps, graceful fallback. The editor accepts changes through a diff, and the AI never silently changes rank, plan, evidence or stats.
- Discard any output that asserts unverified mechanics or turns hypothetical metrics into claims.
- Logs contain only provider, model, timing, usage/error category and run ID. Never prompt text or keys.
- References: [Gemini API data terms](https://ai.google.dev/gemini-api/terms), [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing).

## Hosted controls (Phase 14)

These go in `docs/DEPLOYMENT.md`. Summary:

- Auth gate on every private route. Persistent managed Postgres over pooled TLS with least-privilege roles.
- Fail closed on missing auth or DB config. CSRF protection, no-store caching on private responses.
- No secrets in `VITE_*`, `vercel.json` or Git. `.vercelignore` excludes local data.
- Do not assume Hobby Standard Protection covers production domains.

## Residual risks

To be filled in Phase 11 with actual findings.
