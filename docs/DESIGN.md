# Design

Tokens are implemented as CSS custom properties in Phase 06. The look is an editorial analyst's workstation with original coastal-night styling.

## Tokens (starting values; test contrast and adjust if needed)

| Token | Value | Use |
|---|---|---|
| `--shell` | `#10151D` | App shell |
| `--surface` | `#18202B` | Primary surface |
| `--text` | `#F0F1F3` | Near-white text |
| `--action` | `#70D6BF` | Seafoam, for actions |
| `--emphasis` | `#FF8C79` | Muted coral, for sparse emphasis |

- Use available system fonts and **tabular numerals**.
- Faint original shoreline/contour art may appear in the shell only. It must never be an invented GTA VI map.

## Prohibited

Rockstar logos, copied artwork, in-game screenshots used as shell decoration, neon gradients, glass cards, oversized marketing copy, animated chrome, emoji-heavy dashboards.

Legitimate YouTube thumbnails may appear only in the evidence experience, as sourced content with attribution. Show an **unofficial / no-affiliation** note.

## Layouts

- **Desktop:** slim left navigation, central work area, and an evidence detail rail that can be resized or collapsed if useful.
- **Research** (default landing): sample coverage and one clear next action. Not a cinematic cover.
- **Evidence:** dense sortable table plus a detail drawer.
- **Comparisons:** side-by-side examples with unknowns shown.
- **Planner:** opens to this week's queue, with a 30-day grid and a chronological list.
- **Review:** a record-and-decide workflow.
- **Mobile:** list first, compact filters, full-screen detail, practical tap targets.

## Accessibility and states

- Text or table alternatives for every chart. Visible focus, keyboard routing, reduced-motion support.
- Required states: empty, error, refreshing, quota-limited. Expired data is suppressed, and missing data shows `Unavailable`, `Unknown` or `Not yet collected`.
- No dead controls.

## Visual acceptance

Keyboard and contrast check. Screenshots at about **1440 px** and **390 px**. No overflow. Four distinct real-state examples rendered.
