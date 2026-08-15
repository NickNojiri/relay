import { useMemo, useState } from "react";
import type { Resource, ResourceKind, Slot } from "./types";
import { useHornCenter, useNow } from "./hooks";
import { BookingGrid, GridLegend } from "./components/BookingGrid";
import { BookingDialog } from "./components/BookingDialog";
import { MyReservations } from "./components/MyReservations";
import { KioskDisplay } from "./components/KioskDisplay";
import { UsageBanner } from "./components/UsageBanner";
import { addMinutes, formatDay, startOfDay, toDateInputValue, fromDateInputValue } from "./lib/time";

type Tab = "book" | "mine" | "kiosk";

const KIND_LABELS: Record<ResourceKind | "all", string> = {
  all: "Everything",
  workstation: "Workstations",
  "collab-room": "Collab rooms",
  equipment: "Equipment",
};

export default function App() {
  const state = useHornCenter();
  const now = useNow(30_000);
  const [tab, setTab] = useState<Tab>("book");
  const [kind, setKind] = useState<ResourceKind | "all">("all");
  const [picked, setPicked] = useState<{ resource: Resource; slot: Slot } | null>(null);

  const visibleResources = useMemo(
    () =>
      state.resources.filter((r) => r.isActive && (kind === "all" || r.kind === kind)),
    [state.resources, kind],
  );

  if (state.loading) {
    return (
      <main className="shell">
        <p className="empty">Loading the Horn Center schedule…</p>
      </main>
    );
  }

  if (state.error || !state.user) {
    return (
      <main className="shell">
        <p className="error" role="alert">
          {state.error ?? "Could not identify you. Try signing in again."}
        </p>
      </main>
    );
  }

  const user = state.user;
  const maxDay = addMinutes(startOfDay(now), state.policy.advanceBookingDays * 24 * 60 - 1);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <div>
            <h1>Horn Center Reservations</h1>
            <p>California State University, Long Beach</p>
          </div>
        </div>
        <div className="who">
          <span className="who-name">{user.displayName}</span>
          <span className="who-mail">{user.email}</span>
        </div>
      </header>

      <nav className="tabs" aria-label="Sections">
        {(
          [
            ["book", "Book a space"],
            ["mine", "My reservations"],
            ["kiosk", "Lobby display"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className="tab"
            aria-current={tab === value ? "page" : undefined}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </nav>

      <main>
        {tab === "book" && (
          <div className="stack">
            <div className="toolbar">
              <label className="field field-inline">
                <span>Day</span>
                <input
                  type="date"
                  value={toDateInputValue(state.day)}
                  min={toDateInputValue(now)}
                  max={toDateInputValue(maxDay)}
                  onChange={(e) =>
                    e.target.value && state.setDay(fromDateInputValue(e.target.value))
                  }
                />
              </label>
              <div className="chips" role="group" aria-label="Filter by type">
                {(Object.keys(KIND_LABELS) as Array<ResourceKind | "all">).map((k) => (
                  <button
                    key={k}
                    type="button"
                    className="chip"
                    aria-pressed={kind === k}
                    onClick={() => setKind(k)}
                  >
                    {KIND_LABELS[k]}
                  </button>
                ))}
              </div>
              <GridLegend />
            </div>

            <UsageBanner
              reservations={state.validationSet}
              studentId={user.id}
              day={state.day}
              policy={state.policy}
            />

            <section>
              <h2>{formatDay(state.day)}</h2>
              <BookingGrid
                resources={visibleResources}
                reservations={state.validationSet}
                policy={state.policy}
                day={state.day}
                now={now}
                studentId={user.id}
                onPick={(resource, slot) => setPicked({ resource, slot })}
              />
            </section>
          </div>
        )}

        {tab === "mine" && (
          <MyReservations
            reservations={state.myReservations}
            resources={state.resources}
            policy={state.policy}
            now={now}
            onCancel={state.cancel}
            onCheckIn={state.checkIn}
          />
        )}

        {tab === "kiosk" && (
          <KioskDisplay
            resources={state.resources}
            reservations={state.weekReservations}
            policy={state.policy}
            now={now}
          />
        )}
      </main>

      {picked && (
        <BookingDialog
          resource={picked.resource}
          slot={picked.slot}
          policy={state.policy}
          reservations={state.validationSet}
          studentId={user.id}
          now={now}
          onConfirm={({ startsAt, endsAt, purpose }) =>
            state.book({ resourceId: picked.resource.id, startsAt, endsAt, purpose })
          }
          onClose={() => setPicked(null)}
        />
      )}

      <footer className="footer">
        Prototype · mock data in the browser · see <code>horn-center/docs/SETUP.md</code> to
        point it at Dataverse
      </footer>
    </div>
  );
}
