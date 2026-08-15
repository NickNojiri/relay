# Data model

Three tables, one relationship. Built by `scripts/provision-dataverse.mjs` with
publisher prefix `hcr`. The TypeScript types in `app/src/types.ts` mirror these
one-for-one, so `app/src/services/dataverseService.ts` is a pure mapping layer.

```
hcr_resource ──1:N──> hcr_reservation
hcr_policy   (single active row, no relationships)
```

## hcr_resource — a bookable thing

| Column | Type | Notes |
|---|---|---|
| `hcr_resourceid` | Unique id | Primary key |
| `hcr_name` | Text(100) | Primary name. "Workstation 12", "Collab Room A" |
| `hcr_kind` | Choice | 1 Workstation · 2 Collab room · 3 Equipment |
| `hcr_location` | Text(150) | "Horn Center — Main Lab" |
| `hcr_capacity` | Whole number | 1 for a workstation, seats for a room |
| `hcr_features` | Text(400) | Semicolon-separated tags, surfaced as filter chips |
| `statecode` | Status | Standard. Inactive = not bookable, history preserved |

Deactivate rather than delete. A deleted resource orphans its reservation history,
and the `Delete: Restrict` cascade on the relationship will stop you anyway.

## hcr_reservation — one booking

| Column | Type | Notes |
|---|---|---|
| `hcr_reservationid` | Unique id | Primary key |
| `hcr_name` | Text(200) | Primary name, generated: "Jane Doe · Sep 16, 1:00 PM" |
| `hcr_Resource` | Lookup → `hcr_resource` | Required |
| `hcr_studentaadid` | Text(64) | **Entra object id (`oid`)** — the real key |
| `hcr_studentname` | Text(150) | Denormalised for staff views |
| `hcr_startsat` | Date and time | UserLocal behaviour → stored UTC |
| `hcr_endsat` | Date and time | Half-open: `[startsAt, endsAt)` |
| `hcr_status` | Choice | 1 Booked · 2 Checked in · 3 Completed · 4 Cancelled · 5 No-show |
| `hcr_checkedinat` | Date and time | Set by the check-in action |
| `hcr_purpose` | Text(100) | Optional, student-supplied |
| `createdon` | Date and time | Standard |

### Why the Entra object id and not the email

Students change display names and email addresses; the `oid` claim never moves.
Keying on email quietly orphans someone's booking history the day they change
their name, which is exactly the population you least want to inconvenience.

### Status is what frees a slot

Only `Booked`, `Checked in` and `Completed` occupy time. `Cancelled` and
`No-show` rows stay in the table for reporting but stop blocking the slot. That
rule lives in `ACTIVE_STATUSES` in `app/src/lib/rules.ts` and is mirrored in the
OData filter in `dataverseService.listReservations` — **change both together.**

## hcr_policy — the rules, editable without a redeploy

One active row. Staff edit it in a model-driven app; the React app reads it at
load and the flows read it too, so there is a single source of truth.

| Column | Type | Default |
|---|---|---|
| `hcr_slotminutes` | Whole number | 30 |
| `hcr_minduration` | Whole number | 30 |
| `hcr_maxduration` | Whole number | 120 |
| `hcr_maxminutesperday` | Whole number | 180 |
| `hcr_maxminutesperweek` | Whole number | 600 |
| `hcr_maxactive` | Whole number | 3 |
| `hcr_advancedays` | Whole number | 7 |
| `hcr_checkingrace` | Whole number | 15 |
| `hcr_openhoursjson` | Multiline text | `{"0":{"open":"12:00","close":"18:00"}, …}`, key = day of week, 0 = Sunday |
| `hcr_blackoutsjson` | Multiline text | `[{"start":"…","end":"…","reason":"Lab maintenance"}]` |

JSON blobs are a deliberate shortcut for hours and blackouts. They keep the
schema to three tables, and staff edit them rarely. If front-desk staff end up
editing blackouts weekly, promote it to a real `hcr_blackout` table with a date
range and a resource lookup — the app-side type is already a list.

## Security roles

This is where the data is actually protected. The React role check is cosmetic.

**Horn Center Student**
- `hcr_resource`: Read — Organization
- `hcr_policy`: Read — Organization
- `hcr_reservation`: Create — Organization; Read/Write/Delete — **User**

User-level scope on reservations is the important line: a student can create a
row and can only ever read or modify rows they own. Without it, any student can
query the whole booking table and see who is where at what time.

**Horn Center Staff**
- `hcr_resource`, `hcr_policy`: Read/Write — Organization
- `hcr_reservation`: Read/Write/Delete — Organization

**Kiosk** (if the lobby display uses its own identity)
- `hcr_resource`: Read — Organization
- `hcr_reservation`: Read — Organization, **restricted to a view that excludes
  `hcr_studentname` and `hcr_studentaadid`**

Assign roles via Entra security groups (`horncenter-students`,
`horncenter-staff`) rather than per-user, so ITS can manage membership without
touching the app.

## Indexes

Dataverse indexes lookups and primary keys automatically. Add one manually on
`hcr_startsat` once the table is past a few tens of thousands of rows — every
availability query filters on it.
