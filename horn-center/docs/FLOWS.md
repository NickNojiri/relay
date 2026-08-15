# Power Automate flows

Four automations. Only the first two are needed to launch; the no-show release is
what makes staff trust the system, and the digest is what keeps it funded.

Build them in the maker portal inside the `HornCenterReservations` solution
(solution-aware flows export with `pac solution export`; flows built outside a
solution do not move between environments).

---

## 1. Booking confirmation — required

**Trigger:** Dataverse → *When a row is added* → `hcr_reservation`

**Steps**
1. Get row → `hcr_resource` by `_hcr_resource_value`, for the name and location.
2. Send an email (Outlook connector) to the student.
   - Recipient: look up the user by `hcr_studentaadid` via the Entra connector —
     do not store a mail address on the reservation row just for this.
   - Include an `.ics` attachment so it lands in their calendar. This single
     detail cuts no-shows more than any reminder does.
3. Optional: post an adaptive card to a Teams channel for the front desk.

**Watch for:** the trigger fires on rows the *flow itself* creates if you ever add
one. Filter on `hcr_status eq 1` (Booked) to be safe.

---

## 2. Reminder — required

**Trigger:** Recurrence, every 15 minutes

**Steps**
1. List rows on `hcr_reservation` with a filter of roughly
   `hcr_status eq 1 and hcr_startsat gt <now> and hcr_startsat lt <now + 30min>`.
   Build the timestamps with `utcNow()` and `addMinutes()` expressions.
2. For each, send a short reminder with the check-in link.
3. Stamp a flag column (add `hcr_reminded`, Yes/No) so a row cannot be reminded
   twice when the windows overlap. **Do this — without it every student gets two
   reminders and you will hear about it.**

A 15-minute recurrence is ~2,900 runs/month, which sits inside standard flow
limits. Do not drop it to every minute.

---

## 3. No-show release — the one with operational value

**Trigger:** Recurrence, every 5 minutes

**Steps**
1. Read the active `hcr_policy` row for `hcr_checkingrace`.
2. List `hcr_reservation` rows where status is Booked, `hcr_checkedinat` is null,
   and `hcr_startsat` is more than the grace period ago, and `hcr_endsat` is
   still in the future.
3. Update each to status `5` (No-show).

That last update is what frees the slot — the availability queries in the app
already exclude no-show rows, so the grid opens up within five minutes with no
further work.

The same logic exists client-side in `findNoShows()` (`app/src/lib/rules.ts`) so
the prototype behaves correctly without any flow running. Keep the grace period
in the policy table, not in both places.

---

## 4. Weekly digest — the one that keeps the project alive

**Trigger:** Recurrence, Mondays 07:00 America/Los_Angeles

**Steps**
1. List last week's reservations.
2. Aggregate: total bookings, hours used, no-show rate, busiest resource, busiest
   hour, unique students served.
3. Email the Horn Center coordinator.

"We served 214 unique students and ran at 68% utilisation" is the sentence that
gets a tool renewed. Build this before anyone asks for it.

---

## 5. Server-side rule enforcement — see SETUP.md Phase 3

**Trigger:** Dataverse → *When a row is added or modified* → `hcr_reservation`

Re-check overlap and the caps; on violation, update the row to Cancelled and mail
the student, or fail the flow with a terminate action.

A flow cannot reject a write *before* it commits, so there is a window where an
illegal row exists. For overlap specifically that means two students can both
briefly hold the same slot. If that ever actually happens, replace this flow with
a synchronous pre-operation plug-in, which runs inside the transaction and can
genuinely refuse the write.

---

## Licensing note

All five use only the Dataverse, Outlook and Teams connectors — all standard,
none premium. The Premium licence requirement comes from **Dataverse itself**,
not from these flows, so adding more of them costs nothing extra.
