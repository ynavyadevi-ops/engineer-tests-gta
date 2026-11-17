# Sampling

The query and seed-channel manifest (versioned), its coverage and its funnel reports are added in Phase 04. Eligibility workflow details are added in Phase 05.

## Study population

- **GTA V:** public, discoverable YouTube videos about offline gameplay, from the original launch window through collection day.
  - Target **2,500** unique eligible videos.
  - Minimum usable live-sample gate: **2,000**.
- **Comparators:** aim for **100–200** eligible videos **each** for GTA IV and San Andreas. They do **not** count toward the GTA V floor.
- Older-game samples are YouTube-era surviving uploads, **not** complete launch-era histories.
- No promise to enumerate every original upload, recover removed content or reconstruct launch-week views from a current cumulative counter.

## Exclusions

- GTA Online, FiveM/RP, leaks, trailers without gameplay, duplicate IDs.
- Ambiguous mixed offline/Online entries go to `needs_review`, never into the denominator, until reviewed.
- Offline mods, full playthroughs and archival footage are separately marked or excluded from the main cohort. They are never silently mixed with unmodded discovery videos.
- Original games are kept apart from remasters, DLC and platform re-releases where known.

## Strata

- **GTA V eras:** launch window, early years, mature back catalog, recent uploads. Dates are bounded at collection time.
- **Comparators:** separate age/era buckets. Report launch-year gaps. Record editions and remasters separately.
- Original release dates come from **official sources**, with stored citations.
- **Topic families (long-tail keywords):** systems/physics, maps/secrets, side missions, guides, myths, comparisons.
- Language and region settings are discovery hints, **not** audience demographics.

## Collection method

- Combine date-bounded relevance and date-ordered searches, some popularity searches, and configured uploads playlists or curated YouTube playlists. Never rely only on most-viewed results or on one channel.
- Use a configurable **per-channel concentration threshold**, with an override and an explicit report.
- **CLI modes:** `plan` (no network, gives an estimated budget) and `run`/`resume` (explicit network use; bounded date windows, pages, candidates and search-quota caps).
- **Track:** discovery path, page/cursor, query, era, locale, run time, retries, duplicate IDs, unavailable results, and eligible/excluded/review counts. Checkpoints are idempotent.
- When quota runs out, the run **pauses** and resumes in the next quota window or after an authorized extension. Never use multiple projects or keys.
- **Staged rollout:** tiny smoke run → roughly 200–400 candidates for sampling QA → batches sized to the observed duplicate and exclusion rates. Pilot quality, not raw search count, decides whether coverage is good.
- Fifty full hydration batches cover 2,500 *already-known* IDs. That is not an estimate for the whole collection.

## Eligibility and validation

- Screening states: `accepted`, `excluded`, `needs_review`, each with reasons.
- Record base game/edition, offline confirmation or uncertainty, language when evidenced, format evidence, discovery family and reviewer status, as far as policy allows.
- Metadata search matches are **candidates, not facts**. Under the default policy, use curated queries and seed choices plus a human inclusion queue, not API-derived inferred content types. Optional taxonomy enrichment stays disabled until approved.
- **Format:** manually verified vertical Short / standard upload / build-specific footage / unknown. Duration alone cannot establish format, and there is no reliable public Shorts flag.
- **Audit:** a blind-to-views queue that spans eras, topics, formats and mid-sized channels, including some low or ordinary performers. Start a **100–150 row** stratified packaging audit. At full scale, use vetted seed cohorts plus stratified manual adjudication, spot checks and a conservative unknown bucket. Never certify the entire set as watched.
- Report counts by qualification level (human-verified vs source-qualified).
