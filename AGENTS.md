# Engineer Tests GTA — agent instructions (canonical)

This is the single canonical agent instruction file. `CLAUDE.md` only imports it. Edit rules here, never in both.

Engineer Tests GTA is a Windows 11, local-first creator intelligence tool for one creator's own GTA VI channel. Its one primary loop: **find YouTube evidence → decide what to film → build an actionable 30-day plan** across YouTube long-form, YouTube Shorts and Instagram Reels. Single-player story mode and offline gameplay only. Product scope lives in `APP.md`.

## Read order (every session)

1. This file.
2. `STATUS.md`, which holds the current phase, gate results and the one next action.
3. `docs/phases/NN.md` for the phase you were told to run.
4. Only the spec sections that phase file lists under **Read**.
5. `docs/GATES.md` when you record a gate or a blocker.

Do **not** read `MASTER_PACK.md.md`. Everything canonical has been moved into the files below. Do not read all of `PROMPT_HISTORY.md`, only its last entry when needed.

| File | Owns |
|---|---|
| `APP.md` | Problem, audience, output, scope, exclusions, MVP acceptance |
| `STATUS.md` | Current phase, gate results, exactly one next action (keep under ~80 lines) |
| `PROMPT_HISTORY.md` | Append-only phase log |
| `docs/GATES.md` | The five release gates, independent work vs capability blocks, status vocabulary |
| `docs/SYSTEM_DESIGN.md` | Boundaries, topology, runtime, run commands, data lifecycle, toolchain |
| `docs/DATA_CONTRACT.md` | Entities, fields, null rules, lineage, source hierarchy, data separation |
| `docs/SAMPLING.md` | Study population, strata, exclusions, collection and validation method |
| `docs/YOUTUBE_POLICY.md` | Official source URLs, allowances, disabled features, approval scope, retention, AI data use |
| `docs/ANALYTICS.md` | Standard-mode reporting, editorial ranking, gated analytics, forecasting guardrails |
| `docs/DESIGN.md` | Tokens, layouts, accessibility, responsive and visual acceptance |
| `docs/CONTENT_PLAYBOOK.md` | Pillars, publishing lanes, 30-day plan, brief template, review loop |
| `docs/SECURITY.md` | Threat model, credential and dependency controls, scanning rules |
| `docs/DECISIONS.md` | Canonical decisions D-001 onward |
| `docs/DEPLOYMENT.md` | Hosted topology and runbook, **created in Phase 14 only** |

## Phase workflow and stop rule

- Run **exactly one phase per session**: the one named in the command. Never start the next phase.
- Before changing code, state the scope and acceptance commands. Check `git status` and the previous phase's gate in `STATUS.md`. If a prerequisite fails, report it with evidence. Fix it only if the fix falls inside this phase; otherwise stop at the blocker.
- At the end, record each gate or check as **passed**, **failed**, **not run** or **blocked**, with evidence, in `STATUS.md`. Then append an entry to `PROMPT_HISTORY.md`.
- If a phase grows too large, split it into checkpoints inside that phase and resume from `STATUS.md`.
- If a credential, approval or quota is missing, finish the independent fixture work and record the exact blocked live task (see `docs/GATES.md`).
- Commit or push only when the user asks.

**Next-session command (phase runner).** Replace `NN` with the number in `STATUS.md` → *Next action*:

```text
Execute Phase NN only from docs/phases/NN.md. Start with CLAUDE.md (or AGENTS.md),
STATUS.md, the current phase file, and only the spec sections the phase references.
Check git status and the previous acceptance gate. Report any failing prerequisite with
evidence, fix only what falls inside this phase, and otherwise stop at the blocker.
Implement the phase, run its acceptance tests, and update STATUS.md and PROMPT_HISTORY.md
with exact results and the next command. Do not start the next phase.
```

## Non-negotiable boundaries

- **No fabrication.** Never invent metadata, real video IDs, statistics, tests, source citations, dependency scan results, launch dates or completion. Fixtures contain no real IDs or metrics. Write an observation as "watched" only when a human watched it.
- **No secrets in chat, Git, logs or the frontend.** Never ask the user to paste a key into chat. YouTube keys live only in process env or the gitignored private local config, read by the backend/CLI. Never put a secret in `VITE_*`.
- **Official YouTube Data API only.** No scraping, downloads, transcripts, caption or comment text, or arbitrary URL fetches. Instagram is an output format, never a data source.
- **Respect retention.** Refresh or delete API data within 30 days. Suppress expired data even when a refresh fails (`docs/YOUTUBE_POLICY.md`).
- **Fail closed.** Advanced analytics, AI and hosted live mode stay off until their own gate passes. A local config flag is not evidence of permission.
- **Bounded context.** Never load the ~2,500 rows into agent context. Query bounded samples, schema and summarized health counts.
- **Honest UI.** Unsupported data shows `Unavailable`, `Unknown` or `Not yet collected`. No fake "live" status, hardcoded findings or dead controls.
- **Supply chain.** Verify package versions at install time. Commit `uv.lock` and `package-lock.json` and install with `uv sync --locked` / `npm ci`. Never run `npm audit fix --force`. A stopped scan is not a clean scan (`docs/SECURITY.md`).
- **Preserve user work.** Never overwrite or delete existing user files. Never initialize, install or write outside this repo, except toolchain installs the user approves.
- **No outward action without the user.** No deploy, billing, DNS, Git push, public upload or credential creation.
