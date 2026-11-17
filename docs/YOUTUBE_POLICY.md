# YouTube policy

The URLs below are the official starting references, carried over from the master pack on 2026-11-17. Each phase that relies on them (03, 04, 08, 11, 14) must re-check the current text and record the date checked in the table. Phase 03 verified the Data API pages marked below (HTTP 200, no redirect; the pages show no "last updated" date). The `/youtube/data/...` paths in the original pack are kept for reference only; the verified pages live under `/youtube/v3/...`.

## Official data sources and policy URLs

| Topic | URL | Last verified |
|---|---|---|
| Data API overview and quotas | https://developers.google.com/youtube/v3/getting-started | 2026-11-17 (Phase 03) |
| Quota cost calculator | https://developers.google.com/youtube/v3/determine_quota_cost | 2026-11-17 (Phase 03) |
| `videos.list` | https://developers.google.com/youtube/v3/docs/videos/list | 2026-11-17 (Phase 03) |
| `search.list` | https://developers.google.com/youtube/v3/docs/search/list | 2026-11-17 (Phase 03) |
| `playlistItems.list` | https://developers.google.com/youtube/v3/docs/playlistItems/list | 2026-11-17 (Phase 03) |
| Error reference | https://developers.google.com/youtube/v3/docs/errors | 2026-11-17 (Phase 03) |
| Data API reference | https://developers.google.com/youtube/data/reference/rest | not yet |
| `videos` resource fields | https://developers.google.com/youtube/data/reference/rest/v3/videos | not yet |
| Sample requests (uploads playlist) | https://developers.google.com/youtube/data/sample_requests | not yet |
| Developer Policies | https://developers.google.com/youtube/terms/developer-policies | not yet |
| Developer Policies guide | https://developers.google.com/youtube/terms/developer-policies-guide | not yet |
| Derived metrics and storage policy | https://developers.google.com/youtube/terms/derived-metrics-policy | not yet |
| Audit/amendment application form | https://support.google.com/youtube/contact/yt_api_form | not yet |
| Analytics reports query (own channel, OAuth, later) | https://developers.google.com/youtube/analytics/reference/reports/query | not yet |
| Analytics metric definitions | https://developers.google.com/youtube/analytics/metrics | not yet |
| Gemini API data terms (AI data use) | https://ai.google.dev/gemini-api/terms | not yet |
| Gemini API billing | https://ai.google.dev/gemini-api/docs/billing | not yet |

## Allowed by default (standard mode)

- Read-only official Data API methods: `search.list`, `videos.list`, `channels.list`, `playlistItems.list`.
  - Use an API key restricted to YouTube Data API v3 on a personal Google Cloud project.
  - No OAuth is needed for public discovery.
- Hydrate up to 50 IDs per `videos.list` call, with partial-response `fields`.
- Fields: current title, channel ID/name, `publishedAt`, description only where needed and permitted, duration, category, thumbnails, view/like/comment counts when provided, available language, embeddable/status hints.
- Show source fields, raw sorting, sample coverage and QA counts, and simple aggregations only where expressly supported.
- Show links and thumbnails with attribution. Use the official watch page or IFrame player, and respect non-embeddable videos.
- Editor-only idea ranking from independently entered editorial inputs (`docs/ANALYTICS.md`).

## Quotas (verify before every live run)

Verified on the official pages on 2026-11-17 (Phase 03):

| Method | Bucket | Cost per request |
|---|---|---|
| `search.list` | own **Search Queries** bucket, default **100 calls/day** | 1 |
| `videos.list` | shared bucket, default **10,000 units/day** | 1 |
| `channels.list` | shared bucket | 1 |
| `playlistItems.list` | shared bucket | 1 |

- The docs say defaults are "subject to change". The quota page says daily quotas reset at midnight Pacific Time. It also says every request, including an invalid one, costs at least one unit, so the adapter charges every attempt, retries included.
- The old 100-unit search price is **not** used anywhere. Costs live in one table (`backend/gta_lab/youtube/quota.py`), which a test pins to the values above.
- **Console quotas: not verified.** The project's real limits can only be read in the Google Cloud Console, and no project or key exists yet. Check them before the first live run. A local budget is a self-imposed cap, never permission to go above the Console values.
- Use per-bucket quota estimation. When quota runs out, pause and resume. Never use multiple projects or keys to get around limits.
- Paging limits: `search.list` and `playlistItems.list` return at most 50 per page. Paging always follows `nextPageToken`, and `search.list` results for one channel stop at 500. `videos.list` takes a comma-separated `id` list. The adapter caps it at 50 per request, which is the project rule; the page states no maximum. `maxResults` is not sent with `id`, because the docs say they cannot be combined.

