/**
 * The booking rules engine — pure functions, no I/O, no React.
 *
 * This is deliberately the only place that decides whether a booking is legal.
 * The UI calls it to grey out slots and to explain rejections; the service layer
 * calls it again before writing. When you go to production you should ALSO
 * enforce the same rules server-side (a Dataverse plug-in or a Power Automate
 * flow on Create) — a browser check is a UX affordance, not a security control.
 */

import type {
  BookingRequest,
  Policy,
  Reservation,
  Resource,
  Slot,
  Violation,
  Weekday,
} from "../types";
import {
  addMinutes,
  atTime,
  endOfDay,
  endOfWeek,
  minutesBetween,
  overlapMinutes,
  overlaps,
  startOfDay,
  startOfWeek,
  toDate,
} from "./time";

/** Reservations that still occupy time. Cancelled and no-show rows free their slot. */
export const ACTIVE_STATUSES: ReadonlySet<string> = new Set([
  "booked",
  "checked-in",
  "completed",
]);

export function isActive(reservation: Reservation): boolean {
  return ACTIVE_STATUSES.has(reservation.status);
}

export interface ValidationContext {
  resource: Resource | undefined;
  /** Every active reservation that could conflict — same resource or same student. */
  existing: Reservation[];
  policy: Policy;
  now: Date;
  /** Set when editing, so a reservation does not conflict with itself. */
  ignoreReservationId?: string;
}

/**
 * Returns every reason the request is illegal. Empty array = bookable.
 *
 * All checks run (rather than short-circuiting) so the student sees the full
 * picture at once instead of fixing one problem to reveal the next.
 */
export function validateBooking(
  request: BookingRequest,
  context: ValidationContext,
): Violation[] {
  const { resource, policy, now } = context;
  const violations: Violation[] = [];
  const start = toDate(request.startsAt);
  const end = toDate(request.endsAt);
  const durationMinutes = minutesBetween(start, end);

  if (!resource || !resource.isActive) {
    violations.push({
      code: "RESOURCE_INACTIVE",
      message: "That resource is not available for booking right now.",
    });
  }

  if (end <= now) {
    violations.push({
      code: "IN_THE_PAST",
      message: "That time has already passed.",
    });
  }

  if (durationMinutes < policy.minDurationMinutes) {
    violations.push({
      code: "TOO_SHORT",
      message: `Bookings must be at least ${policy.minDurationMinutes} minutes.`,
    });
  }

  if (durationMinutes > policy.maxDurationMinutes) {
    violations.push({
      code: "TOO_LONG",
      message: `A single booking can be at most ${formatMinutes(policy.maxDurationMinutes)}.`,
    });
  }

  if (!isOnSlotGrid(start, policy) || !isOnSlotGrid(end, policy)) {
    violations.push({
      code: "NOT_ON_SLOT_GRID",
      message: `Start and end must land on ${policy.slotMinutes}-minute boundaries.`,
    });
  }

  if (!isWithinOpenHours(start, end, policy)) {
    violations.push({
      code: "OUTSIDE_OPEN_HOURS",
      message: "The Horn Center is closed during part of that window.",
    });
  }

  const horizon = addMinutes(startOfDay(now), policy.advanceBookingDays * 24 * 60);
  if (start >= horizon) {
    violations.push({
      code: "BEYOND_BOOKING_HORIZON",
      message: `You can only book up to ${policy.advanceBookingDays} days ahead.`,
    });
  }

  const blackout = policy.blackouts.find((b) =>
    overlaps(start, end, b.start, b.end),
  );
  if (blackout) {
    violations.push({
      code: "BLACKOUT",
      message: `Unavailable: ${blackout.reason}.`,
    });
  }

  const others = context.existing.filter(
    (r) => isActive(r) && r.id !== context.ignoreReservationId,
  );

  const resourceClash = others.find(
    (r) => r.resourceId === request.resourceId && overlaps(start, end, r.startsAt, r.endsAt),
  );
  if (resourceClash) {
    violations.push({
      code: "RESOURCE_DOUBLE_BOOKED",
      message: "Someone else already has that slot.",
    });
  }

  const mine = others.filter((r) => r.studentId === request.studentId);

  if (mine.some((r) => overlaps(start, end, r.startsAt, r.endsAt))) {
    violations.push({
      code: "STUDENT_DOUBLE_BOOKED",
      message: "You already have a booking that overlaps this time.",
    });
  }

  const dayUsed = minutesInWindow(mine, startOfDay(start), endOfDay(start));
  if (dayUsed + durationMinutes > policy.maxMinutesPerDay) {
    violations.push({
      code: "DAILY_CAP_EXCEEDED",
      message: `Daily limit is ${formatMinutes(policy.maxMinutesPerDay)}; you have ${formatMinutes(
        policy.maxMinutesPerDay - dayUsed,
      )} left that day.`,
    });
  }

  const weekUsed = minutesInWindow(mine, startOfWeek(start), endOfWeek(start));
  if (weekUsed + durationMinutes > policy.maxMinutesPerWeek) {
    violations.push({
      code: "WEEKLY_CAP_EXCEEDED",
      message: `Weekly limit is ${formatMinutes(policy.maxMinutesPerWeek)}; you have ${formatMinutes(
        policy.maxMinutesPerWeek - weekUsed,
      )} left this week.`,
    });
  }

  const upcoming = mine.filter((r) => toDate(r.endsAt) > now && r.status !== "completed");
  if (upcoming.length >= policy.maxActiveReservations) {
    violations.push({
      code: "TOO_MANY_ACTIVE",
      message: `You can hold ${policy.maxActiveReservations} upcoming bookings at a time. Cancel one to book another.`,
    });
  }

  return violations;
}

