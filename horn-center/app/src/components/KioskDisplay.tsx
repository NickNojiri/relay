import type { Policy, Reservation, Resource } from "../types";
import { resourceStateAt, type ResourceState } from "../lib/rules";
import { formatTime } from "../lib/time";

interface Props {
  resources: Resource[];
  reservations: Reservation[];
  policy: Policy;
  now: Date;
}

/**
 * The lobby screen. Designed for a wall-mounted TV read from across the room:
 * no interaction, huge type, status carried by both colour and words so it
 * survives a washed-out projector and colour-blind viewers alike.
 *
 * The parent re-renders this on a timer (useNow), so it stays current without
 * anyone touching it.
 */
export function KioskDisplay({ resources, reservations, policy, now }: Props) {
  const states = resources
    .filter((r) => r.isActive)
    .map((resource) => ({
      resource,
      state: resourceStateAt({ resource, reservations, policy, now }),
    }));

  const availableCount = states.filter((s) => s.state.kind === "available").length;

  return (
    <div className="kiosk">
      <header className="kiosk-head">
        <div>
          <h2>Horn Center — right now</h2>
          <p className="kiosk-clock">
            {now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} ·{" "}
            {now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}
          </p>
        </div>
        <div className="kiosk-count">
          <strong>{availableCount}</strong>
          <span>open now</span>
        </div>
      </header>

      <ul className="kiosk-grid">
        {states.map(({ resource, state }) => (
          <li key={resource.id} className="kiosk-tile" data-state={state.kind}>
            <span className="kiosk-tile-name">{resource.name}</span>
            <span className="kiosk-tile-status">{headline(state)}</span>
            <span className="kiosk-tile-detail">{detail(state)}</span>
          </li>
        ))}
      </ul>

      <footer className="kiosk-foot">
        Book at the front desk or on your phone · Slots release{" "}
        {policy.checkInGraceMinutes} minutes after start if nobody checks in
      </footer>
    </div>
  );
}

function headline(state: ResourceState): string {
  switch (state.kind) {
    case "available":
      return "Open";
    case "in-use":
      return "In use";
    case "reserved-soon":
      return "Held";
    case "closed":
      return "Closed";
  }
}

function detail(state: ResourceState): string {
  switch (state.kind) {
    case "available":
      return state.freeUntil ? `Free until ${formatTime(state.freeUntil)}` : "Free";
    case "in-use":
      return `Until ${formatTime(state.until)}`;
    case "reserved-soon":
      return `Reserved ${formatTime(state.from)}`;
    case "closed":
      return "Outside opening hours";
  }
}
