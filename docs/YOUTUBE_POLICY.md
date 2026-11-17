# YouTube policy

The URLs below are the official starting references, carried over from the master pack on 2026-11-17. **None of them have been re-verified live yet.** Each phase that relies on them (03, 04, 08, 11, 14) must re-check the current text and record the date checked in the table.

## Official data sources and policy URLs

| Topic | URL | Last verified |
|---|---|---|
| Data API overview and quotas | https://developers.google.com/youtube/data/getting-started | not yet |
| Quota cost calculator | https://developers.google.com/youtube/data/determine_quota_cost | not yet |
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

- At the time of writing, the master pack says the standard allocation is a **100-calls/day search bucket** plus **10,000 daily units** for other methods. Do **not** hardcode the old 100-unit search pricing. Check the actual project limits in the Cloud Console.
- Use per-bucket quota estimation. When quota runs out, pause and resume. Never use multiple projects or keys to get around limits.

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
