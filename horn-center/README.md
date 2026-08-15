# Horn Center Reservations

A student-authenticated reservation dashboard for the Horn Center at CSULB, built
to run on Microsoft Power Platform — with a working React prototype you can demo
today, before anyone has approved an environment.

> This lives in the `relay` repo but is independent of it: it is not a pnpm
> workspace member and Relay's CI does not build it. `cd horn-center/app` and it
> behaves like its own project.

## Run it now

```bash
cd horn-center/app
npm install
npm run dev            # http://localhost:5173
```

No sign-in, no backend, no Azure. Data lives in `localStorage`, seeded around the
current time so every view has something in it.

```bash
npm test               # 35 tests over the booking rules
npm run typecheck
npm run build
```

## What's here

| | |
|---|---|
| `app/` | React + TypeScript prototype — booking grid, my reservations, lobby display |
| `app/src/lib/rules.ts` | The booking rules engine. Pure functions, fully tested, no React |
| `app/src/services/` | One interface, two implementations: `localStorage` and Dataverse |
| `scripts/provision-dataverse.mjs` | Creates the Dataverse tables from code |
| `scripts/seed-dataverse.mjs` | Seeds resources and the default policy |
| `docs/SETUP.md` | **The plan** — phases, CSULB access path, auth, licensing, FERPA |
| `docs/DATA-MODEL.md` | Tables, columns, choice values, security roles |
| `docs/FLOWS.md` | The four Power Automate flows |
| `docs/DEPLOY.md` | Environments, solution export/import, CI |

## The three screens

**Book a space** — resources down the side, 30-minute slots across. Green is
open, click to book. The dialog re-runs the rules as you change the duration, so
"you have 30 minutes left today" appears *before* you submit, not after.

**My reservations** — upcoming and past, with check-in and cancel. Check-in opens
10 minutes before your slot and closes when the grace period expires.

**Lobby display** — a TV view: every resource, open or in use, with the time it
frees up. No student names, ever — see the FERPA note in `docs/SETUP.md`. Outside
opening hours everything reads "Closed", which is correct, if a dull demo.

## How it becomes a real Power App

The prototype is not throwaway. The rules engine, the types and the components
are the production code; only the service implementation changes.

```
app/src/services/index.ts
   VITE_DATA_SOURCE=mock        → localStorage        (today)
   VITE_DATA_SOURCE=dataverse   → Dataverse Web API   (after Phase 1)
```

Everything above that seam — `lib/`, `components/`, `types.ts` — is untouched by
the migration. `docs/SETUP.md` walks the phases; `pac code push` turns this same
bundle into a Power App with CSULB sign-in already wired.

## Booking rules, as shipped

Defaults live in `app/src/lib/policy.ts` and move to the `hcr_policy` Dataverse
row in production, so staff can change them without a redeploy.

- 30-minute slots, 30 minutes to 2 hours per booking
- 3 hours/day, 10 hours/week per student
- 3 upcoming bookings at a time
- Book up to 7 days ahead
- Check in within 15 minutes or the slot is released
- Hours vary by weekday; blackout windows for maintenance and holidays

Every rule reports a specific, student-readable reason when it blocks a slot —
"Daily limit is 3 hours; you have 30 minutes left that day" rather than a generic
refusal. All of them are enforced again server-side in production
(`docs/SETUP.md` Phase 3); the browser copy is a courtesy, not a control.

## Known gaps

- **The Dataverse adapter has not been run against a live org.** It follows the
  documented Web API shapes; expect to correct a logical name or two on first run.
- **Times are the browser's local zone.** The Horn Center is always
  America/Los_Angeles. Pin it before launch — noted in `app/src/lib/time.ts`.
- **Resource names are placeholders.** Replace `app/src/data/seed.ts` and
  `scripts/seed-dataverse.mjs` with the real inventory.
- **Colours approximate CSULB's black and gold.** Swap the `--brand-*` tokens in
  `app/src/styles.css` for the official values and re-check contrast.
- **Accessibility needs a real audit.** Cells are labelled and keyboard-reachable,
  but CSU's ATI policy requires an actual test, not a good-faith attempt.
