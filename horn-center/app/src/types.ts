/**
 * Domain types for Horn Center reservations.
 *
 * These mirror the Dataverse tables one-for-one (see docs/DATA-MODEL.md), so the
 * mock service and the Dataverse service can satisfy the same interface. When you
 * move to Dataverse, only the mapping functions in services/dataverseService.ts
 * change — nothing in lib/ or components/ has to.
 */

export type ResourceKind = "workstation" | "collab-room" | "equipment";

export interface Resource {
  id: string;
  name: string;
  kind: ResourceKind;
  /** Human-readable location, e.g. "Horn Center — Room 101". */
  location: string;
  /** Seats. 1 for a workstation, 6 for a collab room, etc. */
  capacity: number;
  /** Free-form tags surfaced as filter chips: "dual-monitor", "Adobe CC", "whiteboard". */
  features: string[];
  isActive: boolean;
}

export type ReservationStatus =
  | "booked"
  | "checked-in"
  | "completed"
  | "cancelled"
  | "no-show";

export interface Reservation {
  id: string;
  resourceId: string;
  /** Entra ID object id of the student — the stable key, never the email. */
  studentId: string;
  /** Denormalized for display; Dataverse stores this on the row too. */
  studentName: string;
  /** ISO 8601 instants. */
  startsAt: string;
  endsAt: string;
  status: ReservationStatus;
  createdAt: string;
  checkedInAt?: string;
  purpose?: string;
}

export interface Student {
  /** Entra ID object id (oid claim). */
  id: string;
  displayName: string;
  email: string;
  /** Campus ID, if ITS maps it into a claim or Dataverse row. Display only. */
  campusId?: string;
  roles: Array<"student" | "staff" | "admin">;
}

export type Weekday = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export interface OpenWindow {
  /** "08:00" in the center's local time. */
  open: string;
  /** "22:00". */
  close: string;
}

export interface Blackout {
  /** ISO instants. Inclusive start, exclusive end. */
  start: string;
  end: string;
  reason: string;
}

export interface Policy {
  /** Booking grid granularity, in minutes. */
  slotMinutes: number;
  minDurationMinutes: number;
  maxDurationMinutes: number;
  /** Rolling per-calendar-day cap across all resources. */
  maxMinutesPerDay: number;
  /** Per-week cap. Weeks start Sunday 00:00 local. */
  maxMinutesPerWeek: number;
  /** How many future reservations a student may hold at once. */
  maxActiveReservations: number;
  /** How far ahead a student may book. */
  advanceBookingDays: number;
  /** Minutes after start before an un-checked-in booking is released. */
  checkInGraceMinutes: number;
  /** null = closed that day. Index is Weekday (0 = Sunday). */
  openHours: Record<Weekday, OpenWindow | null>;
  blackouts: Blackout[];
}

/** Machine-readable so the UI can style them and tests can assert on them. */
export type ViolationCode =
  | "RESOURCE_INACTIVE"
  | "IN_THE_PAST"
  | "OUTSIDE_OPEN_HOURS"
  | "NOT_ON_SLOT_GRID"
  | "TOO_SHORT"
  | "TOO_LONG"
  | "BEYOND_BOOKING_HORIZON"
  | "RESOURCE_DOUBLE_BOOKED"
  | "STUDENT_DOUBLE_BOOKED"
  | "DAILY_CAP_EXCEEDED"
  | "WEEKLY_CAP_EXCEEDED"
  | "TOO_MANY_ACTIVE"
  | "BLACKOUT";

export interface Violation {
  code: ViolationCode;
  /** Shown directly to the student — keep it actionable. */
  message: string;
}

export interface BookingRequest {
  resourceId: string;
  studentId: string;
  startsAt: string;
  endsAt: string;
}

/** A cell in the day grid. */
export interface Slot {
  startsAt: string;
  endsAt: string;
  status: "free" | "taken" | "closed" | "past" | "blocked";
  /** Populated when status is "taken" — used by the kiosk, not the booking grid. */
  reservationId?: string;
  /** Populated when status is "blocked" — why policy rejected it. */
  reason?: string;
}
