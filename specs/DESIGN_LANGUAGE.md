# DESIGN_LANGUAGE.md — Operator Dashboard Visual & Interaction System

> Scope-locked. Read this before touching any UI code for the operator dashboard.
> This document is **deferred to v2** per `specs/WORKFLOW.md`; it exists now so
> that when the dashboard is built, design decisions are already made.

---

## 1. Purpose & Non-Purpose

**Purpose.** Define the single, opinionated visual and interaction system for the
**operator dashboard** — a read-only monitoring UI used by **one person**: the
operator running their own bot. The dashboard surfaces market data feeds,
detected opportunities, risk decisions, order lifecycle, P&L, and the
kill-switch state.

**Non-purpose.** This document does not cover:

- Trader-facing UIs (there is no end-user trader)
- Marketing pages, landing pages, public website
- Mobile or tablet layouts (operator works at a desktop)
- The bot's CLI or log output (those live elsewhere)
- Internationalization, theming for branding, or white-labeling

If a design question is outside §1 Purpose, it does not belong in this file.

---

## 2. Stack (Frozen)

**Decision.** React 18+ with **Material UI (MUI) v6+** as the sole component
and theming layer. Every UI element on the dashboard is either an MUI component,
an `@mui/x-data-grid` component, or composed exclusively from MUI primitives
and the `sx` prop.

**Why MUI v6+, not something else.**

1. *Maturity.* MUI is the most production-tested React component library; the
   operator dashboard does not need novelty, it needs components that work.
2. *Accessibility.* MUI ships with WCAG-aware defaults (focus rings, ARIA roles,
   keyboard navigation). We do not have a design team to audit accessibility
   from scratch.
3. *Theming.* MUI's `createTheme` + palette tokens give us one place to define
   light/dark and domain semantics. No CSS sprawl.
4. *No design team needed.* The operator is an engineer; "looks like a
   well-built MUI app" is exactly the right ceiling.

**What NOT to use** (hard bans, no exceptions):

- ❌ Tailwind CSS, UnoCSS, or any utility-first CSS layer on top of MUI.
- ❌ Custom CSS frameworks (Bootstrap, Bulma, Chakra, Ant Design).
- ❌ Ad-hoc `styled-components` for **layout** — use MUI's `Box`, `Stack`,
  `Grid`. `styled()` from `@mui/material/styles` is allowed only to extend an
  existing MUI component, never to invent a new layout primitive.
- ❌ Inline `style={{...}}` for anything beyond a one-off pixel nudge. Prefer
  `sx`.
- ❌ Icon sets other than `@mui/icons-material`.

---

## 3. Theme Tokens — One Light, One Dark

Two `createTheme` instances, both following the same palette contract. Operator
toggles via a top-app-bar control; the choice is persisted to `localStorage`.

### 3.1 Light theme

| Token | Hex | Why this color |
|---|---|---|
| `primary.main` | `#1565C0` | Calm, saturated blue — used for primary actions and active nav; not so vivid that it competes with status colors. |
| `secondary.main` | `#455A64` | Slate gray — neutral accent for secondary buttons, never used for status. |
| `error.main` | `#C62828` | Deep red, distinct from the P&L-negative red (§4.1) which is brighter — error is for system failures, not losses. |
| `warning.main` | `#EF6C00` | Amber-orange; passes AA on white and is distinguishable from error to red-green colorblind operators. |
| `info.main` | `#0277BD` | Slightly darker than `primary` so info banners don't read as "primary action." |
| `success.main` | `#2E7D32` | Forest green; reserved for system health, never for P&L. |
| `background.default` | `#FAFAFA` | Off-white. Pure white is hostile on a 10-hour monitoring shift. |
| `background.paper` | `#FFFFFF` | Surfaces sit one level above the canvas — clear elevation cue without a heavy shadow. |
| `text.primary` | `#1A1A1A` | Near-black, not `#000`. Reduces glare while keeping AA contrast on `background.paper`. |
| `text.secondary` | `#5F6368` | Mid-gray for labels and units; legible at small sizes. |

### 3.2 Dark theme

