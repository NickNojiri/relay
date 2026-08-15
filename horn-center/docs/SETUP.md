# Setup plan — Horn Center reservations on Power Platform (CSULB)

The phases below are ordered by what blocks what. Phase 0 is the only one you can
do entirely on your own; Phases 1–2 need CSULB ITS. Start the access request on
day one and build the prototype while you wait — that is the whole point of the
mock-data app in `../app`.

---

## The critical path is access, not code

Be honest with yourself about this up front. On a CSU campus tenant:

- **Students cannot self-provision a Power Platform environment.** Environment
  creation is usually restricted to Power Platform admins. A trial environment
  you spin up on a personal account will not have access to CSULB identities, so
  it cannot demo the one feature that makes this project worth doing.
- **Dataverse needs a licence.** Power Apps Premium is roughly $20/user/month at
  list price; CSU campuses generally have an EES/EA agreement with education
  pricing, and ITS may already own Power Platform capacity. Ask before assuming
  you need to buy anything.
- **App registration in Entra ID is admin-gated.** If you go the standalone-SPA
  route rather than a Code App, someone with Application Administrator has to
  create the registration and grant consent.

**What to ask ITS for, in one message:**

> I'd like to build a reservation dashboard for the Horn Center on Power
> Platform. I need: (1) a Power Platform developer or sandbox environment with
> Dataverse, (2) a Power Apps Premium licence for me plus a handful of Horn
> Center staff, and (3) eventually an Entra ID security group for eligible
> students so the app can be scoped. The app authenticates students with their
> CSULB account and stores booking rows — no grades, no SSN, no financial data.
> I can share the data model and a working prototype.

Having the prototype and `DATA-MODEL.md` in hand when you ask makes this a very
different conversation than asking for access to build something unspecified.

### Compliance, before anyone asks you in a meeting

Reservation rows tie a named student to a time and a place. That is a student
record. Treat it as FERPA-adjacent even though it is not a grade:

- Store the **Entra object id** as the key, not the campus ID number. The schema
  in this repo already does — `hcr_studentaadid`.
- Do not display other students' names in the student-facing UI. This prototype
  shows booked slots as anonymous blocks; only staff roles see who holds what.
- The kiosk display shows **resource state only** — "In use until 3:00" — never a
  name. Do not "improve" this.
- Set a retention rule: delete or anonymise reservation rows after a term or two.
  A bulk-delete job in Dataverse does it on a schedule.
- Expect to fill in a security/data review form. CSULB ITS will have one.

---

## Phase 0 — Prototype with mock data (today, no approvals)

```bash
cd horn-center/app
npm install
npm run dev          # http://localhost:5173
```

You get the booking grid, per-student caps, check-in, cancellation and the lobby
display, all running against `localStorage`. Nothing is stubbed out visually:
what you see is what students would see.

Use it to:

- settle the booking rules with Horn Center staff *before* building anything in
  Dataverse — changing `src/lib/policy.ts` takes seconds, changing a deployed
  Power App takes an afternoon;
- fix the resource inventory (`src/data/seed.ts`) against what the Horn Center
  actually lends out;
- show ITS a working thing when you ask for an environment.

**Deliverable:** staff sign off on caps, hours and the resource list.

---

## Phase 1 — Environment and schema (once ITS says yes)

1. **Install the CLI.**
   ```bash
   dotnet tool install --global Microsoft.PowerApps.CLI.Tool
   pac auth create --environment https://orgXXXXX.crm.dynamics.com
   pac org who                # confirms you are pointed at the right org
   ```

2. **Create the solution.** Everything must live in a solution or you cannot move
   it between environments later.
   ```bash
   pac solution init --publisher-name HornCenter --publisher-prefix hcr
   ```

3. **Create the tables from code**, rather than clicking through the maker portal:
   ```bash
   export DATAVERSE_URL="https://orgXXXXX.crm.dynamics.com"
   export DATAVERSE_TOKEN="..."          # or the AZURE_* client-credentials vars
   node ../scripts/provision-dataverse.mjs --dry-run   # inspect first
   node ../scripts/provision-dataverse.mjs
   node ../scripts/seed-dataverse.mjs
   ```
   This is the payoff of doing it in code: re-running it against the test and
   production environments gives an identical schema, and the schema is a file
   your reviewers can read. See `DATA-MODEL.md` for what it builds.

4. **Publish and verify.**
   ```bash
   pac solution publish
   ```
   Open the maker portal once, look at the three tables, confirm they match.

**Deliverable:** tables exist, seeded, in a solution you can export.

---

## Phase 2 — Auth

You do not write an auth layer. You pick which host does it for you.

### Option A — Power Apps Code App (recommended)

The same React app in `../app`, hosted by Power Apps. Entra sign-in, Dataverse
connection and licence enforcement all come from the host.

```bash
cd horn-center/app
pac code init --displayName "Horn Center Reservations"
pac code add-data-source --apiId /providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps --dataSource hcr_reservation
pac code push
```

