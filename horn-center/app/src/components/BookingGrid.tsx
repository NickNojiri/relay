import { useMemo } from "react";
import type { Policy, Reservation, Resource, Slot } from "../types";
import { buildDaySlots, openWindowFor } from "../lib/rules";
import { formatHourShort, formatTime } from "../lib/time";

interface Props {
  resources: Resource[];
  reservations: Reservation[];
  policy: Policy;
  day: Date;
  now: Date;
  studentId: string;
  onPick: (resource: Resource, slot: Slot) => void;
}

/**
 * One row per resource, one cell per slot.
 *
 * Cells carry their state in a data attribute so the whole legend is CSS —
 * the component stays about layout and the click target.
 */
export function BookingGrid({
  resources,
  reservations,
  policy,
  day,
  now,
  studentId,
  onPick,
}: Props) {
  const window = openWindowFor(day, policy);

  const rows = useMemo(
    () =>
      resources.map((resource) => ({
        resource,
        slots: buildDaySlots({ resource, day, reservations, policy, now, studentId }),
      })),
    [resources, reservations, policy, day, now, studentId],
  );

  if (!window) {
    return (
      <p className="empty">
        The Horn Center is closed on {day.toLocaleDateString([], { weekday: "long" })}. Pick
        another day.
      </p>
    );
  }

  if (resources.length === 0) {
    return <p className="empty">No resources match that filter.</p>;
  }

  return (
    <div className="grid-scroll">
      <table className="grid" role="grid">
        <thead>
          <tr>
            <th className="grid-corner" scope="col">
              Resource
            </th>
            {rows[0]?.slots.map((slot) => {
              // Label only on the hour. The label is absolutely positioned in CSS
              // so a wide label cannot stretch its column and break the tiling.
              const onTheHour = new Date(slot.startsAt).getMinutes() === 0;
              return (
                <th key={slot.startsAt} scope="col" className="grid-tick">
                  {onTheHour && <span>{formatHourShort(slot.startsAt)}</span>}
                </th>
              );
            })}
            {/* Absorbs the leftover width so the slot columns stay content-sized
                and the row rules still reach the edge of the card. */}
            <th className="grid-filler" aria-hidden="true" />
          </tr>
        </thead>
        <tbody>
          {rows.map(({ resource, slots }) => (
            <tr key={resource.id}>
              <th scope="row" className="grid-resource">
                <span className="grid-resource-name">{resource.name}</span>
                <span className="grid-resource-meta">
                  {resource.location}
                  {resource.capacity > 1 ? ` · seats ${resource.capacity}` : ""}
                </span>
              </th>
              {slots.map((slot) => {
                const clickable = slot.status === "free";
                const label = `${resource.name}, ${formatTime(slot.startsAt)} – ${formatTime(
                  slot.endsAt,
                )}`;
                return (
                  <td key={slot.startsAt} className="grid-cell">
                    <button
                      type="button"
                      className="slot"
                      data-status={slot.status}
                      disabled={!clickable}
                      aria-label={
                        clickable ? `Book ${label}` : `${label} — ${describe(slot)}`
                      }
                      title={slot.reason ?? describe(slot)}
                      onClick={() => clickable && onPick(resource, slot)}
                    />
                  </td>
                );
              })}
              <td className="grid-filler" />
            </tr>
          ))}
        </tbody>
      </table>
      <p className="grid-hint">
        Open {formatTime(window.start)} – {formatTime(window.end)}. Click a green slot to book.
      </p>
    </div>
  );
}

function describe(slot: Slot): string {
  switch (slot.status) {
    case "free":
      return "Available";
    case "taken":
      return "Already booked";
    case "past":
      return "Time has passed";
    case "closed":
      return "Closed";
    case "blocked":
      return slot.reason ?? "Not available to you";
  }
}

export function GridLegend() {
  return (
    <ul className="legend" aria-label="Slot legend">
      {(
        [
          ["free", "Available"],
          ["taken", "Booked"],
          ["blocked", "Blocked by policy"],
          ["past", "Past"],
        ] as const
      ).map(([status, label]) => (
        <li key={status}>
          <span className="legend-swatch" data-status={status} aria-hidden="true" />
          {label}
        </li>
      ))}
    </ul>
  );
}