| Token | Hex | Why this color |
|---|---|---|
| `primary.main` | `#64B5F6` | Lightened blue: same hue family as light primary, but bright enough to pass contrast on dark surfaces. |
| `secondary.main` | `#90A4AE` | Lifted slate; secondary actions must read as muted, not invisible. |
| `error.main` | `#EF5350` | Brighter red than light theme — dark backgrounds eat saturation. |
| `warning.main` | `#FFB74D` | Soft amber; high contrast on dark, clearly distinct from error. |
| `info.main` | `#4FC3F7` | Cyan-shifted to separate from primary blue on dark surfaces. |
| `success.main` | `#66BB6A` | Lifted green; system-health only, not P&L. |
| `background.default` | `#121212` | MUI's recommended dark canvas; matches Material's elevation model. |
| `background.paper` | `#1E1E1E` | One step up; cards and tables read as elevated without a hard border. |
| `text.primary` | `#E8EAED` | Off-white; pure white on `#121212` causes ghosting after long sessions. |
| `text.secondary` | `#9AA0A6` | Same role as light theme: labels, units, axis ticks. |

### 3.3 Token contract

- Components MUST consume colors from the theme (`theme.palette.*`), never
  hard-coded hex values in component files.
- Domain semantics (§4) live in `theme.palette.custom.*` extensions and are
  declared once per theme — see §4.

---

## 4. Domain-Specific Color Semantics

Generic MUI gives us `success`/`error`/`warning`. Crypto monitoring needs more.
These tokens extend the theme as `theme.palette.custom.<group>.<state>` and are
the **only** colors allowed for these domain concepts.

### 4.1 P&L direction (positive / negative / flat)

P&L color alone is insufficient — roughly 8% of men have red-green color
deficiency. **Color is paired with a direction icon, always**: `▲` for positive,
`▼` for negative, `■` for flat. Never render a P&L number without its glyph.

| State | Light | Dark | Glyph |
|---|---|---|---|
| Positive | `#1B5E20` | `#81C784` | `▲ ArrowDropUp` |
| Negative | `#B71C1C` | `#E57373` | `▼ ArrowDropDown` |
| Flat | `text.secondary` | `text.secondary` | `■ Remove` |

Positive green is **darker** than `success.main` and negative red is **darker**
than `error.main` so that P&L is visually distinguishable from system
health/error banners at a glance.

### 4.2 Latency tiers

| Tier | Threshold | Light | Dark |
|---|---|---|---|
| Healthy | `< 50ms` | `#2E7D32` | `#66BB6A` |
| Warning | `50–100ms` | `#EF6C00` | `#FFB74D` |
| Critical | `> 100ms` | `#C62828` | `#EF5350` |

Rendered as a `Chip` with `size="small"` plus the numeric value (Roboto Mono,
§5). Above 100ms, the chip pulses once on transition (§10).

### 4.3 WebSocket connection state

| State | Light | Dark | Icon |
|---|---|---|---|
| Connected | `#2E7D32` | `#66BB6A` | `CheckCircle` |
| Reconnecting | `#EF6C00` | `#FFB74D` | `Sync` (rotating, §10) |
| Disconnected | `#C62828` | `#EF5350` | `Cancel` |
| Quarantined | `#455A64` | `#90A4AE` | `Block` |

"Quarantined" = the venue is excluded by the risk layer; visually muted (gray,
not red) because it is an *intentional* state, not a failure.

### 4.4 Order lifecycle

Rendered as `Chip` with the color below and the state name as the label.

| State | Light | Dark |
|---|---|---|
| pending | `#5F6368` | `#9AA0A6` |
| submitted | `#0277BD` | `#4FC3F7` |
| partial | `#EF6C00` | `#FFB74D` |
| filled | `#1B5E20` | `#81C784` |
| cancelled | `#455A64` | `#90A4AE` |
| rejected | `#C62828` | `#EF5350` |
| failed | `#880E4F` | `#F06292` |

`rejected` (exchange said no) and `failed` (network/system fault) are visually
distinct. Operator triage differs.

### 4.5 Kill-switch — unmistakable

When the kill-switch is engaged, the operator MUST see it from any panel:

1. Top app bar background becomes **solid `#C62828` (light) / `#B71C1C`
   (dark)** with white text — overrides the normal app-bar color.
2. A persistent `Banner` (composed from MUI `Alert severity="error"
   variant="filled"`) is rendered as the first child of every page.