/** Minutes a student has already committed inside [from, to). */
export function minutesInWindow(
  reservations: Reservation[],
  from: Date,
  to: Date,
): number {
  return reservations
    .filter(isActive)
    .reduce((total, r) => total + overlapMinutes(r.startsAt, r.endsAt, from, to), 0);
}

export function isOnSlotGrid(value: Date, policy: Policy): boolean {
  const minutesFromMidnight = minutesBetween(startOfDay(value), value);
  return minutesFromMidnight % policy.slotMinutes === 0;
}

export function openWindowFor(day: Date, policy: Policy): { start: Date; end: Date } | null {
  const hours = policy.openHours[day.getDay() as Weekday];
  if (!hours) return null;
  return { start: atTime(day, hours.open), end: atTime(day, hours.close) };
}

export function isWithinOpenHours(start: Date, end: Date, policy: Policy): boolean {
  const window = openWindowFor(start, policy);
  if (!window) return false;
  // A booking may not straddle midnight into a different day's hours.
  return start >= window.start && end <= window.end;
}

/**
 * Build the day's grid for one resource.
 *
 * `studentId` is optional: pass it and slots the student *could* click but that
 * policy would reject (over their daily cap, overlapping their own booking) come
 * back as "blocked" with a reason, instead of looking free and failing on click.
 */
export function buildDaySlots(options: {
  resource: Resource;
  day: Date;
  reservations: Reservation[];
  policy: Policy;
  now: Date;
  studentId?: string;
}): Slot[] {
  const { resource, day, reservations, policy, now, studentId } = options;
  const window = openWindowFor(day, policy);
  if (!window) return [];

  const slots: Slot[] = [];
  const active = reservations.filter(isActive);

  for (
    let cursor = window.start;
    cursor < window.end;
    cursor = addMinutes(cursor, policy.slotMinutes)
  ) {
    const slotEnd = addMinutes(cursor, policy.slotMinutes);
    if (slotEnd > window.end) break;

    const taken = active.find(
      (r) => r.resourceId === resource.id && overlaps(cursor, slotEnd, r.startsAt, r.endsAt),
    );

    if (taken) {
      slots.push({
        startsAt: cursor.toISOString(),
        endsAt: slotEnd.toISOString(),
        status: "taken",
        reservationId: taken.id,
      });
      continue;
    }

    if (slotEnd <= now) {
      slots.push({
        startsAt: cursor.toISOString(),
        endsAt: slotEnd.toISOString(),
        status: "past",
      });
      continue;
    }

    let status: Slot["status"] = "free";
    let reason: string | undefined;

    if (studentId) {
      const violations = validateBooking(
        {
          resourceId: resource.id,
          studentId,
          startsAt: cursor.toISOString(),
          endsAt: slotEnd.toISOString(),
        },
        { resource, existing: reservations, policy, now },
      );
      if (violations.length > 0) {
        status = "blocked";
        reason = violations[0].message;
      }
    }

    slots.push({
      startsAt: cursor.toISOString(),
      endsAt: slotEnd.toISOString(),
      status,
      reason,
    });
  }

  return slots;
}

