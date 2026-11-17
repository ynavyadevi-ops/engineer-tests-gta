# APP — Engineer Tests GTA

## Problem and audience

One solo creator is starting a GTA VI channel. They need a recurring way to see what kinds of GTA videos exist and how they are packaged, then decide what to film themselves and plan a month of output. The audience is that creator, working as their own editor. It is not a multi-user product.

## Output

- A local dashboard and searchable evidence catalog.
- An editor's research workflow that records what a human actually saw.
- A 30-day capture and publishing calendar.
- A weekly review loop for the creator's own releases.

The output that matters is a **brief**. For example: "Test whether NPCs react differently to the same road blockage in two districts", with a fair capture protocol, an opening shot, a thumbnail composition, platform cuts and a fallback if the mechanic is absent. The brief template is in `docs/CONTENT_PLAYBOOK.md`.

## Functional scope

| Area | Route | Scope |
|---|---|---|
| Research | `/research` (default landing) | Sample coverage, QA counts, one clear next action |
| Evidence | `/evidence` | Filterable/sortable catalog of eligible videos with provenance, thumbnails, direct links, fetch dates |
| Comparisons | `/comparisons` | Curated GTA V vs IV / San Andreas evidence boards on the same question |
| Planner | `/planner` | Days 1–3 queue, 30-day grid and list, briefs, editorial ranking |
| Review | `/review` | Own-channel publishing ledger, checkpoints, promising/retest/retire decisions |
| Data health | `/data-health` | Freshness, expiry, quota, run and coverage status |

- **Research lens:** systems and physics, maps and hidden details, side missions and practical guides, mythology/cheats, comparisons. Keep title hook, thumbnail promise and observable cold open distinct. Never claim a hook *caused* performance.
- **Three publishing lanes:** YouTube long-form, YouTube Shorts, Instagram Reels (`docs/CONTENT_PLAYBOOK.md`).
- **Three editorial pillars:** Systems & Myth Tests, Map/World & Hidden Details, Missions & Useful Discoveries. GTA IV/V/SA comparison is a lens across the pillars, not a fourth format.
- **Planner defaults:** configurable start date, time zone (default `Asia/Kolkata`), language (e.g. English/Hinglish) and weekly budget (starter 10–12 h, editable). Starter mix: **4 long-form, 12 Shorts, 8 Reels** over four editorial weeks, then Days 29–30 for review and buffer.

## Study population (summary; full rules in `docs/SAMPLING.md`)

Target **2,500** unique eligible GTA V videos, with **2,000** as the minimum live-sample gate. Separately, aim for **100–200** eligible videos each for GTA IV and San Andreas. These comparator samples do not count toward the GTA V floor.

## Exclusions (not built)

- Monetization guarantees, competitor revenue estimates, virality or view-count predictions.
- Automatic posting, billing, audience automation, multi-user auth (local MVP).
- Instagram as a data source or a performance proxy.
- Scraping, downloading media, transcripts or captions, comment text.
- GTA Online, FiveM/RP, leaks, trailers without gameplay.
- Other creators' private metrics (watch time, CTR, impressions, retention).
- Live deployment. Phase 14 prepares Vercel and does not deploy.

## MVP acceptance

The MVP is accepted through the separate gates in `docs/GATES.md`. **APP READY** (fixture-driven functions and tests pass) is the MVP bar. **LIVE SAMPLE READY**, **ADVANCED ANALYTICS READY**, **AI OPTIONAL** and **VERCEL READINESS** are each reported independently and are never implied by one another.

The end-to-end walkthrough is: evidence → comparison → brief → 30-day plan → weekly review action.