3. The browser tab title is prefixed with `[KILL] `.
4. Every action that would submit an order is `disabled`, with a `Tooltip`
   explaining why.

This is the only place where redundancy is required by design.

---

## 5. Typography

- **Default font:** MUI's default Roboto, loaded via `@fontsource/roboto`.
- **Numeric font:** **Roboto Mono** (`@fontsource/roboto-mono`) for **every**
  number where alignment matters: prices, quantities, P&L, latency, fees,
  timestamps, order IDs. Reason: tabular figures align by digit; proportional
  digits do not. An operator scanning a column of P&L values needs digit
  alignment to detect anomalies.
- **Typography scale:** MUI's default `h1`–`h6`, `body1`, `body2`, `caption`,
  `overline`. Do not invent new variants. Map dashboard structure to the
  default scale:
    - `h4` — page title (only one per page)
    - `h6` — panel/card title
    - `subtitle2` — KPI tile label
    - `body1` — prose, dialogs
    - `body2` — table cells (prose columns only — numeric cells use Mono)
    - `caption` — units, axis labels, timestamps in dense rows

---

## 6. Layout Primitives

- **Spacing scale:** MUI's default 8px base (`theme.spacing(1) === 8px`). Use
  `theme.spacing(n)` everywhere; no raw pixel values for spacing.
- **Container max-widths:** the dashboard is full-bleed. The main content area
  is a `Box` with `maxWidth: theme.breakpoints.values.xl` and `mx: "auto"`.
  Tables are allowed to scroll horizontally within their card; the page does
  not.
- **Breakpoints:** MUI defaults (`xs` 0, `sm` 600, `md` 900, `lg` 1200, `xl`
  1536). Below `md`, the dashboard renders a "this dashboard is desktop-only"
  empty state — we do not adapt for mobile (§1 non-purpose).
- **Canonical layout:**

      ┌──────────────────────────────────────────────────────────────┐
      │  AppBar (top, fixed)                                         │
      │   ├─ App title          ├─ Theme toggle  ├─ Kill-switch chip │
      ├──────────┬───────────────────────────────────────────────────┤
      │          │                                                   │
      │ LeftRail │   Main content area                               │
      │  (nav)   │     ├─ Page title (h4)                            │
      │          │     ├─ Active panel (Cards / DataGrid / ...)      │
      │          │                                                   │
      └──────────┴───────────────────────────────────────────────────┘

  Implementation primitives: `AppBar`, `Drawer variant="permanent"` for the
  left rail, `Box component="main"` for content. No tabs at the top level —
  navigation is the left rail.

---

## 7. Components Catalog (Canonical Usage)

**Allowed and their assigned role.** A component used outside its assigned
role is a bug.

| Component | Role |
|---|---|
| `DataGrid` (`@mui/x-data-grid`) | All tabular data: orders, fills, opportunities, venue health. No `<table>` HTML elsewhere. |
| `Card` + `CardContent` | KPI tiles (single number + label + trend glyph) and panel containers. |
| `LinearProgress` | In-flight indicator for a single named operation (e.g., "submitting order"). |
| `CircularProgress` | Page-level or panel-level loading state only. Size `size={24}` for inline use. |
| `Alert` | Persistent incidents (e.g., venue quarantined). `severity` mapped to §3/§4 semantics. |
| `Snackbar` | Transient notifications (≤ 6s) for completed actions. Never for errors that need acknowledgement. |
| `Chip` | Status badges — order state (§4.4), connection state (§4.3), latency tier (§4.2). Always `size="small"`. |
| `Tooltip` | **Required** on any numeric value whose unit is not in the column header (e.g., a raw `0.0023` without `BTC` next to it). |
| `Dialog` | Confirmation for destructive operator actions (engage kill-switch, force-cancel order). |
| `IconButton` | Single-icon actions in dense rows. Always with `aria-label`. |
| `Switch` | Boolean operator preferences (theme, density override). |
| `Tabs` | Sub-navigation **within** a panel only, never at page level. |

**Explicitly forbidden** on the operator dashboard:

- ❌ `SpeedDial` — playful, hides actions; operators need discoverability.
- ❌ `Stepper` — there are no multi-step wizards in a monitoring UI.
- ❌ `Rating` — no use case.
- ❌ `Avatar` for anything other than the operator's own identity in the app
  bar. No avatars on rows.
