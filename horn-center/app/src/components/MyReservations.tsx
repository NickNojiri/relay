import { useState } from "react";
import type { Policy, Reservation, Resource } from "../types";
import { formatDay, formatDuration, formatRange, minutesBetween, toDate } from "../lib/time";

interface Props {
  reservations: Reservation[];
  resources: Resource[];
  policy: Policy;
  now: Date;
  onCancel: (id: string) => Promise<void>;
  onCheckIn: (id: string) => Promise<void>;
}

export function MyReservations({
  reservations,
  resources,
  policy,
  now,
  onCancel,
  onCheckIn,
}: Props) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const byId = new Map(resources.map((r) => [r.id, r]));

  const sorted = [...reservations].sort(
    (a, b) => toDate(a.startsAt).getTime() - toDate(b.startsAt).getTime(),
  );
  const upcoming = sorted.filter(
    (r) => toDate(r.endsAt) > now && r.status !== "cancelled" && r.status !== "no-show",
  );
  const history = sorted
    .filter((r) => !upcoming.includes(r))
    .reverse()
    .slice(0, 20);

  async function run(id: string, action: (id: string) => Promise<void>) {
    setBusyId(id);
    try {
      await action(id);
    } finally {
      setBusyId(null);
    }
  }

  function canCheckIn(r: Reservation): boolean {
    if (r.status !== "booked") return false;
    const minutesUntilStart = minutesBetween(now, r.startsAt);
    // Open the check-in window 10 minutes early, close it when the grace period ends.
    return minutesUntilStart <= 10 && -minutesUntilStart <= policy.checkInGraceMinutes;
  }

  return (
    <div className="stack">
      <section>
        <h2>Upcoming</h2>
        {upcoming.length === 0 ? (
          <p className="empty">Nothing booked yet. Head to Book a space to reserve one.</p>
        ) : (
          <ul className="cards">
            {upcoming.map((r) => (
              <li key={r.id} className="card">
                <div className="card-main">
                  <h3>{byId.get(r.resourceId)?.name ?? "Resource"}</h3>
                  <p className="card-when">
                    {formatDay(r.startsAt)} · {formatRange(r.startsAt, r.endsAt)} ·{" "}
                    {formatDuration(minutesBetween(r.startsAt, r.endsAt))}
                  </p>
                  <p className="card-meta">
                    {byId.get(r.resourceId)?.location}
                    {r.purpose ? ` · ${r.purpose}` : ""}
                  </p>
                </div>
                <div className="card-actions">
                  <span className="status" data-status={r.status}>
                    {statusLabel(r.status)}
                  </span>
                  {canCheckIn(r) && (
                    <button
                      type="button"
                      className="btn-primary btn-sm"
                      disabled={busyId === r.id}
                      onClick={() => run(r.id, onCheckIn)}
                    >
                      Check in
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn-ghost btn-sm"
                    disabled={busyId === r.id}
                    onClick={() => run(r.id, onCancel)}
                  >
                    Cancel
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {upcoming.some((r) => r.status === "booked") && (
          <p className="note">
            Check in within {policy.checkInGraceMinutes} minutes of your start time or the slot
            is released to someone else.
          </p>
        )}
      </section>

      <section>
        <h2>History</h2>
        {history.length === 0 ? (
          <p className="empty">No past bookings.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Resource</th>
                <th scope="col">Length</th>
                <th scope="col">Outcome</th>
              </tr>
            </thead>
            <tbody>
              {history.map((r) => (
                <tr key={r.id}>
                  <td>{formatDay(r.startsAt)}</td>
                  <td>{byId.get(r.resourceId)?.name ?? "—"}</td>
                  <td>{formatDuration(minutesBetween(r.startsAt, r.endsAt))}</td>
                  <td>
                    <span className="status" data-status={r.status}>
                      {statusLabel(r.status)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function statusLabel(status: Reservation["status"]): string {
  switch (status) {
    case "booked":
      return "Booked";
    case "checked-in":
      return "Checked in";
    case "completed":
      return "Completed";
    case "cancelled":
      return "Cancelled";
    case "no-show":
      return "No-show";
  }
}