Code Apps are a newer, licence-gated capability (Power Apps Premium) and were
still marked preview as of early 2026 — **verify its current status and whether
your tenant has it before committing to this path.** If it is unavailable, Option
B is the fallback and costs you an app registration, not a rewrite.

### Option B — Standalone SPA + MSAL

Host the built app anywhere the campus allows (Azure Static Web Apps, campus web
hosting) and authenticate with MSAL against Dataverse directly.

```ts
// src/services/index.ts — replace the throwing stubs
import { PublicClientApplication } from "@azure/msal-browser";

const msal = new PublicClientApplication({
  auth: {
    clientId: import.meta.env.VITE_ENTRA_CLIENT_ID!,
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_ENTRA_TENANT_ID}`,
    redirectUri: window.location.origin,
  },
});
await msal.initialize();

const scopes = [`${import.meta.env.VITE_DATAVERSE_URL}/user_impersonation`];

async function account() {
  return msal.getActiveAccount() ?? (await msal.loginPopup({ scopes })).account;
}

return new DataverseReservationService({
  orgUrl: import.meta.env.VITE_DATAVERSE_URL!,
  getToken: async () => {
    const acct = await account();
    const result = await msal.acquireTokenSilent({ scopes, account: acct })
      .catch(() => msal.acquireTokenPopup({ scopes }));
    return result.accessToken;
  },
  getUser: async () => {
    const acct = await account();
    return {
      id: acct.idTokenClaims!.oid as string,   // the stable key
      displayName: acct.name ?? "Student",
      email: acct.username,
      roles: ["student"],
    };
  },
});
```

Ask ITS for a **single-page application** registration with the redirect URI of
your host and delegated permission `Dynamics CRM / user_impersonation`.

### Restricting to eligible students, either option

- Create an Entra security group (e.g. `horncenter-students`) and share the app
  with the group rather than the whole tenant.
- Give staff a second group and a Dataverse security role that can read all
  reservation rows; students get a role scoped to **User** on `hcr_reservation`
  so they can only read their own — see `DATA-MODEL.md` § Security roles.
- Dataverse row-level security is what actually protects the data. The React
  role check is cosmetic.

**Deliverable:** you sign in with your CSULB account and see your own bookings.

---

## Phase 3 — Server-side rules

The browser rules engine (`app/src/lib/rules.ts`) is a UX affordance. Anyone with
the org URL and a token can POST a row straight to the Web API and bypass it.

Enforce the same rules where they cannot be skipped, in either of two places:

- **A Power Automate flow on Create/Update of `hcr_reservation`** — easiest, no
  C# required, adds a second or two of latency. Fine for this scale.
- **A Dataverse plug-in (C#, synchronous, pre-operation)** — the correct answer,
  rejects the write inside the transaction so a double-book is impossible rather
  than merely undone.

Start with the flow. Move to a plug-in if you ever see a real double-booking.
The overlap check is the one that matters; the caps are annoyance-prevention.

**Deliverable:** a POST that violates a cap is rejected by the server.

---

## Phase 4 — Flows and the lobby display

See `FLOWS.md` for the four automations (confirmation, reminder, no-show release,
weekly digest). The no-show release is the one with real operational value: it is
what makes a slot free up when someone does not show, and it needs to be running
before staff will trust the system.

For the lobby TV:

- **Cheapest:** open the app's Lobby display tab full-screen on a mini PC in kiosk
  mode. Costs nothing extra, already built, already anonymous.
- **Nicer:** a Power BI report on a Fabric/Premium capacity, which gets you usage
  analytics for free. Note that showing a Power BI report on a screen nobody signs
  into needs Premium/Fabric capacity — this is the hidden cost people trip on.

Start with the kiosk tab. Add Power BI when someone asks for utilisation numbers.

---

## Phase 5 — Pilot

Pilot on **one resource type** — the collab rooms are usually the best candidate,
since demand is visible and the failure mode is mild. Run it for two weeks with
front-desk staff able to override anything, then widen.

Things that will come up, in roughly this order:

1. Students book and do not show. → tighten `checkInGrace`, add the no-show flow.
2. Staff need to block a room for an event. → blackout rows in the policy table.
3. Somebody wants a recurring weekly booking. → resist; it eats the schedule.
4. Accessibility: the grid needs to be usable by keyboard and screen reader. The
   prototype labels every cell, but get an actual test with the campus
   accessibility office before launch. CSU has a systemwide ATI policy and this
   is not optional.

---

## Time and cost, honestly

| Phase | Your time | Blocked on |
|---|---|---|
| 0 Prototype | ~a day (done) | nobody |
| 1 Environment + schema | ~half a day | ITS approval — days to weeks |
| 2 Auth | ~half a day | app registration or Code App licence |
| 3 Server rules | 1–2 days | nothing |
| 4 Flows + display | 1–2 days | a screen and a mini PC |
| 5 Pilot | 2 weeks elapsed | Horn Center staff |

Licence cost is dominated by how many **staff** need Premium, not students —
students consuming a Code App still need the licence, so confirm the student
licensing model with ITS early. That single answer decides whether this is a
$40/month project or a $2,000/month one, so get it in writing before you build
Phase 2.