/**
 * The first day worth showing a student: today if it is open and has time left,
 * otherwise the next open day inside the booking horizon.
 *
 * Without this the app opens on a hatched-out grid every evening after close,
 * which reads as broken rather than as "we're shut".
 */
export function nextBookableDay(now: Date, policy: Policy): Date {
  for (let offset = 0; offset <= policy.advanceBookingDays; offset++) {
    const day = startOfDay(addMinutes(startOfDay(now), offset * 24 * 60));
    const window = openWindowFor(day, policy);
    if (window && window.end > now) return day;
  }
  return startOfDay(now);
}

export type ResourceState =
  | { kind: "closed" }
  | { kind: "available"; freeUntil?: string }
  | { kind: "in-use"; until: string; reservationId: string }
  | { kind: "reserved-soon"; from: string; reservationId: string };

/** What the kiosk display shows for a single resource right now. */
export function resourceStateAt(options: {
  resource: Resource;
  reservations: Reservation[];
  policy: Policy;
  now: Date;
  /** How far ahead counts as "reserved soon". */
  lookaheadMinutes?: number;
}): ResourceState {
  const { resource, reservations, policy, now, lookaheadMinutes = 30 } = options;
  const window = openWindowFor(now, policy);
  if (!resource.isActive || !window || now < window.start || now >= window.end) {
    return { kind: "closed" };
  }

  const mine = reservations
    .filter((r) => r.resourceId === resource.id && isActive(r))
    .sort((a, b) => toDate(a.startsAt).getTime() - toDate(b.startsAt).getTime());

  const current = mine.find((r) => overlaps(now, addMinutes(now, 1), r.startsAt, r.endsAt));
  if (current) {
    return { kind: "in-use", until: current.endsAt, reservationId: current.id };
  }

  const next = mine.find((r) => toDate(r.startsAt) > now);
  if (next && minutesBetween(now, next.startsAt) <= lookaheadMinutes) {
    return { kind: "reserved-soon", from: next.startsAt, reservationId: next.id };
  }

  return { kind: "available", freeUntil: next?.startsAt ?? window.end.toISOString() };
}

/**
 * Bookings past their check-in grace period that nobody claimed.
 *
 * The prototype calls this on load to grey them out. In production this is a
 * scheduled Power Automate flow that flips the rows to `no-show` every 5 minutes,
 * which is what actually frees the slot for the next student — see docs/FLOWS.md.
 */
export function findNoShows(
  reservations: Reservation[],
  now: Date,
  policy: Policy,
): Reservation[] {
  return reservations.filter(
    (r) =>
      r.status === "booked" &&
      !r.checkedInAt &&
      minutesBetween(r.startsAt, now) > policy.checkInGraceMinutes &&
      toDate(r.endsAt) > now,
  );
}

/** Usage summary for the "you have X left" banner. */
export function usageSummary(
  reservations: Reservation[],
  studentId: string,
  reference: Date,
  policy: Policy,
): { dayUsed: number; dayLeft: number; weekUsed: number; weekLeft: number } {
  const mine = reservations.filter((r) => r.studentId === studentId);
  const dayUsed = minutesInWindow(mine, startOfDay(reference), endOfDay(reference));
  const weekUsed = minutesInWindow(mine, startOfWeek(reference), endOfWeek(reference));
  return {
    dayUsed,
    dayLeft: Math.max(0, policy.maxMinutesPerDay - dayUsed),
    weekUsed,
    weekLeft: Math.max(0, policy.maxMinutesPerWeek - weekUsed),
  };
}

function formatMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} minutes`;
  if (m === 0) return h === 1 ? "1 hour" : `${h} hours`;
  return `${h}h ${m}m`;
}
