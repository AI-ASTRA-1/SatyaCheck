# SatyaCheck landing page

Story-driven marketing page for SatyaCheck. New scope, outside the R5/R6
dashboard briefs (see `roles/ROLES.md`). Links into `web/dashboard-a/`.

## Run

```
npm install
cp .env.example .env   # set VITE_DASHBOARD_URL if dashboard-a runs on a different port
npm run dev
```

Build: `npm run build` (type-checks then bundles to `dist/`).

## Stack and why

- **Vite + React + TypeScript** — no server-rendering need; this is a static
  page with client-side scroll animation only.
- **Tailwind CSS v4** (`@tailwindcss/vite`) — CSS-first `@theme`, no separate
  PostCSS config; wired to the design tokens in `src/styles/tokens.css`.
- **GSAP + ScrollTrigger** — the one animation dependency, used for the
  scroll-driven "how it works" section (sticky image, cross-fading product
  shots as text scrolls past). Reliable cross-browser scroll pin/scrub isn't
  yet consistent via native CSS scroll-timeline alone.
- **@fontsource-variable** — self-hosted variable fonts (Playfair Display,
  Outfit), not a CDN.
- No router (one scrolling page), no chart library (no live data here), no
  Three.js/WebGL (the hero uses an animated CSS gradient-mesh instead, to
  avoid the dependency weight and mobile-GPU risk — see the plan for the
  trade-off if more visual weight is wanted later).

## Design system

Dark Luxury palette, Playfair Display + Outfit, 1.333 type scale. Full
rationale in the approved plan (`docs/superpowers` is not used by this repo;
see the session's plan file referenced in the PR/commit, or `AGENTS.md`
wording rules this content follows).

## Content discipline

Every string lives in `src/content/copy.ts`; every numeric claim lives in
`src/content/stats.ts` with a `verified` flag and, where applicable, a
citation. This keeps the wording-rule and citation audit a single-file check:
no "detects" (it warns, a human decides), no "solved", no unhedged "real
time", no unqualified "ID not verified" figure, no em dashes.

## Scope

Landing page only. Does not touch `contracts/`, `backend/`, `ml/`,
`acquisitions/`, `app/`, `tests/`, `docs/`, `roles/`, or `web/dashboard-b/`.
