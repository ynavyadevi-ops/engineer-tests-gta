# Analytics

## Standard mode (default, live)

- Raw source fields, raw sorting by views, date or title, sample coverage and QA counts, kept apart from YouTube business metrics.
- Simple aggregations only where policy expressly supports them (`docs/YOUTUBE_POLICY.md`).
- Detail views show explicit **"unavailable for other creators"** states for watch time, impressions, CTR and retention.
- No API-derived scores, inferred labels or predictive outputs.

## Editorial priority score (planner ranking)

This score uses only independently entered editorial inputs. It is shown line by line and the weights are editable:

| Input | Weight |
|---|---|
| Visual proofability | 25% |
| Originality | 25% |
| Timely/useful payoff | 20% |
| Feasible capture | 15% |
| Repurpose value | 15% |

- It is an **editorial priority score, not demand or probability.**
- Confidence (high/medium/low) reflects real capture and evidence quality, not a predicted percentage.
- There is no default automated link from raw view counts to the ranking. Source links are for the editor to open, as permitted.

## Gated advanced analytics (gate 3; default off, fails closed)

Activate only with scope-specific YouTube approval.

- Compare same-format, edition, era, age and other supportable strata. Report sample n, channel concentration, and medians or distributions if permitted. Mark descriptive associations and small cells.
- Predeclared support: **n ≥ 20 and at least 5 channels**. Suppress sparse cells, run a leave-one-channel-out check, and check selection and survivorship effects.
- Keep view-definition and reporting eras apart, and watch for format or metric changes.
- Current subscriber counts are not historical audience size. Lifetime views divided by video age is not launch velocity. Never fabricate age-aligned history.
- Extra history needs approved retention scope, and statistical and non-statistical fields keep their own expiry rules.
- Prototypes and evaluation use **clearly synthetic data**.

## Forecasting guardrails

- Start with editorial hypotheses and a **no-skill baseline**.
- A real performance model is considered only on permitted, comparable, time-aligned outcomes (for example own-channel day-7 performance), with enough data and proper authorization.
- Validation: later held-out time windows, disjoint channels if multichannel data is approved, feature cutoffs before the outcome, and out-of-sample errors. Use only features observable at decision time. Disclose GTA VI and new-channel domain shift.
- **Do not ship numeric forecasts when data is inadequate or the baseline wins.**
- Never forecast private watch time or CTR, hallucinate view counts, rank creator revenues, promise virality, or imply causal thumbnail lift from public counts.

## Own-channel review metrics (Phase 10)

- Use metric sets appropriate to each format. Long-form: impressions, CTR, average view duration and retention when available. Shorts: engaged views and the relevant Studio metrics. Never compare raw Shorts counts with long-form counts.
- Use 24-hour and day-7 checkpoints, preserving the metric definition, time window and source. Missing values stay blank.
- Decisions are made by human review (promising/retest/retire). No unsupported numeric inference.

## Evaluation plan

Hand-scored fixtures must match the weights. Unknowns surface. Gated capabilities fail closed. Synthetic backtests are reproducible. Research adds uncertainty and alternatives, not made-up predictions.
