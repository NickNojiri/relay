import { useEffect, useMemo, useRef, useState } from "react";
import type { Policy, Reservation, Resource, Slot, Violation } from "../types";
import { validateBooking } from "../lib/rules";
import { addMinutes, formatDay, formatDuration, formatRange, minutesBetween } from "../lib/time";

interface Props {
  resource: Resource;
  slot: Slot;
  policy: Policy;
  reservations: Reservation[];
  studentId: string;
  now: Date;
  onConfirm: (input: { startsAt: string; endsAt: string; purpose?: string }) => Promise<void>;
  onClose: () => void;
}

/**
 * Confirm step. Lets the student extend past the single clicked slot, and
 * re-runs the same rules engine on every change so the reason a length is
 * unavailable is visible before they submit rather than after.
 */
export function BookingDialog({
  resource,
  slot,
  policy,
  reservations,
  studentId,
  now,
  onConfirm,
  onClose,
}: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const [durationMinutes, setDurationMinutes] = useState(policy.slotMinutes);
  const [purpose, setPurpose] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const durationChoices = useMemo(() => {
    const choices: number[] = [];
    for (
      let d = policy.minDurationMinutes;
      d <= policy.maxDurationMinutes;
      d += policy.slotMinutes
    ) {
      choices.push(d);
    }
    return choices;
  }, [policy]);

  const endsAt = useMemo(
    () => addMinutes(slot.startsAt, durationMinutes).toISOString(),
    [slot.startsAt, durationMinutes],
  );

  const violations: Violation[] = useMemo(
    () =>
      validateBooking(
        { resourceId: resource.id, studentId, startsAt: slot.startsAt, endsAt },
        { resource, existing: reservations, policy, now },
      ),
    [resource, studentId, slot.startsAt, endsAt, reservations, policy, now],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    dialogRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const blocked = violations.length > 0;

  async function submit() {
    setSubmitting(true);
    setSubmitError(null);
    try {
      await onConfirm({ startsAt: slot.startsAt, endsAt, purpose: purpose.trim() || undefined });
      onClose();
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Booking failed.");
      setSubmitting(false);
    }
  }

  return (
    <div className="backdrop" onClick={onClose} role="presentation">
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="booking-title"
        ref={dialogRef}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="booking-title">{resource.name}</h2>
        <p className="dialog-sub">
          {resource.location} · {formatDay(slot.startsAt)}
        </p>

        <label className="field">
          <span>How long?</span>
          <select
            value={durationMinutes}
            onChange={(e) => setDurationMinutes(Number(e.target.value))}
          >
            {durationChoices.map((d) => (
              <option key={d} value={d}>
                {formatDuration(d)}
              </option>
            ))}
          </select>
        </label>

        <p className="dialog-range">
          {formatRange(slot.startsAt, endsAt)} ·{" "}
          {formatDuration(minutesBetween(slot.startsAt, endsAt))}
        </p>

        <label className="field">
          <span>
            What for? <em>(optional)</em>
          </span>
          <input
            type="text"
            value={purpose}
            maxLength={100}
            placeholder="Group project, printing, office hours…"
            onChange={(e) => setPurpose(e.target.value)}
          />
        </label>

        {blocked && (
          <ul className="violations" aria-live="polite">
            {violations.map((v) => (
              <li key={v.code}>{v.message}</li>
            ))}
          </ul>
        )}

        {submitError && (
          <p className="error" role="alert">
            {submitError}
          </p>
        )}

        <div className="dialog-actions">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={blocked || submitting}
            onClick={submit}
          >
            {submitting ? "Booking…" : "Confirm booking"}
          </button>
        </div>
      </div>
    </div>
  );
}