- ❌ `Backdrop` over the whole page except for the kill-switch confirmation.
- ❌ `Skeleton` shimmer for sub-1s loads — feels slower than just rendering
  the result (see §10).
- ❌ Decorative dividers, watermarks, gradients, or any visual that does not
  carry information.

---

## 8. Density

The dashboard defaults to MUI's **dense** density (`DataGrid density="compact"`,
`Table size="small"`, `Button size="small"` in toolbars). Reason: the operator
reads dozens of rows at a glance; default Material density wastes vertical
space and forces scrolling that hides anomalies.

The operator can override to "standard" via a top app-bar `Switch`; the choice
is persisted to `localStorage`. "Comfortable" is not offered — it adds visual
weight without adding information.

---

## 9. Empty States & Error States

Every list/table MUST define three states beyond the happy path. No "the table
just doesn't render" — silent empty UIs train the operator to distrust the
dashboard.

| State | What it shows |
|---|---|
| **No data yet** (cold start, no opportunities detected, etc.) | Centered MUI `Box` with a muted icon, a one-sentence explanation in `body2`, and — if applicable — what the operator can do (e.g., "Waiting for first market snapshot — check venue connection state"). |
| **Fetch failed** | `Alert severity="error" variant="outlined"` with the error message and a `Retry` action. Never just hide the error. |
| **Data is stale** | A `Chip` with the age (e.g., "12s ago") in the panel header. Tier: `< 5s` healthy, `5–30s` warning color, `> 30s` critical. Use §4.2 latency colors. The data is still shown — the chip warns the operator that it may be wrong. |

Stale-but-shown beats fresh-but-blank for a monitoring UI: the operator can
reason about old data; they cannot reason about no data.

---

## 10. Motion

**Default: still.** Operators trust still UIs more than animated ones.

Allowed motion:

- `LinearProgress` / `CircularProgress` — required, indicates in-flight work.
- A single brief pulse (300ms, `ease-out`) on a `Chip` when its state changes
  to a worse tier (latency healthy → warning, connection connected →
  reconnecting). State changes to a *better* tier do not animate.
- The `Sync` icon rotates while connection state is `reconnecting`.

Banned motion:

- ❌ Page transitions, panel fade-ins, card flips.
- ❌ Skeleton shimmer for sub-1s loads (see §7).
- ❌ Hover scale, parallax, decorative loops, confetti, anything celebratory.
- ❌ Counting-up number animations on P&L. Show the number.

If a designer asks "wouldn't a small animation make this feel nicer?" — the
answer is no. The operator is watching their money; they do not want it to
feel nice, they want it to feel **honest**.

---

## 11. Accessibility

**WCAG AA contrast is required** for every color combination defined in §3
and §4 against the surface it appears on (`background.default` or
`background.paper` for the relevant theme). This is non-negotiable; operators
read this UI for hours.

Verification (runs in CI before any dashboard PR merges):

1. **MUI's built-in contrast utilities** (`getContrastRatio` from
   `@mui/material/styles`) — unit test that asserts ratio ≥ 4.5 for every
   `text.*` / `background.*` and `custom.*` / `background.*` pair.
2. **axe-core** via `@axe-core/react` in component tests — every page-level
   component is wrapped in an axe assertion that fails on any violation of
   severity `serious` or higher.
3. **Keyboard navigation** — every interactive element reachable by `Tab`;
   no `tabIndex={-1}` workarounds. Order of traversal follows the visual
   left-to-right, top-to-bottom flow.
4. **Color is never the sole signal** — every status color is paired with an
   icon or a text label (see §4.1 for the canonical example).

---

## 12. What This Document Does NOT Cover

Out of scope, full stop:

- Marketing pages, landing pages, public-facing copy.
- Mobile or tablet layouts. The dashboard is desktop-only.
- A user-facing trader UI. There are no end-user traders; the operator is the
  only user.
- Onboarding flows, tutorials, or first-run experiences (the operator built
  the bot).
- Email templates, push notifications, or off-dashboard surfaces.
- Anything outside `src/dashboard/` when that directory exists.

When in doubt, re-read §1. If the question is not §1 Purpose, the answer is
"out of scope; not in this document."