## Adapter behaviour (Phase 03, `backend/gta_lab/youtube/`)

- Only `search.list`, `videos.list`, `channels.list` and `playlistItems.list` can be called. The transport is pinned to `https://www.googleapis.com/youtube/v3/`, refuses redirects and caps bodies at 2 MB. Seed links are parsed, never fetched.
- Partial responses:
  - `videos.list`: `part=snippet,contentDetails,statistics,status`, and `fields` = id, publishedAt, channelId/Title, title, categoryId, defaultLanguage, defaultAudioLanguage, thumbnails, duration, view/like/comment counts, embeddable, privacyStatus, uploadStatus.
  - `search.list`: `part=id`, `type=video`, video IDs only.
  - `playlistItems.list`: `contentDetails.videoId` only.
  - `channels.list`: id, title and uploads playlist.
- **Descriptions are not requested.** Nothing needs them yet, and the DB has no column for them. Comments, captions, files and player embeds are never requested.
- There is no Shorts flag. A `/shorts/` seed link is normalized to a plain video ID, and nothing is inferred from duration.
- Missing counts stay `None`, shown as "Unavailable", never 0.
- Retries: timeouts, network failures, HTTP 429/5xx and 403 rate-limit reasons, up to 4 attempts. Delays use full-jitter exponential backoff (0.5 s base, 8 s cap). `Retry-After` is honoured up to the cap.
- These are never retried and stop cleanly:
  - invalid key or 401 → `bad_key`
  - 403 `quotaExceeded`/`dailyLimitExceeded` → `quota_exhausted` (resumable)
  - other 403 → `permission`
  - 404 → `not_found`
  - other 400 → `bad_request`
  - malformed body → `malformed`
  - local budget → `budget_exhausted` (resumable)
- Paged and batched helpers return their partial results with a resume page token or the remaining IDs.
- The official error page lists `quotaExceeded` (403) and `forbidden` (403). The rate-limit reasons and the invalid-key, `accessNotConfigured` and `SERVICE_DISABLED` reasons are not on that page. They are mapped defensively from Google's standard error format, and this mapping must be confirmed against real responses in the live smoke check.

## Explicitly disabled

- Comment text, caption downloads, video or thumbnail file downloads, transcripts, scraping, arbitrary URL fetches.
- Inferring a Shorts flag from duration alone.
- API-derived scores, inferred labels, automated taxonomy enrichment, predictive performance outputs, and automated links from raw views to rankings.
- Permanent snapshot or history archives of public stats.
- Training or fine-tuning on API data, or sending API data to any external model.
- Combining API metrics with manual notes in one view, unless the policy check in Phase 05 confirms that linking and display are allowed. Otherwise, use links for navigation only.

## Retention (standard mode)

- Refresh or delete applicable API data **no later than 30 calendar days** after fetch, and refresh proactively before expiry.
- On refresh, replace current stats. Do not accumulate them.
- Handle deleted, private and missing items, API errors vs missing data, changed titles and thumbnails, and expired references in derived views and exports.
- **Never read or display stale data just because a refresh failed.**
- Purge expired API-derived cache, associations and artifacts. Keep only independently authored note or brief text with no copied API data.
- Avoid uncontrolled DB backups. Exports, backups and rollbacks must never restore expired API data.

## Approval scope (gate 3, approval-only)

A capability is enabled only with written YouTube approval for the exact use case. A local config flag by itself is **not** evidence. Each row stays `off` until proof exists.

| Capability | Status | Proof source / date | Allowed inputs | Output | Retention |
|---|---|---|---|---|---|
| Cohort analytics (medians, distributions, strata) | off | — | — | — | — |
| Statistical history table | off | — | — | — | — |
| API-derived taxonomy enrichment | off | — | — | — | — |
| Predictive performance model | off | — | — | — | — |

Phase 08 expands this checklist. Prototypes use **synthetic data only**.

## AI data use (Phase 13, optional)

Never send YouTube API data, competitor titles or thumbnails, captions, screenshots, IDs, private Studio metrics, tokens, raw DB rows or full app context to any model. Only explicitly selected, creator-authored, non-sensitive fields are allowed. Rules are in `docs/SECURITY.md`.

## Own-channel data

- Manual entry from YouTube Studio is optional and kept separate from the public corpus.
- OAuth is a later addition only. When added, it needs endpoint and metric support, least privilege, secure token storage, revocation and deletion, and separate verification.
- Instagram performance is out of scope.
