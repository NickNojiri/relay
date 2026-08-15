import type { Policy, Reservation } from "../types";
import { usageSummary } from "../lib/rules";
import { formatDuration } from "../lib/time";

interface Props {
  reservations: Reservation[];
  studentId: string;
  day: Date;
  policy: Policy;
}

/** Shows the student where they stand against the caps before they hit one. */
export function UsageBanner({ reservations, studentId, day, policy }: Props) {
  const usage = usageSummary(reservations, studentId, day, policy);
  const upcoming = reservations.filter(
    (r) => r.studentId === studentId && (r.status === "booked" || r.status === "checked-in"),
  ).length;

  const meters = [
    {
      label: "That day",
      used: usage.dayUsed,
      total: policy.maxMinutesPerDay,
      left: usage.dayLeft,
    },
    {
      label: "That week",
      used: usage.weekUsed,
      total: policy.maxMinutesPerWeek,
      left: usage.weekLeft,
    },
  ];

  return (
    <div className="usage">
      {meters.map((m) => {
        const pct = m.total === 0 ? 0 : Math.min(100, Math.round((m.used / m.total) * 100));
        return (
          <div className="usage-meter" key={m.label}>
            <div className="usage-label">
              <span>{m.label}</span>
              <strong>{formatDuration(m.left)} left</strong>
            </div>
            <div
              className="meter"
              role="meter"
              aria-valuenow={m.used}
              aria-valuemin={0}
              aria-valuemax={m.total}
              aria-label={`${m.label}: ${formatDuration(m.used)} of ${formatDuration(m.total)} used`}
            >
              <span style={{ width: `${pct}%` }} data-full={pct >= 100} />
            </div>
          </div>
        );
      })}
      <div className="usage-meter">
        <div className="usage-label">
          <span>Active bookings</span>
          <strong>
            {upcoming} / {policy.maxActiveReservations}
          </strong>
        </div>
      </div>
    </div>
  );
}
